
import json
import time
import os
from pylibrelinkup.pylibrelinkup import PyLibreLinkUp
from pylibrelinkup.api_url import APIUrl
from pylibrelinkup.exceptions import AuthenticationError, RedirectError
from pydantic import ValidationError

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
        # Maps for missing ones
        "gb": APIUrl.EU,
        "uk": APIUrl.EU,
        "ru": APIUrl.US, # RU often maps to global/US or needs specific handling, defaulting to US for now
        "tw": APIUrl.AP,
        "kr": APIUrl.AP
    }

    def __init__(self, email, password, region="eu"):
        self.email = email
        self.password = password
        self.region = region
        self.api_url = self.REGIONS.get(region, APIUrl.US)
        
        # Monkey-patch HEADERS to include robust User-Agent
        import pylibrelinkup.pylibrelinkup
        pylibrelinkup.pylibrelinkup.HEADERS["User-Agent"] = "LibreLinkUp/4.16.0 (com.abbott.librelinkup; build:4.16.0; Android 14; 34) OkHttp/4.12.0"
        
        self.client = PyLibreLinkUp(email, password, api_url=self.api_url)
        
        self.expiry = 0
        self.session_file = "session.json"
        
        # Load session to hydrate client
        self._load_session()

    def _get_session_path(self):
        # Use ~/.schugaa/session.json for persistence
        home = os.path.expanduser("~")
        app_dir = os.path.join(home, ".schugaa")
        if not os.path.exists(app_dir):
            os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, self.session_file)

    def _save_session(self):
        try:
            # PyLibreLinkUp doesn't expose expiry publicly in a clean way usually, 
            # but we can assume successful login gives us a valid token.
            # We'll just save what we have.
            if not self.client.token:
                return

            data = {
                "token": self.client.token,
                "account_id_hash": self.client.account_id_hash,
                "region": self.region,
                # Save the string value of the enum for restoration
                "api_url": self.client.api_url, 
                "expiry": self.expiry # Managed manually
            }
            with open(self._get_session_path(), 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Failed to save session: {e}")

    def _load_session(self):
        try:
            path = self._get_session_path()
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                    
                # Basic validation (we can't easily validate email owner of token without storing it)
                # But we can try to reuse.
                
                # Check expiry 
                if data.get("expiry") and time.time() < (data["expiry"] - 600):
                    if data.get("token"):
                        self.client._set_token(data["token"])
                    if data.get("account_id_hash"):
                        self.client.account_id_hash = data["account_id_hash"]
                    
                    if data.get("api_url"):
                        self.client.api_url = data["api_url"]
                    if data.get("region"):
                        self.region = data["region"]
                        
                    self.expiry = data.get("expiry")
                    print("Session loaded from disk. Reusing token.")
        except Exception as e:
            print(f"Failed to load session: {e}")

    def login(self):
        # Exponential backoff parameters
        max_retries = 3
        base_delay = 5 
        
        for attempt in range(max_retries):
            try:
                print(f"Logging in to {self.client.api_url} (Attempt {attempt+1})")
                self.client.authenticate()
                
                # Success
                # Estimate expiry (usually 1 hour?) - Library doesn't expose it in response object easy access
                # But we know it works. Let's set a safe default or checking if we can get it.
                # The library doesn't facilitate expiry extraction easily without modifying it.
                # We will assume 1 hour for now to avoid re-login loops.
                self.expiry = int(time.time()) + 3600 
                self._save_session()
                return True

            except RedirectError as e:
                print(f"Redirect received to: {e.region}")
                if e.region == self.client.api_url:
                     print("Redirect loop detected. Aborting.")
                     return False
                     
                self.client.api_url = e.region.value # Must be string value for PyLibreLinkUp
                # Reverse match APIUrl to region string for persistence
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

    def get_latest_glucose(self):
        try:
            # Ensure logged in
            if not self.client.token:
                if not self.login():
                   return None
            
            # Check expiry
            if time.time() > self.expiry:
                print("Token likely expired. Relogging...")
                if not self.login():
                    return None

            # Get Patient (first one)
            try:
                patients = self.client.get_patients()
            except ValidationError as ve:
                print(f"Data format error (likely redirect): {ve}. Relogging...")
                # The session token is likely valid but for the wrong region (pylibrelinkup doesn't auto-redirect on get_patients)
                # We need to force a full login flow which handles redirects
                if self.login():
                    patients = self.client.get_patients()
                else:
                    return None
            
            if not patients:
                print("No patients found.")
                return None
            
            patient_id = patients[0].patient_id
            
            # Get Data
            # Note: Library returns objects, we need to convert to dict structure main.py expects
            
            # 1. Latest
            latest = self.client.latest(patient_id)
            # 2. Graph
            history = self.client.graph(patient_id)
            
            if not latest:
                return None

            # Formatting
            # Timestamp format expected: "MM/DD/YYYY HH:MM:SS AM/PM"
            # PyLibreLinkUp dates are datetime objects
            
            def fmt_ts(dt):
                return dt.strftime("%m/%d/%Y %I:%M:%S %p")

            # Graph Data
            gdata = []
            for h in history:
                gdata.append({
                    "Value": h.value,
                    "Timestamp": fmt_ts(h.timestamp),
                    "FactoryTimestamp": h.factory_timestamp.isoformat()
                })
            
            # Append latest if newer than last graph point
            if latest:
                should_append = False
                if not gdata:
                    should_append = True
                else:
                    # Compare timestamps (objects)
                    last_hist = history[-1]
                    if latest.timestamp > last_hist.timestamp:
                        should_append = True
                
                if should_append:
                    gdata.append({
                        "Value": latest.value,
                        "Timestamp": fmt_ts(latest.timestamp),
                        "FactoryTimestamp": latest.factory_timestamp.isoformat()
                    })
            
            # Latest
            return {
                "Value": latest.value,
                "TrendArrow": latest.trend.value, # Int value for arrow
                "Timestamp": fmt_ts(latest.timestamp),
                "GraphData": gdata
            }
            
        except Exception as e:
            print(f"Glucose fetch error: {e}")
            # Try once to re-login if error might be auth related
            if "401" in str(e) or "403" in str(e):
                 if self.login():
                     # Retry logic could go here but let's avoid infinite recursion complexity for now
                     pass
            return None


