from datetime import datetime
from typing import Tuple, Union

from wetterdienst.provider.dwd.observation import DwdObservationRequest

DateLike = Union[str, datetime]


def dwd_daily_met_distance_plus_solar_rank(
    latlon: Tuple[float, float],
    distance_km: float,
    start_date: DateLike,
    end_date: DateLike,
    solar_rank: int = 3,
    periods: str | None = None,
    drop_nulls: bool = True,
):
    """
    KL variables: stations within distance_km
    Solar variable: closest `solar_rank` stations (enforced via .head()).

    Returns
    -------
    stations_df : polars.DataFrame
    values_df   : polars.DataFrame
    """

    kl_params = [
        ("daily", "kl", "humidity"),
        ("daily", "kl", "wind_speed"),
        ("daily", "kl", "temperature_air_max_2m"),
        ("daily", "kl", "temperature_air_min_2m"),
        ("daily", "kl", "temperature_air_mean_2m"),
        ("daily", "kl", "precipitation_height"),
    ]

    solar_params = [
        ("daily", "solar", "radiation_global"),
    ]

    # ---- KL (distance) ----
    kl_req = DwdObservationRequest(
        parameters=kl_params,
        periods=periods,
        start_date=start_date,
        end_date=end_date,
    )
    kl_df = kl_req.filter_by_distance(latlon=latlon, distance=distance_km).df

    # ---- Solar (rank) ----
    solar_req = DwdObservationRequest(
        parameters=solar_params,
        periods=periods,
        start_date=start_date,
        end_date=end_date,
    )

    # filter_by_rank() often sorts but doesn't truncate -> enforce top-N manually
    solar_df = (
        solar_req
        .filter_by_rank(latlon=latlon, rank=solar_rank)
        .df
        .sort("distance")
        .head(solar_rank)
    )

    # ---- Combine stations, unique by station_id ----
    stations_df = kl_df.vstack(solar_df).unique(subset=["station_id"])

    station_ids = stations_df.select("station_id").to_series().to_list()
    if not station_ids:
        return stations_df, stations_df.clear()

    # ---- Fetch values for merged stations (KL + Solar) ----
    all_params = kl_params + solar_params

    values_req = DwdObservationRequest(
        parameters=all_params,
        periods=periods,
        start_date=start_date,
        end_date=end_date,
    )
    values_df = (
        values_req
        .filter_by_station_id(station_id=tuple(station_ids))
        .values.all()
        .df
    )

    if drop_nulls:
        values_df = values_df.drop_nulls()

    return stations_df, values_df