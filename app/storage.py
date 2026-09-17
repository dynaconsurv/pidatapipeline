"""
JSON file-backed storage for pipeline operational data:
- Pull history (last N pulls with detailed attribute information)
- Publish history (ERP push attempts / pending status records)
- Audit & error logs
Strictly file-based; no database engine used.
"""
import json
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
PULL_HISTORY_FILE = os.path.join(DATA_DIR, "pull_history.json")
PUBLISH_HISTORY_FILE = os.path.join(DATA_DIR, "publish_history.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.json")

_storage_lock = threading.RLock()
MAX_HISTORY_ENTRIES = 100
MAX_LOG_ENTRIES = 200


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -------------------------------------------------------------
# Pull History Management
# -------------------------------------------------------------
def get_pull_history(limit: int = 50) -> List[Dict[str, Any]]:
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(PULL_HISTORY_FILE):
            return []
        try:
            with open(PULL_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data[:limit] if isinstance(data, list) else []
        except Exception:
            return []


def record_pull_batch(batch_record: Dict[str, Any]) -> None:
    """
    batch_record contains:
    - pull_id: str
    - timestamp: ISO string
    - success: bool
    - count: int
    - duration_ms: float
    - error: str or None
    - items: list of {attribute_name, full_path, value, uom, value_timestamp, quality, status}
    """
    ensure_data_dir()
    with _storage_lock:
        current: List[Dict[str, Any]] = []
        if os.path.exists(PULL_HISTORY_FILE):
            try:
                with open(PULL_HISTORY_FILE, "r", encoding="utf-8") as f:
                    current = json.load(f)
                    if not isinstance(current, list):
                        current = []
            except Exception:
                current = []

        current.insert(0, batch_record)
        current = current[:MAX_HISTORY_ENTRIES]

        with open(PULL_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)


# -------------------------------------------------------------
# Publish History Management
# -------------------------------------------------------------
def get_publish_history(limit: int = 50) -> List[Dict[str, Any]]:
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(PUBLISH_HISTORY_FILE):
            return []
        try:
            with open(PUBLISH_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data[:limit] if isinstance(data, list) else []
        except Exception:
            return []


def record_publish_event(publish_record: Dict[str, Any]) -> None:
    """
    publish_record contains:
    - publish_id: str
    - timestamp: ISO string
    - status: 'SUCCESS' | 'FAILED' | 'PENDING_SETUP'
    - message: str
    - record_count: int
    - target_endpoint: str
    - http_code: int or None
    - payload_sample: dict or list
    - response_body: str or dict or None
    - error_detail: str or None
    """
    ensure_data_dir()
    with _storage_lock:
        current: List[Dict[str, Any]] = []
        if os.path.exists(PUBLISH_HISTORY_FILE):
            try:
                with open(PUBLISH_HISTORY_FILE, "r", encoding="utf-8") as f:
                    current = json.load(f)
                    if not isinstance(current, list):
                        current = []
            except Exception:
                current = []

        current.insert(0, publish_record)
        current = current[:MAX_HISTORY_ENTRIES]

        with open(PUBLISH_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)


# -------------------------------------------------------------
# Log Management
# -------------------------------------------------------------
def add_log(level: str, category: str, message: str, details: Any = None) -> None:
    ensure_data_dir()
    entry = {
        "timestamp": _now_iso(),
        "level": level.upper(),  # INFO, WARNING, ERROR, SUCCESS
        "category": category.upper(),  # PI_WEB_API, ORACLE_ERP, PIPELINE, SYSTEM
        "message": message,
        "details": details
    }
    with _storage_lock:
        current: List[Dict[str, Any]] = []
        if os.path.exists(LOGS_FILE):
            try:
                with open(LOGS_FILE, "r", encoding="utf-8") as f:
                    current = json.load(f)
                    if not isinstance(current, list):
                        current = []
            except Exception:
                current = []

        current.insert(0, entry)
        current = current[:MAX_LOG_ENTRIES]

        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)


def get_logs(limit: int = 100, category: str = None) -> List[Dict[str, Any]]:
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(LOGS_FILE):
            return []
        try:
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
                if not isinstance(logs, list):
                    return []
                if category and category.upper() != "ALL":
                    logs = [l for l in logs if l.get("category") == category.upper()]
                return logs[:limit]
        except Exception:
            return []
