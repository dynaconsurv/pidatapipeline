"""
FastAPI application for the AVEVA PI to Oracle ERP Cloud Data Pipeline.
Serves REST endpoints for configuration, live monitoring, AF tree exploration,
and single-page web UI.
"""
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import load_settings, save_settings, load_mappings, save_mappings
from app.pi_client import PIWebApiClient
from app.oracle_erp_client import OracleERPCloudClient
from app.pipeline import pipeline_engine
from app.storage import get_pull_history, get_publish_history, get_logs, add_log
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

# Mount static assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
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
    """Manually trigger an immediate pull & publish cycle."""
    try:
        result = pipeline_engine.execute_cycle()
        return {"success": True, "result": result}
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
    if not config:
        stored = load_settings()
        config = stored.get("pi_web_api", {})
    client = PIWebApiClient(config)
    result = client.test_connection()
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


