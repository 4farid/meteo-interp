import numpy as np

def idw_from_distances(distances, values, power=2.0, eps=1e-12):
    """
    Simple Inverse Distance Weighting (IDW) using precomputed distances.

    Parameters
    ----------
    distances : array-like
        Distance from target point to each station.
    values : array-like
        Station values.
    power : float
        IDW power parameter (commonly 1–3).
    eps : float
        Small value to avoid division by zero.

    Returns
    -------
    float
        Interpolated value.
    """
    d = np.asarray(distances, dtype=float)
    v = np.asarray(values, dtype=float)

    if d.shape != v.shape:
        raise ValueError("distances and values must have the same shape")

    # Remove NaNs / infs
    mask = np.isfinite(d) & np.isfinite(v)
    d, v = d[mask], v[mask]

    if d.size == 0:
        raise ValueError("No valid stations")

    # Exact hit: return station value directly
    zero = d <= eps
    if np.any(zero):
        return float(np.mean(v[zero]))

    weights = 1.0 / (d ** power)
    return float(np.sum(weights * v) / np.sum(weights))

