import streamlit as st
import pandas as pd
import os
import subprocess
import pydeck as pdk

# We need these to fetch the station metadata to display on the map
from datetime import datetime
from wetterdienst.provider.dwd.observation import DwdObservationRequest

# Configuration
st.set_page_config(page_title="Meteo-Interp Dashboard", page_icon="🌤️", layout="wide")
DATA_DIR = "data"

st.title("🌤️ Meteo-Interp Dashboard")
st.markdown("Interpolate weather data for SWAT/SWAT+ hydrological models.")

# --- Helper Function to Fetch Station Metadata ---
@st.cache_data(show_spinner=False)
def fetch_dwd_stations_for_map(latlon, distance_km, solar_rank=3):
    """Fetches station metadata from DWD based on the logic in src/dwd.py"""
    try:
        kl_params = [("daily", "kl", "precipitation_height")]
        solar_params = [("daily", "solar", "radiation_global")]
        
        # We don't need actual data periods, just the station metadata, 
        # but we provide dummy dates to satisfy the API
        start_date = "2020-01-01"
        end_date = "2020-01-01"
        
        # Fetch KL Stations (Distance based)
        kl_req = DwdObservationRequest(
            parameters=kl_params, periods=["historical"], 
            start_date=start_date, end_date=end_date
        )
        kl_df = kl_req.filter_by_distance(latlon=latlon, distance=distance_km).df.to_pandas()
        kl_df['Type'] = 'KL Station (Temp/Rain/Wind)'
        
        # Fetch Solar Stations (Rank based)
        solar_req = DwdObservationRequest(
            parameters=solar_params, periods=["historical"], 
            start_date=start_date, end_date=end_date
        )
        # Replicating the logic in src/dwd.py
        solar_df = solar_req.filter_by_rank(latlon=latlon, rank=solar_rank).df.to_pandas()
        solar_df = solar_df.sort_values(by="distance").head(solar_rank)
        solar_df['Type'] = 'Solar Station (Radiation)'
        
        return kl_df, solar_df
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

# --- SECTION 1: Visualize Inputs & Station Map ---
st.header("1. Watershed & Weather Stations Map")

watershed_path = os.path.join(DATA_DIR, "watershed.xlsx")
params_path = os.path.join(DATA_DIR, "interpolation_parameters.xlsx")

if os.path.exists(watershed_path) and os.path.exists(params_path):
    watershed_df = pd.read_excel(watershed_path)
    params_df = pd.read_excel(params_path)
    
    distance_km = params_df['radius_kl'].iloc[0]
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Subbasin Coordinates")
        st.dataframe(watershed_df, use_container_width=True)
        total_subbasins = len(watershed_df)
        
        # Let user select a subbasin to preview its surrounding stations
        selected_subbasin = st.selectbox("Select a Subbasin to view its fetched DWD stations:", watershed_df['Subbasin'])
        
        sub_row = watershed_df[watershed_df['Subbasin'] == selected_subbasin].iloc[0]
        latlon = (sub_row['Lat'], sub_row['Long'])
        
        with st.spinner(f"Fetching stations from DWD for Subbasin {selected_subbasin}..."):
            kl_stations, solar_stations = fetch_dwd_stations_for_map(latlon, distance_km)
            
        st.success(f"Found **{len(kl_stations)}** KL stations and **{len(solar_stations)}** Solar stations.")
        
        with st.expander("View KL Stations (Used for Temp/Precip/Wind/Humidity)"):
            st.dataframe(kl_stations[['station_id', 'name', 'distance', 'latitude', 'longitude']] if not kl_stations.empty else pd.DataFrame())
            
        with st.expander("View Solar Stations (Used for Radiation)"):
            st.dataframe(solar_stations[['station_id', 'name', 'distance', 'latitude', 'longitude']] if not solar_stations.empty else pd.DataFrame())
        
    with col2:
        st.subheader("Interactive Map")
        # Prepare Data for PyDeck Map
        
        # 1. Subbasin Data
        sub_map_df = watershed_df.copy()
        sub_map_df['color'] = [[0, 128, 255, 200]] * len(sub_map_df) # Blue
        sub_map_df['Type'] = 'Subbasin Centroid'
        sub_map_df['name'] = "Subbasin " + sub_map_df['Subbasin'].astype(str)
        
        # 2. KL Stations
        kl_map_df = pd.DataFrame()
        if not kl_stations.empty:
            kl_map_df = kl_stations.copy()
            kl_map_df['color'] = [[0, 200, 0, 200]] * len(kl_map_df) # Green
            kl_map_df['Long'] = kl_map_df['longitude']
            kl_map_df['Lat'] = kl_map_df['latitude']
            
        # 3. Solar Stations
        solar_map_df = pd.DataFrame()
        if not solar_stations.empty:
            solar_map_df = solar_stations.copy()
            solar_map_df['color'] = [[255, 165, 0, 200]] * len(solar_map_df) # Orange
            solar_map_df['Long'] = solar_map_df['longitude']
            solar_map_df['Lat'] = solar_map_df['latitude']

        # Combine all points to calculate view state
        all_points = pd.concat([sub_map_df, kl_map_df, solar_map_df], ignore_index=True)
        
        if not all_points.empty:
            view_state = pdk.ViewState(
                latitude=all_points['Lat'].mean(),
                longitude=all_points['Long'].mean(),
                zoom=8,
                pitch=0
            )

            # PyDeck Layer
            layer = pdk.Layer(
                'ScatterplotLayer',
                data=all_points,
                get_position='[Long, Lat]',
                get_color='color',
                get_radius=2000, # 2km radius for dots
                pickable=True,
            )
            
            # Map Tooltip
            tooltip = {
                "html": "<b>Type:</b> {Type} <br/> <b>Name/ID:</b> {name} <br/> <b>Lat/Lon:</b> {Lat}, {Long}",
                "style": {"backgroundColor": "steelblue", "color": "white"}
            }

            r = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="road")
            st.pydeck_chart(r)
            
            # Legend
            st.markdown("🔴 **Blue:** Subbasins | 🟢 **Green:** KL Stations (Temp/Rain) | 🟠 **Orange:** Solar Stations")

