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
MAX_DELIVERY_ENTRIES = 1000
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
def get_received_deliveries(
    limit: int = 50,
    status: Optional[str] = None,
    endpoint: Optional[str] = None,
    attribute: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
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

                # Filter by status
                if status and status.upper() != "ALL":
                    data = [d for d in data if (d.get("oracle_status") or "").upper() == status.upper()]

                # Filter by destination endpoint (e.g. 'J5' or 'ORACLE')
                if endpoint and endpoint.upper() != "ALL":
                    ep_target = endpoint.upper()
                    filtered_by_ep = []
                    for d in data:
                        target_types = [str(t).upper() for t in (d.get("oracle_dispatch") or {}).get("target_types", [])]
                        ep_url = str((d.get("oracle_dispatch") or {}).get("target_endpoint") or (d.get("oracle_dispatch") or {}).get("endpoint_url") or "").lower()
                        is_j5 = "J5" in target_types or "hxgnsmartcloud" in ep_url or "purchaseorder" in ep_url
                        is_oracle = "ORACLE" in target_types or "oraclecloudapps" in ep_url or "/ords/" in ep_url or (not is_j5)
                        if ep_target == "J5" and is_j5:
                            filtered_by_ep.append(d)
                        elif ep_target == "ORACLE" and is_oracle:
                            filtered_by_ep.append(d)
                    data = filtered_by_ep

                # Filter by attribute name or tag
                if attribute and attribute.upper() != "ALL":
                    attr_query = attribute.strip().lower()
                    filtered_by_attr = []
                    for d in data:
                        attrs = d.get("attributes_summary") or []
                        if any(
                            attr_query == str(a.get("name") or "").strip().lower() or
                            attr_query == str(a.get("tag") or "").strip().lower()
                            for a in attrs
                        ):
                            filtered_by_attr.append(d)
                    data = filtered_by_attr

                # Filter by cross-column search query
                if search and search.strip():
                    terms = search.strip().lower().split()
                    filtered_by_search = []
                    for d in data:
                        parts = [
                            str(d.get("delivery_id") or ""),
                            str(d.get("client_ip") or ""),
                            str(d.get("notification_name") or ""),
                            str(d.get("event_type") or ""),
                            str(d.get("target_path") or ""),
                            str(d.get("oracle_status") or ""),
                            str(d.get("received_at") or "")
                        ]
                        for a in (d.get("attributes_summary") or []):
                            parts.extend([
                                str(a.get("name") or ""),
                                str(a.get("tag") or ""),
                                str(a.get("description") or ""),
                                str(a.get("value") or ""),
                                str(a.get("uom") or ""),
                                str(a.get("limit") or ""),
                                str(a.get("results") or "")
                            ])
                        disp = d.get("oracle_dispatch") or {}
                        parts.extend([
                            str(disp.get("target_endpoint") or ""),
                            str(disp.get("message") or ""),
                            str(disp.get("error") or "")
                        ])
                        parts.extend([str(t) for t in disp.get("target_types", [])])
                        search_blob = " ".join(parts).lower()
                        if all(term in search_blob for term in terms):
                            filtered_by_search.append(d)
                    data = filtered_by_search

                if limit is not None and limit > 0:
                    return data[:limit]
                return data
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

