"""
J5 / Hexagon Smart Cloud Inbound Message REST API Client.
Implements:
1. HTTP Basic Authentication with J5 credentials:
   - Username: HIRUJR_JZNOT1742577235_TST
   - Password: kah4YAH!bvm-vkt_jzd
2. Connectivity testing and latency probing.
3. Telemetry payload generation and dispatching framework (customizable for J5 message schemas).
4. Robust response handling supporting JSON, plain text, and XML responses.
"""
import base64
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, Union
import requests
from requests.auth import HTTPBasicAuth


DEFAULT_J5_URL = "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=j5_pi_opslogbook"
DEFAULT_J5_USERNAME = "HIRUJR_JZNOT1742577235_TST"
DEFAULT_J5_PASSWORD = "kah4YAH!bvm-vkt_jzd"
DEFAULT_J5_TENANT_ID = "JZNOT1742577235_TST"


def format_j5_timestamp(ts: Any, allow_empty: bool = False) -> Optional[str]:
    """
    Format timestamp to ISO 8601 Zulu UTC: YYYY-MM-DDTHH:MM:SSZ
    Strips fractional microseconds.
    If allow_empty is True, None or empty/null values return None.
    """
    if ts is None:
        return None if allow_empty else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, (int, float)):
        val = float(ts)
        if 20000 <= val <= 100000:
            from datetime import timedelta
            excel_epoch = datetime(1899, 12, 30, tzinfo=timezone.utc)
            sec = round(val * 86400)
            return (excel_epoch + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if val > 1e11:
            val = val / 1000.0
        return datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, str):
        s = ts.strip().strip('"').strip("'")
        if not s or s.lower() in ("null", "none"):
            return None if allow_empty else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            fnum = float(s)
            if 20000 <= fnum <= 100000:
                from datetime import timedelta
                excel_epoch = datetime(1899, 12, 30, tzinfo=timezone.utc)
                sec = round(fnum * 86400)
                return (excel_epoch + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
            if s.isdigit() and len(s) >= 10:
                if fnum > 1e11:
                    fnum = fnum / 1000.0
                return datetime.fromtimestamp(fnum, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
                    dt = dt.replace(tzinfo=timezone.utc)
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


class J5Client:
    """
    REST client for communicating with Hexagon Smart Cloud / J5 Dataflow Inbound Message API.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.config = cfg
        self.enabled = bool(cfg.get("enabled", True))
        self.auth_type = cfg.get("auth_type", "basic").lower()
        self.url = (cfg.get("url") or DEFAULT_J5_URL).strip()
        self.username = (cfg.get("username") or DEFAULT_J5_USERNAME).strip()
        self.password = cfg.get("password") or DEFAULT_J5_PASSWORD
        self.tenant_id = (cfg.get("tenant_id") or DEFAULT_J5_TENANT_ID).strip()
        self.timeout = cfg.get("timeout_seconds", 15)
        self.custom_headers = cfg.get("custom_headers") or {}

    def is_configured(self, target_endpoint: Optional[str] = None) -> Tuple[bool, str]:
        """Check if minimum connection parameters are provided."""
        endpoint = target_endpoint or self.url
        if not endpoint:
            return False, "J5 Endpoint URL is not configured."
        if not self.username or not self.password:
            return False, "J5 Basic Auth username or password is missing."
        return True, "Ready"

    def _build_auth(self) -> Optional[HTTPBasicAuth]:
        if self.username and self.password:
            return HTTPBasicAuth(self.username, self.password)
        return None

    def _build_headers(self, custom: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "text/plain",
            "Accept": "application/json, text/plain, */*",
            "X-Tenant-Id": self.tenant_id
        }
        if self.username and self.password:
            user_pass = f"{self.username}:{self.password}"
            b64_cred = base64.b64encode(user_pass.encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {b64_cred}"

        if isinstance(self.custom_headers, dict):
            headers.update(self.custom_headers)
        if custom and isinstance(custom, dict):
            headers.update(custom)
        return headers

    def test_connection(self, test_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate J5 Inbound Message endpoint connectivity and HTTP Basic Authentication.
        """
        endpoint = str(test_url or self.url).strip()
        if not endpoint:
            return {
                "success": False,
                "status": "FAILED",
                "message": "No J5 endpoint URL configured to test."
            }

        start_t = time.time()
        headers = self._build_headers()
        auth = self._build_auth()

        try:
            # First attempt: OPTIONS request to check routing and allowed methods
            resp = requests.options(endpoint, headers=headers, auth=auth, timeout=self.timeout)
            if resp.status_code in (404, 405, 501):
                # Fallback to HEAD
                try:
                    head_resp = requests.head(endpoint, headers=headers, auth=auth, timeout=self.timeout)
                    if head_resp.status_code not in (404, 405, 501):
                        resp = head_resp
                except Exception:
                    pass

            # If OPTIONS/HEAD returned 401 or 403, authentication is being verified
            latency = round((time.time() - start_t) * 1000, 2)

            # J5 / Hexagon inbound message endpoints may return 200, 204, or 405 for OPTIONS
            if resp.status_code in (200, 201, 202, 204, 405):
                allowed = resp.headers.get("Allow") or ""
                method_info = f" [Allowed: {allowed}]" if allowed else ""
                return {
                    "success": True,
                    "status": "CONNECTED",
                    "status_code": resp.status_code,
                    "latency_ms": latency,
                    "message": f"Successfully connected to J5 endpoint (Basic Auth) - HTTP {resp.status_code}{method_info}",
                    "details": {
                        "endpoint": endpoint,
                        "auth_mode": "HTTP Basic Auth",
                        "username": self.username,
                        "http_code": resp.status_code,
                        "allowed_methods": allowed
                    }
                }
            elif resp.status_code in (401, 403):
                return {
                    "success": False,
                    "status": "AUTH_FAILED",
                    "status_code": resp.status_code,
                    "latency_ms": latency,
                    "message": f"J5 Authentication failed (HTTP {resp.status_code}): Invalid username or password.",
                    "error": resp.text[:400]
                }
            else:
                return {
                    "success": False,
                    "status": "FAILED",
                    "status_code": resp.status_code,
                    "latency_ms": latency,
                    "message": f"J5 endpoint returned HTTP {resp.status_code}",
                    "error": resp.text[:400]
                }
        except requests.exceptions.ConnectionError as e:
            return {
                "success": False,
                "status": "FAILED",
                "latency_ms": round((time.time() - start_t) * 1000, 2),
                "message": "Connection error reaching J5 endpoint. Check host URL and network routing.",
                "error": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "status": "FAILED",
                "latency_ms": round((time.time() - start_t) * 1000, 2),
                "message": f"J5 connection test exception: {str(e)}",
                "error": str(e)
            }

    def publish_data(self, payload: Any, target_endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Dispatches payload to J5 Inbound Message REST API using HTTP Basic Authentication.
        """
        full_url = str(target_endpoint or self.url).strip()
        if not full_url:
            full_url = DEFAULT_J5_URL

        headers = self._build_headers()
        auth = self._build_auth()
        start_t = time.time()

        try:
            body_data = payload if isinstance(payload, str) else json.dumps(payload)
            resp = requests.post(full_url, data=body_data, headers=headers, auth=auth, timeout=self.timeout)
            latency = round((time.time() - start_t) * 1000, 2)
            is_success = resp.status_code in (200, 201, 202, 204)

            # J5 responses may be JSON, plain text, or empty
            content_type = resp.headers.get("content-type", "").lower()
            resp_data: Any = None
            if "application/json" in content_type or resp.text.strip().startswith(("{", "[")):
                try:
                    resp_data = resp.json()
                except Exception:
                    resp_data = {"raw": resp.text[:1000]}
            elif resp.text:
                resp_data = {"text": resp.text[:1000]}
            else:
                resp_data = {"status": "HTTP " + str(resp.status_code), "body": "Empty response"}

            return {
                "target_type": "j5",
                "status": "SUCCESS" if is_success else "FAILED",
                "message": f"J5 responded with HTTP {resp.status_code}" if is_success else f"J5 rejection HTTP {resp.status_code}",
                "record_count": 1 if not isinstance(payload, list) else len(payload),
                "target_endpoint": full_url,
                "http_code": resp.status_code,
                "latency_ms": latency,
                "payload_sample": payload,
                "response_body": resp_data,
                "error_detail": None if is_success else (resp.text[:1000] if resp.text else f"HTTP {resp.status_code}"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "target_type": "j5",
                "status": "FAILED",
                "message": f"Exception connecting to J5 endpoint: {str(e)}",
                "record_count": 1,
                "target_endpoint": full_url,
                "http_code": None,
                "payload_sample": payload,
                "response_body": None,
                "error_detail": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    @staticmethod
    def build_j5_payload(
        attr_data: Dict[str, Any],
        mapping: Optional[Dict[str, Any]] = None,
        custom_schema_fn: Optional[Any] = None,
        skip_params: Optional[Any] = None,
        received_at: Optional[str] = None,
        target_type: str = "j5"
    ) -> Dict[str, Any]:
        """
        Extensible framework for building Octave (J5) Inbound Message payload bodies
        driven by customizable parameter schema mappings (supports separate prod and dev).
        """
        always_skip = {"j5", "jf", "j5dev", "jfdev", "j5_dev", "octave", "octavedev", "octave_dev", "oracle", "oracle_erp", "oracledev", "oracle_dev"}
        user_skip = set()
        if skip_params:
            if isinstance(skip_params, str):
                user_skip = {p.strip().lower() for p in skip_params.replace(";", ",").split(",") if p.strip()}
            elif isinstance(skip_params, (list, set, tuple)):
                user_skip = {str(p).strip().lower() for p in skip_params if str(p).strip()}
        all_skip = always_skip | user_skip

        from app.field_mapper import build_destination_payload
        payload = build_destination_payload(
            target_type=target_type,
            source_attr=attr_data,
            mapping_rule=mapping,
            received_at=received_at,
            skip_params=all_skip
        )

        # Also remove any top-level payload keys explicitly listed in user_skip
        if user_skip:
            for k in list(payload.keys()):
                if k.strip().lower() in user_skip:
                    payload.pop(k, None)

        # If a custom schema transformer is registered, run it
        if callable(custom_schema_fn):
            return custom_schema_fn(payload, attr_data, mapping)

        return payload
