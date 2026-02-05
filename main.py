from pathlib import Path
import pandas as pd

# Folder where main.py lives
BASE_DIR = Path(__file__).resolve().parent

# Data folder
DATA_DIR = BASE_DIR / "data"

# Excel files
watershed_path = DATA_DIR / "Watershed.xlsx"
interp_path = DATA_DIR / "interpolation_parameters.xlsx"
richter_path = DATA_DIR / "richter_parameters.xlsx"

# Read files
df_watershed = pd.read_excel(watershed_path)
df_interpolation = pd.read_excel(interp_path)
df_richter = pd.read_excel(richter_path)



