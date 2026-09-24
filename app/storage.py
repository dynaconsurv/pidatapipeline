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
from typing import Dict, Any, List, Optional

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
PULL_HISTORY_FILE = os.path.join(DATA_DIR, "pull_history.json")
PUBLISH_HISTORY_FILE = os.path.join(DATA_DIR, "publish_history.json")
DELIVERIES_FILE = os.path.join(DATA_DIR, "received_deliveries.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.json")

_storage_lock = threading.RLock()
MAX_HISTORY_ENTRIES = 100
MAX_DELIVERY_ENTRIES = 200
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


# -------------------------------------------------------------
# PI Delivery / Webhook Ingestion Management
# -------------------------------------------------------------
def get_received_deliveries(limit: int = 50, status: str = None) -> List[Dict[str, Any]]:
    """Retrieve list of received deliveries from PI System Explorer / Notifications."""
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(DELIVERIES_FILE):
            return []
        try:
            with open(DELIVERIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return []
                if status and status.upper() != "ALL":
                    data = [d for d in data if d.get("oracle_status") == status.upper()]
                return data[:limit]
        except Exception:
            return []


def get_delivery_by_id(delivery_id: str) -> Optional[Dict[str, Any]]:
    """Find a specific delivery by its ID."""
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(DELIVERIES_FILE):
            return None
        try:
            with open(DELIVERIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return None
                for d in data:
                    if d.get("delivery_id") == delivery_id:
                        return d
        except Exception:
            pass
        return None


def record_received_delivery(delivery_record: Dict[str, Any]) -> None:
    """
    Persist an incoming delivery from PI Notification / WebService into data/received_deliveries.json
    delivery_record contains:
    - delivery_id: str
    - received_at: ISO timestamp
    - client_ip: str
    - notification_name: str
    - event_type: str
    - target_path: str
    - attribute_count: int
    - attributes_summary: list of {name, value, uom, quality, timestamp}
    - raw_payload: dict or list or str
    - oracle_status: 'PENDING_ORACLE' | 'DISPATCHED' | 'FAILED'
    - oracle_dispatch: dict or None
    """
    ensure_data_dir()
    with _storage_lock:
        current: List[Dict[str, Any]] = []
        if os.path.exists(DELIVERIES_FILE):
            try:
                with open(DELIVERIES_FILE, "r", encoding="utf-8") as f:
                    current = json.load(f)
                    if not isinstance(current, list):
                        current = []
            except Exception:
                current = []

        current.insert(0, delivery_record)
        current = current[:MAX_DELIVERY_ENTRIES]

        with open(DELIVERIES_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)


def update_delivery_status(
    delivery_id: str,
    oracle_status: str,
    oracle_dispatch: Dict[str, Any] = None,
    retry_count: Optional[int] = None
) -> bool:
    """Update the Oracle dispatch status of a specific delivery record."""
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(DELIVERIES_FILE):
            return False
        try:
            with open(DELIVERIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return False

            updated = False
            for d in data:
                if d.get("delivery_id") == delivery_id:
                    d["oracle_status"] = oracle_status
                    if oracle_dispatch:
                        d["oracle_dispatch"] = oracle_dispatch
                    if retry_count is not None:
                        d["retry_count"] = retry_count
                    d["updated_at"] = _now_iso()
                    updated = True
                    break

            if updated:
                with open(DELIVERIES_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            return updated
        except Exception:
            return False


def delete_received_delivery(delivery_id: str) -> bool:
    """Delete a single delivery from data/received_deliveries.json."""
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(DELIVERIES_FILE):
            return False
        try:
            with open(DELIVERIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return False

            original_len = len(data)
            data = [d for d in data if d.get("delivery_id") != delivery_id]
            if len(data) < original_len:
                with open(DELIVERIES_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return True
            return False
        except Exception:
            return False


def clear_received_deliveries(status_filter: Optional[str] = None) -> int:
    """
    Clears deliveries from data/received_deliveries.json.
    - status_filter: None or 'ALL': removes all staged deliveries.
    - status_filter: 'PENDING': removes only unsent deliveries (PENDING_ORACLE, PENDING_SETUP, FAILED).
    - status_filter: 'DISPATCHED': removes only already dispatched deliveries.
    Returns count of deleted items.
    """
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(DELIVERIES_FILE):
            return 0
        try:
            with open(DELIVERIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return 0

            original_len = len(data)
            filter_mode = (status_filter or "ALL").upper()
            if filter_mode == "ALL":
                data = []
            elif filter_mode == "PENDING":
                # Keep only already dispatched, discard pending/failed
                data = [d for d in data if d.get("oracle_status") == "DISPATCHED"]
            elif filter_mode == "DISPATCHED":
                # Keep only pending/failed, discard already dispatched
                data = [d for d in data if d.get("oracle_status") != "DISPATCHED"]

            deleted_count = original_len - len(data)
            with open(DELIVERIES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return deleted_count
        except Exception:
            return 0


def clear_pull_history() -> int:
    """Clears all records in data/pull_history.json."""
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(PULL_HISTORY_FILE):
            return 0
        try:
            with open(PULL_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                count = len(data) if isinstance(data, list) else 0
            with open(PULL_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
            return count
        except Exception:
            return 0


def clear_publish_history() -> int:
    """Clears all records in data/publish_history.json."""
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(PUBLISH_HISTORY_FILE):
            return 0
        try:
            with open(PUBLISH_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                count = len(data) if isinstance(data, list) else 0
            with open(PUBLISH_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
            return count
        except Exception:
            return 0


def clear_logs() -> int:
    """Clears all records in data/logs.json."""
    ensure_data_dir()
    with _storage_lock:
        if not os.path.exists(LOGS_FILE):
            return 0
        try:
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                count = len(data) if isinstance(data, list) else 0
            with open(LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
            return count
        except Exception:
            return 0


def clear_all_operational_data() -> Dict[str, int]:
    """
    Clears all staged deliveries, pull history, and publish history.
    Preserves config/settings.json and config/mappings.json.
    """
    deliv_count = clear_received_deliveries(status_filter="ALL")
    pull_count = clear_pull_history()
    pub_count = clear_publish_history()
    add_log(
        "INFO",
        "SYSTEM",
        f"Operational data purged: {deliv_count} deliveries, {pull_count} pulls, {pub_count} publish records."
    )
    return {
        "deliveries_deleted": deliv_count,
        "pulls_deleted": pull_count,
        "publishes_deleted": pub_count
    }

