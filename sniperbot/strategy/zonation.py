import logging
from sniperbot.strategy.swing_points import SwingPoint

logger = logging.getLogger(__name__)


class Zonation:
    PREMIUM = "premium"
    DISCOUNT = "discount"

    def __init__(self, min_excursion: float = 5.0):
        self.min_excursion = min_excursion  # minimum excursion for range-defining swings (price points)

    def determine(self, price: float, swing_points: list[SwingPoint]) -> str | None:
        if not swing_points:
            logger.info("Zonation: no swing points available")
            return None

        # Filter: only swings >= $100 (= 5 NQ points)
        highs = [s for s in swing_points if s.type == "high" and s.excursion_ticks >= self.min_excursion]
        lows = [s for s in swing_points if s.type == "low" and s.excursion_ticks >= self.min_excursion]

        if not highs or not lows:
            logger.info(f"Zonation: need >={self.min_excursion}pt excursion -- "
                        f"got {len(highs)} significant highs, {len(lows)} significant lows")
            return None

        # Most recent significant swing defines the range (ICT dealing range)
        significant_high = max(highs, key=lambda s: s.index)
        significant_low = max(lows, key=lambda s: s.index)

        range_top = significant_high.price
        range_bottom = significant_low.price
        midpoint = (range_top + range_bottom) / 2  # Fibonacci 0.5

        logger.info(
            f"Zonation: top={range_top:.0f} mid={midpoint:.0f} bottom={range_bottom:.0f} "
            f"price={price:.0f} -> "
            f"{'PREMIUM' if midpoint < price < range_top else 'DISCOUNT' if range_bottom < price < midpoint else 'OUT OF RANGE (price ' + ('above top' if price >= range_top else 'below bottom') + ')'}"
        )

        # Premium: upper half (Fib 0%-50%), only SHORT
        if midpoint < price < range_top:
            return self.PREMIUM

        # Discount: lower half (Fib 50%-100%), only LONG
        if range_bottom < price < midpoint:
            return self.DISCOUNT

        return None

    def allowed_direction(self, zone: str | None) -> str | None:
        if zone == self.PREMIUM:
            return "short"
        elif zone == self.DISCOUNT:
            return "long"
        return None
