"""EWMA demand forecast + safety stock + ROP + EOQ."""
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable


def ewma(series: list[float], alpha: float = 0.3) -> float:
    if not series:
        return 0.0
    s = series[0]
    for x in series[1:]:
        s = alpha * x + (1 - alpha) * s
    return s


def safety_stock(series: list[float], service_z: float = 1.65, lead_time_days: int = 7) -> float:
    if len(series) < 2:
        return 0.0
    mean = sum(series) / len(series)
    var = sum((x - mean) ** 2 for x in series) / (len(series) - 1)
    sigma = math.sqrt(var)
    return service_z * sigma * math.sqrt(lead_time_days)


def reorder_point(ewma_daily: float, lead_time_days: int, ss: float) -> float:
    return ewma_daily * lead_time_days + ss


def eoq(annual_demand: float, order_cost: float = 20.0, holding_cost_per_unit: float = 0.50) -> int:
    if annual_demand <= 0 or holding_cost_per_unit <= 0:
        return 0
    q = math.sqrt(2 * annual_demand * order_cost / holding_cost_per_unit)
    return int(round(q))


def daily_series_from_rows(rows: Iterable[tuple[date, float]], window_days: int = 30) -> list[float]:
    end = date.today()
    by_day = defaultdict(float)
    for d, q in rows:
        by_day[d] += float(q)
    return [by_day[end - timedelta(days=(window_days - 1 - i))] for i in range(window_days)]


def z_score_anomaly(today_value: float, window: list[float]) -> float:
    if len(window) < 3:
        return 0.0
    mean = sum(window) / len(window)
    var = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
    sigma = math.sqrt(var) if var > 0 else 1e-6
    return (today_value - mean) / sigma
