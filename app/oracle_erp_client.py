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
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import requests


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
        self.resource_endpoint = config.get("resource_endpoint", "/fscmRestApi/resources/11.13.18.05/standardReceipts").strip()
        self.http_method = config.get("http_method", "POST").upper()
        self.custom_headers = config.get("custom_headers", {})
        self.timeout = config.get("timeout_seconds", 15)
        self.dry_run = config.get("dry_run", False)

        # In-memory token cache
        self._cached_token: Optional[str] = None
        self._token_expiry_timestamp: float = 0

    def is_configured(self) -> Tuple[bool, str]:
        """Check if minimum connection parameters are provided."""
        if not self.enabled:
            return False, "Pending connection setup: Oracle integration is toggled off in settings."

        if self.auth_type in ("none", "no_auth", "open"):
            # Unauthenticated ORDS endpoint - ready!
            return True, "Ready (ORDS Direct - No Auth)"

        if not self.base_url:
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
        configured, reason = self.is_configured()
        if not configured:
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

        # If OAuth 2.0, test token acquisition first
        if self.auth_type == "oauth2":
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

        # Resolve endpoint URL to test
        if test_url:
            full_endpoint = test_url
        elif self.base_url and self.resource_endpoint:
            full_endpoint = f"{self.base_url.rstrip('/')}/{self.resource_endpoint.lstrip('/')}"
        elif self.base_url:
            full_endpoint = self.base_url
        else:
            return {
                "success": False,
                "status": "FAILED",
                "message": "No Oracle endpoint URL configured to test."
            }

        headers = self._build_request_headers()

        try:
            # For ORDS (auth_type in none, no_auth, open), use GET with limit=1 which ORDS natively supports
            if self.auth_type in ("none", "no_auth", "open"):
                test_resp = requests.get(full_endpoint, headers=headers, timeout=self.timeout, params={"limit": 1})
            else:
                test_resp = requests.options(full_endpoint, headers=headers, timeout=self.timeout)

            latency = round((time.time() - start_t) * 1000, 2)

            if test_resp.status_code in (200, 201, 202, 204, 405):
                auth_label = "ORDS Direct (No Auth)" if self.auth_type in ("none", "no_auth", "open") else self.auth_type.upper()
                return {
                    "success": True,
                    "status": "CONNECTED",
                    "status_code": test_resp.status_code,
                    "latency_ms": latency,
                    "message": f"Successfully connected to Oracle endpoint ({auth_label})",
                    "details": {
                        "endpoint": full_endpoint,
                        "auth_mode": auth_label,
                        "http_code": test_resp.status_code
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

    def _build_request_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.auth_type == "oauth2":
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
        # For 'none' / 'no_auth', no Authorization header is added!

        if isinstance(self.custom_headers, dict):
            headers.update(self.custom_headers)

        return headers

    def publish_data(self, payload: Dict[str, Any], target_endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Dispatches transformed PI AF data to Oracle ORDS / ERP Cloud API.
        If target_endpoint is specified, dispatches directly to that individual mapping endpoint URL.
        """
        configured, reason = self.is_configured()
        if not configured:
            return {
                "status": "PENDING_SETUP",
                "message": reason,
                "record_count": 1 if not isinstance(payload.get("items"), list) else len(payload.get("items")),
                "target_endpoint": target_endpoint or f"{self.base_url}{self.resource_endpoint}",
                "http_code": None,
                "payload_sample": payload,
                "response_body": None,
                "error_detail": None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        if target_endpoint:
            if target_endpoint.startswith("http://") or target_endpoint.startswith("https://"):
                full_url = target_endpoint
            else:
                full_url = f"{self.base_url.rstrip('/')}/{target_endpoint.lstrip('/')}"
        elif self.base_url:
            full_url = f"{self.base_url.rstrip('/')}/{self.resource_endpoint.lstrip('/')}"
        else:
            full_url = "https://oracle-ords-endpoint.local"

        headers = self._build_request_headers()
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
