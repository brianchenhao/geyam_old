"""Economic Order Quantity.

EOQ = sqrt(2 * D * S / H)
  D = annual demand (units/year)
  S = fixed ordering cost per PO (RM)
  H = annual holding cost per unit (RM/year)
"""
import math


def eoq(annual_demand: float, order_cost: float = 25.0,
        holding_cost_per_unit: float = 2.0) -> int:
    if annual_demand <= 0 or holding_cost_per_unit <= 0:
        return 0
    q = math.sqrt(2 * annual_demand * order_cost / holding_cost_per_unit)
    return max(1, int(round(q)))
