"""
Oracle ERP Cloud REST API Mock Simulation Server.
Runs as an independent sub-application (default port 8080).
Simulates:
1. Oracle Identity Cloud Service (IDCS/IAM) OAuth 2.0 token endpoint (/oauth2/v1/token).
2. Oracle Fusion Applications REST resource endpoints (/fscmRestApi/resources/...).
3. Basic Authentication and Bearer Token validation.
4. Payload inspection and transaction ledger.
"""
import base64
import json
import os
import sys
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

MOCK_PORT = 8080
DEFAULT_CLIENT_ID = "DEMO_ORCL_CLIENT_ID"
DEFAULT_CLIENT_SECRET = "DEMO_ORCL_SECRET_KEY_9982"

# In-memory transaction storage
_received_transactions: List[Dict[str, Any]] = []
_active_tokens: Dict[str, float] = {}  # token -> expiry_timestamp
_start_time = time.time()

mock_erp_app = FastAPI(
    title="Oracle ERP Cloud REST API Simulator",
    description="Mock simulation service for Oracle Fusion Applications & IDCS OAuth 2.0",
    version="1.0.0"
)

mock_erp_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _verify_auth(request: Request) -> bool:
    """Validate Bearer Token or Basic Auth header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return False

    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        # Accept any valid mock token or any non-empty token in simulation
        if token in _active_tokens and time.time() < _active_tokens[token]:
            return True
        # Also accept demo tokens starting with 'orcl_'
        if token.startswith("orcl_") or len(token) > 10:
            return True
        return False

    if auth_header.startswith("Basic "):
        try:
            b64_str = auth_header.split(" ", 1)[1].strip()
            decoded = base64.b64decode(b64_str).decode("utf-8")
            return ":" in decoded
        except Exception:
            return False

    return False


@mock_erp_app.get("/")
def mock_root():
    return {
        "service": "Oracle ERP Cloud REST API Simulator",
        "status": "ONLINE",
        "port": MOCK_PORT,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "total_transactions_received": len(_received_transactions),
        "docs_endpoints": {
            "oauth_token": "/oauth2/v1/token",
            "fscm_resource": "/fscmRestApi/resources/11.13.18.05/standardReceipts",
            "inspection": "/api/mock/transactions"
        }
    }


# -------------------------------------------------------------
# 1. Oracle IDCS / IAM OAuth 2.0 Token Endpoint
# -------------------------------------------------------------
@mock_erp_app.post("/oauth2/v1/token")
async def oauth_token_endpoint(request: Request):
    """
    Simulates Oracle Identity Cloud Service (IDCS) OAuth 2.0 Client Credentials Grant.
    Accepts Basic Auth (client_id:client_secret) or form data.
    """
    auth_header = request.headers.get("Authorization", "")
    client_id = None
    client_secret = None

    if auth_header.startswith("Basic "):
        try:
            b64_str = auth_header.split(" ", 1)[1].strip()
            decoded = base64.b64decode(b64_str).decode("utf-8")
            parts = decoded.split(":", 1)
            client_id = parts[0]
            client_secret = parts[1] if len(parts) > 1 else ""
        except Exception:
            pass

    # Try body form or json if not in header
    content_type = request.headers.get("Content-Type", "")
    try:
        raw_body = await request.body()
        if raw_body:
            if "json" in content_type:
                body_json = json.loads(raw_body)
                client_id = client_id or body_json.get("client_id")
                client_secret = client_secret or body_json.get("client_secret")
            else:
                parsed_form = urllib.parse.parse_qs(raw_body.decode("utf-8", errors="ignore"))
                cid_val = parsed_form.get("client_id")
                sec_val = parsed_form.get("client_secret")
                client_id = client_id or (cid_val[0] if cid_val else None)
                client_secret = client_secret or (sec_val[0] if sec_val else None)
    except Exception:
        pass

    # Generate a structured Oracle mock bearer token
    token_str = f"orcl_jwt_{uuid.uuid4().hex}_{int(time.time())}"
    expires_in = 3600
    _active_tokens[token_str] = time.time() + expires_in

    return {
        "access_token": token_str,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": "urn:opc:resource:consumer::all",
        "token_id": f"token-{uuid.uuid4().hex[:8]}",
        "issued_at": datetime.now(timezone.utc).isoformat()
    }


# -------------------------------------------------------------
# 2. Oracle Fusion REST Endpoints
# -------------------------------------------------------------
@mock_erp_app.options("/fscmRestApi/resources/{path:path}")
def fscm_options(path: str, request: Request):
    """Handshake/probe endpoint used by clients to check accessibility and REST version."""
    headers = {
        "REST-Framework-Version": "4",
        "Content-Type": "application/vnd.oracle.adf.resourceitem+json",
        "Allow": "OPTIONS, GET, POST, PATCH, PUT"
    }
    return Response(status_code=200, headers=headers)


@mock_erp_app.post("/fscmRestApi/resources/{path:path}", status_code=status.HTTP_201_CREATED)
async def fscm_post_resource(path: str, request: Request):
    """
    Ingests telemetry payload into mock Oracle ERP Cloud (Receipts, Meter Readings, Assets).
    """
    if not _verify_auth(request):
        return JSONResponse(
            status_code=401,
            content={
                "title": "Unauthorized",
                "status": 401,
                "detail": "Oracle Fusion Applications: Invalid or missing authorization credentials (Bearer token or Basic Auth required).",
                "o:errorDetails": [
                    {
                        "errorCode": "FND_CMN_AUTH_FAILED",
                        "message": "User failed authentication challenge."
                    }
                ]
            }
        )

    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode("utf-8", errors="ignore")}

    now_iso = datetime.now(timezone.utc).isoformat()
    txn_id = f"TXN-FUSION-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"

    # Extract items if array or wrapped format
    items = payload.get("items", []) if isinstance(payload, dict) else []
    record_count = len(items) if items else (1 if isinstance(payload, dict) else len(payload))

    transaction_record = {
        "transaction_id": txn_id,
        "resource_path": f"/fscmRestApi/resources/{path}",
        "timestamp": now_iso,
        "client_ip": request.client.host if request.client else "127.0.0.1",
        "auth_type": "Bearer" if "Bearer" in request.headers.get("Authorization", "") else "Basic",
        "item_count": record_count,
        "payload": payload
    }

    _received_transactions.insert(0, transaction_record)
    if len(_received_transactions) > 100:
        _received_transactions.pop()

    response_headers = {
        "REST-Framework-Version": "4",
        "Content-Type": "application/vnd.oracle.adf.resourceitem+json",
        "Location": f"http://127.0.0.1:{MOCK_PORT}/fscmRestApi/resources/{path}/{txn_id}"
    }

    response_body = {
        "TransactionId": txn_id,
        "Status": "PROCESSED",
        "ResourcePath": f"/fscmRestApi/resources/{path}",
        "ProcessedAt": now_iso,
        "ItemCount": record_count,
        "Message": f"Successfully ingested {record_count} telemetry reading(s) into Oracle ERP Cloud.",
        "links": [
            {
                "rel": "self",
                "href": f"http://127.0.0.1:{MOCK_PORT}/fscmRestApi/resources/{path}/{txn_id}",
                "name": path.split("/")[-1]
            }
        ]
    }

    return JSONResponse(status_code=201, content=response_body, headers=response_headers)


@mock_erp_app.patch("/fscmRestApi/resources/{path:path}")
@mock_erp_app.put("/fscmRestApi/resources/{path:path}")
async def fscm_update_resource(path: str, request: Request):
    """Simulate updating an existing resource record in Oracle Fusion."""
    if not _verify_auth(request):
        return JSONResponse(status_code=401, content={"title": "Unauthorized", "status": 401})
    payload = await request.json()
    txn_id = f"TXN-FUSION-UPD-{int(time.time())}"
    return {
        "TransactionId": txn_id,
        "Status": "UPDATED",
        "Message": "Resource successfully updated in Oracle Fusion."
    }


# -------------------------------------------------------------
# 3. Mock Server Management & Diagnostics API
# -------------------------------------------------------------
@mock_erp_app.get("/api/mock/transactions")
def get_mock_transactions(limit: int = 20):
    """Retrieve transactions received from the data pipeline for inspection."""
    return {
        "total": len(_received_transactions),
        "transactions": _received_transactions[:limit]
    }


@mock_erp_app.post("/api/mock/clear")
def clear_mock_transactions():
    """Clear received transactions log."""
    _received_transactions.clear()
    return {"success": True, "message": "Transaction history cleared."}


# -------------------------------------------------------------
# Manager class to start/stop the server inside the main app process
# -------------------------------------------------------------
class MockERPServerManager:
    def __init__(self, port: int = 8080):
        self.port = port
        self.server: Optional[uvicorn.Server] = None
        self._thread = None
        self.is_running = False

    def start(self):
        if self.is_running:
            return
        import threading
        config = uvicorn.Config(
            mock_erp_app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False
        )
        self.server = uvicorn.Server(config)
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="MockERPServer")
        self._thread.start()
        time.sleep(0.5)

    def _run(self):
        try:
            self.server.run()
        finally:
            self.is_running = False

    def stop(self):
        if self.server and self.is_running:
            self.server.should_exit = True
            self.is_running = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "port": self.port,
            "base_url": f"http://127.0.0.1:{self.port}",
            "token_url": f"http://127.0.0.1:{self.port}/oauth2/v1/token",
            "resource_endpoint": "/fscmRestApi/resources/11.13.18.05/standardReceipts",
            "client_id": DEFAULT_CLIENT_ID,
            "client_secret": DEFAULT_CLIENT_SECRET,
            "transactions_count": len(_received_transactions),
            "last_transaction": _received_transactions[0] if _received_transactions else None
        }


mock_erp_manager = MockERPServerManager(port=MOCK_PORT)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else MOCK_PORT
    print(f"Starting standalone Oracle ERP Cloud Mock Server on port {port}...")
    uvicorn.run("app.mock_erp_server:mock_erp_app", host="127.0.0.1", port=port, log_level="info")
