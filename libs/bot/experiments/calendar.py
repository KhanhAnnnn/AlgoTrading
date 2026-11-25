"""
libs/bot/experiments/calendar.py — US Stock Market Session Hours Calendar (GĐ38)
Implements precise regular trading hours, EST/EDT transitions (America/New_York),
weekends, holidays, and early closes with versioned calendar policy.
"""

from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger("market-calendar")

# Canonical Eastern Time Zone
EASTERN_TZ = ZoneInfo("America/New_York")


class MarketSessionCalendar:
    """
    US Equity Market Trading Calendar with EST/EDT handling, holidays, and early closes.
    Calendar policy version: '2026.1'.
    """

    POLICY_VERSION = "2026.1"

    REGULAR_OPEN = time(9, 30, 0)
    REGULAR_CLOSE = time(16, 0, 0)
    EARLY_CLOSE = time(13, 0, 0)

    # Known fixed/observed market holidays
    FIXED_HOLIDAYS = {
        (1, 1): "New Year's Day",
        (6, 19): "Juneteenth National Independence Day",
        (7, 4): "Independence Day",
        (12, 25): "Christmas Day",
    }

    def __init__(self, policy_version: str = POLICY_VERSION):
        self.policy_version = policy_version

    @classmethod
    def _is_weekend(cls, d: date) -> bool:
        return d.weekday() >= 5  # 5=Saturday, 6=Sunday

    @classmethod
    def _get_easter(cls, year: int) -> date:
        """Anonymous Gregorian algorithm for Easter calculation."""
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    @classmethod
    def get_market_holidays(cls, year: int) -> Dict[date, str]:
        """Calculates all US Stock Market official holidays for the given year."""
        holidays: Dict[date, str] = {}

        # 1. New Year's Day (Jan 1, or observed on Dec 31 if Jan 1 is Sat, or Jan 2 if Jan 1 is Sun)
        ny = date(year, 1, 1)
        if ny.weekday() == 6:  # Sunday -> observed Monday Jan 2
            holidays[date(year, 1, 2)] = "New Year's Day (Observed)"
        elif ny.weekday() != 5:  # If Saturday, sometimes not observed or observed Dec 31 previous year
            holidays[ny] = "New Year's Day"

        # 2. Martin Luther King Jr. Day: 3rd Monday in January
        first_jan = date(year, 1, 1)
        mlk_day = first_jan + timedelta(days=(7 - first_jan.weekday()) % 7 + 14)
        holidays[mlk_day] = "Martin Luther King Jr. Day"

        # 3. Washington's Birthday (Presidents' Day): 3rd Monday in February
        first_feb = date(year, 2, 1)
        pres_day = first_feb + timedelta(days=(7 - first_feb.weekday()) % 7 + 14)
        holidays[pres_day] = "Washington's Birthday"

        # 4. Good Friday: Friday before Easter Sunday
        easter = cls._get_easter(year)
        good_friday = easter - timedelta(days=2)
        holidays[good_friday] = "Good Friday"

        # 5. Memorial Day: Last Monday in May
        last_may = date(year, 5, 31)
        mem_day = last_may - timedelta(days=last_may.weekday())
        holidays[mem_day] = "Memorial Day"

        # 6. Juneteenth: June 19 (observed if weekend)
        june19 = date(year, 6, 19)
        if june19.weekday() == 5:
            holidays[date(year, 6, 18)] = "Juneteenth (Observed)"
        elif june19.weekday() == 6:
            holidays[date(year, 6, 20)] = "Juneteenth (Observed)"
        else:
            holidays[june19] = "Juneteenth National Independence Day"

        # 7. Independence Day: July 4 (observed if weekend)
        july4 = date(year, 7, 4)
        if july4.weekday() == 5:
            holidays[date(year, 7, 3)] = "Independence Day (Observed)"
        elif july4.weekday() == 6:
            holidays[date(year, 7, 5)] = "Independence Day (Observed)"
        else:
            holidays[july4] = "Independence Day"

        # 8. Labor Day: 1st Monday in September
        first_sep = date(year, 9, 1)
        labor_day = first_sep + timedelta(days=(7 - first_sep.weekday()) % 7)
        holidays[labor_day] = "Labor Day"

        # 9. Thanksgiving Day: 4th Thursday in November
        first_nov = date(year, 11, 1)
        tg_day = first_nov + timedelta(days=(3 - first_nov.weekday()) % 7 + 21)
        holidays[tg_day] = "Thanksgiving Day"

        # 10. Christmas Day: Dec 25 (observed if weekend)
        xmas = date(year, 12, 25)
        if xmas.weekday() == 5:
            holidays[date(year, 12, 24)] = "Christmas Day (Observed)"
        elif xmas.weekday() == 6:
            holidays[date(year, 12, 26)] = "Christmas Day (Observed)"
        else:
            holidays[xmas] = "Christmas Day"

        return holidays

    @classmethod
    def get_early_close_days(cls, year: int) -> Dict[date, str]:
        """Calculates days with 1:00 PM Eastern early closes."""
        early_closes: Dict[date, str] = {}
        # Day before Independence Day (if July 3 is weekday and July 4 is weekday)
        july3 = date(year, 7, 3)
        if july3.weekday() < 5 and date(year, 7, 4).weekday() < 5:
            early_closes[july3] = "Day Before Independence Day"

        # Black Friday: Day after Thanksgiving (4th Friday in Nov)
        first_nov = date(year, 11, 1)
        tg_day = first_nov + timedelta(days=(3 - first_nov.weekday()) % 7 + 21)
        black_friday = tg_day + timedelta(days=1)
        early_closes[black_friday] = "Day After Thanksgiving (Black Friday)"

        # Christmas Eve: Dec 24 (if weekday)
        xmas_eve = date(year, 12, 24)
        if xmas_eve.weekday() < 5 and date(year, 12, 25).weekday() != 0:
            early_closes[xmas_eve] = "Christmas Eve"

        return early_closes

    def is_trading_day(self, d: Any) -> bool:
        """Determines if the specified date is an active market trading day."""
        if isinstance(d, datetime):
            d = d.date()
        if self._is_weekend(d):
            return False
        holidays = self.get_market_holidays(d.year)
        return d not in holidays

    def get_session_hours(self, d: Any) -> Optional[Tuple[time, time]]:
        """Returns (open_time, close_time) in Eastern Time, or None if market is closed."""
        if isinstance(d, datetime):
            d = d.date()
        if not self.is_trading_day(d):
            return None
        early_closes = self.get_early_close_days(d.year)
        if d in early_closes:
            return (self.REGULAR_OPEN, self.EARLY_CLOSE)
        return (self.REGULAR_OPEN, self.REGULAR_CLOSE)

    def is_market_open(self, dt: datetime) -> bool:
        """Checks whether the exact timestamp falls within active market hours."""
        if dt.tzinfo is None:
            # Assume UTC if naive, then convert to Eastern
            dt = dt.replace(tzinfo=timezone.utc).astimezone(EASTERN_TZ)
        else:
            dt = dt.astimezone(EASTERN_TZ)

        session = self.get_session_hours(dt.date())
        if not session:
            return False
        open_time, close_time = session
        current_time = dt.time()
        return open_time <= current_time < close_time

    def filter_trading_minutes(self, bars: List[Any]) -> List[Any]:
        """Filters a list of bars to only those within market trading hours."""
        filtered = []
        for bar in bars:
            ts = getattr(bar, "timestamp", None) or getattr(bar, "event_time", None)
            if ts is None and isinstance(bar, dict):
                ts = bar.get("timestamp") or bar.get("event_time")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if ts and self.is_market_open(ts):
                filtered.append(bar)
        return filtered

    def get_market_calendar_policy(self) -> Dict[str, Any]:
        """Returns structured metadata about the active calendar policy."""
        return {
            "policy_version": self.policy_version,
            "timezone": "America/New_York",
            "regular_open": "09:30:00",
            "regular_close": "16:00:00",
            "early_close": "13:00:00",
            "est_edt_handling": "Dynamic via ZoneInfo(America/New_York)",
        }
