from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


def _first_available_column(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """Find the first candidate column that exists in the DataFrame."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _prepare_df_index_by_date(df: pd.DataFrame) -> pd.DataFrame:
    """Convert DataFrame to have date as index, normalized to midnight."""
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        return df.set_index("date")
    if isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index).normalize()
        return df
    return df


def _get_for_date(df: pd.DataFrame, d: pd.Timestamp, col_name: Optional[str]):
    """Retrieve value from DataFrame for a specific date and column."""
    if col_name is None:
        return None
    try:
        if d in df.index:
            v = df.at[d, col_name]
            if isinstance(v, pd.Series):
                v = v.dropna().astype(float).mean() if not v.dropna().empty else None
            return None if pd.isna(v) else float(v)
    except Exception:
        return None
    return None


def write_swat_temperature(
    output_folder: str | Path,
    subbasin_id: int,
    interpolation_dates: pd.DatetimeIndex,
    interpolated_data_temp: pd.DataFrame,
    start_date: Optional[pd.Timestamp] = None,
) -> Path:
    """Write legacy SWAT temperature file (.txt).

    Output format:
    - first line: start date YYYYMMDD
    - subsequent lines: "max,min,mean" (comma-separated, no spaces)
    """
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    dates = pd.to_datetime(interpolation_dates)
    if start_date is None:
        start_date = dates[0]

    df = _prepare_df_index_by_date(interpolated_data_temp)

    max_col = _first_available_column(df, ("temperature_air_max_2m", "max_Temperature", "Max_Temperature", "tmax", "temperature_max"))
    min_col = _first_available_column(df, ("temperature_air_min_2m", "min_Temperature", "Min_Temperature", "tmin", "temperature_min"))
    mean_col = _first_available_column(df, ("temperature_air_mean_2m", "mean_Temperature", "Mean_Temperature", "tmean", "temperature_mean"))

    file_name = f"tmp{int(subbasin_id):03d}.txt"
    out_path = out_dir / file_name

    lines = [start_date.strftime("%Y%m%d")]
    for d in dates:
        d0 = pd.to_datetime(d).normalize()
        mx = _get_for_date(df, d0, max_col)
        mn = _get_for_date(df, d0, min_col)
        mean = _get_for_date(df, d0, mean_col)

        def fmt(x):
            return "" if x is None else "{:.2f}".format(x)

        lines.append(f"{fmt(mx)},{fmt(mn)},{fmt(mean)}")

    out_path.write_text("\n".join(lines))
    return out_path


def write_swat_other(
    output_folder: str | Path,
    subbasin_id: int,
    interpolation_dates: pd.DatetimeIndex,
    interpolated_data: pd.DataFrame,
    var_column: str,
    start_date: Optional[pd.Timestamp] = None,
) -> Path:
    """Write legacy SWAT file (.txt) for non-temperature variables.

    Output format:
    - first line: start date YYYYMMDD
    - subsequent lines: one value per line
    
    File naming uses explicit mapping:
    - precipitation_height -> pcp
    - humidity -> rh
    - wind_speed -> wind
    - radiation_global -> solar
    """
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    dates = pd.to_datetime(interpolation_dates)
    if start_date is None:
        start_date = dates[0]

    df = _prepare_df_index_by_date(interpolated_data)

    prefix_map = {
        "precipitation_height": "pcp",
        "pcp": "pcp",
        "humidity": "rh",
        "rh": "rh",
        "wind_speed": "wind",
        "wind": "wind",
        "radiation_global": "solar",
        "solar": "solar",
    }

    prefix = prefix_map.get(var_column, "var")
    file_name = f"{prefix}{int(subbasin_id):03d}.txt"
    out_path = out_dir / file_name

    lines = [start_date.strftime("%Y%m%d")]
    for d in dates:
        d0 = pd.to_datetime(d).normalize()
        v = _get_for_date(df, d0, var_column)
        lines.append("" if v is None else "{:.2f}".format(v))

    out_path.write_text("\n".join(lines))
    return out_path


def write_swatplus_temperature(
    output_folder: str | Path,
    subbasin_id: int,
    interpolation_dates: pd.DatetimeIndex,
    interpolated_data_temp: pd.DataFrame,
    lat: float,
    lon: float,
    elev: float,
) -> Path:
    """Write SWAT+ temperature file (.tmp).

    Output format:
    - line 1: filename
    - line 2: header "nbyr tstep lat lon elev"
    - line 3: metadata row
    - subsequent lines: "year yday max min" (tab-separated)
    """
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    dates = pd.to_datetime(interpolation_dates)
    df = _prepare_df_index_by_date(interpolated_data_temp)

    max_col = _first_available_column(df, ("temperature_air_max_2m", "max_Temperature", "Max_Temperature", "tmax", "temperature_max"))
    min_col = _first_available_column(df, ("temperature_air_min_2m", "min_Temperature", "Min_Temperature", "tmin", "temperature_min"))

    file_name = f"tmp{int(subbasin_id):03d}.tmp"
    out_path = out_dir / file_name

    with out_path.open("w", newline="") as fh:
        fh.write(f"{file_name}\n")
        fh.write("\t".join(["nbyr", "tstep", "lat", "lon", "elev"]) + "\n")
        nbyr = len(pd.Index(dates.year).unique())
        fh.write("\t".join([str(nbyr), "0", f"{round(lat, 2):.2f}", f"{round(lon, 2):.2f}", f"{round(elev, 2):.2f}"]) + "\n")

        for d in dates:
            d0 = pd.to_datetime(d).normalize()
            year = d0.year
            yday = int(d0.dayofyear)
            mx = _get_for_date(df, d0, max_col)
            mn = _get_for_date(df, d0, min_col)
            mx_s = "" if mx is None else "{:.2f}".format(mx)
            mn_s = "" if mn is None else "{:.2f}".format(mn)
            fh.write("\t".join([str(year), str(yday), mx_s, mn_s]) + "\n")

    return out_path


def write_swatplus_other(
    output_folder: str | Path,
    subbasin_id: int,
    interpolation_dates: pd.DatetimeIndex,
    interpolated_data: pd.DataFrame,
    var_column: str,
    lat: float,
    lon: float,
    elev: float,
) -> Path:
    """Write SWAT+ file for non-temperature variables.

    Output format:
    - line 1: filename
    - line 2: header "nbyr tstep lat lon elev"
    - line 3: metadata row
    - subsequent lines: "year yday value" (tab-separated)
    
    File naming uses explicit mapping:
    - precipitation_height -> pcp.pcp
    - humidity -> rh.hmd
    - wind_speed -> wind.wnd
    - radiation_global -> solar.slr
    """
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    dates = pd.to_datetime(interpolation_dates)
    df = _prepare_df_index_by_date(interpolated_data)

    ext_map = {
        "precipitation_height": ("pcp", "pcp"),
        "pcp": ("pcp", "pcp"),
        "humidity": ("rh", "hmd"),
        "rh": ("rh", "hmd"),
        "wind_speed": ("wind", "wnd"),
        "wind": ("wind", "wnd"),
        "radiation_global": ("solar", "slr"),
        "solar": ("solar", "slr"),
    }

    prefix, ext = ext_map.get(var_column, ("var", "tmp"))
    file_name = f"{prefix}{int(subbasin_id):03d}.{ext}"
    out_path = out_dir / file_name

    with out_path.open("w", newline="") as fh:
        fh.write(f"{file_name}\n")
        fh.write("\t".join(["nbyr", "tstep", "lat", "lon", "elev"]) + "\n")
        nbyr = len(pd.Index(dates.year).unique())
        fh.write("\t".join([str(nbyr), "0", f"{round(lat, 2):.2f}", f"{round(lon, 2):.2f}", f"{round(elev, 2):.2f}"]) + "\n")

        for d in dates:
            d0 = pd.to_datetime(d).normalize()
            year = d0.year
            yday = int(d0.dayofyear)
            v = _get_for_date(df, d0, var_column)
            v_s = "" if v is None else "{:.2f}".format(v)
            fh.write("\t".join([str(year), str(yday), v_s]) + "\n")

    return out_path


__all__ = [
    "write_swat_temperature",
    "write_swat_other",
    "write_swatplus_temperature",
    "write_swatplus_other",
]
