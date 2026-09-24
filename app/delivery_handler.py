"""
AVEVA PI AF Notifications & Webhook Delivery Handler.
Receives push telemetry from PI System Explorer WebService REST delivery endpoints,
persists the incoming payload into data/received_deliveries.json,
and handles forwarding / dispatching to Oracle ERP Cloud.
"""
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from app.storage import (
    record_received_delivery,
    update_delivery_status,
    get_delivery_by_id,
    get_received_deliveries,
    record_publish_event,
    add_log
)
from app.config import load_settings, load_mappings
from app.oracle_erp_client import OracleERPCloudClient


def parse_pi_notification_payload(raw_data: Any) -> Tuple[str, str, str, List[Dict[str, Any]]]:
    """
    Parses various PI AF Notification WebService JSON payload structures:
    Returns: (notification_name, event_type, target_path, attributes_list)
    """
    notification_name = "PI_Notification"
    event_type = "Update"
    target_path = ""
    attributes: List[Dict[str, Any]] = []

    now_iso = datetime.now(timezone.utc).isoformat()

    if isinstance(raw_data, dict):
        # 1. Check common PI Notification fields
        notification_name = (
            raw_data.get("Notification") or
            raw_data.get("NotificationName") or
            raw_data.get("EventFrame") or
            raw_data.get("Name") or
            raw_data.get("notification") or
            raw_data.get("name") or
            "PI_Notification"
        )
        event_type = (
            raw_data.get("Event") or
            raw_data.get("EventType") or
            raw_data.get("event") or
            raw_data.get("eventType") or
            ("Test Ping" if not raw_data else "Trigger")
        )
        target_path = (
            raw_data.get("Target") or
            raw_data.get("Element") or
            raw_data.get("Path") or
            raw_data.get("target") or
            raw_data.get("element") or
            raw_data.get("path") or
            ""
        )

        # 2. Check for nested Attributes dict or list under standard PI AF keys:
        # Items (standard PI AF WebService format), Attributes, Values, Data, Content
        raw_attrs = (
            raw_data.get("Items") or
            raw_data.get("items") or
            raw_data.get("Attributes") or
            raw_data.get("attributes") or
            raw_data.get("Values") or
            raw_data.get("values") or
            raw_data.get("Data") or
            raw_data.get("data") or
            raw_data.get("Content") or
            raw_data.get("content")
        )

        if isinstance(raw_attrs, dict):
            for attr_name, attr_val in raw_attrs.items():
                if isinstance(attr_val, dict):
                    val = attr_val.get("Value") if "Value" in attr_val else attr_val.get("value", attr_val)
                    if isinstance(val, dict):
                        val = val.get("Value", val.get("value", val))
                    attributes.append({
                        "name": attr_name,
                        "value": val,
                        "uom": attr_val.get("UOM", attr_val.get("uom", "")),
                        "timestamp": attr_val.get("Timestamp", attr_val.get("time", now_iso)),
                        "quality": attr_val.get("Quality", attr_val.get("quality", "Good"))
                    })
                else:
                    attributes.append({
                        "name": attr_name,
                        "value": attr_val,
                        "uom": "",
                        "timestamp": now_iso,
                        "quality": "Good"
                    })
        elif isinstance(raw_attrs, list):
            for item in raw_attrs:
                if isinstance(item, dict):
                    name = (
                        item.get("Name") or
                        item.get("name") or
                        item.get("Attribute") or
                        item.get("attribute") or
                        item.get("Tag") or
                        item.get("tag") or
                        item.get("TagName") or
                        (item.get("Path", "").split("|")[-1] if "|" in item.get("Path", "") else None) or
                        f"Attribute_{len(attributes)+1}"
                    )
                    raw_val = item.get("Value") if "Value" in item else (item.get("value") if "value" in item else item.get("Val"))
                    if isinstance(raw_val, dict):
                        val = raw_val.get("Value", raw_val.get("value", raw_val))
                    else:
                        val = raw_val

                    uom = item.get("UOM") or item.get("uom") or (raw_val.get("UOM") if isinstance(raw_val, dict) else "") or ""
                    ts = item.get("Timestamp") or item.get("timestamp") or item.get("Time") or item.get("time") or now_iso
                    quality = item.get("Quality") or item.get("quality") or (raw_val.get("Quality") if isinstance(raw_val, dict) else "Good") or "Good"

                    attributes.append({
                        "name": name,
                        "value": val,
                        "uom": uom,
                        "timestamp": ts,
                        "quality": quality
                    })
                else:
                    attributes.append({
                        "name": f"Value_{len(attributes)+1}",
                        "value": item,
                        "uom": "",
                        "timestamp": now_iso,
                        "quality": "Good"
                    })
        else:
            # Flat dictionary: treat top-level key-values as attributes (excluding metadata keys)
            meta_keys = {
                "notification", "notificationname", "event", "eventtype",
                "target", "element", "path", "starttime", "endtime", "id",
                "items", "attributes", "values", "data", "content"
            }
            for k, v in raw_data.items():
                if k.lower() not in meta_keys:
                    # If v is a list of dicts (e.g. wrapper), unpack each item
                    if isinstance(v, list) and all(isinstance(x, dict) for x in v):
                        for sub_idx, sub_item in enumerate(v):
                            sub_name = sub_item.get("Name") or sub_item.get("Attribute") or sub_item.get("name") or f"{k}_{sub_idx+1}"
                            sub_raw = sub_item.get("Value") if "Value" in sub_item else sub_item.get("value", sub_item)
                            if isinstance(sub_raw, dict):
                                sub_val = sub_raw.get("Value", sub_raw.get("value", sub_raw))
                            else:
                                sub_val = sub_raw
                            attributes.append({
                                "name": sub_name,
                                "value": sub_val,
                                "uom": sub_item.get("UOM", sub_item.get("uom", "")),
                                "timestamp": sub_item.get("Timestamp", sub_item.get("Time", now_iso)),
                                "quality": sub_item.get("Quality", "Good")
                            })
                    elif isinstance(v, dict):
                        attributes.append({
                            "name": k,
                            "value": v.get("Value", v.get("value", str(v))),
                            "uom": v.get("UOM", v.get("uom", "")),
                            "timestamp": v.get("Timestamp", v.get("time", now_iso)),
                            "quality": v.get("Quality", "Good")
                        })
                    else:
                        attributes.append({
                            "name": k,
                            "value": v,
                            "uom": "",
                            "timestamp": now_iso,
                            "quality": "Good"
                        })

    elif isinstance(raw_data, list):
        # Array of attribute readings
        for item in raw_data:
            if isinstance(item, dict):
                name = (
                    item.get("Name") or
                    item.get("name") or
                    item.get("Attribute") or
                    item.get("attribute") or
                    item.get("Tag") or
                    item.get("tag") or
                    item.get("TagName") or
                    (item.get("Path", "").split("|")[-1] if "|" in item.get("Path", "") else None) or
                    f"Attribute_{len(attributes)+1}"
                )
                raw_val = item.get("Value") if "Value" in item else (item.get("value") if "value" in item else item.get("Val"))
                if isinstance(raw_val, dict):
                    val = raw_val.get("Value", raw_val.get("value", raw_val))
                else:
                    val = raw_val

                uom = item.get("UOM") or item.get("uom") or (raw_val.get("UOM") if isinstance(raw_val, dict) else "") or ""
                ts = item.get("Timestamp") or item.get("timestamp") or item.get("Time") or item.get("time") or now_iso
                quality = item.get("Quality") or item.get("quality") or (raw_val.get("Quality") if isinstance(raw_val, dict) else "Good") or "Good"

                attributes.append({
                    "name": name,
                    "value": val,
                    "uom": uom,
                    "timestamp": ts,
                    "quality": quality
                })
            else:
                attributes.append({
                    "name": f"Value_{len(attributes)+1}",
                    "value": item,
                    "uom": "",
                    "timestamp": now_iso,
                    "quality": "Good"
                })

    return notification_name, event_type, target_path, attributes


