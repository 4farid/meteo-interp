from pathlib import Path
import pandas as pd
import numpy as np

from src.dwd import dwd_daily_met_distance_plus_solar_rank
from src.idw import idw_from_distances

# Set the paths manually
BASE_DIR = Path("/home/ghnfarid/Projects/meteo-interp")
DATA_DIR = BASE_DIR / "data"
# store results for all subbasins: { subbasin: { param: DataFrame } }
all_results = {}

# Now read the files
watershed = pd.read_excel(DATA_DIR / "watershed.xlsx")
interpolation_pars = pd.read_excel(DATA_DIR / "interpolation_parameters.xlsx")
richter_pars = pd.read_excel(DATA_DIR / "richter_parameters.xlsx")


for index, row in watershed.iterrows():
    subbasin = row["Subbasin"]
    latlon = (row["Lat"], row["Long"])

    # ---- DWD Data Fetching ----
    start_date = interpolation_pars['start_date'].iloc[0].strftime("%Y-%m-%d")
    end_date = interpolation_pars['end_date'].iloc[0].strftime("%Y-%m-%d")
    distance_km = interpolation_pars['radius_kl'].iloc[0]
    periods = ["historical"]

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

    parameter_dfs = {}

    if is_long:
        station_col, date_col, param_col, value_col = _infer_value_columns(values_pd)
        if not all([station_col, date_col, param_col, value_col]):
            raise KeyError(f"Could not infer columns from values_df: {list(values_pd.columns)}")

        # ensure datetime
        values_pd[date_col] = pd.to_datetime(values_pd[date_col])

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
    print(f"Stored interpolated parameters for subbasin '{subbasin}' in all_results")

