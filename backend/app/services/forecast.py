"""EWMA sales forecast + safety stock.

EWMA(alpha) = alpha * x_t + (1-alpha) * EWMA_{t-1}
safety_stock = z * sigma * sqrt(lead_time_days)     (z=1.645 for 95% service)
"""
import math
import statistics


def ewma(values: list[float], alpha: float = 0.3) -> float:
    if not values:
        return 0.0
    s = float(values[0])
    for v in values[1:]:
        s = alpha * float(v) + (1 - alpha) * s
    return s


def forecast_daily(daily_series: list[float], alpha: float = 0.3) -> float:
    """Expected units sold on the next day."""
    return ewma(daily_series, alpha)


def safety_stock(daily_series: list[float], *, lead_time_days: int = 3,
                 z: float = 1.645) -> float:
    if len(daily_series) < 2:
        return 0.0
    sigma = statistics.stdev(daily_series)
    return z * sigma * math.sqrt(max(lead_time_days, 1))


def reorder_point(
    daily_series: list[float], *, lead_time_days: int = 3, z: float = 1.645
) -> float:
    return forecast_daily(daily_series) * lead_time_days + safety_stock(
        daily_series, lead_time_days=lead_time_days, z=z,
    )