def process_incoming_delivery(raw_payload: Any, client_ip: str = "Unknown") -> Dict[str, Any]:
    """
    Handles receipt of data from PI System Explorer / PI AF Notification WebService.
    Stages the payload into data/received_deliveries.json and returns tracking info.
    """
    delivery_id = f"deliv-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    notif_name, event_type, target_path, attributes = parse_pi_notification_payload(raw_payload)

    delivery_record = {
        "delivery_id": delivery_id,
        "received_at": now_iso,
        "client_ip": client_ip,
        "notification_name": notif_name,
        "event_type": event_type,
        "target_path": target_path,
        "attribute_count": len(attributes),
        "attributes_summary": attributes,
        "raw_payload": raw_payload,
        "oracle_status": "PENDING_ORACLE",
        "oracle_dispatch": None
    }

    record_received_delivery(delivery_record)
    add_log(
        "INFO",
        "PI_DELIVERY",
        f"Received PI Notification data [{notif_name}] with {len(attributes)} attributes from {client_ip}. Staged in JSON.",
        {"delivery_id": delivery_id, "attributes_count": len(attributes)}
    )

    # Step 2: Immediate Auto-Dispatch to Oracle ERP Cloud upon receipt
    settings = load_settings()
    erp_cfg = settings.get("oracle_erp", {})
    auto_dispatch_enabled = settings.get("pipeline", {}).get("auto_dispatch", True) and settings.get("pipeline", {}).get("auto_dispatch_deliveries", True)

    if erp_cfg.get("enabled", False) and auto_dispatch_enabled:
        try:
            dispatch_result = dispatch_delivery_to_oracle(delivery_id, is_retry=False, retry_count=0)
            delivery_record["oracle_status"] = dispatch_result.get("status", "DISPATCHED")
            delivery_record["oracle_dispatch"] = dispatch_result
            if delivery_record["oracle_status"] == "DISPATCHED":
                add_log(
                    "SUCCESS",
                    "ORACLE_ERP",
                    f"Immediate auto-dispatch succeeded for PI delivery [{notif_name}] ({delivery_id}) to Oracle ERP Cloud."
                )
            else:
                interval = settings.get("pipeline", {}).get("interval_seconds", 30)
                add_log(
                    "WARNING",
                    "ORACLE_ERP",
                    f"Immediate dispatch for [{notif_name}] ({delivery_id}) failed: {dispatch_result.get('message')}. Queued for scheduler retry every {interval}s."
                )
        except Exception as e:
            delivery_record["oracle_status"] = "FAILED"
            interval = settings.get("pipeline", {}).get("interval_seconds", 30)
            add_log(
                "WARNING",
                "ORACLE_ERP",
                f"Immediate dispatch exception for [{notif_name}] ({delivery_id}): {str(e)}. Queued for scheduler retry every {interval}s."
            )
    elif not erp_cfg.get("enabled", False):
        dispatch_info = {
            "status": "PENDING_SETUP",
            "message": "Oracle ERP Cloud integration is not enabled in settings. Delivery held in JSON staging.",
            "dispatched_at": now_iso
        }
        update_delivery_status(delivery_id, "PENDING_SETUP", dispatch_info)
        delivery_record["oracle_status"] = "PENDING_SETUP"
        delivery_record["oracle_dispatch"] = dispatch_info

    return {
        "success": True,
        "delivery_id": delivery_id,
        "received_at": now_iso,
        "notification_name": notif_name,
        "attribute_count": len(attributes),
        "staged_file": "data/received_deliveries.json",
        "oracle_status": delivery_record["oracle_status"],
        "message": f"Successfully received and staged in data/received_deliveries.json (Status: {delivery_record['oracle_status']})"
    }