else:
    st.warning("⚠️ `data/watershed.xlsx` or `interpolation_parameters.xlsx` not found.")
    total_subbasins = 1

st.divider()

# --- SECTION 2: Run Interpolation ---
st.header("2. Run Interpolation Pipeline")

if st.button("🚀 Run `main.py`"):
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_output = st.empty()
    
    process = subprocess.Popen(
        ["python", "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    completed_subbasins = 0
    full_logs = ""
    
    for line in process.stdout:
        full_logs += line
        log_output.text_area("Terminal Output", full_logs, height=200)
        
        if "Stored interpolated parameters for subbasin" in line:
            completed_subbasins += 1
            progress = min(completed_subbasins / total_subbasins, 1.0)
            progress_bar.progress(progress)
            status_text.text(f"Processed {completed_subbasins} / {total_subbasins} subbasins...")
            
    process.wait()
    
    if process.returncode == 0:
        progress_bar.progress(1.0)
        status_text.success("✅ Interpolation completed successfully!")
    else:
        status_text.error("❌ Interpolation failed. Check the terminal output above.")

st.divider()

# --- SECTION 3: Visualize Output ---
st.header("3. View Interpolated Data")

swat_dir = os.path.join(DATA_DIR, "interpolated_swat")
swatplus_dir = os.path.join(DATA_DIR, "interpolated_swatplus")

available_files = []
if os.path.exists(swat_dir):
    available_files += [os.path.join(swat_dir, f) for f in os.listdir(swat_dir) if any(char.isdigit() for char in f)]
if os.path.exists(swatplus_dir):
    available_files += [os.path.join(swatplus_dir, f) for f in os.listdir(swatplus_dir) if any(char.isdigit() for char in f)]

if available_files:
    file_options = {os.path.basename(f): f for f in sorted(available_files)}
    selected_file = st.selectbox("Select a generated file to visualize:", list(file_options.keys()))
    file_path = file_options[selected_file]
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
        
    if lines:
        try:
            start_date_str = lines[0].strip()
            data_values = []
            for line in lines[1:]:
                parts = line.strip().split(',')
                if len(parts) == 1:
                    data_values.append([float(parts[0])])
                else:
                    data_values.append([float(p) for p in parts])
                    
            start_date = pd.to_datetime(start_date_str, format="%Y%m%d")
            dates = pd.date_range(start=start_date, periods=len(data_values), freq='D')
            
            df_plot = pd.DataFrame(data_values, index=dates)
            
            if selected_file.startswith('tmp'):
                df_plot.columns = ['Max Temp (°C)', 'Min Temp (°C)']
                st.line_chart(df_plot, color=["#FF0000", "#0000FF"])
            elif selected_file.startswith('pcp'):
                df_plot.columns = ['Precipitation (mm)']
                st.bar_chart(df_plot, color="#0080FF")
            elif selected_file.startswith('rh') or selected_file.startswith('hmd'):
                df_plot.columns = ['Relative Humidity']
                st.line_chart(df_plot, color="#00FF80")
            elif selected_file.startswith('wind') or selected_file.startswith('wnd'):
                df_plot.columns = ['Wind Speed (m/s)']
                st.line_chart(df_plot, color="#808080")
            elif selected_file.startswith('solar') or selected_file.startswith('slr'):
                df_plot.columns = ['Solar Radiation (MJ/m²)']
                st.area_chart(df_plot, color="#FFB000")
            else:
                df_plot.columns = [f"Value {i+1}" for i in range(df_plot.shape[1])]
                st.line_chart(df_plot)
            
            with st.expander("View Raw DataFrame"):
                st.dataframe(df_plot)
                
        except Exception as e:
            st.error(f"Error parsing file {selected_file}: {e}")
else:
    st.info("No interpolated output files found yet. Run the interpolation above to generate them!")