"""
NeuroPlan-3D — Steel Truss Dataset XLSX Parser

Reads the actual downloaded dataset file. Every value returned is the raw
cell value from the workbook — this module performs NO unit conversion,
no smoothing, no interpolation. Unit conversion (where needed) happens in
`comparison/units.py`, as separate, individually tested functions, so a
conversion bug can never silently alter what "the experimental value" is
understood to be internally.

The file is not committed to the repository (81.5 MB, third-party
CC-BY-4.0 data — the user downloads it directly from Zenodo). If it is not
present at the configured path, every function here raises
`DatasetFileNotFoundError` rather than falling back to invented numbers.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_XLSX_PATH = os.environ.get(
    "NEUROPLAN_STEEL_TRUSS_XLSX",
    os.path.join(
        os.path.expanduser("~"), "Downloads",
        "LatentMechanisms_SteelTruss_ExperimentalData.xlsx",
    ),
)


class DatasetFileNotFoundError(FileNotFoundError):
    """Raised when the experimental dataset file is not present on disk."""


@dataclass
class SensorTimeSeries:
    sheet: str
    sensor_column: str
    time: list[float]
    jack_load_kn: list[float]
    value: list[float]


def _require_openpyxl():
    try:
        import openpyxl  # noqa: F401
        return openpyxl
    except ImportError as e:  # pragma: no cover - environment issue, not logic
        raise ImportError(
            "openpyxl is required to parse the steel truss dataset "
            "(pip install openpyxl)"
        ) from e


def dataset_path(path: str | None = None) -> str:
    p = path or DEFAULT_XLSX_PATH
    if not os.path.isfile(p):
        raise DatasetFileNotFoundError(
            f"Steel truss dataset not found at '{p}'. Download it from "
            "https://zenodo.org/records/15658671 and place it there, or set "
            "the NEUROPLAN_STEEL_TRUSS_XLSX environment variable."
        )
    return p


@lru_cache(maxsize=4)
def _load_workbook(path: str):
    openpyxl = _require_openpyxl()
    return openpyxl.load_workbook(path, read_only=True, data_only=True)


@lru_cache(maxsize=8)
def _load_sheet_rows(path: str, sheet_name: str) -> tuple[tuple, ...]:
    """
    Materialize a sheet's rows once per (path, sheet) and reuse across
    calls. The dataset's sheets are large (thousands of rows x ~98
    columns) and several sensor columns are typically read from the same
    sheet in one session, so this avoids re-scanning the workbook from
    disk for every single sensor column.
    """
    wb = _load_workbook(path)
    ws = wb[sheet_name]
    return tuple(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))


def list_sheets(path: str | None = None) -> list[str]:
    wb = _load_workbook(dataset_path(path))
    return list(wb.sheetnames)


def read_header(sheet_name: str, path: str | None = None) -> list[str]:
    """Return the raw column header row for a sheet, unmodified."""
    wb = _load_workbook(dataset_path(path))
    ws = wb[sheet_name]
    row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    return list(row)


def read_sensor_at_peak_load(
    sheet_name: str,
    sensor_column: str,
    path: str | None = None,
) -> tuple[float, float]:
    """
    Return (jack_load_kn, sensor_value) at the row of maximum Jack_Load in
    the given sheet — the raw recorded values, not recomputed.
    """
    resolved = dataset_path(path)
    rows = _load_sheet_rows(resolved, sheet_name)
    header = list(rows[0])
    data = rows[1:]

    if "Jack_Load" not in header:
        raise ValueError(f"Sheet '{sheet_name}' has no Jack_Load column")
    if sensor_column not in header:
        raise ValueError(f"Sheet '{sheet_name}' has no column '{sensor_column}'")

    idx_load = header.index("Jack_Load")
    idx_sensor = header.index(sensor_column)

    best_row = max(
        (r for r in data if r[idx_load] is not None),
        key=lambda r: r[idx_load],
    )
    return float(best_row[idx_load]), float(best_row[idx_sensor])


def read_full_series(
    sheet_name: str,
    sensor_column: str,
    path: str | None = None,
) -> SensorTimeSeries:
    """Return the complete raw time series for one sensor column."""
    resolved = dataset_path(path)
    rows = _load_sheet_rows(resolved, sheet_name)
    header = list(rows[0])
    data = rows[1:]

    idx_time = header.index("Time")
    idx_load = header.index("Jack_Load")
    idx_sensor = header.index(sensor_column)

    return SensorTimeSeries(
        sheet=sheet_name,
        sensor_column=sensor_column,
        time=[float(r[idx_time]) for r in data if r[idx_time] is not None],
        jack_load_kn=[float(r[idx_load]) for r in data if r[idx_load] is not None],
        value=[float(r[idx_sensor]) for r in data if r[idx_sensor] is not None],
    )
