"""Phase 11 — unit tests for forecast math (no DB)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.forecast import (
    ewma, safety_stock, reorder_point, eoq, z_score_anomaly, daily_series_from_rows,
)


def test_ewma_empty():
    assert ewma([]) == 0.0


def test_ewma_constant_series_converges():
    # Constant series EWMA should equal the constant
    assert abs(ewma([5.0] * 10, 0.3) - 5.0) < 1e-9


def test_ewma_weights_recent_more():
    # Jump at the end should pull the average up
    low = ewma([1.0] * 9 + [1.0], 0.5)
    high = ewma([1.0] * 9 + [100.0], 0.5)
    assert high > low + 10


def test_safety_stock_zero_variance():
    assert safety_stock([5.0] * 10) == 0.0


def test_safety_stock_positive_with_variance():
    assert safety_stock([1.0, 5.0, 10.0, 2.0, 8.0]) > 0


def test_reorder_point():
    # ewma=10/day, lead=7, ss=5  -> 75
    assert reorder_point(10.0, 7, 5.0) == 75.0


def test_eoq_zero_demand():
    assert eoq(0) == 0


def test_eoq_positive_demand():
    # sqrt(2*3650*20/0.5) ≈ 540
    q = eoq(3650, order_cost=20, holding_cost_per_unit=0.5)
    assert 500 <= q <= 600


def test_z_score_insufficient_data():
    assert z_score_anomaly(10.0, [1.0, 2.0]) == 0.0


def test_z_score_detects_spike():
    window = [10.0] * 29
    z = z_score_anomaly(1000.0, window)
    assert z > 3  # clear anomaly


def test_daily_series_pads_missing_days():
    series = daily_series_from_rows([], window_days=30)
    assert len(series) == 30
    assert all(v == 0.0 for v in series)
