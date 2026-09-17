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

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start background pipeline if configured
    settings = load_settings()
    if settings.get("pipeline", {}).get("auto_start", True):
        pipeline_engine.start()
    add_log("INFO", "SYSTEM", "AVEVA PI to Oracle ERP Cloud Pipeline Server ready.")
    yield
    # Shutdown: stop pipeline
    pipeline_engine.stop()


app = FastAPI(
    title="AVEVA PI to Oracle ERP Cloud Data Pipeline",
    description="Industrial IoT data pipeline pulling telemetry from AVEVA PI Web API and streaming into Oracle ERP Cloud.",
    version="1.0.0",
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
    settings = load_settings()
    mappings = load_mappings()
    enabled = [m for m in mappings if m.get("enabled", True)]

    # Fetch sample/simulated readings for enabled mappings
    client = PIWebApiClient(settings.get("pi_web_api", {}))
    sample_items = [client.fetch_attribute_value(m) for m in enabled]

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
