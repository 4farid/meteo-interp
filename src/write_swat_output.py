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
    - subsequent lines: "max,min" (comma-separated, no spaces)
    """
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    dates = pd.to_datetime(interpolation_dates)
    if start_date is None:
        start_date = dates[0]

    df = _prepare_df_index_by_date(interpolated_data_temp)

    max_col = _first_available_column(df, ("temperature_air_max_2m", "max_Temperature", "Max_Temperature", "tmax", "temperature_max"))
    min_col = _first_available_column(df, ("temperature_air_min_2m", "min_Temperature", "Min_Temperature", "tmin", "temperature_min"))

    file_name = f"tmp{int(subbasin_id):03d}.txt"
    out_path = out_dir / file_name

    lines = [start_date.strftime("%Y%m%d")]
    for d in dates:
        d0 = pd.to_datetime(d).normalize()
        mx = _get_for_date(df, d0, max_col)
        mn = _get_for_date(df, d0, min_col)

        def fmt(x):
            return "" if x is None else "{:.2f}".format(x)

        lines.append(f"{fmt(mx)},{fmt(mn)}")

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

    # Prepare DataFrame with date, year, yday, max, min
    df = interpolated_data_temp.copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['year'] = df['date'].dt.year
    df['yday'] = df['date'].dt.dayofyear

    max_col = _first_available_column(df, ("temperature_air_max_2m", "max_Temperature", "Max_Temperature", "tmax", "temperature_max"))
    min_col = _first_available_column(df, ("temperature_air_min_2m", "min_Temperature", "Min_Temperature", "tmin", "temperature_min"))

    file_name = f"tmp{int(subbasin_id):03d}.tmp"
    out_path = out_dir / file_name

    with out_path.open("w", newline="") as fh:
        fh.write(f"{file_name}\n")
        fh.write("\t".join(["nbyr", "tstep", "lat", "lon", "elev"]) + "\n")
        nbyr = df['year'].nunique()
        fh.write("\t".join([str(nbyr), "0", f"{round(lat, 2):.2f}", f"{round(lon, 2):.2f}", f"{round(elev, 2):.2f}"]) + "\n")

        for _, row in df.iterrows():
            mx = row[max_col] if max_col and max_col in df.columns else None
            mn = row[min_col] if min_col and min_col in df.columns else None
            mx_s = "" if pd.isna(mx) else f"{mx:.2f}"
            mn_s = "" if pd.isna(mn) else f"{mn:.2f}"
            fh.write("\t".join([str(row['year']), str(row['yday']), mx_s, mn_s]) + "\n")

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

    # Prepare DataFrame with date, year, yday, value
    df = interpolated_data.copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['year'] = df['date'].dt.year
    df['yday'] = df['date'].dt.dayofyear

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
        nbyr = df['year'].nunique()
        fh.write("\t".join([str(nbyr), "0", f"{round(lat, 2):.2f}", f"{round(lon, 2):.2f}", f"{round(elev, 2):.2f}"]) + "\n")

        for _, row in df.iterrows():
            v = row[var_column]
            v_s = "" if pd.isna(v) else f"{v:.2f}"
            fh.write("\t".join([str(row['year']), str(row['yday']), v_s]) + "\n")

    return out_path


def write_swat_stations_metadata(
    output_folder: str | Path,
    stations_data: list[dict],
) -> Path:
    """Write SWAT stations metadata files.
    
    Creates metadata files for each variable type listing all subbasins.
    
    Parameters
    ----------
    output_folder : str | Path
        Output directory for metadata files
    stations_data : list[dict]
        List of station dictionaries with keys:
        - variable: variable type (e.g., 'temperature', 'precipitation')
        - prefix: file prefix (e.g., 'tmp', 'pcp')
        - subbasin_id : subbasin ID
        - name : station name (e.g., 'tmp001')
        - lat : latitude
        - lon : longitude
        - elev : elevation
    """
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Group by variable type
    by_variable = {}
    for station in stations_data:
        var = station['variable']
        if var not in by_variable:
            by_variable[var] = []
        by_variable[var].append(station)
    
    # Write one file per variable type
    prefix_map = {
        'temperature': 'tmp',
        'precipitation_height': 'pcp',
        'humidity': 'rh',
        'wind_speed': 'wind',
        'radiation_global': 'solar',
    }
    
    paths = []
    for var, stations in by_variable.items():
        prefix = prefix_map.get(var, 'var')
        file_name = f"{prefix}.txt"
        out_path = out_dir / file_name
        
        lines = ["ID,NAME,LAT,LONG,ELEVATION"]
        for station in sorted(stations, key=lambda x: x['subbasin_id']):
            line = (
                f"{station['subbasin_id']},"
                f"{station['name']},"
                f"{station['lat']},"
                f"{station['lon']},"
                f"{station['elev']}"
            )
            lines.append(line)
        
        out_path.write_text("\n".join(lines))
        paths.append(out_path)
    
    return paths


def write_swatplus_climate_files(
    output_folder: str | Path,
    subbasin_ids: list[int],
) -> list[Path]:
    """Write SWAT+ climate list files (.cli).
    
    Creates .cli files that list all station data files for each variable type.
    
    Parameters
    ----------
    output_folder : str | Path
        Output directory for .cli files
    subbasin_ids : list[int]
        List of subbasin IDs to include in the climate files
    
    Returns
    -------
    list[Path]
        List of created .cli file paths
    """
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Define climate file mappings
    climate_files = {
        'tmp.cli': [f'tmp{sid:03d}.tmp' for sid in sorted(subbasin_ids)],
        'pcp.cli': [f'pcp{sid:03d}.pcp' for sid in sorted(subbasin_ids)],
        'hmd.cli': [f'rh{sid:03d}.hmd' for sid in sorted(subbasin_ids)],
        'wnd.cli': [f'wind{sid:03d}.wnd' for sid in sorted(subbasin_ids)],
        'slr.cli': [f'solar{sid:03d}.slr' for sid in sorted(subbasin_ids)],
    }
    
    paths = []
    for cli_name, data_files in climate_files.items():
        out_path = out_dir / cli_name
        
        lines = [cli_name]  # First line is the filename with .cli extension
        lines.extend(data_files)
        
        out_path.write_text("\n".join(lines) + "\n")
        paths.append(out_path)
    
    return paths


__all__ = [
    "write_swat_temperature",
    "write_swat_other",
    "write_swatplus_temperature",
    "write_swatplus_other",
    "write_swat_stations_metadata",
    "write_swatplus_climate_files",
]
