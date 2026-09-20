"""
NeuroPlan-3D — Thermal Loading and Support Settlement (Priority 8)

────────────────────────────────────────────────────────────────────────
THERMAL: FORMULATION
────────────────────────────────────────────────────────────────────────
A bar subjected to a uniform temperature change dT wants to change
length by the free thermal elongation

    delta_T = alpha * dT * L

If it is restrained, that elongation is resisted and an axial force
develops. The standard treatment is an equivalent nodal load vector
applied alongside the mechanical loads:

    N_T = E * A * alpha * dT            [N]

    f_thermal = N_T * [-cx, -cy, -cz, +cx, +cy, +cz]^T

where (cx, cy, cz) are the direction cosines from node i to node j. A
temperature RISE pushes the two ends apart, hence the sign pattern.

After solving, the member's TOTAL axial force is the elastic force
implied by the nodal displacements MINUS the thermal contribution:

    N = (E*A/L) * (c . (u_j - u_i))  -  E * A * alpha * dT

This subtraction is essential and easy to get wrong. Physically:

  - Fully restrained bar, dT > 0: the ends cannot move, so the first
    term is 0 and N = -E*A*alpha*dT, i.e. COMPRESSION. Correct.
  - Free bar, dT > 0: it expands by alpha*dT*L, the first term equals
    E*A*alpha*dT, the two cancel and N = 0. Correct — an unrestrained
    bar develops no thermal stress.

Both cases are asserted in the tests.

ASSUMPTIONS
  - Uniform temperature change over the whole member. No through-depth
    gradient (which would cause bending, and this solver has no
    rotational DOF to carry it).
  - alpha is constant, i.e. independent of temperature.
  - Material properties (E) do not change with temperature. Real steel
    loses stiffness and strength well before 600 C, so this model is
    only valid for ordinary service temperature swings, NOT for fire.
  - Linear elastic response throughout.

────────────────────────────────────────────────────────────────────────
SETTLEMENT: FORMULATION
────────────────────────────────────────────────────────────────────────
An imposed support movement is a PRESCRIBED non-zero displacement. The
system is partitioned into free (f) and constrained (c) DOF:

    [ K_ff  K_fc ] { u_f }   { F_f }
    [ K_cf  K_cc ] { u_c } = { R   }

With u_c prescribed (no longer zero), the first row gives

    K_ff * u_f = F_f - K_fc * u_c

so the settlement enters as an equivalent load term -K_fc * u_c. The
reactions then follow from the second row:

    R = K_cf * u_f + K_cc * u_c - F_c

Note the consequence: in a STATICALLY DETERMINATE structure, support
settlement produces displacement but NO member force — the structure
simply follows the movement. Forces only develop in indeterminate
structures. This is asserted in the tests, because a formulation that
produced forces in a determinate truss would be wrong.

ASSUMPTIONS
  - Settlement is a known, imposed displacement. It is NOT derived from
    soil properties, bearing capacity or consolidation theory — there is
    no soil model here. The magnitude is an input.
  - Instantaneous and final: no time-dependent consolidation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ...models.structure import Structure, MATERIAL_LIBRARY
from .elements import direction_cosines

# Coefficient of thermal expansion, per kelvin.
# Structural steel: 1.2e-5 /K is the conventional design value used in
# IS 800:2007 cl. 2.2.4.1 and EN 1993-1-1 cl. 3.2.6.
THERMAL_EXPANSION: dict[str, float] = {
    "A36": 1.2e-5,
    "A992": 1.2e-5,
    "AL6061": 2.32e-5,   # aluminium expands roughly twice as much as steel
}

DEFAULT_ALPHA = 1.2e-5

# Above this the assumption "E does not vary with temperature" fails.
MAX_VALID_TEMPERATURE_CHANGE_K = 150.0


@dataclass
class ThermalLoadCase:
    """A uniform temperature change applied to the whole structure."""
    delta_t: float                      # kelvin (= degrees Celsius change)
    alpha_by_material: dict[str, float] = field(default_factory=lambda: dict(THERMAL_EXPANSION))
    description: str = ""

    def alpha_for(self, material_key: str) -> float:
        return self.alpha_by_material.get(material_key, DEFAULT_ALPHA)

    def validity_warning(self) -> str:
        if abs(self.delta_t) > MAX_VALID_TEMPERATURE_CHANGE_K:
            return (
                f"Temperature change {self.delta_t:+.0f} K exceeds "
                f"{MAX_VALID_TEMPERATURE_CHANGE_K:.0f} K. This model holds E "
                f"constant with temperature, which is not valid at elevated "
                f"temperature. Results are NOT applicable to fire conditions."
            )
        return ""


@dataclass
class SupportSettlement:
    """An imposed displacement at one support node, in metres."""
    node_id: int
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0

    def as_vector(self) -> tuple[float, float, float]:
        return (self.dx, self.dy, self.dz)


def thermal_axial_force(E: float, area: float, alpha: float, delta_t: float) -> float:
    """N_T = E * A * alpha * dT — the force a fully restrained bar develops."""
    return E * area * alpha * delta_t


def build_thermal_load_vector(
    structure: Structure,
    dof_map: dict[int, tuple[int, int, int]],
    thermal: ThermalLoadCase,
) -> np.ndarray:
    """
    Equivalent nodal load vector for a uniform temperature change.

    f_thermal = N_T * [-c, +c] per member, assembled globally.
    """
    n_dof = 3 * len(structure.nodes)
    F = np.zeros(n_dof)
    if thermal.delta_t == 0.0:
        return F

    nodes = structure.node_dict()
    for member in structure.members:
        material = MATERIAL_LIBRARY.get(member.material_key)
        if material is None:
            continue
        ni, nj = nodes[member.node_i], nodes[member.node_j]
        cx, cy, cz, length = direction_cosines(ni, nj)
        if length <= 0:
            continue

        n_t = thermal_axial_force(
            material.E, member.section.area,
            thermal.alpha_for(member.material_key), thermal.delta_t,
        )

        dofs_i = dof_map[member.node_i]
        dofs_j = dof_map[member.node_j]
        for k, c in enumerate((cx, cy, cz)):
            F[dofs_i[k]] -= n_t * c
            F[dofs_j[k]] += n_t * c

    return F


def thermal_force_correction(
    structure: Structure,
    thermal: ThermalLoadCase | None,
) -> dict[int, float]:
    """
    Per-member thermal force N_T, to be SUBTRACTED from the elastic force
    during recovery. Returns {member_id: N_T}.
    """
    if thermal is None or thermal.delta_t == 0.0:
        return {}

    correction: dict[int, float] = {}
    for member in structure.members:
        material = MATERIAL_LIBRARY.get(member.material_key)
        if material is None:
            continue
        correction[member.id] = thermal_axial_force(
            material.E, member.section.area,
            thermal.alpha_for(member.material_key), thermal.delta_t,
        )
    return correction


def build_prescribed_displacement_vector(
    structure: Structure,
    dof_map: dict[int, tuple[int, int, int]],
    settlements: list[SupportSettlement],
) -> np.ndarray:
    """
    Full-length vector u_c holding the prescribed support displacements
    (zero everywhere else).

    Only components that are actually RESTRAINED can be prescribed: it is
    meaningless to impose a displacement on a direction the support
    leaves free, since the structure is already free to move there.
    """
    n_dof = 3 * len(structure.nodes)
    u_c = np.zeros(n_dof)
    if not settlements:
        return u_c

    support_by_node = {s.node_id: s for s in structure.supports}
    for settlement in settlements:
        support = support_by_node.get(settlement.node_id)
        if support is None:
            raise ValueError(
                f"Settlement specified at node {settlement.node_id}, which has "
                f"no support. A prescribed displacement can only be applied to "
                f"a restrained DOF."
            )
        dofs = dof_map[settlement.node_id]
        restrained = (support.dx, support.dy, support.dz)
        for k, (value, is_restrained) in enumerate(
            zip(settlement.as_vector(), restrained)
        ):
            if value != 0.0 and not is_restrained:
                raise ValueError(
                    f"Settlement of {value} m specified at node "
                    f"{settlement.node_id} in a direction the support does not "
                    f"restrain. That DOF is already free to move, so imposing "
                    f"a displacement there is meaningless."
                )
            u_c[dofs[k]] = value

    return u_c
