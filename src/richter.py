"""
Richter (1995) precipitation correction method based on temperature.
Corrects systematic gauge undercatch errors for different precipitation types.
"""

import pandas as pd
import numpy as np


def apply_richter_correction(
    precipitation: pd.DataFrame,
    temperature: pd.DataFrame,
    richter_pars: pd.DataFrame,
) -> pd.DataFrame:
    """
    Apply Richter (1995) correction to precipitation data based on temperature.
    
    Parameters
    ----------
    precipitation : pd.DataFrame
        DataFrame with columns ['date', 'precipitation_height'] containing precipitation values
    temperature : pd.DataFrame
        DataFrame with columns ['date', 'temperature'] containing temperature values
    richter_pars : pd.DataFrame
        DataFrame with Richter correction parameters containing:
        - epsilon_Snow, b_Snow: Snow correction parameters
        - epsilon_Mix, b_Mix: Mix correction parameters
        - epsilon_Summer, b_Summer: Summer rain correction parameters
        - epsilon_Winter, b_Winter: Winter rain correction parameters
        - T_Snow: Temperature threshold for snow [°C]
        - T_Mix: Temperature threshold for mix [°C]
        - maximum_changes: Maximum relative change (dmax)
        - Summer_month_Start: Month when summer period starts
        - Winter_month_Start: Month when winter period starts
    
    Returns
    -------
    pd.DataFrame
        Corrected precipitation DataFrame with same structure as input
    """
    
    # Extract Richter parameters
    eps_snow = richter_pars['epsilon_Snow'].iloc[0]
    b_snow = richter_pars['b_Snow'].iloc[0]
    
    eps_mix = richter_pars['epsilon_Mix'].iloc[0]
    b_mix = richter_pars['b_Mix'].iloc[0]
    
    eps_summer = richter_pars['epsilon_Summer'].iloc[0]
    b_summer = richter_pars['b_Summer'].iloc[0]
    
    eps_winter = richter_pars['epsilon_Winter'].iloc[0]
    b_winter = richter_pars['b_Winter'].iloc[0]
    
    t_snow = richter_pars['T_Snow'].iloc[0]
    t_mix = richter_pars['T_Mix'].iloc[0]
    dmax = richter_pars['maximum_changes'].iloc[0]
    
    summer_month_start = int(richter_pars['Summer_month_Start'].iloc[0])
    winter_month_start = int(richter_pars['Winter_month_Start'].iloc[0])
    
    # Create output dataframe
    result = precipitation.copy()
    
    # Ensure we have datetime objects
    result['date'] = pd.to_datetime(result['date'])
    temp_df = temperature.copy()
    temp_df['date'] = pd.to_datetime(temp_df['date'])
    
    # Merge precipitation and temperature data
    merged = result.merge(temp_df, on='date', how='left')
    
    # Apply correction for each row
    corrected_values = []
    
    for idx, row in merged.iterrows():
        pcp = row['precipitation_height']
        temp = row.get('temperature', np.nan)
        date = row['date']
        
        # Skip invalid precipitation values
        if pd.isna(pcp) or pcp == -99:
            corrected_values.append(pcp)
            continue
        
        # Skip if temperature is missing
        if pd.isna(temp):
            corrected_values.append(pcp)
            continue
        
        # Determine correction type based on temperature
        if temp <= t_snow:
            # Snow correction
            dchange = b_snow * (pcp ** eps_snow)
        elif temp <= t_mix:
            # Mix correction
            dchange = b_mix * (pcp ** eps_mix)
        else:
            # Rain correction: summer or winter based on month
            month = date.month
            if month >= summer_month_start or month < winter_month_start:
                # Summer rain correction
                dchange = b_summer * (pcp ** eps_summer)
            else:
                # Winter rain correction
                dchange = b_winter * (pcp ** eps_winter)
        
        # Limit change to maximum
        max_change = dmax * pcp
        if dchange > max_change:
            dchange = max_change
        
        # Apply correction
        corrected_pcp = round(pcp + dchange, 2)
        corrected_values.append(corrected_pcp)
    
    # Update result with corrected values
    result['precipitation_height'] = corrected_values
    
    return result
