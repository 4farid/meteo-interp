import numpy as np

def idw_from_dataframe_group(group, dist_col, val_col, power=2.0, missing_value=-99.0):
    """
    Compute IDW from a DataFrame group with distance and value columns.
    
    Designed for use with pandas groupby().apply() for vectorized interpolation.

    Parameters
    ----------
    group : pd.DataFrame
        A subset of data (e.g., one date's worth of station measurements).
    dist_col : str
        Column name containing distances.
    val_col : str
        Column name containing values.
    power : float
        IDW power parameter (commonly 1–3).
    missing_value : float
        Value to return when no valid data is available.

    Returns
    -------
    float
        Interpolated value, or missing_value if insufficient data.
    """
    d = group[dist_col].values.astype(float)
    v = group[val_col].values.astype(float)
    mask = np.isfinite(d) & np.isfinite(v)
    d, v = d[mask], v[mask]
    
    if len(d) == 0:
        return missing_value
    
    # Check for exact hit (distance ~= 0)
    eps = 1e-12
    zero = d <= eps
    if np.any(zero):
        return float(np.mean(v[zero]))
    
    weights = 1.0 / (d ** power)
    return float(np.sum(weights * v) / np.sum(weights))
