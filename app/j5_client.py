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


DEFAULT_J5_URL = "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder"
DEFAULT_J5_USERNAME = "HIRUJR_JZNOT1742577235_TST"
DEFAULT_J5_PASSWORD = "kah4YAH!bvm-vkt_jzd"


def format_j5_timestamp(ts: Any) -> str:
    """
    Format timestamp to ISO 8601 Zulu UTC: YYYY-MM-DDTHH:MM:SSZ
    """
    if not ts:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, str):
        s = ts.strip().strip('"').strip("'")
        try:
            clean_s = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_s)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            if "." in s:
                base = s.split(".")[0]
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
            "Accept": "application/json, text/plain, */*"
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
        custom_schema_fn: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Extensible framework for building J5 Inbound Message payload bodies.
        
        NOTE FOR USER ADJUSTMENT:
        When sample body format for J5 is provided, adjust this function or
        provide a custom transformer to output the exact schema expected by J5.
        
        Currently structures standard telemetry:
        - tag / message identifier
        - timestamp (ISO 8601 Zulu)
        - value (scaled and rounded)
        - description
        - uom
        - quality
        - limit / operating parameters
        - results
        """
        mapping = mapping or {}
        now_iso = datetime.now(timezone.utc).isoformat()

        # Scale and round value if configured in mapping
        raw_val = attr_data.get("value")
        scale = float(mapping.get("scale_factor", 1.0))
        decimals = int(mapping.get("round_decimals", 2))
        scaled_val = raw_val
        try:
            if raw_val is not None and str(raw_val).strip() != "":
                scaled_val = round(float(raw_val) * scale, decimals)
        except Exception:
            scaled_val = raw_val

        # Tag selection: mapping tag > attr tag > attr name > default
        tag_val = (
            mapping.get("tag") or
            mapping.get("meter_tag") or
            attr_data.get("tag") or
            attr_data.get("name") or
            "purchaseorder"
        )

        desc_val = (
            mapping.get("description") or
            attr_data.get("description") or
            mapping.get("name") or
            attr_data.get("name") or
            ""
        )

        limit_val = (
            attr_data.get("limit") if attr_data.get("limit") is not None and str(attr_data.get("limit")).strip() != ""
            else (mapping.get("limit") or "")
        )

        results_val = (
            attr_data.get("results") if attr_data.get("results") is not None and str(attr_data.get("results")).strip() != ""
            else (mapping.get("results") or ("Normal" if attr_data.get("quality", "Good") == "Good" else "Check"))
        )

        uom_val = mapping.get("uom") or attr_data.get("uom") or ""
        ts_val = format_j5_timestamp(attr_data.get("timestamp") or now_iso)
        quality_val = attr_data.get("quality") or "Good"

        # Default extensible J5 telemetry framework payload
        payload = {
            "sourceSystem": "AVEVA_PI_NOTIFICATION",
            "messageTag": str(tag_val),
            "tag": str(tag_val),
            "description": str(desc_val),
            "value": str(scaled_val) if scaled_val is not None else "",
            "readingValue": scaled_val,
            "unitOfMeasure": str(uom_val),
            "uom": str(uom_val),
            "limit": str(limit_val),
            "results": str(results_val),
            "quality": str(quality_val),
            "timestamp": ts_val,
            "readingTimestamp": ts_val
        }

        # If a custom schema transformer is registered, run it
        if callable(custom_schema_fn):
            return custom_schema_fn(payload, attr_data, mapping)

        return payload
