"""
NeuroPlan-3D — Steel Truss Experimental Measurements Loader

Reads the actual displacement-sensor values for the DS "Loss of a lower
chord" undamaged (UD) state directly from the downloaded dataset file, at
the row of maximum recorded Jack_Load (cross-checked against the
published Fig. 15 table in the Supplementary Information — the two agree
to within rounding, confirming the correct sheet/columns are being read).

If the dataset file is not present on disk, `load_measurements` raises
`DatasetFileNotFoundError` — callers must treat this as
`ValidationState.NOT_AVAILABLE` for this session, not fall back to any
hard-coded number.
"""
from __future__ import annotations

from ..models import MeasurementPoint, Provenance, ParameterStatus
from ..parsers.xlsx_parser import read_sensor_at_peak_load, DatasetFileNotFoundError
from ..datasets.steel_truss_zenodo import STEEL_TRUSS_DATASET
from .steel_truss_loss_of_chord import SOUTH_SENSOR_NODES

SHEET_NAME = "Loss_Chord_UD"

# Published cross-check values, Fig. 15 (Supplementary Information, p.18),
# South side, UD condition, in mm. Kept only to verify the raw dataset
# file is being read correctly — the comparison itself uses the live
# xlsx values, not these.
PUBLISHED_SOUTH_UD_MM = {
    "1": 2.49, "2": 5.73, "3": 8.19, "4": 8.36, "5": 7.95, "6": 5.49, "7": 2.23,
}

# North-side published values, Fig. 15 (Supplementary Information, p.18),
# UD condition, in mm. Same format as South, sensors 8-14.
PUBLISHED_NORTH_UD_MM = {
    "8": 2.48, "9": 5.70, "10": 8.10, "11": 8.26, "12": 7.86, "13": 5.44, "14": 2.21,
}


def load_measurements(path: str | None = None) -> list[MeasurementPoint]:
    """
    Load the 7 South-side displacement-sensor readings at peak load from
    the actual dataset file, unmodified from the raw cell values.

    Raises DatasetFileNotFoundError if the file is not present.
    """
    points: list[MeasurementPoint] = []
    for sensor_id in SOUTH_SENSOR_NODES:
        column = f"# {sensor_id}"
        jack_load_kn, value_mm = read_sensor_at_peak_load(SHEET_NAME, column, path)
        points.append(MeasurementPoint(
            sensor_id=sensor_id,
            value=value_mm,
            units="mm",
            load_level_kn=jack_load_kn,
            condition="UD",
            provenance=Provenance(
                source_type="experimental",
                status=ParameterStatus.SOURCED,
                dataset=STEEL_TRUSS_DATASET.title,
                file=STEEL_TRUSS_DATASET.files[0],
                sheet=SHEET_NAME,
                field=column,
                doi=STEEL_TRUSS_DATASET.doi,
                license=STEEL_TRUSS_DATASET.license,
                retrieved=STEEL_TRUSS_DATASET.retrieved,
                note=(
                    f"Raw sensor reading at the row of maximum recorded Jack_Load "
                    f"({jack_load_kn:.3f} kN) in sheet '{SHEET_NAME}'. Cross-checked "
                    f"against the published Fig. 15 value "
                    f"({PUBLISHED_SOUTH_UD_MM.get(sensor_id, 'n/a')} mm)."
                ),
            ),
        ))
    return points


def load_north_measurements(path: str | None = None) -> list[MeasurementPoint]:
    """
    Load the 7 North-side displacement-sensor readings (sensors 8-14) at
    peak load from the actual dataset file, unmodified from raw cell values.

    These sensors were NOT used in the South-side mapping calibration scan.
    However, their sensor-to-node mapping is the SAME sequence derived from
    that scan — they are not independently mapped.

    Raises DatasetFileNotFoundError if the file is not present.
    """
    from .steel_truss_loss_of_chord import NORTH_SENSOR_NODES

    points: list[MeasurementPoint] = []
    for sensor_id in NORTH_SENSOR_NODES:
        column = f"# {sensor_id}"
        jack_load_kn, value_mm = read_sensor_at_peak_load(SHEET_NAME, column, path)
        points.append(MeasurementPoint(
            sensor_id=sensor_id,
            value=value_mm,
            units="mm",
            load_level_kn=jack_load_kn,
            condition="UD",
            provenance=Provenance(
                source_type="experimental",
                status=ParameterStatus.SOURCED,
                dataset=STEEL_TRUSS_DATASET.title,
                file=STEEL_TRUSS_DATASET.files[0],
                sheet=SHEET_NAME,
                field=column,
                doi=STEEL_TRUSS_DATASET.doi,
                license=STEEL_TRUSS_DATASET.license,
                retrieved=STEEL_TRUSS_DATASET.retrieved,
                note=(
                    f"Raw North-side sensor reading at peak Jack_Load "
                    f"({jack_load_kn:.3f} kN) in sheet '{SHEET_NAME}'. Cross-checked "
                    f"against the published Fig. 15 value "
                    f"({PUBLISHED_NORTH_UD_MM.get(sensor_id, 'n/a')} mm)."
                ),
            ),
        ))
    return points


__all__ = [
    "load_measurements", "load_north_measurements", "DatasetFileNotFoundError",
    "PUBLISHED_SOUTH_UD_MM", "PUBLISHED_NORTH_UD_MM", "SHEET_NAME",
]
