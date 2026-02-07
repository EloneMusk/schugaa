
import json
import time
import os
from pylibrelinkup.pylibrelinkup import PyLibreLinkUp
from pylibrelinkup.api_url import APIUrl
from pylibrelinkup.exceptions import AuthenticationError, RedirectError
from pydantic import ValidationError
from datetime import datetime

class LibreClient:
    REGIONS = {
        "global": APIUrl.US,
        "eu": APIUrl.EU,
        "eu2": APIUrl.EU2,
        "de": APIUrl.DE,
        "fr": APIUrl.FR,
        "jp": APIUrl.JP,
        "ap": APIUrl.AP,
        "au": APIUrl.AU,
        "ae": APIUrl.AE,
        "us": APIUrl.US,
        "ca": APIUrl.CA,
        "la": APIUrl.LA,
        "gb": APIUrl.EU,
        "uk": APIUrl.EU,
        "ru": APIUrl.US, 
        "tw": APIUrl.AP,
        "kr": APIUrl.AP
    }

    def __init__(self, email, password, region="eu"):
        self.email = email
        self.password = password
        self.region = region
        self.api_url = self.REGIONS.get(region, APIUrl.US)
        self.last_error = None
        
        import pylibrelinkup.pylibrelinkup
        pylibrelinkup.pylibrelinkup.HEADERS["User-Agent"] = "LibreLinkUp/4.16.0 (com.abbott.librelinkup; build:4.16.0; Android 14; 34) OkHttp/4.12.0"
        
        self.client = PyLibreLinkUp(email, password, api_url=self.api_url)
        
        self.expiry = 0
        self.session_file = "session.json"
        self.sensor_history_file = "sensors.json"
        
        self._load_session()
        self.sensor_history = self._load_sensor_history()

    def _get_sensor_history_path(self):
        home = os.path.expanduser("~")
        app_dir = os.path.join(home, ".schugaa")
        if not os.path.exists(app_dir):
            os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, self.sensor_history_file)

    def _load_sensor_history(self):
        try:
            path = self._get_sensor_history_path()
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Failed to load sensor history: {e}")
        return {}

    def _save_sensor_history(self):
        try:
            path = self._get_sensor_history_path()
            with open(path, 'w') as f:
                json.dump(self.sensor_history, f, indent=2)
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
        except Exception as e:
            print(f"Failed to save sensor history: {e}")

    def _get_or_register_sensor(self, serial_number, api_activation_time):
        """Get stored activation time for sensor, or register new sensor with current time."""
        if not serial_number:
            return api_activation_time
            
        if serial_number in self.sensor_history:
            stored = self.sensor_history[serial_number]
            print(f"Found stored sensor {serial_number}, first seen: {stored.get('first_seen')}")
            return stored.get('first_seen_ts', api_activation_time)
        else:
            # New sensor - save with current API activation time
            now = int(time.time())
            self.sensor_history[serial_number] = {
                'first_seen': datetime.fromtimestamp(now).isoformat(),
                'first_seen_ts': now,
                'api_activation': api_activation_time
            }
            self._save_sensor_history()
            print(f"Registered new sensor {serial_number} at {datetime.fromtimestamp(now)}")
            return now


    def _normalize_timestamp(self, ts):
        if ts is None:
            return None
        if isinstance(ts, str):
            ts_str = ts.strip()
            if ts_str.isdigit():
                try:
                    ts = int(ts_str)
                except Exception:
                    return None
            else:
                try:
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    dt = datetime.fromisoformat(ts_str)
                    return int(dt.timestamp())
                except Exception:
                    return None

        try:
            ts_val = float(ts)
        except Exception:
            return None

        if ts_val > 1e11:
            ts_val = ts_val / 1000.0

        return int(ts_val)

    def _extract_sensor_times(self, graph_response):
        sensor_activated = None
        sensor_expires = None
        sensor_serial = None

        expire_keys = (
            "e",
            "exp",
            "expires",
            "expiration",
            "sensorExpires",
            "sensorExpiration",
            "end",
            "endDate",
            "endTime",
        )

        try:
            data = (graph_response or {}).get("data") or {}
            connection = data.get("connection") or {}
            sensor = connection.get("sensor") or {}

            sensor_activated = self._normalize_timestamp(sensor.get("a"))
            sensor_serial = sensor.get("sn")

            for key in expire_keys:
                if key in sensor:
                    sensor_expires = self._normalize_timestamp(sensor.get(key))
                    if sensor_expires:
                        break

            if not sensor_activated or not sensor_expires or not sensor_serial:
                active_sensors = data.get("activeSensors") or []
                for item in active_sensors:
                    s = (item or {}).get("sensor") or {}
                    if not sensor_activated:
                        sensor_activated = self._normalize_timestamp(s.get("a"))
                    if not sensor_serial:
                        sensor_serial = s.get("sn")
                    if not sensor_expires:
                        for key in expire_keys:
                            if key in s:
                                sensor_expires = self._normalize_timestamp(s.get(key))
                                if sensor_expires:
                                    break
                    if sensor_activated and sensor_serial:
                        break
        except Exception:
            pass

        # Use stored activation time if we have the serial number
        if sensor_serial:
            stored_activation = self._get_or_register_sensor(sensor_serial, sensor_activated)
            if stored_activation:
                sensor_activated = stored_activation

        # If no explicit expiry found, calculate from activation (14 days for Libre 2/3)
        if sensor_activated and not sensor_expires:
            sensor_expires = sensor_activated + (14 * 24 * 60 * 60)

        return sensor_activated, sensor_expires



    def _infer_sensor_duration_seconds(self, sensor):
        duration_days = 14
        try:
            if sensor and sensor.sn and len(sensor.sn) >= 10:
                duration_days = 15
        except Exception:
            pass

        return duration_days * 24 * 60 * 60

    def _coerce_api_url(self, value):
        if isinstance(value, APIUrl):
            return value
        for _, url_enum in self.REGIONS.items():
            if getattr(url_enum, "value", None) == value:
                return url_enum
        return value

    def _get_session_path(self):
        home = os.path.expanduser("~")
        app_dir = os.path.join(home, ".schugaa")
        if not os.path.exists(app_dir):
            os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, self.session_file)

    def _save_session(self):
        try:
            if not self.client.token:
                return

            data = {
                "token": self.client.token,
                "account_id_hash": self.client.account_id_hash,
                "region": self.region,
                "api_url": self.client.api_url.value if hasattr(self.client.api_url, "value") else self.client.api_url,
                "expiry": self.expiry 
            }
            path = self._get_session_path()
            with open(path, 'w') as f:
                json.dump(data, f)
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
        except Exception as e:
            print(f"Failed to save session: {e}")

    def _load_session(self):
        try:
            path = self._get_session_path()
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                    
                
                if data.get("expiry") and time.time() < (data["expiry"] - 600):
                    if data.get("token"):
                        self.client._set_token(data["token"])
                    if data.get("account_id_hash"):
                        self.client.account_id_hash = data["account_id_hash"]
                    
                    if data.get("api_url"):
                        self.client.api_url = self._coerce_api_url(data["api_url"])
                    if data.get("region"):
                        self.region = data["region"]
                        
                    self.expiry = data.get("expiry")
                    print("Session loaded from disk. Reusing token.")
        except Exception as e:
            print(f"Failed to load session: {e}")

    def login(self):
        max_retries = 3
        base_delay = 5 
        
        for attempt in range(max_retries):
            try:
                print(f"Logging in to {self.client.api_url} (Attempt {attempt+1})")
                self.client.authenticate()
                
                self.expiry = int(time.time()) + 3600 
                self._save_session()
                return True

            except RedirectError as e:
                print(f"Redirect received to: {e.region}")
                if e.region == self.client.api_url:
                     print("Redirect loop detected. Aborting.")
                     return False
                     
                self.client.api_url = e.region.value 
                for region_code, url_enum in self.REGIONS.items():
                    if url_enum == e.region:
                        self.region = region_code
                        break
                continue

            except Exception as e:
                print(f"Login error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(base_delay * (2 ** attempt))
                    
        return False

    def get_latest_glucose(self, retry=True):
        try:
            self.last_error = None
            if not self.client.token:
                if not self.login():
                   return None
            
            if time.time() > self.expiry:
                print("Token likely expired. Relogging...")
                if self.login():
                    if retry:
                        return self.get_latest_glucose(retry=False)
                return None

            try:
                patients = self.client.get_patients()
            except ValidationError as ve:
                print(f"Data format error (likely redirect): {ve}. Relogging...")
                if self.login():
                    if retry:
                        return self.get_latest_glucose(retry=False)
                return None
            
            
            if not patients:
                print("No patients found.")
                return None
            
            patient_id = patients[0].patient_id
            
            # Get graph data
            graph_response = self.client._get_graph_data_json(patient_id)
            
            # Extract connection status from raw response
            connection_status = None
            try:
                data_section = graph_response.get("data", {})
                connection_section = data_section.get("connection", {})
                connection_status = connection_section.get("status")
            except Exception:
                pass

            from pylibrelinkup.models.connection import GraphResponse
            try:
                graph_obj = GraphResponse.model_validate(graph_response)
            except ValidationError:
                # API returned None for glucoseMeasurement/glucoseItem (signal loss)
                # Return partial result with connection status
                sensor_activated, sensor_expires = self._extract_sensor_times(graph_response)
                result = {
                    "Value": None,
                    "TrendArrow": None,
                    "Timestamp": None,
                    "GraphData": [],
                    "ConnectionStatus": connection_status
                }
                if sensor_activated:
                    result["SensorActivated"] = sensor_activated
                if sensor_expires:
                    result["SensorExpires"] = sensor_expires
                return result

            
            latest = graph_obj.current
            history = graph_obj.history or []
            
            if not latest:
                # Return partial result with connection status even if no latest reading
                sensor_activated, sensor_expires = self._extract_sensor_times(graph_response)
                result = {
                    "Value": None,
                    "TrendArrow": None,
                    "Timestamp": None,
                    "GraphData": [],
                    "ConnectionStatus": connection_status
                }
                if sensor_activated:
                    result["SensorActivated"] = sensor_activated
                if sensor_expires:
                    result["SensorExpires"] = sensor_expires
                return result



            
            def fmt_ts(dt):
                return dt.strftime("%m/%d/%Y %I:%M:%S %p")

            gdata = []
            for h in history:
                gdata.append({
                    "Value": h.value,
                    "Timestamp": fmt_ts(h.timestamp),
                    "FactoryTimestamp": h.factory_timestamp.isoformat()
                })
            
            if latest:
                should_append = False
                if not gdata:
                    should_append = True
                else:
                    last_hist = history[-1]
                    if latest.timestamp > last_hist.timestamp:
                        should_append = True
                
                if should_append:
                    gdata.append({
                        "Value": latest.value,
                        "Timestamp": fmt_ts(latest.timestamp),
                        "FactoryTimestamp": latest.factory_timestamp.isoformat()
                    })
            
            sensor_activated = None
            sensor_expires = None
            try:
                sensor_activated, sensor_expires = self._extract_sensor_times(graph_response)
                if not sensor_expires:
                    sensor = graph_obj.data.connection.sensor
                    if sensor and sensor.a:
                        sensor_activated = self._normalize_timestamp(sensor.a) or sensor_activated
                        duration_seconds = self._infer_sensor_duration_seconds(sensor)
                        if sensor_activated and duration_seconds:
                            sensor_expires = sensor_activated + duration_seconds
            except Exception as e:
                print(f"Could not extract sensor data: {e}")
            
            result = {
                "Value": latest.value,
                "TrendArrow": latest.trend.value, 
                "Timestamp": fmt_ts(latest.timestamp),
                "GraphData": gdata,
                "ConnectionStatus": connection_status
            }

            
            if sensor_activated:
                result["SensorActivated"] = sensor_activated
            if sensor_expires:
                result["SensorExpires"] = sensor_expires
                
            return result


            

        except AuthenticationError:
            print("Authentication failed. Token likely expired. Relogging...")
            if self.login() and retry:
                return self.get_latest_glucose(retry=False)
            return None

        except Exception as e:
            print(f"Glucose fetch error: {e}")
            if "429" in str(e) or "Too Many Requests" in str(e):
                self.last_error = {
                    "type": "rate_limit",
                    "message": "Rate limit hit. Backing off and retrying."
                }
                return None
            
            # Catch other potential auth errors
            if "401" in str(e) or "403" in str(e):
                 if self.login() and retry:
                     return self.get_latest_glucose(retry=False)
            return None

