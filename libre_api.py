
import requests
import json
import time
import hashlib

class LibreClient:
    REGIONS = {
        "global": "https://api.libreview.io",
        "eu": "https://api-eu.libreview.io",
        "eu2": "https://api-eu2.libreview.io",
        "de": "https://api-de.libreview.io",
        "fr": "https://api-fr.libreview.io",
        "jp": "https://api-jp.libreview.io",
        "ap": "https://api-ap.libreview.io",
        "au": "https://api-au.libreview.io",
        "ae": "https://api-ae.libreview.io",
        "us": "https://api-us.libreview.io",
        "ca": "https://api-ca.libreview.io",
        "la": "https://api-la.libreview.io",
        "gb": "https://api-eu.libreview.io",
        "uk": "https://api-eu.libreview.io",
        "ru": "https://api.libreview.io",
        "tw": "https://api-ap.libreview.io",
        "kr": "https://api-ap.libreview.io"
    }

    HEADERS = {
        "version": "4.16.0",
        "product": "llu.android",
        "culture": "en-us",
        "Content-Type": "application/json; charset=utf-8",
        # Assuming build number increments or just using the version number safely
        "User-Agent": "LibreLinkUp/4.16.0 (com.abbott.librelinkup; build:4.16.0; Android 14; 34) OkHttp/4.12.0",
        "Accept-Encoding": "gzip, deflate, br"
    }

    def __init__(self, email, password, region="eu"):
        self.email = email
        self.password = password
        self.region = region
        self.base_url = self.REGIONS.get(region, self.REGIONS["global"])
        self.token = None
        self.patient_id = None
        self.account_id_hash = None
        self.expiry = 0
        self.session_file = "session.json"
        self._load_session()

    def _get_session_path(self):
        import os
        # Same directory as script
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), self.session_file)

    def _save_session(self):
        try:
            data = {
                "token": self.token,
                "expiry": self.expiry,
                "patient_id": self.patient_id,
                "account_id_hash": self.account_id_hash,
                "base_url": self.base_url,
                "region": self.region
            }
            with open(self._get_session_path(), 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Failed to save session: {e}")

    def _load_session(self):
        try:
            import os
            path = self._get_session_path()
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                    
                # Basic validation
                if data.get("email") and data["email"] != self.email:
                     # Different user, don't load
                     return

                # Check expiry (give 10 mins buffer)
                if data.get("expiry") and time.time() < (data["expiry"] - 600):
                    self.token = data.get("token")
                    self.expiry = data.get("expiry")
                    self.patient_id = data.get("patient_id")
                    self.account_id_hash = data.get("account_id_hash")
                    # Restore region-specific URL if redirect happened
                    if data.get("base_url"):
                        self.base_url = data["base_url"]
                    if data.get("region"):
                        self.region = data["region"]
                    print("Session loaded from disk. Reusing token.")
        except Exception as e:
            print(f"Failed to load session: {e}")

    def login(self):
        import time
        # Exponential backoff parameters
        max_retries = 3
        base_delay = 5 # seconds
        
        for attempt in range(max_retries):
            try:
                # 1. Login
                url = f"{self.base_url}/llu/auth/login"
                payload = {
                    "email": self.email,
                    "password": self.password
                }
                
                print(f"Logging in to {self.base_url} (Attempt {attempt+1})")
                response = requests.post(url, headers=self.HEADERS, json=payload)
                
                if response.status_code == 429:
                    print("429 Too Many Requests. Backing off...")
                    # Wait longer if rate limited
                    time.sleep(base_delay * (attempt + 1) * 2)
                    continue
                
                # Check for other errors
                if response.status_code != 200:
                    # Check json for redirect before raising
                    try:
                        data = response.json()
                    except:
                         response.raise_for_status()
                else:
                    data = response.json()

                # 2. Success
                if "data" in data and "authTicket" in data["data"]:
                    self.token = data["data"]["authTicket"]["token"]
                    self.expiry = int(time.time()) + data["data"]["authTicket"]["duration"]
                    
                    if "user" in data["data"] and "id" in data["data"]["user"]:
                        self.account_id_hash = hashlib.sha256(data["data"]["user"]["id"].encode('utf-8')).hexdigest()
                    
                    # 3. Get Connection (Session)
                    self._get_connection()
                    
                    # 4. Save Session
                    self._save_session()
                    return True

                # 3. Redirect Handling
                elif "data" in data and data["data"].get("redirect") and data["data"].get("region"):
                    new_region = data["data"]["region"]
                    print(f"Redirect received to region: {new_region}")
                    if new_region in self.REGIONS:
                        self.base_url = self.REGIONS[new_region]
                        self.region = new_region # Update region
                        # Important: Don't recurse immediately in a tight loop without limits, 
                        # but in this case, we just updated base_url and will retry naturally in next loop or we can just retry once immediately?
                        # Better to just update and continue the loop if we haven't exhausted retries.
                        # But loop uses same URL? No, self.base_url is updated.
                        # Recursion is cleaner for flow, but loop handles backoff.
                        # Let's recurse ONCE for redirect to avoid loop issue
                        # actually, just continue loop? Loop variable URL is dynamic?
                        # url var is defined inside loop.
                        # We must reset attempt count or just allow it to use a retry?
                        # Let's just return self.login() which is recursive.
                        return self.login()
                    else:
                        print(f"Unknown region in redirect: {new_region}")
                        return False
                else:
                    print(f"Login failed: {data}")
                    return False

            except Exception as e:
                print(f"Login error: {e}")
                # Wait before retry
                if attempt < max_retries - 1:
                    time.sleep(base_delay * (2 ** attempt))
        
        return False

    def _get_connection(self):
        if not self.token:
            return
        
        url = f"{self.base_url}/llu/connections"
        headers = self.HEADERS.copy()
        headers["Authorization"] = f"Bearer {self.token}"
        if self.account_id_hash:
            headers["Account-Id"] = self.account_id_hash

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 401: # Token expired
                 self.token = None
                 return
            response.raise_for_status()
            data = response.json()
            
            if "data" in data and len(data["data"]) > 0:
                self.patient_id = data["data"][0]["patientId"]
                self._save_session()
        except Exception as e:
            print(f"Connection fetch error: {e}")

    def get_latest_glucose(self):
        # 1. Reuse Token logic
        if not self.token:
            # Try loading again? Already done in init.
            if not self.login():
                return None
        
        # Check expiry
        if time.time() > self.expiry:
            print("Token expired. Relogging...")
            if not self.login():
                return None

        if not self.patient_id:
            self._get_connection()
            if not self.patient_id:
                return None

        url = f"{self.base_url}/llu/connections/{self.patient_id}/graph"
        headers = self.HEADERS.copy()
        headers["Authorization"] = f"Bearer {self.token}"
        if self.account_id_hash:
            headers["Account-Id"] = self.account_id_hash

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 401:
                print("Token rejected (401). Relogging...")
                if self.login():
                    return self.get_latest_glucose() # Retry once
                return None
            
            # Simple 429 check here too
            if response.status_code == 429:
                print("429 Rate Limit on Data Fetch. Waiting...")
                time.sleep(10) # Simple wait
                return None # Don't retry immediately, skip this cycle

            response.raise_for_status()
            data = response.json()
            
            if "data" in data and "connection" in data["data"]:
                conn = data["data"]["connection"]
                gdata = data["data"].get("graphData", [])
                
                measurement = conn.get("glucoseMeasurement")
                if measurement:
                    latest_val = measurement.get("Value")
                    latest_ts = measurement.get("Timestamp")
                    
                    last_graph_ts = None
                    if gdata and len(gdata) > 0:
                        last_graph_ts = gdata[-1].get("Timestamp")
                        
                    if latest_val and latest_ts and latest_ts != last_graph_ts:
                         gdata.append({
                             "Value": latest_val,
                             "Timestamp": latest_ts,
                             "FactoryTimestamp": measurement.get("FactoryTimestamp")
                         })
                    
                    return {
                        "Value": latest_val,
                        "TrendArrow": measurement.get("TrendArrow"),
                        "Timestamp": latest_ts,
                        "GraphData": gdata
                    }
            return None
        except Exception as e:
            print(f"Glucose fetch error: {e}")
            return None
