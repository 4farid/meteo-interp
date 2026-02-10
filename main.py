from pathlib import Path
import pandas as pd
import numpy as np
import time
from math import radians, sin, cos, sqrt, atan2

from src.dwd import dwd_daily_met_distance_plus_solar_rank


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth (in km).
    Uses the Haversine formula.
    """
    R = 6371.0  # Earth's radius in kilometers
    
    lat1_rad, lon1_rad = radians(lat1), radians(lon1)
    lat2_rad, lon2_rad = radians(lat2), radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    return R * c
from src.idw import idw_from_distances
from src.richter import apply_richter_correction
from src.write_swat_output import (
    write_swat_temperature,
    write_swat_other,
    write_swatplus_temperature,
    write_swatplus_other,
    write_swat_stations_metadata,
    write_swatplus_climate_files,
)

# Set the paths based on the location of this script
BASE_DIR = Path(__file__).resolve().parent

# Set the paths manually
#BASE_DIR = Path("/home/ghnfarid/Projects/meteo-interp")

DATA_DIR = BASE_DIR / "data"
# store results for all subbasins: { subbasin: { param: DataFrame } }
all_results = {}

# Now read the files
watershed = pd.read_excel(DATA_DIR / "watershed.xlsx")
interpolation_pars = pd.read_excel(DATA_DIR / "interpolation_parameters.xlsx")
richter_pars = pd.read_excel(DATA_DIR / "richter_parameters.xlsx")

# Check which output format to write (1 = SWAT+, 0 = SWAT)
swatplus = int(interpolation_pars['swatplus'].iloc[0])

# Check if Richter(1995) correction should be applied (1 = apply, 0 = skip)
apply_richter = int(interpolation_pars['apply_richter'].iloc[0]) if 'apply_richter' in interpolation_pars.columns else 0

# Check if data source is DWD (1 = DWD, 0 = custom xlsx files)
is_dwd = int(interpolation_pars['is_dwd'].iloc[0]) if 'is_dwd' in interpolation_pars.columns else 1

# Start timing
start_time = time.time()

for index, row in watershed.iterrows():
    subbasin = row["Subbasin"]
    latlon = (row["Lat"], row["Long"])

    # ---- Data Fetching (DWD or custom xlsx) ----
    start_date = interpolation_pars['start_date'].iloc[0].strftime("%Y-%m-%d")
    end_date = interpolation_pars['end_date'].iloc[0].strftime("%Y-%m-%d")
    distance_km = interpolation_pars['radius_kl'].iloc[0]
    periods = ["historical"]

    if is_dwd == 1:
        # Fetch stations and values from DWD
        stations_df, values_df = dwd_daily_met_distance_plus_solar_rank(
            latlon=latlon,
            distance_km=distance_km,
            start_date=start_date,
            end_date=end_date,
            periods=periods,
            drop_nulls=True,
        )

        if len(stations_df) == 0:
            print(f"No stations found for subbasin {subbasin}")
            continue

        # Convert to pandas for easier manipulation
        stations_pd = stations_df.to_pandas() if hasattr(stations_df, 'to_pandas') else stations_df
        values_pd = values_df.to_pandas() if hasattr(values_df, 'to_pandas') else values_df
    else:
        # Read stations and values from user-provided xlsx files
        # Expected file structure:
        #   - stations.xlsx: station_id, latitude, longitude
        #   - values.xlsx (wide format): station_id, date, precipitation_height, temperature_air_max_2m, 
        #                                temperature_air_min_2m, humidity, wind_speed, radiation_global, etc.
        stations_file = DATA_DIR / "stations.xlsx"
        values_file = DATA_DIR / "values.xlsx"
        
        if not stations_file.exists():
            print(f"Subbasin {subbasin}: stations.xlsx not found in {DATA_DIR}")
            continue
        if not values_file.exists():
            print(f"Subbasin {subbasin}: values.xlsx not found in {DATA_DIR}")
            continue
        
        stations_pd = pd.read_excel(stations_file)
        values_pd = pd.read_excel(values_file)
        
        # Standardize column names: lowercase and strip whitespace
        stations_pd.columns = stations_pd.columns.str.lower().str.strip()
        values_pd.columns = values_pd.columns.str.lower().str.strip()
        
        # Ensure required columns exist in stations file
        required_station_cols = {'station_id', 'latitude', 'longitude'}
        missing_cols = required_station_cols - set(stations_pd.columns)
        if missing_cols:
            print(f"Subbasin {subbasin}: stations.xlsx missing columns: {missing_cols}")
            print(f"  Available columns: {list(stations_pd.columns)}")
            continue
        
        # Ensure required columns exist in values file
        required_values_cols = {'station_id', 'date'}
        missing_values_cols = required_values_cols - set(values_pd.columns)
        if missing_values_cols:
            print(f"Subbasin {subbasin}: values.xlsx missing columns: {missing_values_cols}")
            print(f"  Available columns: {list(values_pd.columns)}")
            continue
        
        if len(stations_pd) == 0:
            print(f"No stations found for subbasin {subbasin}")
            continue
        
        # Calculate distance from subbasin centroid to each station using haversine
        subbasin_lat, subbasin_lon = latlon
        stations_pd['distance'] = stations_pd.apply(
            lambda r: haversine_distance(subbasin_lat, subbasin_lon, r['latitude'], r['longitude']),
            axis=1
        )
        
        print(f"Subbasin {subbasin}: Loaded {len(stations_pd)} stations from xlsx (distances calculated from lat/lon)")
    
    # Support both wide and long (tidy) formats from wetterdienst
    def _infer_value_columns(df: pd.DataFrame):
        cols = {c.lower(): c for c in df.columns}
        station_col = cols.get('station_id') or cols.get('stations_id') or cols.get('stationid')
        date_col = cols.get('date') or cols.get('mess_datum') or cols.get('datetime') or cols.get('time')
        param_col = cols.get('parameter') or cols.get('element') or cols.get('observation_type')
        value_col = cols.get('value') or cols.get('wert') or cols.get('measurement')
        return station_col, date_col, param_col, value_col

    # Detect long vs wide format
    lower_cols = set(c.lower() for c in values_pd.columns)
    is_long = any(x in lower_cols for x in ('parameter', 'element', 'observation_type'))

    # ---- Apply Richter (1995) Correction to Raw Precipitation Data ----
    if apply_richter == 1:
        if is_long:
            station_col, date_col, param_col, value_col = _infer_value_columns(values_pd)
            values_pd[date_col] = pd.to_datetime(values_pd[date_col], utc=True)
            
            # Extract precipitation and temperature data
            pcp_data = values_pd[values_pd[param_col] == 'precipitation_height'].copy() if 'precipitation_height' in values_pd[param_col].values else None
            temp_data = values_pd[values_pd[param_col] == 'temperature_air_mean_2m'].copy() if 'temperature_air_mean_2m' in values_pd[param_col].values else None
            
            if pcp_data is not None and temp_data is not None:
                # Merge precipitation with temperature by date and station
                merged = pcp_data.merge(
                    temp_data[[station_col, date_col, value_col]],
                    on=[station_col, date_col],
                    suffixes=('_pcp', '_temp')
                )
                
                try:
                    corrected_values = []
                    for _, row in merged.iterrows():
                        pcp = float(row[f'{value_col}_pcp'])
                        temp = float(row[f'{value_col}_temp'])
                        
                        if pd.isna(pcp) or pcp == -99 or pd.isna(temp):
                            corrected_values.append(pcp)
                            continue
                        
                        # Apply Richter correction
                        if temp <= richter_pars['T_Snow'].iloc[0]:
                            dchange = richter_pars['b_Snow'].iloc[0] * (pcp ** richter_pars['epsilon_Snow'].iloc[0])
                        elif temp <= richter_pars['T_Mix'].iloc[0]:
                            dchange = richter_pars['b_Mix'].iloc[0] * (pcp ** richter_pars['epsilon_Mix'].iloc[0])
                        else:
                            month = row[date_col].month
                            if month >= richter_pars['Summer_month_Start'].iloc[0] or month < richter_pars['Winter_month_Start'].iloc[0]:
                                dchange = richter_pars['b_Summer'].iloc[0] * (pcp ** richter_pars['epsilon_Summer'].iloc[0])
                            else:
                                dchange = richter_pars['b_Winter'].iloc[0] * (pcp ** richter_pars['epsilon_Winter'].iloc[0])
                        
                        max_change = richter_pars['maximum_changes'].iloc[0] * pcp
                        if dchange > max_change:
                            dchange = max_change
                        
                        corrected_pcp = round(pcp + dchange, 2)
                        corrected_values.append(corrected_pcp)
                    
                    # Update precipitation values in values_pd
                    corrected_df = pd.DataFrame({
                        station_col: merged[station_col].values,
                        date_col: merged[date_col].values,
                        value_col: corrected_values
                    })
                    
                    # Remove old precipitation values and add corrected ones
                    values_pd = values_pd[values_pd[param_col] != 'precipitation_height']
                    corrected_df[param_col] = 'precipitation_height'
                    values_pd = pd.concat([values_pd, corrected_df], ignore_index=True)
                    
                    print(f"Subbasin {subbasin}: Applied Richter(1995) correction to raw precipitation")
                except Exception as e:
                    print(f"Subbasin {subbasin}: Error applying Richter correction: {e}")
        else:
            # Wide format correction would go here if needed
            pass

    parameter_dfs = {}

    if is_long:
        station_col, date_col, param_col, value_col = _infer_value_columns(values_pd)
        if not all([station_col, date_col, param_col, value_col]):
            raise KeyError(f"Could not infer columns from values_df: {list(values_pd.columns)}")

        # ensure datetime (handle mixed tz-aware/naive values)
        values_pd[date_col] = pd.to_datetime(values_pd[date_col], utc=True)

        params = values_pd[param_col].unique()
        for param in params:
            df_rows = []
            dates = sorted(values_pd[date_col].unique())
            for d in dates:
                subset = values_pd[(values_pd[date_col] == d) & (values_pd[param_col] == param)]
                # map station -> distance
                distances = []
                vals = []
                for _, r in subset.iterrows():
                    sid = r[station_col]
                    station_distance = stations_pd[stations_pd['station_id'] == sid]['distance'].values
                    if len(station_distance) == 0:
                        continue
                    v = r[value_col]
                    if pd.isna(v):
                        continue
                    distances.append(float(station_distance[0]))
                    vals.append(float(v))

                if len(distances) > 0 and len(vals) > 0:
                    try:
                        val = idw_from_distances(distances, vals, power=2.0)
                    except Exception:
                        val = -99
                else:
                    val = -99
                df_rows.append({'date': d, 'value': val})

            parameter_dfs[param] = pd.DataFrame(df_rows)
            print(f"Subbasin {subbasin}, Parameter {param}: {len(parameter_dfs[param])} values interpolated")
    else:
        # wide format: parameter columns are all except known metadata
        exclude_cols = {'station_id', 'latitude', 'longitude', 'distance', 'date', 'start_date', 'end_date'}
        parameter_cols = [col for col in values_pd.columns if col not in exclude_cols]

        for param in parameter_cols:
            df_rows = []
            dates = sorted(values_pd['date'].unique())
            for d in dates:
                date_data = values_pd[values_pd['date'] == d]
                distances = []
                vals = []
                for _, r in date_data.iterrows():
                    sid = r.get('station_id')
                    station_distance = stations_pd[stations_pd['station_id'] == sid]['distance'].values
                    if len(station_distance) == 0:
                        continue
                    v = r.get(param)
                    if pd.isna(v):
                        continue
                    distances.append(float(station_distance[0]))
                    vals.append(float(v))

                if len(distances) > 0 and len(vals) > 0:
                    try:
                        val = idw_from_distances(distances, vals, power=2.0)
                    except Exception:
                        val = -99
                else:
                    val = -99
                df_rows.append({'date': d, 'value': val})

            parameter_dfs[param] = pd.DataFrame(df_rows)
            print(f"Subbasin {subbasin}, Parameter {param}: {len(parameter_dfs[param])} values interpolated")

    # Store parameter DataFrames separately for this subbasin (kept in memory)
    all_results[subbasin] = parameter_dfs
    elapsed_time = time.time() - start_time
    print(f"Stored interpolated parameters for subbasin '{subbasin}' in all_results. Duration: {elapsed_time:.2f} seconds")


# ---- Write SWAT Output Files ----
print("\n=== Writing SWAT Output Files ===")

swat_output_dir = DATA_DIR / "interpolated_swat"
swatplus_output_dir = DATA_DIR / "interpolated_swatplus"

# Collect station metadata for metadata file generation
stations_metadata = []

for subbasin, parameter_dfs in all_results.items():
    # Get subbasin metadata
    subbasin_row = watershed[watershed['Subbasin'] == subbasin].iloc[0]
    lat = subbasin_row['Lat']
    lon = subbasin_row['Long']
    elev = subbasin_row.get('Elevation', subbasin_row.get('Elev', 0))  # Try common column names
    subbasin_id = int(subbasin)
    
    # Get interpolation dates from any parameter (they should all have the same dates)
    if not parameter_dfs:
        continue
    first_param_df = next(iter(parameter_dfs.values()))
    interpolation_dates = pd.to_datetime(first_param_df['date'])
    
    # ---- Temperature Data (merge max, min) ----
    temp_df = None
    temp_params = {
        'temperature_air_max_2m': 'temperature_air_max_2m',
        'temperature_air_min_2m': 'temperature_air_min_2m',
    }
    
    has_temp = any(p in parameter_dfs for p in temp_params)
    if has_temp:
        temp_df = pd.DataFrame({'date': interpolation_dates})
        for dwd_param, col_name in temp_params.items():
            if dwd_param in parameter_dfs:
                df = parameter_dfs[dwd_param].copy()
                df.columns = ['date', col_name]
                temp_df = temp_df.merge(df, on='date', how='left')
        
        # Add to metadata
        stations_metadata.append({
            'variable': 'temperature',
            'prefix': 'tmp',
            'subbasin_id': subbasin_id,
            'name': f"tmp{subbasin_id:03d}",
            'lat': lat,
            'lon': lon,
            'elev': elev,
        })
        
        # Write legacy SWAT temperature
        if swatplus == 0:
            try:
                write_swat_temperature(
                    output_folder=swat_output_dir,
                    subbasin_id=subbasin_id,
                    interpolation_dates=interpolation_dates,
                    interpolated_data_temp=temp_df,
                )
                print(f"  ✓ Subbasin {subbasin}: wrote legacy SWAT temperature")
            except Exception as e:
                print(f"  ✗ Subbasin {subbasin}: error writing legacy SWAT temperature: {e}")
        
        # Write SWAT+ temperature
        if swatplus == 1:
            try:
                write_swatplus_temperature(
                    output_folder=swatplus_output_dir,
                    subbasin_id=subbasin_id,
                    interpolation_dates=interpolation_dates,
                    interpolated_data_temp=temp_df,
                    lat=lat,
                    lon=lon,
                    elev=elev,
                )
                print(f"  ✓ Subbasin {subbasin}: wrote SWAT+ temperature")
            except Exception as e:
                print(f"  ✗ Subbasin {subbasin}: error writing SWAT+ temperature: {e}")
    
    # ---- Other Variables (one file per variable) ----
    other_params = [
        'precipitation_height',
        'humidity',
        'wind_speed',
        'radiation_global',
    ]
    
    for param in other_params:
        if param not in parameter_dfs:
            continue
        
        param_df = parameter_dfs[param].copy()
        param_df.columns = ['date', param]
        
        # Map parameter to prefix for metadata
        prefix_map = {
            'precipitation_height': 'pcp',
            'humidity': 'rh',
            'wind_speed': 'wind',
            'radiation_global': 'solar',
        }
        prefix = prefix_map.get(param, 'var')
        
        # Add to metadata
        stations_metadata.append({
            'variable': param,
            'prefix': prefix,
            'subbasin_id': subbasin_id,
            'name': f"{prefix}{subbasin_id:03d}",
            'lat': lat,
            'lon': lon,
            'elev': elev,
        })
        
        # Write legacy SWAT
        if swatplus == 0:
            try:
                write_swat_other(
                    output_folder=swat_output_dir,
                    subbasin_id=subbasin_id,
                    interpolation_dates=interpolation_dates,
                    interpolated_data=param_df,
                    var_column=param,
                )
                print(f"  ✓ Subbasin {subbasin}: wrote legacy SWAT {param}")
            except Exception as e:
                print(f"  ✗ Subbasin {subbasin}: error writing legacy SWAT {param}: {e}")
        
        # Write SWAT+
        if swatplus == 1:
            try:
                write_swatplus_other(
                    output_folder=swatplus_output_dir,
                    subbasin_id=subbasin_id,
                    interpolation_dates=interpolation_dates,
                    interpolated_data=param_df,
                    var_column=param,
                    lat=lat,
                    lon=lon,
                    elev=elev,
                )
                print(f"  ✓ Subbasin {subbasin}: wrote SWAT+ {param}")
            except Exception as e:
                print(f"  ✗ Subbasin {subbasin}: error writing SWAT+ {param}: {e}")

# Write station metadata files
if swatplus == 0 and stations_metadata:
    try:
        write_swat_stations_metadata(swat_output_dir, stations_metadata)
        print(f"  ✓ Written SWAT climate list files (tmp.txt, pcp.txt, rh.txt, wind.txt, solar.txt)")
    except Exception as e:
        print(f"  ✗ Written SWAT climate list files: {e}")

# Write SWAT+ climate list files
if swatplus == 1 and all_results:
    try:
        subbasin_ids = [int(sb) for sb in all_results.keys()]
        write_swatplus_climate_files(swatplus_output_dir, subbasin_ids)
        print(f"  ✓ Written SWAT+ climate list files (tmp.cli, pcp.cli, hmd.cli, wnd.cli, slr.cli)")
    except Exception as e:
        print(f"  ✗ Error writing SWAT+ climate list files: {e}")

print("\n=== SWAT Output Generation Complete ===")