def dispatch_delivery_to_oracle(delivery_id: str, is_retry: bool = False, retry_count: int = 0) -> Dict[str, Any]:
    """
    Reads a staged delivery record from JSON, maps its attributes, and dispatches to Oracle ERP Cloud.
    """
    delivery = get_delivery_by_id(delivery_id)
    if not delivery:
        raise ValueError(f"Delivery record {delivery_id} not found in storage.")

    settings = load_settings()
    erp_cfg = settings.get("oracle_erp", {})
    erp_client = OracleERPCloudClient(erp_cfg)

    # Check if Oracle ERP is configured & enabled
    if not erp_cfg.get("enabled", False):
        dispatch_info = {
            "status": "PENDING_SETUP",
            "message": "Oracle ERP Cloud integration is not enabled in settings.json. Delivery held in JSON staging.",
            "dispatched_at": datetime.now(timezone.utc).isoformat()
        }
        update_delivery_status(delivery_id, "PENDING_SETUP", dispatch_info)
        return dispatch_info

    # Build Oracle ERP Payload based on attributes & mappings
    mappings = load_mappings()
    enabled_mappings = [m for m in mappings if m.get("enabled", True)]
    mapping_by_name = {m.get("attribute_name", "").strip().lower(): m for m in enabled_mappings}

    items_to_send = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for attr in delivery.get("attributes_summary", []):
        attr_name = attr.get("name", "")
        m = mapping_by_name.get(attr_name.strip().lower(), {})

        target_field = m.get("target_field", "readingValue")
        target_tag_field = m.get("target_tag_field", "meterCode")
        meter_tag = m.get("meter_tag") or attr_name

        scale = float(m.get("scale_factor", 1.0))
        raw_val = attr.get("value")
        scaled_val = raw_val
        try:
            scaled_val = round(float(raw_val) * scale, 4)
        except Exception:
            pass

        items_to_send.append({
            target_tag_field: meter_tag,
            target_field: scaled_val,
            "readingTimestamp": attr.get("timestamp", now_iso),
            "unitOfMeasure": m.get("uom") or attr.get("uom", ""),
            "sourceQuality": attr.get("quality", "Good")
        })

    erp_payload = {
        "sourceSystem": "AVEVA_PI_NOTIFICATION",
        "notificationName": delivery.get("notification_name"),
        "deliveryId": delivery_id,
        "batchTimestamp": now_iso,
        "itemCount": len(items_to_send),
        "items": items_to_send
    }

    publish_result = erp_client.publish_data(erp_payload)

    if publish_result.get("status") == "SUCCESS":
        status = "SUCCESS"
        oracle_status = "DISPATCHED"
    elif publish_result.get("status") == "PENDING_SETUP":
        status = "PENDING_SETUP"
        oracle_status = "PENDING_SETUP"
    else:
        status = "FAILED"
        oracle_status = "FAILED"

    is_success = (status == "SUCCESS")

    dispatch_info = {
        "status": oracle_status,
        "http_code": publish_result.get("http_code"),
        "message": publish_result.get("message"),
        "dispatched_at": now_iso,
        "items_count": len(items_to_send),
        "is_retry": is_retry,
        "retry_count": retry_count,
        "erp_response": publish_result.get("response_body"),
        "error": publish_result.get("error_detail")
    }

    update_delivery_status(delivery_id, oracle_status, dispatch_info, retry_count=retry_count)

    # Record in publish history
    publish_record = {
        "publish_id": f"pub-{delivery_id}" if not is_retry else f"pub-{delivery_id}-r{retry_count}",
        "timestamp": now_iso,
        "status": status,
        "message": publish_result.get("message", "Dispatched from PI Delivery Endpoint"),
        "record_count": len(items_to_send),
        "target_endpoint": erp_cfg.get("base_url", "") + erp_cfg.get("resource_endpoint", ""),
        "http_code": publish_result.get("http_code"),
        "payload_sample": erp_payload,
        "response_body": publish_result.get("response_body"),
        "error_detail": publish_result.get("error_detail")
    }
    record_publish_event(publish_record)

    retry_label = f" (Retry attempt #{retry_count})" if is_retry else ""
    add_log(
        "SUCCESS" if is_success else "ERROR",
        "ORACLE_ERP",
        f"Delivery {delivery_id}{retry_label} dispatch to Oracle ERP: {status}. HTTP {publish_result.get('http_code')}",
        dispatch_info
    )

    return dispatch_info


