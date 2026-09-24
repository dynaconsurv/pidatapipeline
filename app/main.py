"""
FastAPI application for the AVEVA PI to Oracle ERP Cloud Data Pipeline.
Serves REST endpoints for configuration, live monitoring, AF tree exploration,
and single-page web UI.
"""
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import load_settings, save_settings, load_mappings, save_mappings
from app.pi_client import PIWebApiClient
from app.oracle_erp_client import OracleERPCloudClient
from app.pipeline import pipeline_engine
from app.storage import (
    get_pull_history,
    get_publish_history,
    get_logs,
    add_log,
    get_received_deliveries,
    get_delivery_by_id,
    delete_received_delivery,
    clear_received_deliveries,
    clear_pull_history,
    clear_publish_history,
    clear_logs,
    clear_all_operational_data
)
from app.delivery_handler import (
    process_incoming_delivery,
    dispatch_delivery_to_oracle,
    dispatch_all_pending_deliveries,
    validate_delivery_security
)
from app.mock_erp_server import mock_erp_manager
from app.version import __version__, APP_NAME, GITHUB_REPO

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start background pipeline if configured
    settings = load_settings()
    if settings.get("pipeline", {}).get("auto_start", True):
        pipeline_engine.start()
    add_log("INFO", "SYSTEM", f"{APP_NAME} v{__version__} ready.")
    yield
    # Shutdown: stop pipeline and mock server if running
    pipeline_engine.stop()
    mock_erp_manager.stop()


app = FastAPI(
    title=APP_NAME,
    description="Industrial IoT data pipeline pulling telemetry from AVEVA PI Web API and streaming into Oracle ERP Cloud.",
    version=__version__,
    lifespan=lifespan
)

# Prevent stale browser caching of frontend UI scripts and HTML
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Mount static assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse({"message": "Data Pipeline API is online. Static UI file pending."})


# -------------------------------------------------------------
# Dashboard & Pipeline Operations
# -------------------------------------------------------------
@app.get("/api/dashboard")
def get_dashboard_summary():
    """Retrieve full live dashboard data: PI status, ERP status, last 5 pulls, countdown."""
    status = pipeline_engine.get_status()
    return status


