
import requests
import json
import time
import hashlib

class LibreClient:
    REGIONS = {
        "global": "https://api.libreview.io",
        "eu": "https://api-eu.libreview.io",
        "de": "https://api-de.libreview.io",
        "fr": "https://api-fr.libreview.io",
        "jp": "https://api-jp.libreview.io",
        "ap": "https://api-ap.libreview.io",
        "ae": "https://api-ae.libreview.io"
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
        self.base_url = self.REGIONS.get(region, self.REGIONS["global"])
        self.token = None
        self.patient_id = None
        self.account_id_hash = None
        self.expiry = 0

    def login(self):
        url = f"{self.base_url}/llu/auth/login"
        payload = {
            "email": self.email,
            "password": self.password
        }
        
        try:
            response = requests.post(url, headers=self.HEADERS, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if "data" in data and "authTicket" in data["data"]:
                self.token = data["data"]["authTicket"]["token"]
                self.expiry = int(time.time()) + data["data"]["authTicket"]["duration"]
                
                if "user" in data["data"] and "id" in data["data"]["user"]:
                    self.account_id_hash = hashlib.sha256(data["data"]["user"]["id"].encode('utf-8')).hexdigest()

                # After login, we might need to update the patient_id
                self._get_connection()
                return True
            elif "data" in data and data["data"].get("redirect") and data["data"].get("region"):
                new_region = data["data"]["region"]
                print(f"Redirect received to region: {new_region}")
                if new_region in self.REGIONS:
                    self.base_url = self.REGIONS[new_region]
                    return self.login()
                else:
                    print(f"Unknown region in redirect: {new_region}")
                    return False
            else:
                print(f"Login failed: {data}")
                return False
        except Exception as e:
            print(f"Login error: {e}")
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
            response.raise_for_status()
            data = response.json()
            
            if "data" in data and len(data["data"]) > 0:
                # Use the first active connection. 
                # Ideally we should look for one specifically but usually there's one primary.
                self.patient_id = data["data"][0]["patientId"]
        except Exception as e:
            print(f"Connection fetch error: {e}")
            if 'response' in locals():
                print(f"Error response text: {response.text}")

    def get_latest_glucose(self):
        if not self.token or time.time() > self.expiry:
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
            response.raise_for_status()
            data = response.json()
            
            if "data" in data and "connection" in data["data"]:
                conn = data["data"]["connection"]
                # graphData is a sibling of connection, inside data['data']
                gdata = data["data"].get("graphData")
                
                measurement = conn.get("glucoseMeasurement")
                if measurement:
                    latest_val = measurement.get("Value")
                    latest_ts = measurement.get("Timestamp")
                    
                    # Ensure graph data mimics the structure: {"Value": 100, "Timestamp": "..."}
                    # Check if latest timestamp is already in graph data to avoid duplicates
                    last_graph_ts = None
                    if gdata and len(gdata) > 0:
                        last_graph_ts = gdata[-1].get("Timestamp")
                        
                    if latest_val and latest_ts and latest_ts != last_graph_ts:
                         # Append latest point to graph so it's fresh
                         # Assuming FactoryTimestamp matches or is close enough, but using Timestamp for display
                         gdata.append({
                             "Value": latest_val,
                             "Timestamp": latest_ts,
                             "FactoryTimestamp": measurement.get("FactoryTimestamp")
                         })
                    
                    return {
                        "Value": latest_val,
                        "TrendArrow": measurement.get("TrendArrow"),
                        "Timestamp": latest_ts,
                        "GraphData": gdata or []
                    }
            return None
        except Exception as e:
            print(f"Glucose fetch error: {e}")
            return None
