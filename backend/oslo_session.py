"""Verified 2026 Oslo cash calendar. Unknown years/half-day close remain unknown.

Sources checked 2026-09-24:
https://www.euronext.com/en/trading/trading-hours-holidays
https://connect2.euronext.com/sites/default/files/it-documentation/Oslo_Bors_Migration%20Guidelines%20-%20v2.3.1_0.pdf
Closing auction ends at 16:25; 16:20 is the end of continuous trading.
The exceptional 1 April session requires its specific timetable; do not guess it.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
OSLO = ZoneInfo('Europe/Oslo')
CLOSED_2026 = {'2026-01-01','2026-04-02','2026-04-03','2026-04-06','2026-05-01','2026-05-14','2026-05-25','2026-12-24','2026-12-25','2026-12-31'}


def previous_close(now=None):
    local = (now or datetime.now(timezone.utc)).astimezone(OSLO)
    day = local.date()
    for _ in range(14):
        if day.year != 2026:
            return None
        if day.weekday() < 5 and day.isoformat() not in CLOSED_2026:
            if day.isoformat() == '2026-04-01':
                return None
            close = datetime.combine(day, time(16,25), OSLO)
            if close <= local:
                return close
        day -= timedelta(days=1)
    return None