@app.post("/api/pipeline/run-now")
def trigger_pipeline_run():
    """Manually trigger an immediate cycle (dispatch staged in endpoint mode, or pull & publish in pull mode)."""
    try:
        settings = load_settings()
        mode = settings.get("pipeline", {}).get("ingestion_mode", "endpoint")
        if mode == "endpoint":
            from app.delivery_handler import dispatch_all_pending_deliveries
            result = dispatch_all_pending_deliveries()
            return {"success": True, "mode": "endpoint", "result": result}
        else:
            result = pipeline_engine.execute_cycle()
            return {"success": True, "mode": "pull", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pipeline/pause")
def pause_pipeline():
    pipeline_engine.pause()
    return {"success": True, "is_paused": True}


@app.post("/api/pipeline/resume")
def resume_pipeline():
    pipeline_engine.resume()
    return {"success": True, "is_paused": False}


# -------------------------------------------------------------
# PI System Explorer / Notifications Delivery Ingestion Endpoints
# (Matches WebService REST delivery channel in PI System Explorer)
# -------------------------------------------------------------
@app.post("/api/security/generate-key")
def generate_api_key_endpoint():
    """Generates a secure random 32-character hexadecimal API Key."""
    import secrets
    new_key = f"pi_sec_{secrets.token_hex(16)}"
    return {"api_key": new_key}


@app.post("/api/v1/delivery")
@app.post("/api/v1/webhook")
@app.post("/api/v1/pi-notifications")
async def receive_pi_delivery(request: Request):
    """
    HTTP POST WebService Delivery Endpoint for AVEVA PI System Explorer / PI AF Notifications.
    Validates endpoint security (Option 1: API Key, Option 2: IP Whitelist)
    and temporarily stages incoming payload into data/received_deliveries.json prior to Oracle ERP dispatch.
    """
    client_ip = request.client.host if request.client else "Unknown"
    headers = dict(request.headers)
    query_params = dict(request.query_params)

    # Validate endpoint security
    is_valid, status_code, sec_err = validate_delivery_security(
        client_ip=client_ip,
        headers=headers,
        query_params=query_params
    )
    if not is_valid:
        return JSONResponse(status_code=status_code, content={"success": False, "error": sec_err})

    try:
        content_type = request.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            raw_data = await request.json()
        else:
            raw_bytes = await request.body()
            if not raw_bytes:
                raw_data = {}
            else:
                try:
                    import json
                    raw_data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
                except Exception:
                    raw_data = {"raw_text": raw_bytes.decode("utf-8", errors="replace")}
    except Exception as e:
        raw_data = {"parse_error": str(e)}

    result = process_incoming_delivery(
        raw_data,
        client_ip=client_ip,
        query_params=query_params,
        headers=headers
    )
    return JSONResponse(status_code=200, content=result)


@app.get("/api/deliveries")
def get_deliveries_list(limit: int = 50, status: str = None):
    """Retrieve staged deliveries received from PI System Explorer."""
    return get_received_deliveries(limit=limit, status=status)


@app.get("/api/deliveries/{delivery_id}")
def get_single_delivery(delivery_id: str):
    """Inspect full raw JSON and parsed metadata for a single delivery."""
    delivery = get_delivery_by_id(delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery record not found.")
    return delivery


@app.post("/api/deliveries/{delivery_id}/dispatch")
def trigger_delivery_dispatch(delivery_id: str):
    """Manually dispatch a staged delivery to Oracle ERP Cloud."""
    try:
        result = dispatch_delivery_to_oracle(delivery_id)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/deliveries/dispatch-pending")
def trigger_dispatch_all_pending():
    """Dispatch all deliveries currently staged and pending Oracle forwarding."""
    try:
        result = dispatch_all_pending_deliveries()
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/deliveries/{delivery_id}")
def delete_single_delivery(delivery_id: str):
    """Delete a single staged delivery record from data/received_deliveries.json."""
    success = delete_received_delivery(delivery_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Delivery {delivery_id} not found in storage.")
    add_log("INFO", "SYSTEM", f"Staged delivery {delivery_id} deleted by user.")
    return {"success": True, "message": f"Delivery {delivery_id} deleted successfully."}


@app.delete("/api/deliveries")
def clear_deliveries_endpoint(filter: str = "ALL"):
    """
    Purge accumulated deliveries from data/received_deliveries.json.
    Query parameter 'filter': 'ALL' (purge all), 'PENDING' (purge unsent/failed), 'DISPATCHED' (purge sent).
    """
    count = clear_received_deliveries(status_filter=filter)
    add_log("INFO", "SYSTEM", f"Purged {count} delivery record(s) from JSON storage (filter: {filter}).")
    return {
        "success": True,
        "deleted_count": count,
        "filter": filter,
        "message": f"Successfully deleted {count} staged deliveries."
    }


@app.post("/api/storage/clear")
def clear_storage_data_endpoint(request: Dict[str, Any]):
    """
    Purge operational JSON storage files before production deployment.
    target options: 'deliveries', 'pull_history', 'publish_history', 'logs', 'all'.
    """
    target = request.get("target", "deliveries").lower()
    filter_mode = request.get("filter", "ALL")
    if target == "deliveries":
        count = clear_received_deliveries(status_filter=filter_mode)
        return {"success": True, "target": target, "filter": filter_mode, "deleted_count": count, "message": f"Deleted {count} staged deliveries ({filter_mode})."}
    elif target == "pull_history":
        count = clear_pull_history()
        return {"success": True, "target": target, "deleted_count": count, "message": f"Deleted {count} pull history records."}
    elif target == "publish_history":
        count = clear_publish_history()
        return {"success": True, "target": target, "deleted_count": count, "message": f"Deleted {count} ERP publish records."}
    elif target == "logs":
        count = clear_logs()
        return {"success": True, "target": target, "deleted_count": count, "message": f"Deleted {count} diagnostic log records."}
    elif target in ("all", "preflight", "production_reset"):
        include_logs = bool(request.get("include_logs", False))
        results = clear_all_operational_data()
        if include_logs:
            results["logs_deleted"] = clear_logs()
        return {
            "success": True,
            "target": "all",
            "results": results,
            "message": "Operational test data purged. Configuration and mappings are strictly preserved."
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown storage purge target: {target}")



@app.post("/api/deliveries/simulate")
def simulate_pi_delivery():
    """
    Generate and ingest a realistic sample PI AF Notification delivery
    matching the 'Process Engineering_XZV' template from PI System Explorer.
    """
    import random
    import time
    now_iso = datetime.now(timezone.utc).isoformat()
    mock_payload = {
        "Notification": "Process Engineering_XZV",
        "Target": r"\\MYTLAVMPIMSAPP1\Plant_Operations\Process_Unit_1\Reactor_XZV",
        "Event": "Trigger",
        "StartTime": now_iso,
        "EndTime": now_iso,
        "Attributes": {
            "Level_Sensor": {
                "Value": round(75.0 + random.uniform(-10.0, 15.0), 2),
                "UOM": "%",
                "Timestamp": now_iso,
                "Quality": "Good"
            },
            "Flow_Rate": {
                "Value": round(120.0 + random.uniform(-15.0, 25.0), 2),
                "UOM": "m3/h",
                "Timestamp": now_iso,
                "Quality": "Good"
            },
            "Temperature_Reactor": {
                "Value": round(145.0 + random.uniform(-8.0, 12.0), 2),
                "UOM": "degC",
                "Timestamp": now_iso,
                "Quality": "Good"
            },
            "Pressure_Inlet": {
                "Value": round(4.2 + random.uniform(-0.4, 0.6), 2),
                "UOM": "bar",
                "Timestamp": now_iso,
                "Quality": "Good"
            }
        }
    }
    result = process_incoming_delivery(mock_payload, client_ip="127.0.0.1 (Simulator)")
    return {"success": True, "delivery": result}



# -------------------------------------------------------------
# Settings API
# -------------------------------------------------------------
@app.get("/api/settings")
def get_pipeline_settings():
    return load_settings()


@app.post("/api/settings")
def update_pipeline_settings(settings: Dict[str, Any]):
    save_settings(settings)
    # Hot-reload scheduler interval if modified
    new_interval = settings.get("pipeline", {}).get("interval_seconds")
    if new_interval:
        pipeline_engine.set_interval(new_interval)
    add_log("INFO", "SYSTEM", "Pipeline configuration settings updated.")
    return {"success": True, "message": "Settings saved successfully to config/settings.json"}


@app.post("/api/settings/test-pi")
def test_pi_connection(config: Dict[str, Any] = None):
    """Test connection to AVEVA PI Web API using provided or stored config."""
    is_stored = False
    if not config:
        stored = load_settings()
        config = stored.get("pi_web_api", {})
        is_stored = True
    client = PIWebApiClient(config)
    result = client.test_connection()
    if is_stored or result.get("success"):
        pipeline_engine.refresh_pi_connection_status(result)
    return result


@app.post("/api/settings/test-erp")
def test_oracle_erp_connection(config: Dict[str, Any] = None):
    """Test connection to Oracle ERP Cloud API and token handshake."""
    if not config:
        stored = load_settings()
        config = stored.get("oracle_erp", {})
    client = OracleERPCloudClient(config)
    result = client.test_connection()
    return result


# -------------------------------------------------------------
# Attribute Mappings API & PI AF Explorer
# -------------------------------------------------------------
@app.get("/api/mappings")
def get_attribute_mappings():
    return load_mappings()


@app.post("/api/mappings")
def update_attribute_mappings(mappings: List[Dict[str, Any]]):
    save_mappings(mappings)
    add_log("INFO", "PIPELINE", f"Updated {len(mappings)} attribute mappings in config/mappings.json")
    return {"success": True, "count": len(mappings)}


@app.get("/api/pi/browse")
def browse_af(path: str = ""):
    """Browse AF hierarchy (servers, databases, elements, attributes)."""
    settings = load_settings()
    client = PIWebApiClient(settings.get("pi_web_api", {}))
    items = client.browse_af_hierarchy(path)
    return {"path": path, "items": items}


@app.get("/api/mappings/preview")
def preview_erp_payload():
    """Generate a preview of the Oracle ERP Cloud payload based on currently configured mappings."""
    mappings = load_mappings()
    enabled = [m for m in mappings if m.get("enabled", True)]

    # Use the latest pulled values from pull history if available, else clean preview values
    recent_batches = get_pull_history(limit=1)
    cached_values = {}
    if recent_batches and recent_batches[0].get("items"):
        for it in recent_batches[0]["items"]:
            if it.get("attribute_name"):
                cached_values[it["attribute_name"]] = it

    sample_items = []
    for m in enabled:
        attr_name = m.get("attribute_name", "Tag")
        if attr_name in cached_values:
            sample_items.append(cached_values[attr_name])
        else:
            sample_items.append({
                "attribute_name": attr_name,
                "full_path": m.get("full_path", ""),
                "value": 100.0 * float(m.get("scale_factor", 1.0)),
                "uom": m.get("uom", ""),
                "timestamp": "2026-09-17T10:00:00Z",
                "quality": "Good",
                "status": "Sample"
            })

    payload = pipeline_engine._build_erp_payload(sample_items, enabled)
    return payload


# -------------------------------------------------------------
# History & Logs API
# -------------------------------------------------------------
@app.get("/api/history/pulls")
def get_all_pull_history(limit: int = 20):
    return get_pull_history(limit)


@app.get("/api/history/publishes")
def get_all_publish_history(limit: int = 20):
    return get_publish_history(limit)


@app.get("/api/logs")
def get_pipeline_logs(limit: int = 50, category: str = "ALL"):
    return get_logs(limit, category)


# -------------------------------------------------------------
# Oracle ERP Cloud Mock Simulator Management API
# -------------------------------------------------------------
@app.get("/api/mock-erp/status")
def get_mock_erp_status():
    """Check running status, port, and stats of the Oracle ERP Mock Simulator."""
    return mock_erp_manager.get_status()


@app.post("/api/mock-erp/start")
def start_mock_erp():
    """Spawn the Oracle ERP Mock Simulator on port 8080."""
    mock_erp_manager.start()
    add_log("INFO", "SYSTEM", f"Started Oracle ERP Cloud Mock Simulator sub-app on port {mock_erp_manager.port}")
    return mock_erp_manager.get_status()


@app.post("/api/mock-erp/stop")
def stop_mock_erp():
    """Stop the Oracle ERP Mock Simulator sub-app."""
    mock_erp_manager.stop()
    add_log("INFO", "SYSTEM", "Stopped Oracle ERP Cloud Mock Simulator")
    return mock_erp_manager.get_status()


@app.post("/api/mock-erp/apply-to-settings")
def apply_mock_erp_to_settings():
    """Auto-fill and save pipeline settings to connect to the local mock ERP simulator."""
    settings = load_settings()
    mock_status = mock_erp_manager.get_status()
    settings["oracle_erp"] = {
        "enabled": True,
        "auth_type": "oauth2",
        "base_url": mock_status["base_url"],
        "token_url": mock_status["token_url"],
        "client_id": mock_status["client_id"],
        "client_secret": mock_status["client_secret"],
        "scope": "urn:opc:resource:consumer::all",
        "username": "",
        "password": "",
        "bearer_token": "",
        "resource_endpoint": mock_status["resource_endpoint"],
        "http_method": "POST",
        "dry_run": False,
        "custom_headers": {
            "Content-Type": "application/vnd.oracle.adf.resourceitem+json",
            "REST-Framework-Version": "4"
        },
        "timeout_seconds": 15
    }
    save_settings(settings)
    add_log("INFO", "SYSTEM", "Applied Oracle ERP Cloud Mock Simulator credentials to settings.json")
    return {"success": True, "settings": settings, "mock_status": mock_status}


@app.get("/api/mock-erp/transactions")
def get_mock_erp_transactions(limit: int = 20):
    """Retrieve telemetry payloads received by the mock ERP server."""
    from app.mock_erp_server import _received_transactions
    return {"total": len(_received_transactions), "items": _received_transactions[:limit]}


# -------------------------------------------------------------
# System Version, Patching & Auto-Update API (No Git Required)
# -------------------------------------------------------------
from app.updater import check_for_updates, download_and_apply_update, apply_patch_from_zip
from fastapi import Request
import tempfile


@app.get("/api/system/version")
def get_system_version():
    """Returns current software version and GitHub repository information."""
    return {
        "app_name": APP_NAME,
        "version": __version__,
        "repo": GITHUB_REPO,
        "github_url": f"https://github.com/{GITHUB_REPO}"
    }


@app.get("/api/system/updates/check")
def check_software_updates(token: str = None):
    """Check GitHub Releases for new updates/patches."""
    return check_for_updates(github_token=token)


@app.post("/api/system/updates/apply")
def apply_latest_update(token: str = None):
    """Download and apply latest update from GitHub Releases."""
    res = download_and_apply_update(github_token=token)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to apply update"))
    return res


@app.post("/api/system/updates/upload-patch")
async def upload_offline_patch(request: Request):
    """Upload and apply an offline patch ZIP archive directly via HTTP."""
    body = await request.body()
    if len(body) < 100:
        raise HTTPException(status_code=400, detail="Invalid or empty patch payload.")

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
        tf.write(body)
        tmp_path = tf.name

    try:
        res = apply_patch_from_zip(tmp_path, backup=True)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Failed to apply patch"))
        return res
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.post("/api/system/restart")
def restart_server():
    """Trigger clean, detached server restart."""
    from app.updater import restart_server_process
    restart_server_process()
    return {"success": True, "message": "Server restart initiated. Reconnecting in 3 seconds..."}


