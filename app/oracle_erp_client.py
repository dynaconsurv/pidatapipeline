"""
Oracle ERP Cloud REST API Client.
Implements:
1. OAuth 2.0 Client Credentials Grant with Oracle Identity Cloud Service (IDCS) / IAM.
   - Automatic token acquisition, caching, and renewal.
2. Basic Authentication (RFC 7617) as supported by Oracle Fusion Applications.
3. Bearer Token / API Key passthrough.
4. "Pending connection setup" state handling when requirements/credentials are not yet provided.
5. Dry-run / Validation mode to inspect generated payloads before transmission.
"""
import base64
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
import requests

TZ_UTC8 = timezone(timedelta(hours=8))


def format_ords_timestamp(ts: Any, allow_empty: bool = False, already_utc8: bool = False) -> Optional[str]:
    """
    Format timestamp to ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ) in UTC+8 local clock time.
    Converts incoming UTC timestamps (ending in Z / +00:00 or UTC datetime objects) to UTC+8
    so that e.g. 7:00 AM local time (sent as 23:00:00Z UTC by PI AF) stays 07:00:00Z.
    Strips fractional microseconds which cause Oracle DATE column parsing issues.
    If allow_empty is True, None or empty/null values return None.
    """
    if ts is None:
        return None if allow_empty else datetime.now(TZ_UTC8).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, datetime):
        if ts.tzinfo is not None:
            ts = ts.astimezone(TZ_UTC8)
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, (int, float)):
        val = float(ts)
        if 20000 <= val <= 100000:
            excel_epoch = datetime(1899, 12, 30, tzinfo=TZ_UTC8)
            sec = round(val * 86400)
            return (excel_epoch + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if val > 1e11:
            val = val / 1000.0
        return datetime.fromtimestamp(val, tz=TZ_UTC8).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, str):
        s = ts.strip().strip('"').strip("'")
        if not s or s.lower() in ("null", "none"):
            return None if allow_empty else datetime.now(TZ_UTC8).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            fnum = float(s)
            if 20000 <= fnum <= 100000:
                excel_epoch = datetime(1899, 12, 30, tzinfo=TZ_UTC8)
                sec = round(fnum * 86400)
                return (excel_epoch + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
            if s.isdigit() and len(s) >= 10:
                if fnum > 1e11:
                    fnum = fnum / 1000.0
                return datetime.fromtimestamp(fnum, tz=TZ_UTC8).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
        try:
            clean_s = s.replace("Z", "+00:00")
            if "." in clean_s:
                parts = clean_s.split(".", 1)
                date_time_part = parts[0]
                rest = parts[1]
                tz_idx = -1
                for idx, ch in enumerate(rest):
                    if ch in ("+", "-"):
                        tz_idx = idx
                        break
                if tz_idx != -1:
                    frac = rest[:tz_idx][:6]
                    tz = rest[tz_idx:]
                    clean_s = f"{date_time_part}.{frac}{tz}"
                else:
                    clean_s = f"{date_time_part}.{rest[:6]}"
            dt = datetime.fromisoformat(clean_s)
            if dt.tzinfo is not None and not already_utc8:
                dt = dt.astimezone(TZ_UTC8)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
                "%m/%d/%Y %H:%M:%S",
                "%d-%b-%Y %H:%M:%S",
                "%d-%B-%Y %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    dt = datetime.strptime(s.split(".")[0], fmt)
                    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    continue

            if "." in s:
                base = s.split(".")[0]
                if " " in base and "T" not in base:
                    base = base.replace(" ", "T")
                return f"{base}Z" if not base.endswith("Z") else base
            if " " in s and "T" not in s:
                s = s.replace(" ", "T")
            if not s.endswith("Z") and ("+" not in s and "-" not in s[10:]):
                return f"{s}Z"
            return s
    return str(ts)


def sanitize_endpoint_url(url: Optional[str]) -> str:
    """
    Sanitizes an endpoint URL to remove duplicate consecutive path segments
    (e.g. /Final_Discharge_Effluent/Final_Discharge_Effluent/) and normalize slashes.
    """
    if not url or not isinstance(url, str):
        return ""
    u = str(url).strip().strip('"').strip("'")
    if not u:
        return ""
    if not (u.startswith("http://") or u.startswith("https://")):
        return u
    try:
        import urllib.parse
        parsed = urllib.parse.urlsplit(u)
        raw_segments = [s for s in parsed.path.split("/") if s]
        deduped = []
        for s in raw_segments:
            if deduped and s.lower() == deduped[-1].lower():
                continue
            deduped.append(s)
        new_path = "/" + "/".join(deduped)
        if parsed.path.endswith("/") and not new_path.endswith("/"):
            new_path += "/"
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, new_path, parsed.query, parsed.fragment))
    except Exception:
        return u