def dispatch_all_pending_deliveries() -> Dict[str, Any]:
    """
    Scans staged deliveries for any in FAILED, PENDING_RETRY, or PENDING_ORACLE state and retries dispatching them to Oracle ERP.
    Only triggers on deliveries that failed or are pending; already dispatched deliveries are untouched.
    """
    settings = load_settings()
    erp_cfg = settings.get("oracle_erp", {})
    auto_dispatch_enabled = settings.get("pipeline", {}).get("auto_dispatch", True) and settings.get("pipeline", {}).get("auto_dispatch_deliveries", True)

    if not auto_dispatch_enabled or not erp_cfg.get("enabled", False):
        return {
            "total_pending": 0,
            "dispatched": 0,
            "failed": 0,
            "errors": [],
            "message": "Auto-dispatch disabled or Oracle ERP not configured."
        }

    all_deliveries = get_received_deliveries(limit=200)
    # Target only deliveries that failed or are pending retry/setup
    pending = [
        d for d in all_deliveries
        if d.get("oracle_status") in ("FAILED", "PENDING_RETRY", "PENDING_ORACLE", "PENDING_SETUP")
    ]

    if not pending:
        # All deliveries are already DISPATCHED - nothing to retry
        return {
            "total_pending": 0,
            "dispatched": 0,
            "failed": 0,
            "errors": [],
            "message": "No failed or pending deliveries to retry."
        }

    dispatched = 0
    failed = 0
    errors = []

    for d in pending:
        deliv_id = d.get("delivery_id")
        current_retry = d.get("retry_count", 0) + 1
        try:
            res = dispatch_delivery_to_oracle(deliv_id, is_retry=True, retry_count=current_retry)
            if res.get("status") == "DISPATCHED":
                dispatched += 1
            else:
                failed += 1
                if res.get("message"):
                    errors.append(f"{deliv_id}: {res['message']}")
        except Exception as e:
            failed += 1
            errors.append(f"{deliv_id}: {str(e)}")

    if dispatched > 0:
        add_log(
            "SUCCESS",
            "ORACLE_ERP",
            f"Scheduler retry cycle: Successfully forwarded {dispatched} previously failed/pending delivery(ies) to Oracle ERP Cloud."
        )

    return {
        "total_pending": len(pending),
        "dispatched": dispatched,
        "failed": failed,
        "errors": errors
    }

