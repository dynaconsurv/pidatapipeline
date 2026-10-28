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
from app.config import load_settings, load_mappings, save_mappings
from app.oracle_erp_client import OracleERPCloudClient, format_ords_timestamp
from app.j5_client import J5Client, DEFAULT_J5_URL, format_j5_timestamp


def is_j5_param_enabled(val: Any) -> bool:
    """
    Determines whether an incoming 'J5' parameter value indicates J5 dispatch/auto-mapping should be enabled.
    When the 'J5' parameter key is provided by PI AF, any non-false value (including empty string '', 'true',
    '1', 'yes', 'J5', or a custom URL/tag) enables J5.
    """
    if val is None or val is False:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("false", "0", "no", "off", "disabled", "none", "null", "n"):
            return False
        return True
    return bool(val)


def extract_j5_flag_and_url(source_dict: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """
    Checks a dictionary (case-insensitive) for a 'J5' parameter.
    Returns (is_j5_enabled, custom_j5_url_if_any).
    """
    if not isinstance(source_dict, dict):
        return False, None
    for k, v in source_dict.items():
        if k is not None and str(k).strip().lower() == "j5":
            enabled = is_j5_param_enabled(v)
            custom_url = None
            if enabled and isinstance(v, str):
                v_clean = v.strip().strip('"').strip("'")
                if v_clean.lower().startswith(("http://", "https://")):
                    custom_url = v_clean
            return enabled, custom_url
    return False, None


def validate_delivery_security(
    client_ip: str,
    headers: Optional[Dict[str, str]] = None,
    query_params: Optional[Dict[str, str]] = None
) -> Tuple[bool, int, str]:
    """
    Validates incoming delivery against endpoint security settings:
    Option 1: API Key / Shared Secret Token
    Option 2: IP Whitelisting
    Returns: (is_valid, http_status_code, error_message)
    """
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    query_params = {k.lower(): v for k, v in (query_params or {}).items()}

    settings = load_settings()
    sec_cfg = settings.get("endpoint_security", {})

    # 1. Option 2: IP Whitelisting Check
    if sec_cfg.get("ip_whitelist_enabled", False):
        raw_allowed = (sec_cfg.get("allowed_ips") or "").strip()
        if raw_allowed:
            allowed_list = [ip.strip() for ip in raw_allowed.replace(";", ",").split(",") if ip.strip()]
            # Always permit localhost/loopback or testclient for local debugging
            is_local = client_ip in ("127.0.0.1", "::1", "localhost", "testclient")
            if not is_local and client_ip not in allowed_list:
                msg = f"Forbidden: Client IP [{client_ip}] is not authorized. Allowed IPs: {', '.join(allowed_list)}"
                add_log(
                    "WARNING",
                    "SECURITY",
                    f"Blocked unauthorized delivery push from non-whitelisted IP: {client_ip}",
                    {"client_ip": client_ip, "allowed_ips": allowed_list}
                )
                return False, 403, msg

    # 2. Option 1: API Key Check
    if sec_cfg.get("api_key_enabled", False):
        expected_key = (sec_cfg.get("api_key") or "").strip()
        if expected_key:
            # Check Header: X-API-Key or API-Key
            provided_key = headers.get("x-api-key") or headers.get("api-key")

            # Check Header: Authorization: Bearer <key> or Apikey <key>
            if not provided_key and "authorization" in headers:
                auth_val = headers["authorization"].strip()
                if auth_val.lower().startswith("bearer "):
                    provided_key = auth_val[7:].strip()
                elif auth_val.lower().startswith("apikey "):
                    provided_key = auth_val[7:].strip()

            # Check URL query param: ?api_key=<key> or ?key=<key> or ?token=<key>
            if not provided_key:
                provided_key = query_params.get("api_key") or query_params.get("key") or query_params.get("token")

            if not provided_key or provided_key != expected_key:
                msg = "Unauthorized: Missing or invalid API Key. Include 'X-API-Key' header or '?api_key=' URL parameter."
                add_log(
                    "WARNING",
                    "SECURITY",
                    f"Blocked unauthorized delivery from {client_ip}: Missing or invalid API Key.",
                    {"client_ip": client_ip, "has_provided_key": bool(provided_key)}
                )
                return False, 401, msg

    return True, 200, "Authorized"


def extract_direct_telemetry_record(
    item_dict: Dict[str, Any],
    default_timestamp: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Checks if a dictionary represents a direct PI Notification telemetry record containing
    fields like Tagname, Description, Value, Limit, Result, Timestamp (instead of being wrapped in Items).
    Returns parsed attribute dictionary or None if not a direct record.
    """
    if not isinstance(item_dict, dict) or not item_dict:
        return None

    lower_map = {str(k).strip().lower(): v for k, v in item_dict.items() if k is not None}

    # Identify if direct variables exist
    has_tagname = any(k in lower_map for k in ("tagname", "tag_name", "meter_tag"))
    has_tag = has_tagname or ("tag" in lower_map and "notification" not in str(lower_map.get("tag", "")).lower())
    has_attr_key = any(k in lower_map for k in ("attribute", "attribute_name", "attributename", "name"))
    has_val = any(k in lower_map for k in ("value", "val", "readingvalue", "reading_value"))
    has_desc = any(k in lower_map for k in ("description", "desc"))
    has_limit = any(k in lower_map for k in ("limit", "limits"))
    has_result = any(k in lower_map for k in ("result", "results"))
    j5_enabled, j5_custom_url = extract_j5_flag_and_url(item_dict)

    # Direct telemetry record condition:
    # 1. Has Tagname/Tag and Value
    # 2. Or has Value and (Description or Limit or Result or J5 or Attribute/Name)
    # 3. Or has Tagname/Attribute and (Description or Limit or Result or J5)
    is_direct = (
        (has_tag and has_val) or
        (has_val and (has_desc or has_limit or has_result or j5_enabled or has_attr_key)) or
        ((has_tag or has_attr_key) and (has_desc or has_limit or has_result or j5_enabled))
    )

    if not is_direct:
        return None

    # Tag extraction
    tag_val = (
        lower_map.get("tagname") or
        lower_map.get("tag_name") or
        lower_map.get("tag") or
        lower_map.get("meter_tag") or
        lower_map.get("name") or
        lower_map.get("attribute") or
        lower_map.get("attribute_name") or
        lower_map.get("attributename") or
        ""
    )

    explicit_attr_name = (
        lower_map.get("attribute") or
        lower_map.get("attribute_name") or
        lower_map.get("attributename") or
        None
    )

    # Description extraction
    desc_val = (
        lower_map.get("description") or
        lower_map.get("desc") or
        ""
    )

    # Value extraction
    raw_val = None
    if "value" in lower_map:
        raw_val = lower_map["value"]
    elif "val" in lower_map:
        raw_val = lower_map["val"]
    elif "readingvalue" in lower_map:
        raw_val = lower_map["readingvalue"]
    elif "reading_value" in lower_map:
        raw_val = lower_map["reading_value"]

    if isinstance(raw_val, dict):
        raw_val = raw_val.get("Value", raw_val.get("value", raw_val))

    # Limit extraction
    limit_val = (
        lower_map.get("limit") if "limit" in lower_map else
        lower_map.get("limits") if "limits" in lower_map else
        ""
    )

    # Result extraction
    result_val = (
        lower_map.get("result") if "result" in lower_map else
        lower_map.get("results") if "results" in lower_map else
        ""
    )

    # Timestamp extraction
    ts_val = (
        lower_map.get("timestamp") or
        lower_map.get("time") or
        lower_map.get("starttime") or
        lower_map.get("start_time") or
        lower_map.get("readingtimestamp") or
        default_timestamp or
        datetime.now(timezone.utc).isoformat()
    )

    # UOM extraction
    uom_val = lower_map.get("uom") or lower_map.get("unit") or lower_map.get("unitofmeasure") or ""

    # Target endpoint override (if PI notification specifies an explicit individual URL)
    target_endpoint = (
        lower_map.get("target_endpoint_url") or
        lower_map.get("endpoint_url") or
        lower_map.get("target_endpoint") or
        lower_map.get("endpoint") or
        None
    )

    quality_val = (
        lower_map.get("quality") or
        ("Normal" if str(result_val).lower() in ("normal", "ok", "good") else "Good")
    )

    attr_name = str(explicit_attr_name or tag_val).strip() or str(desc_val).strip() or "PI_Telemetry"

    res_record = {
        "name": attr_name,
        "tag": str(tag_val).strip() if tag_val is not None else "",
        "description": str(desc_val).strip() if desc_val is not None else "",
        "value": raw_val,
        "limit": str(limit_val).strip() if limit_val is not None else "",
        "results": str(result_val).strip() if result_val is not None else "",
        "uom": str(uom_val).strip() if uom_val is not None else "",
        "timestamp": ts_val,
        "quality": quality_val,
        "target_endpoint_url": str(target_endpoint).strip().strip('"').strip("'") if target_endpoint else None
    }
    if j5_enabled:
        res_record["j5"] = True
        if j5_custom_url:
            res_record["target_endpoint_url_j5"] = j5_custom_url
    return res_record


def parse_pi_notification_payload(
    raw_data: Any,
    query_params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None
) -> Tuple[str, str, str, List[Dict[str, Any]]]:
    """
    Parses various PI AF Notification WebService JSON payload structures:
    Extracts notification name from URL query parameter, HTTP headers, or payload body.
    Supports direct attributes (Tagname, Description, Value, Limit, Result) as well as legacy wrapped Items.
    Returns: (notification_name, event_type, target_path, attributes_list)
    """
    query_params = {k.lower(): v for k, v in (query_params or {}).items()}
    headers = {k.lower(): v for k, v in (headers or {}).items()}

    # Priority 1: Query parameter (e.g. /api/v1/delivery?notification=MyRuleName)
    query_name = (
        query_params.get("notification") or
        query_params.get("notificationname") or
        query_params.get("name") or
        query_params.get("rule")
    )

    # Priority 2: Custom HTTP Header (e.g. X-Notification-Name: MyRuleName)
    header_name = (
        headers.get("x-notification-name") or
        headers.get("x-pi-notification") or
        headers.get("x-rule-name")
    )

    body_name = None
    event_type = "Update"
    target_path = ""
    attributes: List[Dict[str, Any]] = []

    now_iso = datetime.now(timezone.utc).isoformat()

    # Check if 'J5' extra parameter was passed via query params, headers, or top-level JSON body
    top_j5_enabled = False
    top_j5_url = None
    if "j5" in query_params:
        top_j5_enabled = is_j5_param_enabled(query_params.get("j5"))
        q_val = str(query_params.get("j5") or "").strip().strip('"').strip("'")
        if top_j5_enabled and q_val.lower().startswith(("http://", "https://")):
            top_j5_url = q_val
    elif "x-j5" in headers or "j5" in headers:
        h_val = headers.get("x-j5") if "x-j5" in headers else headers.get("j5")
        top_j5_enabled = is_j5_param_enabled(h_val)

    if isinstance(raw_data, dict):
        body_j5_enabled, body_j5_url = extract_j5_flag_and_url(raw_data)
        if body_j5_enabled:
            top_j5_enabled = True
            if body_j5_url:
                top_j5_url = body_j5_url

        # Priority 3: Body attributes
        body_name = (
            raw_data.get("NotificationRule") or
            raw_data.get("NotificationName") or
            raw_data.get("Notification") or
            raw_data.get("EventFrame") or
            raw_data.get("EventFrameName") or
            raw_data.get("Rule") or
            raw_data.get("Analysis") or
            raw_data.get("Name") or
            raw_data.get("notificationRule") or
            raw_data.get("notificationName") or
            raw_data.get("notification") or
            raw_data.get("name")
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

        # Check for nested Attributes dict or list under standard PI AF keys:
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

        # Check if raw_data itself is a direct telemetry record (Tagname, Description, Value, Limit, Result)
        direct_top = extract_direct_telemetry_record(raw_data, default_timestamp=now_iso)

        if raw_attrs and isinstance(raw_attrs, list):
            for item in raw_attrs:
                if isinstance(item, dict):
                    # Check if item is a direct telemetry record (Tagname, Description, Limit, Result, Value)
                    direct_item = extract_direct_telemetry_record(item, default_timestamp=now_iso)
                    if direct_item:
                        attributes.append(direct_item)
                    else:
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

        elif raw_attrs and isinstance(raw_attrs, dict):
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

        elif direct_top:
            # Direct attributes in top-level payload (Tagname, Description, Value, Limit, Result)
            attributes.append(direct_top)

        else:
            # Flat dictionary: treat top-level key-values as attributes (excluding metadata keys)
            meta_keys = {
                "notification", "notificationname", "notificationrule", "event", "eventtype",
                "target", "element", "path", "starttime", "endtime", "id",
                "items", "attributes", "values", "data", "content", "j5"
            }
            for k, v in raw_data.items():
                if k.lower() not in meta_keys:
                    # If v is a list of dicts (e.g. wrapper), unpack each item
                    if isinstance(v, list) and all(isinstance(x, dict) for x in v):
                        for sub_idx, sub_item in enumerate(v):
                            sub_direct = extract_direct_telemetry_record(sub_item, default_timestamp=now_iso)
                            if sub_direct:
                                attributes.append(sub_direct)
                            else:
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
        # Array of attribute readings or records
        for item in raw_data:
            if isinstance(item, dict):
                direct_item = extract_direct_telemetry_record(item, default_timestamp=now_iso)
                if direct_item:
                    attributes.append(direct_item)
                else:
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
                    item_j5, item_j5_url = extract_j5_flag_and_url(item)

                    attr_entry = {
                        "name": name,
                        "value": val,
                        "uom": uom,
                        "timestamp": ts,
                        "quality": quality
                    }
                    if item_j5:
                        attr_entry["j5"] = True
                        if item_j5_url:
                            attr_entry["target_endpoint_url_j5"] = item_j5_url
                    attributes.append(attr_entry)
            else:
                attributes.append({
                    "name": f"Value_{len(attributes)+1}",
                    "value": item,
                    "uom": "",
                    "timestamp": now_iso,
                    "quality": "Good"
                })

    # Propagate top-level J5 parameter flag to all extracted attributes in this push delivery
    if top_j5_enabled:
        for attr in attributes:
            attr["j5"] = True
            if top_j5_url and not attr.get("target_endpoint_url_j5"):
                attr["target_endpoint_url_j5"] = top_j5_url

    notification_name = query_name or header_name or body_name or ("PI_Notification_Ping" if not raw_data and not attributes else "PI_Notification")
    return notification_name, event_type, target_path, attributes


def ensure_j5_mapping_for_attribute(
    attr: Dict[str, Any],
    target_path: str = "",
    settings: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    When PI AF sends a push with the extra parameter 'J5', automatically creates a new attribute
    mapping in config/mappings.json if one does not already exist for that attribute, or ensures
    the existing mapping has 'j5' enabled in its target_types so data is dispatched to J5 as well.
    """
    if not attr or not attr.get("j5"):
        return None

    settings = settings or load_settings()
    if not settings.get("pipeline", {}).get("auto_create_j5_mapping", True):
        return None

    attr_name = str(attr.get("name") or attr.get("tag") or "").strip()
    attr_tag = str(attr.get("tag") or "").strip()
    if not attr_name and not attr_tag:
        return None
    if not attr_name:
        attr_name = attr_tag

    erp_cfg = settings.get("oracle_erp", {})
    oracledev_cfg = settings.get("oracledev", {})
    j5_cfg = settings.get("j5_endpoint", {})

    base_url = (erp_cfg.get("base_url") or "").rstrip("/")
    res_ep = (erp_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/").lstrip("/")
    default_oracle_url = f"{base_url}/{res_ep}" if base_url else ""

    dev_base_url = (oracledev_cfg.get("base_url") or "").rstrip("/")
    dev_res_ep = (oracledev_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/").lstrip("/")
    default_dev_url = f"{dev_base_url}/{dev_res_ep}" if dev_base_url else ""

    default_j5_url = str(attr.get("target_endpoint_url_j5") or j5_cfg.get("url") or DEFAULT_J5_URL).strip()

    mappings = load_mappings()
    a_name_l = attr_name.lower()
    a_tag_l = attr_tag.lower()

    matching = []
    for m in mappings:
        m_attr = str(m.get("attribute_name") or "").strip().lower()
        m_tag = str(m.get("tag") or m.get("meter_tag") or "").strip().lower()
        if (
            (m_attr and (m_attr == a_name_l or (a_tag_l and m_attr == a_tag_l)))
            or (m_tag and ((a_tag_l and m_tag == a_tag_l) or m_tag == a_name_l))
        ):
            matching.append(m)

    if matching:
        # Mapping already exists: ensure it is enabled and includes 'j5' in target_types if needed
        updated = False
        for m in matching:
            if not m.get("enabled", True):
                m["enabled"] = True
                updated = True
            t_types = list(m.get("target_types") or ([m.get("target_type")] if m.get("target_type") else ["oracle"]))
            if "j5" not in [str(t).strip().lower() for t in t_types]:
                t_types.append("j5")
                m["target_types"] = t_types
                updated = True
            if not m.get("target_endpoint_url_j5"):
                m["target_endpoint_url_j5"] = default_j5_url
                updated = True
        if updated:
            save_mappings(mappings)
            add_log(
                "INFO",
                "PIPELINE",
                f"Updated existing mapping for [{attr_name}] to include J5 destination (triggered by 'J5' push parameter)."
            )
        return matching[0]

    # Mapping does not exist: automatically create a new mapping with J5 destination enabled as well
    target_types = []
    if erp_cfg.get("enabled", True):
        target_types.append("oracle")
    if oracledev_cfg.get("enabled", False):
        target_types.append("oracledev")
    if "j5" not in target_types:
        target_types.append("j5")

    new_mapping = {
        "id": f"map-j5-{int(time.time())}-{uuid.uuid4().hex[:4]}",
        "name": str(attr.get("description") or attr_name).strip(),
        "attribute_name": attr_name,
        "af_server": "",
        "af_database": "",
        "element_path": target_path or "",
        "full_path": target_path or "",
        "target_type": target_types[0],
        "target_types": target_types,
        "target_endpoint_url": default_oracle_url or default_j5_url,
        "target_endpoint_url_oracle": default_oracle_url,
        "target_endpoint_url_dev": default_dev_url,
        "target_endpoint_url_j5": default_j5_url,
        "tag": attr_tag,
        "meter_tag": attr_tag,
        "description": str(attr.get("description") or "").strip(),
        "limit": str(attr.get("limit") or "").strip(),
        "results": str(attr.get("results") or "").strip(),
        "target_field": "value",
        "target_tag_field": "tag",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 2,
        "uom": str(attr.get("uom") or "").strip(),
        "enabled": True
    }
    mappings.append(new_mapping)
    save_mappings(mappings)
    add_log(
        "INFO",
        "PIPELINE",
        f"Auto-created new attribute mapping for [{attr_name}] with J5 destination (triggered by 'J5' push parameter).",
        {"mapping_id": new_mapping["id"], "attribute_name": attr_name, "target_types": target_types}
    )
    return new_mapping


def process_incoming_delivery(
    raw_payload: Any,
    client_ip: str = "Unknown",
    query_params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Handles receipt of data from PI System Explorer / PI AF Notification WebService.
    Stages the payload into data/received_deliveries.json and returns tracking info.
    """
    delivery_id = f"deliv-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    notif_name, event_type, target_path, attributes = parse_pi_notification_payload(
        raw_payload,
        query_params=query_params,
        headers=headers
    )

    settings = load_settings()

    # Auto-create/update attribute mapping if PI AF sent push with extra parameter "J5"
    for attr in attributes:
        if attr.get("j5"):
            ensure_j5_mapping_for_attribute(attr, target_path=target_path, settings=settings)

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

    # Step 2: Immediate Auto-Dispatch to Oracle ERP Cloud or J5 upon receipt
    erp_cfg = settings.get("oracle_erp", {})
    oracledev_cfg = settings.get("oracledev", {})
    j5_cfg = settings.get("j5_endpoint", {})
    auto_dispatch_enabled = settings.get("pipeline", {}).get("auto_dispatch", True) and settings.get("pipeline", {}).get("auto_dispatch_deliveries", True)

    has_j5_attr = any(a.get("j5") for a in attributes)
    any_endpoint_enabled = erp_cfg.get("enabled", False) or oracledev_cfg.get("enabled", False) or j5_cfg.get("enabled", False) or has_j5_attr

    if any_endpoint_enabled and auto_dispatch_enabled:
        try:
            dispatch_result = dispatch_delivery_to_oracle(delivery_id, is_retry=False, retry_count=0)
            delivery_record["oracle_status"] = dispatch_result.get("status", "DISPATCHED")
            delivery_record["oracle_dispatch"] = dispatch_result
            if delivery_record["oracle_status"] == "DISPATCHED":
                add_log(
                    "SUCCESS",
                    "ENDPOINT_DISPATCH",
                    f"Immediate auto-dispatch succeeded for PI delivery [{notif_name}] ({delivery_id}) to destination endpoint(s)."
                )
            else:
                interval = settings.get("pipeline", {}).get("interval_seconds", 30)
                add_log(
                    "WARNING",
                    "ENDPOINT_DISPATCH",
                    f"Immediate dispatch for [{notif_name}] ({delivery_id}) failed: {dispatch_result.get('message')}. Queued for scheduler retry every {interval}s."
                )
        except Exception as e:
            delivery_record["oracle_status"] = "FAILED"
            interval = settings.get("pipeline", {}).get("interval_seconds", 30)
            add_log(
                "WARNING",
                "ENDPOINT_DISPATCH",
                f"Immediate dispatch exception for [{notif_name}] ({delivery_id}): {str(e)}. Queued for scheduler retry every {interval}s."
            )
    elif not any_endpoint_enabled:
        dispatch_info = {
            "status": "PENDING_SETUP",
            "message": "Destination endpoints (Oracle ERP / J5) are not enabled in settings. Delivery held in JSON staging.",
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
    Reads a staged delivery record from JSON, maps its attributes, and dispatches to
    configured destination endpoints (Oracle ORDS / ERP Cloud or J5 Inbound Message API).
    """
    delivery = get_delivery_by_id(delivery_id)
    if not delivery:
        raise ValueError(f"Delivery record {delivery_id} not found in storage.")

    settings = load_settings()
    erp_cfg = settings.get("oracle_erp", {})
    oracledev_cfg = settings.get("oracledev", {})
    j5_cfg = settings.get("j5_endpoint", {})
    erp_client = OracleERPCloudClient(erp_cfg)
    oracledev_client = OracleERPCloudClient(oracledev_cfg)
    j5_client = J5Client(j5_cfg)

    now_iso = datetime.now(timezone.utc).isoformat()
    raw_attrs = delivery.get("attributes_summary", [])
    if not raw_attrs:
        raw_attrs = [{
            "name": delivery.get("notification_name") or "PI_Delivery",
            "value": 0,
            "timestamp": now_iso,
            "quality": "Good"
        }]

    # Ensure any attribute with 'j5' flag has a mapping created/updated before loading mappings
    for attr in raw_attrs:
        if attr.get("j5"):
            ensure_j5_mapping_for_attribute(attr, target_path=delivery.get("target_path", ""), settings=settings)

    # Build destination payload based on attributes & mappings
    mappings = load_mappings()
    enabled_mappings = [m for m in mappings if m.get("enabled", True)]

    item_results = []
    all_succeeded = True
    any_succeeded = False
    is_pending_setup = False

    for attr in raw_attrs:
        attr_name = attr.get("name", "")
        attr_tag = str(attr.get("tag", "")).strip().lower()
        attr_name_l = attr_name.strip().lower()

        # Check mappings: find all matching mappings (supports 1-to-many multicast)
        matching_mappings = [
            m for m in enabled_mappings
            if (
                (m.get("attribute_name") and m.get("attribute_name").strip().lower() in (attr_name_l, attr_tag) and (attr_name_l or attr_tag))
                or (attr_tag and m.get("tag") and str(m.get("tag")).strip().lower() == attr_tag)
                or (attr_tag and m.get("meter_tag") and str(m.get("meter_tag")).strip().lower() == attr_tag)
                or (attr_name_l and m.get("tag") and str(m.get("tag")).strip().lower() == attr_name_l)
            )
        ]

        # If no specific mapping matched, create fallback default mapping for direct PI delivery
        if not matching_mappings:
            raw_target = str(attr.get("target_endpoint_url") or "").strip().strip('"').strip("'")
            targets = []
            if raw_target:
                if "hxgnsmartcloud" in raw_target.lower():
                    targets.append("j5")
                elif "dev" in raw_target.lower():
                    targets.append("oracledev")
                else:
                    targets.append("oracle")
            else:
                if erp_cfg.get("enabled", False):
                    targets.append("oracle")
                if oracledev_cfg.get("enabled", False):
                    targets.append("oracledev")
                if attr.get("j5") and "j5" not in targets:
                    targets.append("j5")
                if not targets:
                    targets = ["j5"] if attr.get("j5") else ["oracle"]
            matching_mappings = [{
                "target_types": targets,
                "target_endpoint_url": raw_target or None,
                "target_endpoint_url_j5": attr.get("target_endpoint_url_j5") or None
            }]

        for m in matching_mappings:
            raw_target = str(attr.get("target_endpoint_url") or m.get("target_endpoint_url") or "").strip().strip('"').strip("'")
            target_types = list(m.get("target_types") or [])
            if not target_types:
                if m.get("target_type"):
                    target_types = [m.get("target_type")]
                else:
                    if "hxgnsmartcloud" in raw_target.lower() or "tag=purchaseorder" in raw_target.lower():
                        target_types = ["j5"]
                    elif "dev" in raw_target.lower():
                        target_types = ["oracledev"]
                    else:
                        target_types = ["oracle"]
            if attr.get("j5") and "j5" not in [str(t).strip().lower() for t in target_types]:
                target_types.append("j5")

            # Compute transformed telemetry values
            scale = float(m.get("scale_factor", 1.0))
            raw_val = attr.get("value")
            scaled_val = raw_val
            try:
                if raw_val is not None and str(raw_val).strip() != "":
                    scaled_val = round(float(raw_val) * scale, int(m.get("round_decimals", 2)))
            except Exception:
                scaled_val = raw_val

            timestamp_val = format_ords_timestamp(attr.get("timestamp") or now_iso)
            tag_val = attr.get("tag") or m.get("tag") or m.get("meter_tag") or ""
            desc_val = attr.get("description") or m.get("description") or m.get("name") or ""

            # Limit: prioritize direct attribute from PI Notification, then mapping, else empty
            if attr.get("limit") is not None and str(attr.get("limit")).strip() != "":
                limit_val = attr.get("limit")
            elif m.get("limit") is not None and str(m.get("limit")).strip() != "":
                limit_val = m.get("limit")
            else:
                limit_val = ""

            # Results: prioritize direct attribute from PI Notification, then mapping, else empty
            if attr.get("results") is not None and str(attr.get("results")).strip() != "":
                results_val = attr.get("results")
            elif attr.get("result") is not None and str(attr.get("result")).strip() != "":
                results_val = attr.get("result")
            elif m.get("results") is not None and str(m.get("results")).strip() != "":
                results_val = m.get("results")
            else:
                results_val = ""

            # UOM: prioritize direct attribute from PI Notification, then mapping
            if attr.get("uom") is not None and str(attr.get("uom")).strip() != "":
                uom_val = attr.get("uom")
            elif attr.get("UOM") is not None and str(attr.get("UOM")).strip() != "":
                uom_val = attr.get("UOM")
            elif attr.get("unit") is not None and str(attr.get("unit")).strip() != "":
                uom_val = attr.get("unit")
            elif m.get("uom") is not None and str(m.get("uom")).strip() != "":
                uom_val = m.get("uom")
            elif m.get("unit") is not None and str(m.get("unit")).strip() != "":
                uom_val = m.get("unit")
            else:
                uom_val = ""

            ords_payload = {
                "timestamp": timestamp_val,
                "tag": str(tag_val),
                "description": str(desc_val),
                "value": str(scaled_val) if scaled_val is not None else "",
                "limit": str(limit_val),
                "results": str(results_val),
                "uom": str(uom_val)
            }

            for t_type in target_types:
                t_lower = str(t_type).strip().lower()

                if t_lower == "j5":
                    if not j5_cfg.get("enabled", True) and not attr.get("j5"):
                        item_results.append({
                            "target_type": "j5",
                            "attribute_name": attr_name,
                            "target_endpoint": m.get("target_endpoint_url_j5") or (raw_target if "hxgnsmartcloud" in raw_target.lower() else None) or j5_cfg.get("url") or DEFAULT_J5_URL,
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": "J5 endpoint integration is disabled in settings.",
                            "message": "J5 integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    j5_payload = J5Client.build_j5_payload(attr, mapping=m)
                    target_url = m.get("target_endpoint_url_j5") or (raw_target if "hxgnsmartcloud" in raw_target.lower() else None) or j5_cfg.get("url") or DEFAULT_J5_URL
                    pub_res = j5_client.publish_data(j5_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": "j5",
                        "attribute_name": attr_name,
                        "target_endpoint": pub_res.get("target_endpoint"),
                        "status": pub_res.get("status"),
                        "http_code": pub_res.get("http_code"),
                        "payload": j5_payload,
                        "response": pub_res.get("response_body"),
                        "error": pub_res.get("error_detail"),
                        "message": pub_res.get("message")
                    })

                    if pub_res.get("status") == "SUCCESS":
                        any_succeeded = True
                    else:
                        all_succeeded = False

                elif t_lower in ("oracledev", "oracle_dev"):
                    if not oracledev_cfg.get("enabled", False):
                        item_results.append({
                            "target_type": "oracledev",
                            "attribute_name": attr_name,
                            "target_endpoint": m.get("target_endpoint_url_dev") or m.get("target_endpoint_url_oracledev") or oracledev_cfg.get("base_url"),
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": "Oracle Dev integration is disabled in settings.",
                            "message": "Oracle Dev integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    target_url = m.get("target_endpoint_url_dev") or m.get("target_endpoint_url_oracledev") or (raw_target if "dev" in raw_target.lower() else None) or None
                    pub_res = oracledev_client.publish_data(ords_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": "oracledev",
                        "attribute_name": attr_name,
                        "target_endpoint": pub_res.get("target_endpoint"),
                        "status": pub_res.get("status"),
                        "http_code": pub_res.get("http_code"),
                        "payload": ords_payload,
                        "response": pub_res.get("response_body"),
                        "error": pub_res.get("error_detail"),
                        "message": pub_res.get("message")
                    })

                    if pub_res.get("status") == "SUCCESS":
                        any_succeeded = True
                    elif pub_res.get("status") == "PENDING_SETUP":
                        is_pending_setup = True
                        all_succeeded = False
                    else:
                        all_succeeded = False

                else:
                    # Oracle ORDS / ERP Cloud Production
                    if not erp_cfg.get("enabled", False):
                        item_results.append({
                            "target_type": "oracle",
                            "attribute_name": attr_name,
                            "target_endpoint": m.get("target_endpoint_url") or m.get("target_endpoint_url_oracle") or (raw_target if "hxgnsmartcloud" not in raw_target.lower() and "dev" not in raw_target.lower() else None) or erp_cfg.get("base_url"),
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": "Oracle ERP integration is disabled in settings.",
                            "message": "Oracle ERP integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    target_url = m.get("target_endpoint_url") or m.get("target_endpoint_url_oracle") or (raw_target if "hxgnsmartcloud" not in raw_target.lower() and "dev" not in raw_target.lower() else None) or None
                    pub_res = erp_client.publish_data(ords_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": "oracle",
                        "attribute_name": attr_name,
                        "target_endpoint": pub_res.get("target_endpoint"),
                        "status": pub_res.get("status"),
                        "http_code": pub_res.get("http_code"),
                        "payload": ords_payload,
                        "response": pub_res.get("response_body"),
                        "error": pub_res.get("error_detail"),
                        "message": pub_res.get("message")
                    })

                    if pub_res.get("status") == "SUCCESS":
                        any_succeeded = True
                    elif pub_res.get("status") == "PENDING_SETUP":
                        is_pending_setup = True
                        all_succeeded = False
                    else:
                        all_succeeded = False

    if all_succeeded and item_results:
        status = "SUCCESS"
        oracle_status = "DISPATCHED"
    elif is_pending_setup and not any_succeeded:
        status = "PENDING_SETUP"
        oracle_status = "PENDING_SETUP"
    else:
        status = "FAILED"
        oracle_status = "FAILED"

    is_success = (status == "SUCCESS")
    primary_code = item_results[0].get("http_code") if item_results else None
    primary_endpoint = item_results[0].get("target_endpoint") if item_results else None
    payload_samples = [r["payload"] for r in item_results] if len(item_results) > 1 else (item_results[0]["payload"] if item_results else {})
    response_samples = [r["response"] for r in item_results] if len(item_results) > 1 else (item_results[0]["response"] if item_results else {})
    error_msgs = [f"[{r['attribute_name']}]: {r['error'] or r['message']}" for r in item_results if r.get("status") != "SUCCESS"]
    error_summary = "; ".join(error_msgs) if error_msgs else None

    # Summary of target endpoints used (e.g. "Oracle", "J5", or "Oracle & J5")
    target_types_used = list(dict.fromkeys(r.get("target_type", "oracle").upper() for r in item_results))
    targets_label = " & ".join(target_types_used) if target_types_used else "Endpoint"

    dispatch_info = {
        "status": oracle_status,
        "http_code": primary_code,
        "target_endpoint": primary_endpoint,
        "target_types": target_types_used,
        "message": f"Successfully dispatched {len(item_results)} attribute(s) to {targets_label}." if is_success else f"{targets_label} dispatch failed for {len(error_msgs)} attribute(s): {error_summary}",
        "dispatched_at": now_iso,
        "items_count": len(item_results),
        "is_retry": is_retry,
        "retry_count": retry_count,
        "erp_response": response_samples,
        "error": error_summary,
        "dispatches": item_results
    }

    update_delivery_status(delivery_id, oracle_status, dispatch_info, retry_count=retry_count)

    publish_record = {
        "publish_id": f"pub-{delivery_id}" if not is_retry else f"pub-{delivery_id}-r{retry_count}",
        "timestamp": now_iso,
        "status": status,
        "message": dispatch_info["message"],
        "record_count": len(item_results),
        "target_endpoint": primary_endpoint,
        "http_code": primary_code,
        "payload_sample": payload_samples,
        "response_body": response_samples,
        "error_detail": error_summary
    }
    record_publish_event(publish_record)

    retry_label = f" (Retry attempt #{retry_count})" if is_retry else ""
    add_log(
        "SUCCESS" if is_success else "ERROR",
        "ENDPOINT_DISPATCH",
        f"Delivery {delivery_id}{retry_label} dispatch to {targets_label}: {status}. HTTP {primary_code}",
        dispatch_info
    )
    return dispatch_info

dispatch_delivery_to_endpoint = dispatch_delivery_to_oracle


def dispatch_all_pending_deliveries() -> Dict[str, Any]:
    """
    Scans staged deliveries for any in FAILED, PENDING_RETRY, or PENDING_ORACLE state and retries dispatching them to Oracle ERP.
    Only triggers on deliveries that failed or are pending; already dispatched deliveries are untouched.
    """
    settings = load_settings()
    erp_cfg = settings.get("oracle_erp", {})
    j5_cfg = settings.get("j5_endpoint", {})
    auto_dispatch_enabled = settings.get("pipeline", {}).get("auto_dispatch", True) and settings.get("pipeline", {}).get("auto_dispatch_deliveries", True)
    any_enabled = erp_cfg.get("enabled", False) or j5_cfg.get("enabled", False)

    if not auto_dispatch_enabled or not any_enabled:
        return {
            "total_pending": 0,
            "dispatched": 0,
            "failed": 0,
            "errors": [],
            "message": "Auto-dispatch disabled or destination endpoints not configured."
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