KNOWN_ORDS_RESOURCE_SEGMENTS = (
    "final_discharge_effluent",
    "production_utilities_consumption",
    "production_daily_output",
)


def build_oracle_endpoint_url(base_url: Optional[str], resource_endpoint: Optional[str]) -> str:
    """
    Safely joins base_url and resource_endpoint without duplicating paths.
    Handles situations where base_url already contains the resource_endpoint or another known resource endpoint.
    """
    base = sanitize_endpoint_url(str(base_url or "").strip().rstrip("/"))
    res = (resource_endpoint or "").strip().strip("/")
    if not base:
        return f"/{res}/" if res else "/"

    if res:
        # If res is provided, strip any known trailing resource segment from base to avoid appending resource onto resource
        for seg in KNOWN_ORDS_RESOURCE_SEGMENTS:
            if base.lower().endswith("/" + seg):
                base = base[:-(len(seg) + 1)].rstrip("/")
                break
        res_lower = res.lower()
        if base.lower().endswith("/" + res_lower):
            raw_url = f"{base}/"
        else:
            raw_url = f"{base}/{res}/"
    else:
        raw_url = f"{base}/"

    return sanitize_endpoint_url(raw_url)


class OracleERPCloudClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = bool(config.get("enabled", False))
        self.auth_type = config.get("auth_type", "oauth2").lower()
        self.base_url = (config.get("base_url") or "").rstrip("/")
        self.token_url = (config.get("token_url") or "").strip()
        self.client_id = config.get("client_id", "").strip()
        self.client_secret = config.get("client_secret", "").strip()
        self.scope = config.get("scope", "urn:opc:resource:consumer::all").strip()
        self.username = config.get("username", "").strip()
        self.password = config.get("password", "").strip()
        self.bearer_token = config.get("bearer_token", "").strip()
        self.resource_endpoint = (config.get("resource_endpoint") or "").strip()
        self.http_method = config.get("http_method", "POST").upper()
        self.custom_headers = config.get("custom_headers", {})
        self.timeout = config.get("timeout_seconds", 15)
        self.dry_run = config.get("dry_run", False)

        # In-memory token cache
        self._cached_token: Optional[str] = None
        self._token_expiry_timestamp: float = 0

    def is_configured(self, target_endpoint: Optional[str] = None) -> Tuple[bool, str]:
        """Check if minimum connection parameters are provided."""
        is_direct = (
            self.auth_type in ("none", "no_auth", "open") or
            not self.client_id
        )
        if is_direct:
            # Unauthenticated endpoint - ready!
            return True, "Ready (Direct - No Auth)"

        if not self.enabled and not target_endpoint:
            return False, "Pending connection setup: Oracle integration is toggled off in settings."

        if not self.base_url and not target_endpoint:
            return False, "Pending connection setup: Oracle Cloud Base URL is not configured."

        if self.auth_type == "oauth2":
            if not self.token_url or not self.client_id or not self.client_secret:
                return False, "Pending connection setup: OAuth 2.0 Token URL, Client ID, or Client Secret is missing."
        elif self.auth_type == "basic":
            if not self.username:
                return False, "Pending connection setup: Oracle Cloud username is missing."

        return True, "Ready"

    def get_token(self, force_refresh: bool = False) -> Tuple[Optional[str], Optional[str]]:
        """
        Acquire OAuth 2.0 Access Token from Oracle Identity Cloud Service (IDCS/IAM).
        Returns: (access_token, error_message)
        """
        now = time.time()
        # Return cached token if valid for at least 60 more seconds
        if not force_refresh and self._cached_token and now < (self._token_expiry_timestamp - 60):
            return self._cached_token, None

        if not self.token_url:
            return None, "Token URL is empty"

        payload = {
            "grant_type": "client_credentials"
        }
        if self.scope:
            payload["scope"] = self.scope

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        # IDCS supports Basic Auth with Client ID & Client Secret
        auth = requests.auth.HTTPBasicAuth(self.client_id, self.client_secret)

        try:
            resp = requests.post(
                self.token_url,
                data=payload,
                headers=headers,
                auth=auth,
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                if token:
                    self._cached_token = token
                    self._token_expiry_timestamp = now + float(expires_in)
                    return token, None
                else:
                    return None, f"Token endpoint response missing 'access_token': {resp.text[:200]}"
            else:
                return None, f"OAuth Token request failed (HTTP {resp.status_code}): {resp.text[:300]}"
        except Exception as e:
            return None, f"OAuth Token request exception: {str(e)}"

    def test_connection(self, test_url: Optional[str] = None) -> Dict[str, Any]:
        """Validate Oracle Cloud / ORDS connection settings."""
        if not self.enabled:
            return {
                "success": False,
                "status": "PENDING_SETUP",
                "message": "Oracle ERP integration is currently disabled in settings.",
                "details": {
                    "auth_type": self.auth_type,
                    "base_url": self.base_url or "(Not set)",
                    "enabled": False
                }
            }
        # Resolve endpoint URL to test
        if test_url:
            clean_test = sanitize_endpoint_url(str(test_url).strip().strip('"').strip("'"))
            full_endpoint = clean_test
        elif self.base_url:
            full_endpoint = build_oracle_endpoint_url(self.base_url, self.resource_endpoint)
        else:
            return {
                "success": False,
                "status": "FAILED",
                "message": "No Oracle endpoint URL configured to test."
            }

        # Check if direct/unauthenticated endpoint (auth_type none or client_id is empty)
        is_direct = (
            self.auth_type in ("none", "no_auth", "open") or
            not self.client_id
        )

        configured, reason = self.is_configured(target_endpoint=full_endpoint if is_direct else None)
        if not configured and not is_direct:
            return {
                "success": False,
                "status": "PENDING_SETUP",
                "message": reason,
                "details": {
                    "auth_type": self.auth_type,
                    "base_url": self.base_url or "(Not set)",
                    "enabled": self.enabled
                }
            }

        start_t = time.time()

        # If OAuth 2.0 and NOT direct, test token acquisition first
        if self.auth_type == "oauth2" and not is_direct:
            token, err = self.get_token(force_refresh=True)
            token_latency = round((time.time() - start_t) * 1000, 2)
            if not token:
                return {
                    "success": False,
                    "status": "FAILED",
                    "latency_ms": token_latency,
                    "message": "Failed to acquire OAuth 2.0 token from Oracle IDCS",
                    "error": err
                }

        headers = self._build_request_headers(target_endpoint=full_endpoint)

        try:
            # Probe connectivity using OPTIONS (validates route existence, server response, and allowed verbs like POST without requiring table SELECT permissions)
            test_resp = requests.options(full_endpoint, headers=headers, timeout=self.timeout)
            if test_resp.status_code not in (200, 201, 202, 204, 405):
                # Fallback to HEAD
                try:
                    head_resp = requests.head(full_endpoint, headers=headers, timeout=self.timeout)
                    if head_resp.status_code in (200, 201, 202, 204, 405):
                        test_resp = head_resp
                except Exception:
                    pass

            latency = round((time.time() - start_t) * 1000, 2)

            if test_resp.status_code in (200, 201, 202, 204, 405):
                auth_label = "ORDS Direct (No Auth)" if is_direct else self.auth_type.upper()
                allowed_methods = test_resp.headers.get("Allow") or ""
                method_info = f" [Allowed: {allowed_methods}]" if allowed_methods else ""
                return {
                    "success": True,
                    "status": "CONNECTED",
                    "status_code": test_resp.status_code,
                    "latency_ms": latency,
                    "message": f"Successfully connected to Oracle endpoint ({auth_label}) - HTTP {test_resp.status_code}{method_info}",
                    "details": {
                        "endpoint": full_endpoint,
                        "auth_mode": auth_label,
                        "http_code": test_resp.status_code,
                        "allowed_methods": allowed_methods
                    }
                }
            else:
                return {
                    "success": False,
                    "status": "FAILED",
                    "status_code": test_resp.status_code,
                    "latency_ms": latency,
                    "message": f"Oracle returned HTTP {test_resp.status_code}",
                    "error": test_resp.text[:400]
                }
        except requests.exceptions.ConnectionError as e:
            return {
                "success": False,
                "status": "FAILED",
                "latency_ms": round((time.time() - start_t) * 1000, 2),
                "message": "Connection error reaching Oracle endpoint",
                "error": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "status": "FAILED",
                "latency_ms": round((time.time() - start_t) * 1000, 2),
                "message": "Oracle connection test failed",
                "error": str(e)
            }

    def _build_request_headers(self, target_endpoint: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        effective_endpoint = target_endpoint or self.base_url or ""
        is_direct = (
            self.auth_type in ("none", "no_auth", "open") or
            not self.client_id
        )
        if is_direct:
            # Direct unauthenticated request - no Authorization header
            if isinstance(self.custom_headers, dict):
                headers.update(self.custom_headers)
            return headers

        if self.auth_type == "oauth2":
            if "/ords/" not in effective_endpoint.lower():
                headers["Content-Type"] = "application/vnd.oracle.adf.resourceitem+json"
                headers["REST-Framework-Version"] = "4"
            token, _ = self.get_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif self.auth_type == "basic" and self.username:
            user_pass = f"{self.username}:{self.password}"
            b64_cred = base64.b64encode(user_pass.encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {b64_cred}"
        elif self.auth_type == "bearer" and self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        if isinstance(self.custom_headers, dict):
            headers.update(self.custom_headers)

        # CRITICAL: For Oracle ORDS endpoints, Content-Type MUST ALWAYS be application/json
        # Oracle ORDS ignores bodies sent with application/vnd.oracle.adf.resourceitem+json,
        # resulting in empty NULL inserts!
        if "/ords/" in effective_endpoint.lower():
            headers["Content-Type"] = "application/json"
            headers["Accept"] = "application/json"
            headers.pop("REST-Framework-Version", None)

        return headers

    def publish_data(self, payload: Dict[str, Any], target_endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Dispatches transformed PI AF data to Oracle ORDS / ERP Cloud API.
        If target_endpoint is specified, dispatches directly to that individual mapping endpoint URL.
        """
        effective_endpoint = target_endpoint or self.base_url or ""
        is_direct = (
            self.auth_type in ("none", "no_auth", "open") or
            not self.client_id
        )
        configured, reason = self.is_configured(target_endpoint=target_endpoint if is_direct else None)
        if not configured and not is_direct:
            return {
                "status": "PENDING_SETUP",
                "message": reason,
                "record_count": 1 if not isinstance(payload.get("items"), list) else len(payload.get("items")),
                "target_endpoint": sanitize_endpoint_url(target_endpoint) or build_oracle_endpoint_url(self.base_url, self.resource_endpoint),
                "http_code": None,
                "payload_sample": payload,
                "response_body": None,
                "error_detail": None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        if target_endpoint:
            clean_target = sanitize_endpoint_url(str(target_endpoint).strip().strip('"').strip("'"))
            if clean_target.startswith("http://") or clean_target.startswith("https://"):
                full_url = clean_target
            else:
                full_url = build_oracle_endpoint_url(self.base_url, clean_target)
        elif self.base_url:
            full_url = build_oracle_endpoint_url(self.base_url, self.resource_endpoint)
        else:
            full_url = "https://oracle-ords-endpoint.local"
        full_url = sanitize_endpoint_url(full_url)

        headers = self._build_request_headers(target_endpoint=full_url)
        start_t = time.time()

        if self.dry_run:
            return {
                "status": "SUCCESS",
                "message": "Dry Run: Validated payload structure for Oracle (Transmission simulated)",
                "record_count": 1 if not isinstance(payload.get("items"), list) else len(payload.get("items")),
                "target_endpoint": full_url,
                "http_code": 201,
                "payload_sample": payload,
                "response_body": {
                    "TransactionId": f"TXN-ORCL-DRY-{int(time.time())}",
                    "Status": "SIMULATED_ACCEPTED",
                    "links": [{"rel": "self", "href": f"{full_url}SIMULATED_ITEM"}]
                },
                "error_detail": None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        try:
            resp = requests.post(full_url, json=payload, headers=headers, timeout=self.timeout)
            latency = round((time.time() - start_t) * 1000, 2)
            is_success = resp.status_code in (200, 201, 202, 204)

            try:
                resp_data = resp.json()
            except Exception:
                resp_data = {"raw": resp.text[:500]}

            return {
                "status": "SUCCESS" if is_success else "FAILED",
                "message": f"Oracle responded with HTTP {resp.status_code}" if is_success else f"Oracle rejection HTTP {resp.status_code}",
                "record_count": 1 if not isinstance(payload.get("items"), list) else len(payload.get("items")),
                "target_endpoint": full_url,
                "http_code": resp.status_code,
                "latency_ms": latency,
                "payload_sample": payload,
                "response_body": resp_data,
                "error_detail": None if is_success else resp.text[:1000],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "status": "FAILED",
                "message": f"Exception connecting to Oracle endpoint: {str(e)}",
                "record_count": 1 if not isinstance(payload.get("items"), list) else len(payload.get("items")),
                "target_endpoint": full_url,
                "http_code": None,
                "payload_sample": payload,
                "response_body": None,
                "error_detail": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    # Alias for API compatibility
    publish_readings = publish_data
