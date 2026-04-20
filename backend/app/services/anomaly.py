"""z-score anomaly: return items whose last-day sales deviate > threshold sigma."""
import statistics


def zscore_flag(daily_series: list[float], threshold: float = 2.0) -> tuple[float, bool]:
    """Return (z, is_anomaly). Needs at least 3 points; else (0, False)."""
    if len(daily_series) < 3:
        return 0.0, False
    last = float(daily_series[-1])
    history = daily_series[:-1]
    mu = statistics.mean(history)
    try:
        sigma = statistics.stdev(history)
    except statistics.StatisticsError:
        return 0.0, False
    if sigma == 0:
        return 0.0, False
    z = (last - mu) / sigma
    return z, abs(z) >= threshold
