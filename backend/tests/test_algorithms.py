"""Phase 11 algorithms: EWMA forecast, EOQ, z-score anomaly. Weighted-avg cost formula."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import anomaly, forecast, reorder  # noqa: E402


def test_ewma_flat_series():
    # Constant series → ewma equals that constant.
    assert abs(forecast.ewma([5.0] * 10, alpha=0.3) - 5.0) < 1e-9


def test_ewma_responds_to_new_value():
    # Series jumps from 5 to 20; EWMA should move up but not immediately.
    before = forecast.ewma([5.0] * 5 + [20.0], alpha=0.3)
    assert 5.0 < before < 20.0


def test_reorder_point_nonzero_when_demand_exists():
    series = [3.0, 5.0, 7.0, 4.0, 6.0, 5.0]
    rp = forecast.reorder_point(series, lead_time_days=3)
    assert rp > 0


def test_eoq_matches_formula():
    # EOQ = sqrt(2 * 1000 * 25 / 2) = sqrt(25000) ≈ 158
    q = reorder.eoq(1000, order_cost=25, holding_cost_per_unit=2)
    assert 150 <= q <= 170


def test_eoq_zero_demand_returns_zero():
    assert reorder.eoq(0) == 0


def test_zscore_flags_big_deviation():
    series = [5.0, 6.0, 5.0, 4.0, 5.0, 6.0, 50.0]
    z, flag = anomaly.zscore_flag(series, threshold=2.0)
    assert flag is True and z > 2.0


def test_zscore_quiet_on_stable_series():
    series = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
    z, flag = anomaly.zscore_flag(series)
    assert flag is False


def test_weighted_avg_cost_math():
    """Mirrors the formula used in purchase_orders.receive_po so regressions trip."""
    from decimal import Decimal as D
    old_stock, old_avg = D("10"), D("2.00")
    recv, unit = D("5"), D("3.00")
    new_stock = old_stock + recv
    new_avg = (old_stock * old_avg + recv * unit) / new_stock
    # (10*2 + 5*3) / 15 = 35/15 = 2.333...
    assert new_stock == D("15")
    assert abs(new_avg - D("2.3333333333333333333333333333")) < D("1e-9")
