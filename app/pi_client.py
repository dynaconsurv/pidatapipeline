"""
AVEVA PI Web API Client.
Communicates with OSIsoft / AVEVA PI Web API to browse AF hierarchy and retrieve current/recorded stream values.
Includes realistic plant simulation mode for offline development and testing.
"""
import math
import random
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests
import urllib3

# Suppress insecure SSL warnings if user disables verify_ssl
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from requests_negotiate_sspi import HttpNegotiateAuth
    HAS_SSPI = True
except ImportError:
    HAS_SSPI = False


class PIWebApiClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        raw_url = (config.get("url") or "").strip()
        if raw_url and not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            raw_url = f"https://{raw_url}"
        raw_url = raw_url.rstrip("/")
        # If user configured host without virtual directory (e.g. https://pi-srv.local), default to /piwebapi
        parsed = urllib.parse.urlparse(raw_url)
        if parsed.netloc and parsed.path in ("", "/"):
            raw_url = f"{raw_url}/piwebapi"
        self.url = raw_url

        self.auth_type = config.get("auth_type", "basic").lower()
        self.username = (config.get("username") or "").strip()
        self.password = config.get("password", "")
        self.bearer_token = (config.get("bearer_token") or "").strip()
        self.verify_ssl = config.get("verify_ssl", False)
        self.timeout = config.get("timeout_seconds", 10)
        self.simulation_mode = config.get("simulation_mode", False)

    def _parse_domain_and_user(self, username: str):
        """Extract domain and user from strings like DOMAIN\\user or user@domain.com."""
        if not username:
            return None, None
        u = username.strip()
        if "\\" in u:
            domain, user = u.split("\\", 1)
            return domain.strip(), user.strip()
        elif "@" in u:
            user, domain = u.split("@", 1)
            return domain.strip(), user.strip()
        return None, u

    def _get_negotiate_auth(self):
        """Build Windows Integrated (Kerberos / NTLM / SSPI) auth handler with delegation and host matching."""
        if not HAS_SSPI:
            return None
        parsed = urllib.parse.urlparse(self.url)
        host = parsed.hostname

        if not self.username and not self.password:
            # Single Sign-On using the current logged-in Windows user session (exactly like browser)
            return HttpNegotiateAuth(host=host, delegate=True)
        domain, user = self._parse_domain_and_user(self.username)
        return HttpNegotiateAuth(
            username=user,
            domain=domain,
            password=self.password or None,
            host=host,
            delegate=True
        )

    def _get_auth(self):
        if self.auth_type == "kerberos":
            auth = self._get_negotiate_auth()
            if auth:
                return auth
            elif self.username:
                return requests.auth.HTTPBasicAuth(self.username, self.password)
        elif self.auth_type == "basic":
            if self.username or self.password:
                return requests.auth.HTTPBasicAuth(self.username, self.password)
        return None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if self.auth_type == "bearer" and self.bearer_token:
            token = self.bearer_token
            if not token.lower().startswith("bearer "):
                headers["Authorization"] = f"Bearer {token}"
            else:
                headers["Authorization"] = token
        return headers

    def _get_session(self) -> requests.Session:
        """Create a configured requests.Session with connection pooling and headers."""
        s = requests.Session()
        s.verify = self.verify_ssl
        s.headers.update(self._get_headers())
        auth = self._get_auth()
        if auth:
            s.auth = auth
        return s

    def _get_candidate_base_urls(self) -> List[str]:
        """Generate candidate PI Web API base URLs to probe."""
        if not self.url:
            return []
        candidates = [self.url]
        if self.url.lower().endswith("/piwebapi"):
            # Also test root in case IIS or reverse proxy exposes PI Web API at the root
            root = self.url[:-9].rstrip("/")
            if root and root not in candidates:
                candidates.append(root)
        else:
            # If user entered base without /piwebapi, candidate with /piwebapi
            with_pi = f"{self.url}/piwebapi"
            if with_pi not in candidates:
                candidates.insert(0, with_pi)
        return candidates

    def test_connection(self) -> Dict[str, Any]:
        """
        Test connectivity and authentication against the PI Web API instance.
        Performs multi-probe discovery across candidate roots (/piwebapi, /system, /assetservers)
        to prevent false 404s caused by missing virtual directories or deprecated endpoints.
        """
        if self.simulation_mode:
            return {
                "success": True,
                "is_simulation": True,
                "status_code": 200,
                "latency_ms": 18.5,
                "message": "PI Simulation Mode Active (Simulated Plant Data Engine - Not connected to a physical PI server)",
                "details": {
                    "productTitle": "OSIsoft PI Web API (Simulation Engine)",
                    "serverVersion": "2023 SP1 (1.18.0.450)",
                    "afServer": self.config.get("af_server", "PISRV01"),
                    "afDatabase": self.config.get("af_database", "Plant_Operations"),
                    "note": "Turn off 'Simulation Mode' in Settings to connect to your live AVEVA PI Web API server URL."
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

        tested_endpoints = []
        last_latency = 0
        session = self._get_session()

        for base in self._get_candidate_base_urls():
            # Standard PI Web API discovery endpoints:
            # 1. Base URL itself (returns PI Web API landing document with links)
            # 2. Base URL with trailing slash (required by some IIS configurations)
            # 3. /system (System status and version metadata)
            # 4. /assetservers (AF Asset Servers list)
            probes = [base, f"{base}/", f"{base}/system", f"{base}/assetservers"]
            unique_probes = []
            for p in probes:
                if p not in unique_probes:
                    unique_probes.append(p)

            for probe_url in unique_probes:
                tested_endpoints.append(probe_url)
                start_time = time.time()
                try:
                    resp = session.get(
                        probe_url,
                        timeout=self.timeout
                    )
                    latency = round((time.time() - start_time) * 1000, 2)
                    last_latency = latency

                    if resp.status_code in (200, 201):
                        self.url = base  # Auto-normalize base URL to working root
                        try:
                            data = resp.json()
                        except Exception:
                            data = {"raw": resp.text[:200]}
                        return {
                            "success": True,
                            "status_code": resp.status_code,
                            "latency_ms": latency,
                            "normalized_url": base,
                            "endpoint_tested": probe_url,
                            "message": "Successfully connected to AVEVA PI Web API",
                            "details": data
                        }
                    elif resp.status_code in (401, 403):
                        # Server and endpoint exist, but authentication failed
                        self.url = base
                        www_auth = resp.headers.get("WWW-Authenticate", "")
                        
                        # Extract server error message (JSON or text)
                        server_msg = ""
                        try:
                            json_body = resp.json()
                            if isinstance(json_body, dict):
                                server_msg = json_body.get("Message") or json_body.get("message") or ""
                        except Exception:
                            pass
                        
                        if not server_msg and resp.text:
                            clean_text = re.sub(r'<[^>]+>', ' ', resp.text[:400]).strip()
                            clean_text = " ".join(clean_text.split())
                            if clean_text:
                                server_msg = clean_text[:250]

                        # Detect server-supported authentication methods from WWW-Authenticate
                        schemes_lower = www_auth.lower()
                        server_supports_negotiate = "negotiate" in schemes_lower or "kerberos" in schemes_lower
                        server_supports_ntlm = "ntlm" in schemes_lower
                        server_supports_basic = "basic" in schemes_lower

                        server_methods = []
                        if server_supports_negotiate:
                            server_methods.append("Kerberos / Negotiate")
                        if server_supports_ntlm:
                            server_methods.append("NTLM")
                        if server_supports_basic:
                            server_methods.append("Basic Authentication")
                        
                        server_methods_str = ", ".join(server_methods) if server_methods else (www_auth or "Unspecified by server")

                        # AUTO-TRIAL: Test alternative authentication scheme if supported by server!
                        alt_auth_success = None
                        alt_method_name = ""

                        # Probe 1: If user configured Basic, but server supports Negotiate, test Kerberos/SSPI probe
                        if self.auth_type == "basic" and (server_supports_negotiate or server_supports_ntlm) and HAS_SSPI:
                            try:
                                alt_auth = self._get_negotiate_auth()
                                alt_resp = requests.get(
                                    probe_url,
                                    auth=alt_auth,
                                    headers=self._get_headers(),
                                    verify=self.verify_ssl,
                                    timeout=self.timeout
                                )
                                if alt_resp.status_code in (200, 201):
                                    alt_auth_success = "kerberos"
                                    alt_method_name = "Windows Integrated (Kerberos/NTLM)"
                            except Exception:
                                pass

                        # Probe 2: If user configured Kerberos, but server supports Basic, test Basic probe if username & password provided
                        elif self.auth_type == "kerberos" and server_supports_basic and self.username and self.password:
                            try:
                                alt_auth = requests.auth.HTTPBasicAuth(self.username, self.password)
                                alt_resp = requests.get(
                                    probe_url,
                                    auth=alt_auth,
                                    headers=self._get_headers(),
                                    verify=self.verify_ssl,
                                    timeout=self.timeout
                                )
                                if alt_resp.status_code in (200, 201):
                                    alt_auth_success = "basic"
                                    alt_method_name = "Basic Authentication"
                            except Exception:
                                pass

                        # Build tailored diagnostic message
                        domain, user = self._parse_domain_and_user(self.username)
                        has_domain = bool(domain)

                        err_lines = [
                            f"HTTP {resp.status_code} Unauthorized / Access Denied at {probe_url}.",
                            f"• Server Authentication Methods Accepted: {server_methods_str}",
                            f"• Current Client Configuration: Method='{self.auth_type.upper()}', User='{self.username or '(Current Windows User)'}'"
                        ]

                        if server_msg:
                            err_lines.append(f"• Server Message: \"{server_msg}\"")

                        err_lines.append("\nDiagnostic & Recommended Actions:")

                        if alt_auth_success:
                            err_lines.append(
                                f"★ AUTOMATIC DETECTION: While '{self.auth_type.upper()}' was rejected by the server, "
                                f"'{alt_method_name}' SUCCEEDED!\n"
                                f"→ Recommendation: Switch 'Authentication Method' to '{alt_method_name}' and click 'Save Settings'."
                            )
                        else:
                            if self.auth_type == "basic":
                                if not has_domain and self.username:
                                    err_lines.append(
                                        f"1. Domain Qualification (Most Common): In Windows IIS / PI Web API, Basic Auth requires the domain. "
                                        f"Update your username from '{self.username}' to 'YOUR_DOMAIN\\{self.username}' or '{self.username}@yourdomain.com' "
                                        f"(or '.\\{self.username}' for a local server account)."
                                    )
                                if not self.password:
                                    err_lines.append("2. Password: Ensure the password field is entered.")
                                if not self.url.lower().startswith("https://"):
                                    err_lines.append("3. HTTPS Required: PI Web API automatically blocks Basic Authentication over unencrypted http://. Use https://.")
                                if server_supports_negotiate or server_supports_ntlm:
                                    err_lines.append(
                                        "4. Try Windows Integrated Auth: The server accepts Kerberos/NTLM. "
                                        "Switch 'Authentication Method' to 'Windows Integrated (Kerberos/NTLM)'. "
                                        "If your PC is on the domain, you can leave Username and Password blank to use Windows Single Sign-On (SSO)."
                                    )
                            elif self.auth_type == "kerberos":
                                if not HAS_SSPI:
                                    err_lines.append("1. Python SSPI: 'requests-negotiate-sspi' is required on Windows for Kerberos/NTLM authentication.")
                                err_lines.append(
                                    "1. Windows SSO: If logged in as a domain user with PI permissions, leave Username and Password blank in Settings."
                                )
                                err_lines.append(
                                    "2. Explicit Credentials: If typing a username, ensure domain format 'DOMAIN\\username'."
                                )
                                if server_supports_basic:
                                    err_lines.append(
                                        "3. Try Basic Auth: The server also accepts Basic Authentication. "
                                        "Switch 'Authentication Method' to 'Basic Authentication' with 'DOMAIN\\username'."
                                    )

                            if server_msg and ("denied" in server_msg.lower() or "identity" in server_msg.lower()):
                                err_lines.append(
                                    "\nPI AF Identity Mapping:\n"
                                    "The Windows credentials reached the server, but PI Web API reported 'Authorization denied'. "
                                    "Confirm in PI System Management Tools (SMT) or PI System Explorer that this Windows account is mapped "
                                    "to a PI Identity or PI AF Identity with Read permissions on the AF Database."
                                )

                        return {
                            "success": False,
                            "status_code": resp.status_code,
                            "latency_ms": latency,
                            "normalized_url": base,
                            "endpoint_tested": probe_url,
                            "www_authenticate": www_auth,
                            "server_message": server_msg,
                            "recommended_auth": alt_auth_success,
                            "message": f"PI Web API reachable, but authentication failed (HTTP {resp.status_code})",
                            "error": "\n".join(err_lines)
                        }
                    elif resp.status_code != 404:
                        # Non-404 error (e.g. 500 Internal Server Error, 503 Service Unavailable)
                        return {
                            "success": False,
                            "status_code": resp.status_code,
                            "latency_ms": latency,
                            "normalized_url": base,
                            "endpoint_tested": probe_url,
                            "message": f"PI Web API responded with HTTP {resp.status_code}",
                            "error": resp.text[:500]
                        }
                    # If 404, continue to next probe/candidate
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

        # If all candidates and probes returned 404
        endpoints_str = "\n".join(f"  • {ep}" for ep in tested_endpoints)
        return {
            "success": False,
            "status_code": 404,
            "latency_ms": last_latency,
            "message": "PI Web API responded with HTTP 404 (Not Found)",
            "error": (
                f"All probed endpoints returned HTTP 404:\n{endpoints_str}\n\n"
                "Troubleshooting Checklist:\n"
                "1. Virtual Directory: OSIsoft / AVEVA PI Web API is standardly hosted under '/piwebapi'. "
                "Ensure your URL is formatted as: https://your-server/piwebapi\n"
                "2. Service Status: Ensure the 'PI Web API' service is running on the host server.\n"
                "3. IIS Bindings: Confirm PI Web API website is bound to port 443 (or custom port like 8443) and started.\n"
                "4. Browser Verification: Open https://your-server/piwebapi directly in a web browser on the same network to verify the landing JSON."
            )
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
        session = self._get_session()
        start_t = time.time()
        try:
            # If web_id is present, query stream directly
            if web_id:
                endpoint = f"{self.url}/streams/{web_id}/value"
            elif full_path:
                # Resolve WebId via path
                encoded_path = urllib.parse.quote(full_path)
                lookup_url = f"{self.url}/attributes?path={encoded_path}"
                lookup_resp = session.get(
                    lookup_url,
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

            val_resp = session.get(
                endpoint,
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

            session = self._get_session()
            resp = session.get(
                endpoint,
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
