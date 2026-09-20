"""
NeuroPlan-3D — Steel Truss Bridge Experimental Dataset (Zenodo)

Citation and provenance for:

  Reyes, J.C., Buitrago, M., Barros, B., Mammeri, S., Makoond, N.,
  Lázaro, C., Riveiro, B. & Adam, J.M. (2025).
  "Latent resistance mechanisms of steel truss bridges after critical
  failures — Experimental dataset." Zenodo.
  https://doi.org/10.5281/zenodo.15658671

Companion peer-reviewed publication:
  Reyes, J.C. et al. (2025). "Latent resistance mechanisms of steel truss
  bridges after critical failures." Nature.
  https://doi.org/10.1038/s41586-025-09300-8
  Supplementary Information (geometry, materials, test protocol):
  https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-025-09300-8/MediaObjects/41586_2025_9300_MOESM1_ESM.pdf

Retrieved and read directly (Zenodo record page, Nature/PMC article text,
and the full 114-page Supplementary Information PDF) on 2026-09-19 for this
integration. No secondary summary was relied upon for the numbers used in
`server/validation/cases/steel_truss_loss_of_chord.py`.

The local data file actually used by this integration
(`LatentMechanisms_SteelTruss_ExperimentalData.xlsx`, 81.5 MB, the sole
file in the Zenodo record) must be supplied by the user — it is not
committed to this repository. See `parsers/xlsx_parser.py` for how it is
read and `DEFAULT_XLSX_PATH` for where it is expected.
"""
from ..models import DatasetMetadata

STEEL_TRUSS_DATASET = DatasetMetadata(
    title=(
        "Latent resistance mechanisms of steel truss bridges after "
        "critical failures — Experimental dataset"
    ),
    authors=[
        "Juan Camilo Reyes",
        "Manuel Buitrago",
        "Brais Barros",
        "Safae Mammeri",
        "Nirvan Makoond",
        "Carlos Lázaro",
        "Belén Riveiro",
        "Jose M. Adam",
    ],
    institution="Universitat Politècnica de València; Universidade de Vigo",
    doi="10.5281/zenodo.15658671",
    license="Creative Commons Attribution 4.0 International (CC-BY-4.0)",
    publication_date="2025-06-13",
    version="v1",
    repository="Zenodo",
    files=["LatentMechanisms_SteelTruss_ExperimentalData.xlsx"],
    description=(
        "Sensor records (80 strain gauges, 14 displacement transducers) from "
        "a scaled-down (lambda_L = 3.5) steel Pratt truss bridge specimen, "
        "6 m isostatic span, tested under quasi-static hydraulic jack "
        "loading for a baseline (undamaged) condition and a series of "
        "structural component-removal (damage) scenarios: loss of a lower "
        "chord, a diagonal, a vertical, horizontal bracing, vertical "
        "bracing, and a transversal beam, plus a test taken to global "
        "collapse."
    ),
    linked_publication_title=(
        "Latent resistance mechanisms of steel truss bridges after "
        "critical failures"
    ),
    linked_publication_doi="10.1038/s41586-025-09300-8",
    linked_publication_url="https://doi.org/10.1038/s41586-025-09300-8",
    retrieved="2026-09-19",
)
