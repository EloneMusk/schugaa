import time
from datetime import datetime

try:
    from pydexcom import Dexcom
except Exception:  # pragma: no cover
    Dexcom = None


class DexcomClient:
    def __init__(self, email, password, region="us"):
        self.email = email
        self.password = password
        self.region = (region or "us").lower()
        self.last_error = None
        self.client = None

    def login(self):
        if Dexcom is None:
            self.last_error = {
                "type": "missing_dependency",
                "message": "pydexcom is not installed."
            }
            return False

        try:
            self.client = Dexcom(username=self.email, password=self.password, region=self.region)
            # Test by fetching last reading
            _ = self.client.get_current_glucose_reading()
            return True
        except Exception as e:
            self.last_error = {
                "type": "login_failed",
                "message": str(e)
            }
            return False

    def _trend_to_arrow(self, trend):
        if not trend:
            return 3
        trend_str = str(trend).upper()
        mapping = {
            "DOUBLE_UP": 5,
            "SINGLE_UP": 5,
            "FORTY_FIVE_UP": 4,
            "FLAT": 3,
            "FORTY_FIVE_DOWN": 2,
            "SINGLE_DOWN": 1,
            "DOUBLE_DOWN": 1,
        }
        return mapping.get(trend_str, 3)

    def get_latest_glucose(self, retry=True):
        try:
            self.last_error = None
            if not self.client:
                if not self.login():
                    return None

            readings = self.client.get_glucose_readings()
            if not readings:
                return None

            def fmt_ts(dt):
                return dt.strftime("%m/%d/%Y %I:%M:%S %p")

            def reading_time(reading):
                ts = reading.datetime
                if isinstance(ts, (int, float)):
                    return datetime.fromtimestamp(ts)
                return ts

            sorted_readings = sorted(readings, key=reading_time)
            latest = sorted_readings[-1]

            gdata = []
            for r in sorted_readings:
                ts_dt = reading_time(r)
                gdata.append({
                    "Value": r.value,
                    "Timestamp": fmt_ts(ts_dt)
                })

            latest_dt = reading_time(latest)

            return {
                "Value": latest.value,
                "TrendArrow": self._trend_to_arrow(latest.trend),
                "Timestamp": fmt_ts(latest_dt),
                "GraphData": gdata,
            }

        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                self.last_error = {
                    "type": "rate_limit",
                    "message": "Rate limit hit. Backing off and retrying."
                }
                return None
            if retry:
                time.sleep(2)
                return self.get_latest_glucose(retry=False)
            self.last_error = {
                "type": "fetch_failed",
                "message": str(e)
            }
            return None
