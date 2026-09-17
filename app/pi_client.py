"""
AVEVA PI Web API Client.
Communicates with OSIsoft / AVEVA PI Web API to browse AF hierarchy and retrieve current/recorded stream values.
Includes realistic plant simulation mode for offline development and testing.
"""
import math
import random
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests
import urllib3

# Suppress insecure SSL warnings if user disables verify_ssl
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class PIWebApiClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.url = (config.get("url") or "").rstrip("/")
        self.auth_type = config.get("auth_type", "basic").lower()
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.bearer_token = config.get("bearer_token", "")
        self.verify_ssl = config.get("verify_ssl", False)
        self.timeout = config.get("timeout_seconds", 10)
        self.simulation_mode = config.get("simulation_mode", False)

    def _get_auth(self):
        if self.auth_type == "basic" and self.username:
            return requests.auth.HTTPBasicAuth(self.username, self.password)
        return None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "X-Requested-With": "PIWebApiClient"
        }
        if self.auth_type == "bearer" and self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def test_connection(self) -> Dict[str, Any]:
        """Test connectivity and authentication against the PI Web API instance."""
        if self.simulation_mode:
            return {
                "success": True,
                "status_code": 200,
                "latency_ms": 18.5,
                "message": "Connected to AVEVA PI Web API (Simulation Engine Active)",
                "details": {
                    "productTitle": "OSIsoft PI Web API (Simulated)",
                    "serverVersion": "2023 SP1 (1.18.0.450)",
                    "afServer": self.config.get("af_server", "PISRV01"),
                    "afDatabase": self.config.get("af_database", "Plant_Operations"),
                    "simulation": True
                }
            }

        if not self.url or not self.url.startswith("http"):
            return {
                "success": False,
                "status_code": None,
                "latency_ms": 0,
                "message": "Invalid PI Web API URL configured",
                "error": "URL must begin with http:// or https://"
            }

        start_time = time.time()
        test_endpoint = f"{self.url}/system/landing"
        try:
            resp = requests.get(
                test_endpoint,
                auth=self._get_auth(),
                headers=self._get_headers(),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            latency = round((time.time() - start_time) * 1000, 2)
            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text[:200]}
                return {
                    "success": True,
                    "status_code": resp.status_code,
                    "latency_ms": latency,
                    "message": "Successfully connected to AVEVA PI Web API",
                    "details": data
                }
            else:
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "latency_ms": latency,
                    "message": f"PI Web API responded with HTTP {resp.status_code}",
                    "error": resp.text[:500]
                }
        except requests.exceptions.SSLError as e:
            return {
                "success": False,
                "status_code": None,
                "latency_ms": round((time.time() - start_time) * 1000, 2),
                "message": "SSL Certificate verification failed",
                "error": str(e) + " (Tip: Turn off 'Verify SSL' in Settings if PI Web API uses a self-signed plant certificate)"
            }
        except requests.exceptions.ConnectionError as e:
            return {
                "success": False,
                "status_code": None,
                "latency_ms": round((time.time() - start_time) * 1000, 2),
                "message": "Unable to connect to PI Web API host",
                "error": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "latency_ms": round((time.time() - start_time) * 1000, 2),
                "message": "PI Web API connection test failed",
                "error": str(e)
            }

    def fetch_attribute_value(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch current value for a single attribute mapping."""
        attr_name = mapping.get("attribute_name", "Unknown Attribute")
        full_path = mapping.get("full_path", "")
        web_id = mapping.get("web_id", "")
        uom = mapping.get("uom", "")

        if self.simulation_mode:
            return self._simulate_attribute_value(mapping)

        # Live PI Web API query
        start_t = time.time()
        try:
            # If web_id is present, query stream directly
            if web_id:
                endpoint = f"{self.url}/streams/{web_id}/value"
            elif full_path:
                # Resolve WebId via path
                encoded_path = urllib.parse.quote(full_path)
                lookup_url = f"{self.url}/attributes?path={encoded_path}"
                lookup_resp = requests.get(
                    lookup_url,
                    auth=self._get_auth(),
                    headers=self._get_headers(),
                    verify=self.verify_ssl,
                    timeout=self.timeout
                )
                if lookup_resp.status_code != 200:
                    return {
                        "attribute_name": attr_name,
                        "full_path": full_path,
                        "success": False,
                        "value": None,
                        "uom": uom,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "quality": "Bad",
                        "error": f"Path lookup failed (HTTP {lookup_resp.status_code}): {lookup_resp.text[:200]}"
                    }
                web_id = lookup_resp.json().get("WebId")
                endpoint = f"{self.url}/streams/{web_id}/value"
            else:
                return {
                    "attribute_name": attr_name,
                    "full_path": full_path,
                    "success": False,
                    "value": None,
                    "uom": uom,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "quality": "ConfigurationError",
                    "error": "Neither WebId nor Full AF Path provided in mapping"
                }

            val_resp = requests.get(
                endpoint,
                auth=self._get_auth(),
                headers=self._get_headers(),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            if val_resp.status_code == 200:
                body = val_resp.json()
                raw_val = body.get("Value")
                pi_time = body.get("Timestamp", datetime.now(timezone.utc).isoformat())
                good = body.get("Good", True)

                # Process value if numerical
                transformed_val = self._apply_transformation(raw_val, mapping)

                return {
                    "attribute_name": attr_name,
                    "full_path": full_path,
                    "web_id": web_id,
                    "success": True,
                    "raw_value": raw_val,
                    "value": transformed_val,
                    "uom": uom,
                    "timestamp": pi_time,
                    "quality": "Good" if good else "Questionable",
                    "status": "Online",
                    "latency_ms": round((time.time() - start_t) * 1000, 2),
                    "error": None
                }
            else:
                return {
                    "attribute_name": attr_name,
                    "full_path": full_path,
                    "success": False,
                    "value": None,
                    "uom": uom,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "quality": "Bad",
                    "status": f"HTTP {val_resp.status_code}",
                    "error": val_resp.text[:300]
                }
        except Exception as ex:
            return {
                "attribute_name": attr_name,
                "full_path": full_path,
                "success": False,
                "value": None,
                "uom": uom,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "quality": "Bad",
                "status": "Error",
                "error": str(ex)
            }

    def _apply_transformation(self, raw_val: Any, mapping: Dict[str, Any]) -> Any:
        try:
            scale = float(mapping.get("scale_factor", 1.0))
            decimals = int(mapping.get("round_decimals", 2))
            if isinstance(raw_val, (int, float)):
                v = raw_val * scale
                return round(v, decimals)
            # If string representation of number
            if isinstance(raw_val, str):
                try:
                    v = float(raw_val) * scale
                    return round(v, decimals)
                except ValueError:
                    return raw_val
            return raw_val
        except Exception:
            return raw_val

    def _simulate_attribute_value(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        """Generate realistic dynamic industrial plant values."""
        attr_name = mapping.get("attribute_name", "").lower()
        now_ts = datetime.now(timezone.utc).isoformat()
        t = time.time() / 10.0

        if "temp" in attr_name:
            # Base 540 °C with gentle sinusoidal drift and noise
            val = 540.0 + (5.0 * math.sin(t)) + random.uniform(-0.8, 0.8)
            uom = mapping.get("uom") or "deg C"
        elif "press" in attr_name:
            # Steam pressure ~165 bar
            val = 165.0 + (2.0 * math.cos(t * 0.8)) + random.uniform(-0.3, 0.3)
            uom = mapping.get("uom") or "bar"
        elif "flow" in attr_name:
            # Feedwater flow ~1250 m3/h
            val = 1250.0 + (25.0 * math.sin(t * 1.2)) + random.uniform(-4.0, 4.0)
            uom = mapping.get("uom") or "m3/h"
        elif "power" in attr_name:
            # Generator power ~320 MW
            val = 320.0 + (8.0 * math.cos(t * 0.5)) + random.uniform(-1.2, 1.2)
            uom = mapping.get("uom") or "MW"
        elif "vibe" in attr_name or "vibration" in attr_name:
            # Vibration ~2.35 mm/s RMS
            val = 2.35 + (0.3 * math.sin(t * 2.0)) + random.uniform(-0.08, 0.08)
            uom = mapping.get("uom") or "mm/s"
        elif "status" in attr_name:
            val = "RUNNING"
            uom = "status"
        else:
            val = 100.0 + (10.0 * math.sin(t)) + random.uniform(-2.0, 2.0)
            uom = mapping.get("uom") or ""

        transformed = self._apply_transformation(val, mapping) if isinstance(val, (int, float)) else val

        return {
            "attribute_name": mapping.get("attribute_name", "Simulated Tag"),
            "full_path": mapping.get("full_path", ""),
            "web_id": mapping.get("web_id", "SIM_WEBID"),
            "success": True,
            "raw_value": round(val, 3) if isinstance(val, float) else val,
            "value": transformed,
            "uom": uom,
            "timestamp": now_ts,
            "quality": "Good",
            "status": "Online (Simulated)",
            "latency_ms": round(random.uniform(12.0, 28.0), 1),
            "error": None
        }

    def browse_af_hierarchy(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Browse AF databases, elements, and attributes."""
        if self.simulation_mode:
            return self._mock_af_hierarchy(path)

        # Real AF browsing via PI Web API
        try:
            if not path or path == "/":
                endpoint = f"{self.url}/assetservers"
            else:
                encoded = urllib.parse.quote(path)
                endpoint = f"{self.url}/elements?path={encoded}"

            resp = requests.get(
                endpoint,
                auth=self._get_auth(),
                headers=self._get_headers(),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("Items", [])
                return items
            return []
        except Exception:
            return []

    def _mock_af_hierarchy(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Provides simulated AF tree nodes for exploration."""
        server = self.config.get("af_server", "PISRV01")
        database = self.config.get("af_database", "Plant_Operations")

        if not path or path in ("/", ""):
            return [
                {"name": server, "type": "AssetServer", "path": f"\\\\{server}", "hasChildren": True}
            ]
        if path == f"\\\\{server}":
            return [
                {"name": database, "type": "AssetDatabase", "path": f"\\\\{server}\\{database}", "hasChildren": True},
                {"name": "Fleet_Analytics", "type": "AssetDatabase", "path": f"\\\\{server}\\Fleet_Analytics", "hasChildren": True}
            ]
        if path == f"\\\\{server}\\{database}":
            return [
                {"name": "Unit 1", "type": "Element", "path": f"\\\\{server}\\{database}\\Unit 1", "hasChildren": True},
                {"name": "Unit 2", "type": "Element", "path": f"\\\\{server}\\{database}\\Unit 2", "hasChildren": True},
                {"name": "Utilities", "type": "Element", "path": f"\\\\{server}\\{database}\\Utilities", "hasChildren": True}
            ]
        if "Unit 1" in path:
            return [
                {"name": "Boiler-101", "type": "Element", "path": f"{path}\\Boiler-101", "hasChildren": True},
                {"name": "Turbine-TG01", "type": "Element", "path": f"{path}\\Turbine-TG01", "hasChildren": True},
                {"name": "Gen-01", "type": "Element", "path": f"{path}\\Gen-01", "hasChildren": True}
            ]
        if "Boiler-101" in path:
            return [
                {"name": "Steam Temperature", "type": "Attribute", "path": f"{path}|Steam Temperature", "hasChildren": False, "uom": "deg C", "type_desc": "Single"},
                {"name": "Steam Pressure", "type": "Attribute", "path": f"{path}|Steam Pressure", "hasChildren": False, "uom": "bar", "type_desc": "Single"},
                {"name": "Flue Gas O2", "type": "Attribute", "path": f"{path}|Flue Gas O2", "hasChildren": False, "uom": "%", "type_desc": "Single"},
                {"name": "Fuel Gas Flow", "type": "Attribute", "path": f"{path}|Fuel Gas Flow", "hasChildren": False, "uom": "Nm3/h", "type_desc": "Single"}
            ]
        if "Turbine-TG01" in path:
            return [
                {"name": "Feedwater Flow", "type": "Attribute", "path": f"{path}|Feedwater Flow", "hasChildren": False, "uom": "m3/h", "type_desc": "Single"},
                {"name": "Inlet Steam Enthalpy", "type": "Attribute", "path": f"{path}|Inlet Steam Enthalpy", "hasChildren": False, "uom": "kJ/kg", "type_desc": "Single"},
                {"name": "Shaft Speed RPM", "type": "Attribute", "path": f"{path}|Shaft Speed RPM", "hasChildren": False, "uom": "rpm", "type_desc": "Single"}
            ]
        if "Gen-01" in path:
            return [
                {"name": "Active Power", "type": "Attribute", "path": f"{path}|Active Power", "hasChildren": False, "uom": "MW", "type_desc": "Single"},
                {"name": "Reactive Power", "type": "Attribute", "path": f"{path}|Reactive Power", "hasChildren": False, "uom": "MVAR", "type_desc": "Single"},
                {"name": "Stator Temperature", "type": "Attribute", "path": f"{path}|Stator Temperature", "hasChildren": False, "uom": "deg C", "type_desc": "Single"}
            ]
        if "Utilities" in path:
            return [
                {"name": "Pumps", "type": "Element", "path": f"{path}\\Pumps", "hasChildren": True},
                {"name": "Compressors", "type": "Element", "path": f"{path}\\Compressors", "hasChildren": True}
            ]
        if "Pumps" in path:
            return [
                {"name": "Pump-2A", "type": "Element", "path": f"{path}\\Pump-2A", "hasChildren": True},
                {"name": "Pump-2B", "type": "Element", "path": f"{path}\\Pump-2B", "hasChildren": True}
            ]
        if "Pump-2A" in path:
            return [
                {"name": "Vibration Overall", "type": "Attribute", "path": f"{path}|Vibration Overall", "hasChildren": False, "uom": "mm/s", "type_desc": "Single"},
                {"name": "Discharge Pressure", "type": "Attribute", "path": f"{path}|Discharge Pressure", "hasChildren": False, "uom": "bar", "type_desc": "Single"},
                {"name": "Motor Current", "type": "Attribute", "path": f"{path}|Motor Current", "hasChildren": False, "uom": "A", "type_desc": "Single"}
            ]

        return []
