"""
AVEVA PI AF Notifications & Webhook Delivery Handler.
Receives push telemetry from PI System Explorer WebService REST delivery endpoints,
persists the incoming payload into data/received_deliveries.json,
and handles forwarding / dispatching to Oracle ERP Cloud.
"""
import json
import re
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
from app.config import load_settings, load_mappings, save_mappings, get_oracle_custom_endpoints, normalize_oracle_endpoint_key
from app.oracle_erp_client import OracleERPCloudClient, format_ords_timestamp, sanitize_endpoint_url, build_oracle_endpoint_url
from app.j5_client import J5Client, DEFAULT_J5_URL, format_j5_timestamp
from app.field_mapper import build_destination_payload


def is_j5_param_enabled(val: Any) -> bool:
    """
    Determines whether an incoming target routing parameter value (e.g. 'j5', 'j5dev', 'oracle', 'oracledev')
    indicates dispatch/auto-mapping should be enabled.
    Values like 'true', '1', 'yes', 'y', 'on', 'J5', or a custom URL enable the target;
    empty string '', 'false', '0', 'no', 'off', 'disabled', 'none', 'null', 'n' do not.
    """
    if val is None or val is False:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        s = val.strip().lower()
        if not s or s in ("false", "0", "no", "off", "disabled", "none", "null", "n"):
            return False
        return True
    return bool(val)


def is_target_param_disabled(val: Any) -> bool:
    """
    Determines whether an incoming target routing parameter value (e.g. 'oracle=no', 'oracledev=false', 'j5=0')
    explicitly requests that dispatch/auto-mapping to this target endpoint be disabled.
    """
    if val is False:
        return True
    if val is None:
        return False
    if isinstance(val, bool):
        return not val
    if isinstance(val, (int, float)):
        return val == 0
    if isinstance(val, str):
        s = val.strip().lower()
        return s in ("false", "0", "no", "off", "disabled", "none", "null", "n")
    return False


TARGET_PARAM_ALIASES: Dict[str, Tuple[str, ...]] = {
    "oracle": ("oracle", "oracle_erp", "oracleerp", "oracle_effluent", "oracleeffluent", "effluent"),
    "oracle_utility": ("oracle_utility", "oracleutility", "utility", "oracle_prod_utility"),
    "oracle_production": ("oracle_production", "oracleproduction", "oracle_daily_production", "daily_production", "dailyproduction", "production_daily_output", "oracle_prod_production", "daily_output"),
    "oracledev": ("oracledev", "oracle_dev", "oracledev_effluent", "oracle_dev_effluent"),
    "oracledev_utility": ("oracledev_utility", "oracle_dev_utility", "dev_utility"),
    "oracledev_production": ("oracledev_production", "oracle_dev_production", "dev_production", "dev_daily_production", "oracledev_daily_production", "dev_daily_output"),
    "j5": ("j5", "jf", "octave"),
    "j5dev": ("j5dev", "jfdev", "j5_dev", "jf_dev", "octavedev", "octave_dev"),
}

ENDPOINT_PARAM_KEYS = {
    "endpoint", "endpoints", "delivery_endpoint", "deliveryendpoint",
    "target_endpoint", "target_endpoints", "targetendpoint"
}

ENVIRONMENT_PARAM_KEYS = {
    "environment", "env", "stage"
}

ALL_ROUTING_PARAM_KEYS = (
    {alias for aliases in TARGET_PARAM_ALIASES.values() for alias in aliases}
    | ENDPOINT_PARAM_KEYS
    | ENVIRONMENT_PARAM_KEYS
)


def resolve_endpoint_and_env_targets(
    source_dict: Optional[Dict[str, Any]],
    fallback_env: Optional[str] = None
) -> Tuple[List[str], Dict[str, str], List[str]]:
    """
    Parses 'Endpoint' (e.g. Oracle_Effluent, Oracle_Utility, Oracle, Octave, or combinations like Oracle_Utility,Octave)
    and 'Environment' (Prod / Test) routing parameters per specification:
    - Endpoint=Oracle_Effluent (or Oracle), Environment=Prod -> Oracle Cloud Prod Effluent ('oracle')
    - Endpoint=Oracle_Effluent (or Oracle), Environment=Test -> Oracle Cloud Dev Effluent ('oracledev')
    - Endpoint=Oracle_Utility, Environment=Prod -> Oracle Cloud Prod Utility ('oracle_utility')
    - Endpoint=Oracle_Utility, Environment=Test -> Oracle Cloud Dev Utility ('oracledev_utility')
    - Endpoint=Octave, Environment=Prod -> Octave ('j5')
    - Endpoint=Octave, Environment=Test -> Octave Dev ('j5dev')
    - Endpoint=Oracle_Utility,Octave, Environment=Prod -> Oracle Cloud Prod Utility & Octave ('oracle_utility', 'j5')
    - Endpoint=Oracle_Utility,Octave, Environment=Test -> Oracle Cloud Dev Utility & Octave Dev ('oracledev_utility', 'j5dev')

    Returns: (enabled_targets, custom_urls, disabled_targets)
    """
    if not isinstance(source_dict, dict) or not source_dict:
        return [], {}, []

    lower_map: Dict[str, Any] = {}
    for k, v in source_dict.items():
        if k is not None:
            lower_map[str(k).strip().lower()] = v

    endpoint_val = None
    for ep_k in ENDPOINT_PARAM_KEYS:
        if ep_k in lower_map and lower_map[ep_k] is not None:
            raw_s = str(lower_map[ep_k]).strip()
            if raw_s:
                endpoint_val = raw_s
                break

    if not endpoint_val:
        return [], {}, []

    env_val = None
    for env_k in ENVIRONMENT_PARAM_KEYS:
        if env_k in lower_map and lower_map[env_k] is not None:
            raw_env = str(lower_map[env_k]).strip()
            if raw_env:
                env_val = raw_env
                break

    if not env_val and fallback_env:
        env_val = fallback_env

    env_lower = (env_val or "prod").strip().lower()
    is_test = env_lower in ("test", "dev", "development", "tst", "sandbox")

    # Split endpoint_val by comma, semicolon, slash, or plus
    # e.g. "Oracle_Utility,Octave", "Oracle, Octave", "Oracle_Effluent/Octave"
    raw_tokens = re.split(r"[,;/+]", endpoint_val)
    tokens = [t.strip().lower() for t in raw_tokens if t.strip()]

    wants_oracle_effluent = False
    wants_oracle_utility = False
    wants_oracle_production = False
    wants_octave = False
    wants_custom_keys: List[str] = []
    custom_urls: Dict[str, str] = {}

    custom_eps = get_oracle_custom_endpoints()
    custom_lookup: Dict[str, str] = {}
    for ce in custom_eps:
        ck = ce["key"]
        custom_lookup[ck] = ck
        custom_lookup[f"oracle_{ck}"] = ck
        custom_lookup[f"oracledev_{ck}"] = ck
        lbl_slug = normalize_oracle_endpoint_key(ce.get("label"))
        if lbl_slug:
            custom_lookup[lbl_slug] = ck
            custom_lookup[f"oracle_{lbl_slug}"] = ck
        prod_slug = normalize_oracle_endpoint_key(ce.get("prod_path"))
        if prod_slug:
            custom_lookup[prod_slug] = ck
        dev_slug = normalize_oracle_endpoint_key(ce.get("dev_path"))
        if dev_slug:
            custom_lookup[dev_slug] = ck

    for t in tokens:
        t_slug = normalize_oracle_endpoint_key(t)
        matched_custom_key = custom_lookup.get(t_slug)
        if not matched_custom_key and t_slug:
            for alias_slug, ck in custom_lookup.items():
                if alias_slug and (alias_slug == t_slug or (len(alias_slug) >= 4 and alias_slug in t_slug)):
                    matched_custom_key = ck
                    break

        if matched_custom_key:
            if matched_custom_key not in wants_custom_keys:
                wants_custom_keys.append(matched_custom_key)
            if t.startswith(("http://", "https://")):
                key = f"oracledev_{matched_custom_key}" if is_test else f"oracle_{matched_custom_key}"
                custom_urls[key] = t
        elif "utility" in t:
            wants_oracle_utility = True
            if t.startswith(("http://", "https://")):
                key = "oracledev_utility" if is_test else "oracle_utility"
                custom_urls[key] = t
        elif "production" in t or "daily" in t or "output" in t:
            wants_oracle_production = True
            if t.startswith(("http://", "https://")):
                key = "oracledev_production" if is_test else "oracle_production"
                custom_urls[key] = t
        elif "oracle" in t or "effluent" in t:
            wants_oracle_effluent = True
            if t.startswith(("http://", "https://")):
                key = "oracledev" if is_test else "oracle"
                custom_urls[key] = t
        elif any(o in t for o in ("octave", "j5", "jf")):
            wants_octave = True
            if t.startswith(("http://", "https://")):
                key = "j5dev" if is_test else "j5"
                custom_urls[key] = t

    enabled_targets: List[str] = []
    disabled_targets: List[str] = []

    if wants_oracle_effluent:
        if is_test:
            enabled_targets.append("oracledev")
            disabled_targets.append("oracle")
        else:
            enabled_targets.append("oracle")
            disabled_targets.append("oracledev")

    if wants_oracle_utility:
        if is_test:
            enabled_targets.append("oracledev_utility")
            disabled_targets.append("oracle_utility")
        else:
            enabled_targets.append("oracle_utility")
            disabled_targets.append("oracledev_utility")

    if wants_oracle_production:
        if is_test:
            enabled_targets.append("oracledev_production")
            disabled_targets.append("oracle_production")
        else:
            enabled_targets.append("oracle_production")
            disabled_targets.append("oracledev_production")

    for ck in wants_custom_keys:
        if is_test:
            enabled_targets.append(f"oracledev_{ck}")
            disabled_targets.append(f"oracle_{ck}")
        else:
            enabled_targets.append(f"oracle_{ck}")
            disabled_targets.append(f"oracledev_{ck}")

    if wants_octave:
        if is_test:
            enabled_targets.append("j5dev")
            disabled_targets.append("j5")
        else:
            enabled_targets.append("j5")
            disabled_targets.append("j5dev")

    # When explicit Endpoint is provided, any other target not requested is explicitly disabled
    all_possible = [
        "oracle", "oracle_utility", "oracle_production",
        "oracledev", "oracledev_utility", "oracledev_production",
        "j5", "j5dev"
    ]
    for ce in custom_eps:
        ck = ce["key"]
        all_possible.append(f"oracle_{ck}")
        all_possible.append(f"oracledev_{ck}")
    for p in all_possible:
        if p not in enabled_targets and p not in disabled_targets:
            disabled_targets.append(p)

    return enabled_targets, custom_urls, disabled_targets


def extract_target_flags_and_urls(
    source_dict: Optional[Dict[str, Any]],
    fallback_env: Optional[str] = None
) -> Tuple[List[str], Dict[str, str], List[str]]:
    """
    Checks a dictionary (case-insensitive) for target routing parameters:
    1. New standard: 'Endpoint' (Oracle / Octave / Oracle,Octave) and 'Environment' (Prod / Test)
    2. Legacy individual flags: j5 / jf / octave, j5dev / octavedev, oracle, oracledev
    Returns (enabled_target_types, custom_urls_by_target_type, disabled_target_types).
    """
    if not isinstance(source_dict, dict):
        return [], {}, []

    # 1. Try Endpoint + Environment resolution first
    ep_targets, ep_urls, ep_disabled = resolve_endpoint_and_env_targets(source_dict, fallback_env=fallback_env)
    if ep_targets or ep_disabled:
        # Check if legacy custom URLs were passed in addition
        for k, v in source_dict.items():
            if k is not None and isinstance(v, str):
                v_clean = v.strip().strip('"').strip("'")
                if v_clean.lower().startswith(("http://", "https://")):
                    k_lower = str(k).strip().lower()
                    for canonical_target, aliases in TARGET_PARAM_ALIASES.items():
                        if k_lower in aliases and canonical_target in ep_targets and canonical_target not in ep_urls:
                            ep_urls[canonical_target] = v_clean
        return ep_targets, ep_urls, ep_disabled

    # 2. Fall back to individual target flag aliases (j5=true, oracle=true, etc.)
    enabled_targets: List[str] = []
    disabled_targets: List[str] = []
    custom_urls: Dict[str, str] = {}
    for k, v in source_dict.items():
        if k is None:
            continue
        k_lower = str(k).strip().lower()
        for canonical_target, aliases in TARGET_PARAM_ALIASES.items():
            if k_lower in aliases:
                if is_j5_param_enabled(v):
                    if canonical_target not in enabled_targets:
                        enabled_targets.append(canonical_target)
                    if canonical_target in disabled_targets:
                        disabled_targets.remove(canonical_target)
                    if isinstance(v, str):
                        v_clean = v.strip().strip('"').strip("'")
                        if v_clean.lower().startswith(("http://", "https://")):
                            custom_urls[canonical_target] = v_clean
                elif is_target_param_disabled(v):
                    if canonical_target not in disabled_targets:
                        disabled_targets.append(canonical_target)
                    if canonical_target in enabled_targets:
                        enabled_targets.remove(canonical_target)
                break
    return enabled_targets, custom_urls, disabled_targets


def extract_j5_flag_and_url(source_dict: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """
    Checks a dictionary (case-insensitive) for a 'J5' / 'JF' / 'Octave' parameter.
    Returns (is_j5_enabled, custom_j5_url_if_any).
    """
    targets, urls, _ = extract_target_flags_and_urls(source_dict)
    if "j5" in targets:
        return True, urls.get("j5")
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


STANDARD_TELEMETRY_KEYS = {
    "tagname", "tag_name", "tag", "meter_tag", "name",
    "attribute", "attribute_name", "attributename", "attribute name",
    "description", "desc",
    "value", "val", "readingvalue", "reading_value",
    "limit", "limits",
    "result", "results",
    "timestamp", "time", "readingtimestamp",
    "uom", "unit", "unitofmeasure",
    "target_endpoint_url", "endpoint_url", "target_endpoint", "endpoint",
    "quality",
    "notification", "notificationname", "notificationrule", "eventframe", "eventframename",
    "rule", "analysis", "event", "eventtype", "target", "element", "path", "id",
    "items", "attributes", "values", "data", "content",
} | ALL_ROUTING_PARAM_KEYS


def extract_extra_parameters(source_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extracts non-standard extra parameters (such as hilimit, low limit, etc.) from a PI AF dictionary
    while excluding standard mapped telemetry keys and target routing parameters (j5, j5dev, oracle, oracledev).
    """
    if not isinstance(source_dict, dict):
        return {}
    extra: Dict[str, Any] = {}
    for k, v in source_dict.items():
        if k is None:
            continue
        k_str = str(k).strip()
        if not k_str:
            continue
        if k_str.lower() in STANDARD_TELEMETRY_KEYS:
            continue
        if isinstance(v, (dict, list)):
            continue
        extra[k_str] = v
    return extra


def extract_direct_telemetry_record(
    item_dict: Dict[str, Any],
    default_timestamp: Optional[str] = None,
    fallback_env: Optional[str] = None
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
    has_attr_key = any(k in lower_map for k in ("attribute", "attribute_name", "attributename", "attribute name", "name"))
    has_val = any(k in lower_map for k in ("value", "val", "readingvalue", "reading_value")) or any("value" in k for k in lower_map)
    has_desc = any(k in lower_map for k in ("description", "desc"))
    has_limit = any(k in lower_map for k in ("limit", "limits"))
    has_result = any(k in lower_map for k in ("result", "results"))
    target_flags, target_custom_urls, disabled_target_flags = extract_target_flags_and_urls(item_dict, fallback_env=fallback_env)
    has_target_flag = bool(target_flags or disabled_target_flags)

    # Direct telemetry record condition:
    # 1. Has Tagname/Tag and Value
    # 2. Or has Value and (Description or Limit or Result or TargetFlag or Attribute/Name)
    # 3. Or has Tagname/Attribute and (Description or Limit or Result or TargetFlag)
    is_direct = (
        (has_tag and has_val) or
        (has_val and (has_desc or has_limit or has_result or has_target_flag or has_attr_key)) or
        ((has_tag or has_attr_key) and (has_desc or has_limit or has_result or has_target_flag))
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
        lower_map.get("attribute name") or
        ""
    )

    explicit_attr_name = (
        lower_map.get("attribute") or
        lower_map.get("attribute_name") or
        lower_map.get("attributename") or
        lower_map.get("attribute name") or
        None
    )

    # Description extraction
    desc_val = (
        lower_map.get("description") or
        lower_map.get("desc") or
        ""
    )

    # Value extraction: check 'value', 'val', or any parameter containing 'value' (e.g. UtilityValue, EffluentValue)
    raw_val = None
    if "value" in lower_map and lower_map["value"] is not None and str(lower_map["value"]).strip() != "":
        raw_val = lower_map["value"]
    elif "val" in lower_map and lower_map["val"] is not None and str(lower_map["val"]).strip() != "":
        raw_val = lower_map["val"]
    elif "readingvalue" in lower_map and lower_map["readingvalue"] is not None and str(lower_map["readingvalue"]).strip() != "":
        raw_val = lower_map["readingvalue"]
    elif "reading_value" in lower_map and lower_map["reading_value"] is not None and str(lower_map["reading_value"]).strip() != "":
        raw_val = lower_map["reading_value"]
    else:
        # Check any parameter containing the word 'value'
        for k, v in lower_map.items():
            if "value" in k and v is not None and str(v).strip() != "":
                raw_val = v
                break

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

    # Timestamp extraction (prioritize SourceTime / AnalysisTime from PI AF)
    ts_val = (
        lower_map.get("sourcetime") or
        lower_map.get("source_time") or
        lower_map.get("record_at") or
        lower_map.get("recorded_at") or
        lower_map.get("analysistime") or
        lower_map.get("analysis_time") or
        lower_map.get("event time") or
        lower_map.get("eventtime") or
        lower_map.get("event_time") or
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

    res_record: Dict[str, Any] = {
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
    if target_flags:
        res_record["target_flags"] = list(target_flags)
        for t_flag in target_flags:
            res_record[t_flag] = True
        if target_custom_urls.get("j5"):
            res_record["target_endpoint_url_j5"] = target_custom_urls["j5"]
        if target_custom_urls.get("j5dev"):
            res_record["target_endpoint_url_j5dev"] = target_custom_urls["j5dev"]
        if target_custom_urls.get("oracle"):
            res_record["target_endpoint_url_oracle"] = target_custom_urls["oracle"]
        if target_custom_urls.get("oracle_utility"):
            res_record["target_endpoint_url_oracle_utility"] = target_custom_urls["oracle_utility"]
        if target_custom_urls.get("oracledev"):
            res_record["target_endpoint_url_dev"] = target_custom_urls["oracledev"]
        if target_custom_urls.get("oracledev_utility"):
            res_record["target_endpoint_url_dev_utility"] = target_custom_urls["oracledev_utility"]
    if disabled_target_flags:
        res_record["disabled_target_flags"] = list(disabled_target_flags)
        for d_flag in disabled_target_flags:
            res_record[d_flag] = False

    extra_fields = extract_extra_parameters(item_dict)
    if extra_fields:
        res_record["extra_fields"] = extra_fields

    return res_record


def parse_pi_notification_payload(
    raw_data: Any,
    query_params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None
) -> Tuple[str, str, str, List[Dict[str, Any]]]:
    """
    Parses various PI AF Notification WebService JSON payload structures:
    Extracts notification/attribute name from URL query parameter, HTTP headers, or payload body.
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

    # Look for top-level Environment parameter in query_params, headers, or raw_data
    top_env = None
    for src in (query_params, headers, raw_data if isinstance(raw_data, dict) else None):
        if isinstance(src, dict):
            for env_k in ENVIRONMENT_PARAM_KEYS:
                for k, v in src.items():
                    if k is not None and str(k).strip().lower() == env_k and v is not None:
                        val_s = str(v).strip()
                        if val_s:
                            top_env = val_s
                            break
                if top_env:
                    break
        if top_env:
            break

    # Check if target routing parameters (Endpoint/Environment or legacy j5/oracle/etc.)
    # were passed via query params, headers, or top-level JSON body
    top_target_flags: List[str] = []
    top_disabled_flags: List[str] = []
    top_target_urls: Dict[str, str] = {}

    q_flags, q_urls, q_dis = extract_target_flags_and_urls(query_params, fallback_env=top_env)
    for tf in q_flags:
        if tf not in top_target_flags:
            top_target_flags.append(tf)
        if tf in top_disabled_flags:
            top_disabled_flags.remove(tf)
    for df in q_dis:
        if df not in top_disabled_flags:
            top_disabled_flags.append(df)
        if df in top_target_flags:
            top_target_flags.remove(df)
    top_target_urls.update(q_urls)

    for canonical_target, aliases in TARGET_PARAM_ALIASES.items():
        for alias in aliases:
            for h_key in (alias, f"x-{alias}"):
                if h_key in headers:
                    h_val = headers.get(h_key)
                    if is_j5_param_enabled(h_val):
                        if canonical_target not in top_target_flags:
                            top_target_flags.append(canonical_target)
                        if canonical_target in top_disabled_flags:
                            top_disabled_flags.remove(canonical_target)
                    elif is_target_param_disabled(h_val):
                        if canonical_target not in top_disabled_flags:
                            top_disabled_flags.append(canonical_target)
                        if canonical_target in top_target_flags:
                            top_target_flags.remove(canonical_target)

    top_extra_fields: Dict[str, Any] = {}

    if isinstance(raw_data, dict):
        body_flags, body_urls, body_dis = extract_target_flags_and_urls(raw_data, fallback_env=top_env)
        for tf in body_flags:
            if tf not in top_target_flags:
                top_target_flags.append(tf)
            if tf in top_disabled_flags:
                top_disabled_flags.remove(tf)
        for df in body_dis:
            if df not in top_disabled_flags:
                top_disabled_flags.append(df)
            if df in top_target_flags:
                top_target_flags.remove(df)
        top_target_urls.update(body_urls)
        top_extra_fields = extract_extra_parameters(raw_data)

        lower_raw = {str(k).strip().lower(): v for k, v in raw_data.items() if k is not None}

        # Prioritize Description, then Tagname, Name, Attribute, or Attribute Name before falling back to NotificationRule
        preferred_attr_title = None
        for key_candidate in ("description", "desc", "tagname", "tag_name", "tag", "name", "attribute", "attribute name", "attributename", "attribute_name"):
            val_candidate = lower_raw.get(key_candidate)
            if val_candidate is not None:
                val_s = str(val_candidate).strip()
                if val_s and val_s.lower() not in ("null", "none", "na", "n/a"):
                    preferred_attr_title = val_s
                    break

        body_name = (
            preferred_attr_title or
            raw_data.get("NotificationRule") or
            raw_data.get("NotificationName") or
            raw_data.get("Notification") or
            raw_data.get("EventFrame") or
            raw_data.get("EventFrameName") or
            raw_data.get("Rule") or
            raw_data.get("Analysis") or
            raw_data.get("notificationRule") or
            raw_data.get("notificationName") or
            raw_data.get("notification")
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
        direct_top = extract_direct_telemetry_record(raw_data, default_timestamp=now_iso, fallback_env=top_env)

        if raw_attrs and isinstance(raw_attrs, list):
            for item in raw_attrs:
                if isinstance(item, dict):
                    # Check if item is a direct telemetry record (Tagname, Description, Limit, Result, Value)
                    direct_item = extract_direct_telemetry_record(item, default_timestamp=now_iso, fallback_env=top_env)
                    if direct_item:
                        attributes.append(direct_item)
                    else:
                        name = (
                            item.get("Tagname") or
                            item.get("TagName") or
                            item.get("tagname") or
                            item.get("Name") or
                            item.get("name") or
                            item.get("Attribute") or
                            item.get("attribute") or
                            item.get("Attribute Name") or
                            item.get("AttributeName") or
                            item.get("Tag") or
                            item.get("tag") or
                            (item.get("Path", "").split("|")[-1] if "|" in item.get("Path", "") else None) or
                            f"Attribute_{len(attributes)+1}"
                        )
                        raw_val = item.get("Value") if "Value" in item else (item.get("value") if "value" in item else item.get("Val"))
                        if raw_val is None or str(raw_val).strip() == "":
                            for k, v in item.items():
                                if "value" in str(k).lower() and v is not None and str(v).strip() != "":
                                    raw_val = v
                                    break
                        if isinstance(raw_val, dict):
                            val = raw_val.get("Value", raw_val.get("value", raw_val))
                        else:
                            val = raw_val

                        uom = item.get("UOM") or item.get("uom") or (raw_val.get("UOM") if isinstance(raw_val, dict) else "") or ""
                        ts = item.get("SourceTime") or item.get("sourcetime") or item.get("AnalysisTime") or item.get("Event Time") or item.get("Timestamp") or item.get("timestamp") or item.get("Time") or item.get("time") or now_iso
                        quality = item.get("Quality") or item.get("quality") or (raw_val.get("Quality") if isinstance(raw_val, dict) else "Good") or "Good"
                        item_flags, item_urls, item_dis = extract_target_flags_and_urls(item, fallback_env=top_env)
                        item_extra = extract_extra_parameters(item)

                        attr_entry: Dict[str, Any] = {
                            "name": name,
                            "value": val,
                            "uom": uom,
                            "timestamp": ts,
                            "quality": quality
                        }
                        if item_flags:
                            attr_entry["target_flags"] = list(item_flags)
                            for tf in item_flags:
                                attr_entry[tf] = True
                            if item_urls.get("j5"):
                                attr_entry["target_endpoint_url_j5"] = item_urls["j5"]
                            if item_urls.get("j5dev"):
                                attr_entry["target_endpoint_url_j5dev"] = item_urls["j5dev"]
                            if item_urls.get("oracle"):
                                attr_entry["target_endpoint_url_oracle"] = item_urls["oracle"]
                            if item_urls.get("oracle_utility"):
                                attr_entry["target_endpoint_url_oracle_utility"] = item_urls["oracle_utility"]
                            if item_urls.get("oracledev"):
                                attr_entry["target_endpoint_url_dev"] = item_urls["oracledev"]
                            if item_urls.get("oracledev_utility"):
                                attr_entry["target_endpoint_url_dev_utility"] = item_urls["oracledev_utility"]
                        if item_dis:
                            attr_entry["disabled_target_flags"] = list(item_dis)
                            for df in item_dis:
                                attr_entry[df] = False
                        if item_extra:
                            attr_entry["extra_fields"] = item_extra
                        attributes.append(attr_entry)
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
                    if val is None or str(val).strip() == "":
                        for k, v in attr_val.items():
                            if "value" in str(k).lower() and v is not None and str(v).strip() != "":
                                val = v
                                break
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
            # Flat dictionary: treat top-level key-values as attributes (excluding metadata and routing keys)
            meta_keys = {
                "notification", "notificationname", "notificationrule", "event", "eventtype",
                "target", "element", "path", "starttime", "endtime", "id",
                "items", "attributes", "values", "data", "content"
            } | ALL_ROUTING_PARAM_KEYS
            for k, v in raw_data.items():
                if k.lower() not in meta_keys:
                    # If v is a list of dicts (e.g. wrapper), unpack each item
                    if isinstance(v, list) and all(isinstance(x, dict) for x in v):
                        for sub_idx, sub_item in enumerate(v):
                            sub_direct = extract_direct_telemetry_record(sub_item, default_timestamp=now_iso, fallback_env=top_env)
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
                direct_item = extract_direct_telemetry_record(item, default_timestamp=now_iso, fallback_env=top_env)
                if direct_item:
                    attributes.append(direct_item)
                else:
                    name = (
                        item.get("Tagname") or
                        item.get("TagName") or
                        item.get("tagname") or
                        item.get("Name") or
                        item.get("name") or
                        item.get("Attribute") or
                        item.get("attribute") or
                        item.get("Attribute Name") or
                        item.get("AttributeName") or
                        item.get("Tag") or
                        item.get("tag") or
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
                    item_flags, item_urls, item_dis = extract_target_flags_and_urls(item, fallback_env=top_env)
                    item_extra = extract_extra_parameters(item)

                    attr_entry = {
                        "name": name,
                        "value": val,
                        "uom": uom,
                        "timestamp": ts,
                        "quality": quality
                    }
                    if item_flags:
                        attr_entry["target_flags"] = list(item_flags)
                        for tf in item_flags:
                            attr_entry[tf] = True
                        if item_urls.get("j5"):
                            attr_entry["target_endpoint_url_j5"] = item_urls["j5"]
                        if item_urls.get("j5dev"):
                            attr_entry["target_endpoint_url_j5dev"] = item_urls["j5dev"]
                        if item_urls.get("oracle"):
                            attr_entry["target_endpoint_url_oracle"] = item_urls["oracle"]
                        if item_urls.get("oracle_utility"):
                            attr_entry["target_endpoint_url_oracle_utility"] = item_urls["oracle_utility"]
                        if item_urls.get("oracledev"):
                            attr_entry["target_endpoint_url_dev"] = item_urls["oracledev"]
                        if item_urls.get("oracledev_utility"):
                            attr_entry["target_endpoint_url_dev_utility"] = item_urls["oracledev_utility"]
                    if item_dis:
                        attr_entry["disabled_target_flags"] = list(item_dis)
                        for df in item_dis:
                            attr_entry[df] = False
                    if item_extra:
                        attr_entry["extra_fields"] = item_extra
                    attributes.append(attr_entry)
            else:
                attributes.append({
                    "name": f"Value_{len(attributes)+1}",
                    "value": item,
                    "uom": "",
                    "timestamp": now_iso,
                    "quality": "Good"
                })

    # Propagate top-level target parameter flags and extra fields to all extracted attributes in this push delivery
    if top_target_flags or top_disabled_flags or top_extra_fields:
        for attr in attributes:
            if top_target_flags:
                existing_flags = list(attr.get("target_flags") or [])
                for tf in top_target_flags:
                    if tf not in existing_flags:
                        existing_flags.append(tf)
                    attr[tf] = True
                attr["target_flags"] = existing_flags
                if top_target_urls.get("j5") and not attr.get("target_endpoint_url_j5"):
                    attr["target_endpoint_url_j5"] = top_target_urls["j5"]
                if top_target_urls.get("j5dev") and not attr.get("target_endpoint_url_j5dev"):
                    attr["target_endpoint_url_j5dev"] = top_target_urls["j5dev"]
                if top_target_urls.get("oracle") and not attr.get("target_endpoint_url_oracle"):
                    attr["target_endpoint_url_oracle"] = top_target_urls["oracle"]
                if top_target_urls.get("oracle_utility") and not attr.get("target_endpoint_url_oracle_utility"):
                    attr["target_endpoint_url_oracle_utility"] = top_target_urls["oracle_utility"]
                if top_target_urls.get("oracledev") and not attr.get("target_endpoint_url_dev"):
                    attr["target_endpoint_url_dev"] = top_target_urls["oracledev"]
                if top_target_urls.get("oracledev_utility") and not attr.get("target_endpoint_url_dev_utility"):
                    attr["target_endpoint_url_dev_utility"] = top_target_urls["oracledev_utility"]
            if top_disabled_flags:
                existing_dis = list(attr.get("disabled_target_flags") or [])
                for df in top_disabled_flags:
                    if df not in existing_dis:
                        existing_dis.append(df)
                    attr[df] = False
                    if attr.get("target_flags") and df in attr["target_flags"]:
                        attr["target_flags"].remove(df)
                attr["disabled_target_flags"] = existing_dis
            if top_extra_fields:
                merged_extra = dict(top_extra_fields)
                if isinstance(attr.get("extra_fields"), dict):
                    merged_extra.update(attr["extra_fields"])
                attr["extra_fields"] = merged_extra

    # If top-level Description/Tagname was not found, check attributes list (prioritize description, then tagname)
    first_attr_title = None
    if attributes and isinstance(attributes[0], dict):
        first_attr = attributes[0]
        first_desc = str(first_attr.get("description") or first_attr.get("desc") or "").strip()
        first_tag = str(first_attr.get("tag") or first_attr.get("tagname") or first_attr.get("tag_name") or "").strip()
        first_name = str(first_attr.get("name") or "").strip()
        if first_desc and first_desc.lower() not in ("null", "none", "na", "n/a"):
            first_attr_title = first_desc
        elif first_tag and first_tag.lower() not in ("null", "none", "na", "n/a"):
            first_attr_title = first_tag
        elif first_name and not first_name.lower().startswith("value") and not first_name.lower().startswith("attribute_"):
            first_attr_title = first_name

    notification_name = (
        (preferred_attr_title if isinstance(raw_data, dict) else None) or
        first_attr_title or
        query_name or
        header_name or
        body_name or
        ("PI_Notification_Ping" if not raw_data and not attributes else "PI_Notification")
    )
    return notification_name, event_type, target_path, attributes


ALL_CANONICAL_TARGETS = ("oracle", "oracle_utility", "oracle_production", "oracledev", "oracledev_utility", "oracledev_production", "j5", "j5dev")


def get_requested_targets_from_attr(attr: Optional[Dict[str, Any]]) -> List[str]:
    """
    Returns the list of explicit target types ('oracle', 'oracle_utility', 'oracle_production', 'oracle_<custom>', etc.)
    requested via routing parameters on the attribute dictionary, strictly excluding any explicitly disabled.
    """
    if not isinstance(attr, dict):
        return []
    targets: List[str] = []
    disabled = set(str(d).strip().lower() for d in (attr.get("disabled_target_flags") or []))
    for tf in (attr.get("target_flags") or []):
        tf_clean = str(tf).strip().lower()
        is_valid = (
            tf_clean in ALL_CANONICAL_TARGETS
            or tf_clean.startswith("oracle_")
            or tf_clean.startswith("oracledev_")
        )
        if is_valid and tf_clean not in targets and tf_clean not in disabled and attr.get(tf_clean) is not False:
            targets.append(tf_clean)
    for t_key in ALL_CANONICAL_TARGETS:
        if attr.get(t_key) is True and t_key not in targets and t_key not in disabled:
            targets.append(t_key)
    return targets


def ensure_j5_mapping_for_attribute(
    attr: Dict[str, Any],
    target_path: str = "",
    settings: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    When PI AF sends a push with target routing parameters ('Endpoint', 'Environment', or legacy target flags),
    automatically creates a new attribute mapping in config/mappings.json if one does not already exist
    with ONLY the requested destination(s), or updates existing mappings to match the requested/disabled destinations.
    """
    requested_targets = get_requested_targets_from_attr(attr)
    disabled_targets = [str(d).strip().lower() for d in (attr.get("disabled_target_flags") or []) if d]
    if not attr:
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
    j5dev_cfg = settings.get("j5dev_endpoint", {})

    # If no explicit target was requested in the push, resolve targets from active endpoints in settings
    if not requested_targets:
        default_targets = []
        if oracledev_cfg.get("enabled", False) and "oracledev" not in disabled_targets:
            default_targets.append("oracledev")
        if erp_cfg.get("enabled", False) and "oracle" not in disabled_targets:
            default_targets.append("oracle")
        if j5_cfg.get("enabled", False) and "j5" not in disabled_targets:
            default_targets.append("j5")
        if j5dev_cfg.get("enabled", False) and "j5dev" not in disabled_targets:
            default_targets.append("j5dev")
        if not default_targets:
            default_targets = ["oracle"]
        requested_targets = default_targets

    base_url = (erp_cfg.get("base_url") or "").rstrip("/")
    res_ep = (erp_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/").strip()
    util_res_ep = (erp_cfg.get("utility_resource_endpoint") or "/production_utilities_consumption/").strip()
    prod_data_res_ep = (erp_cfg.get("daily_production_resource_endpoint") or "/production_daily_output/").strip()
    default_oracle_url = sanitize_endpoint_url(str(attr.get("target_endpoint_url_oracle") or (build_oracle_endpoint_url(base_url, res_ep) if base_url else "")))
    default_oracle_util_url = sanitize_endpoint_url(str(attr.get("target_endpoint_url_oracle_utility") or (build_oracle_endpoint_url(base_url, util_res_ep) if base_url else "")))
    default_oracle_prod_data_url = sanitize_endpoint_url(str(attr.get("target_endpoint_url_oracle_production") or (build_oracle_endpoint_url(base_url, prod_data_res_ep) if base_url else "")))

    dev_base_url = (oracledev_cfg.get("base_url") or "").rstrip("/")
    dev_res_ep = (oracledev_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/").strip()
    dev_util_res_ep = (oracledev_cfg.get("utility_resource_endpoint") or "/production_utilities_consumption/").strip()
    dev_prod_data_res_ep = (oracledev_cfg.get("daily_production_resource_endpoint") or "/production_daily_output/").strip()
    default_dev_url = sanitize_endpoint_url(str(attr.get("target_endpoint_url_dev") or (build_oracle_endpoint_url(dev_base_url, dev_res_ep) if dev_base_url else "")))
    default_dev_util_url = sanitize_endpoint_url(str(attr.get("target_endpoint_url_dev_utility") or (build_oracle_endpoint_url(dev_base_url, dev_util_res_ep) if dev_base_url else "")))
    default_dev_prod_data_url = sanitize_endpoint_url(str(attr.get("target_endpoint_url_dev_production") or (build_oracle_endpoint_url(dev_base_url, dev_prod_data_res_ep) if dev_base_url else "")))

    default_j5_url = sanitize_endpoint_url(str(attr.get("target_endpoint_url_j5") or j5_cfg.get("url") or DEFAULT_J5_URL).strip())
    default_j5dev_url = sanitize_endpoint_url(str(attr.get("target_endpoint_url_j5dev") or j5dev_cfg.get("url") or DEFAULT_J5_URL).strip())

    custom_eps = get_oracle_custom_endpoints(settings)
    custom_prod_urls: Dict[str, str] = {}
    custom_dev_urls: Dict[str, str] = {}
    for ce in custom_eps:
        ck = ce["key"]
        custom_prod_urls[ck] = sanitize_endpoint_url(str(attr.get(f"target_endpoint_url_oracle_{ck}") or (build_oracle_endpoint_url(base_url, ce["prod_path"]) if base_url else "")))
        custom_dev_urls[ck] = sanitize_endpoint_url(str(attr.get(f"target_endpoint_url_dev_{ck}") or (build_oracle_endpoint_url(dev_base_url, ce["dev_path"]) if dev_base_url else "")))

    def resolve_target_url(tgt: str) -> str:
        tgt_l = tgt.lower()
        if tgt_l == "j5":
            return default_j5_url
        elif tgt_l == "j5dev":
            return default_j5dev_url
        elif tgt_l in ("oracle_production", "oracleproduction", "oracle_daily_production", "daily_production", "production_daily_output"):
            return default_oracle_prod_data_url
        elif tgt_l in ("oracledev_production", "oracle_dev_production", "dev_production", "dev_daily_production"):
            return default_dev_prod_data_url
        elif tgt_l in ("oracle_utility", "oracleutility", "utility", "oracle_prod_utility"):
            return default_oracle_util_url
        elif tgt_l in ("oracledev_utility", "oracle_dev_utility", "dev_utility"):
            return default_dev_util_url
        elif tgt_l in ("oracledev", "oracle_dev", "oracledev_effluent"):
            return default_dev_url
        elif tgt_l.startswith("oracledev_"):
            ck = tgt_l[len("oracledev_"):]
            if ck in custom_dev_urls:
                return custom_dev_urls[ck]
            return sanitize_endpoint_url(build_oracle_endpoint_url(dev_base_url, f"/{ck}/") if dev_base_url else "")
        elif tgt_l.startswith("oracle_"):
            ck = tgt_l[len("oracle_"):]
            if ck in custom_prod_urls:
                return custom_prod_urls[ck]
            return sanitize_endpoint_url(build_oracle_endpoint_url(base_url, f"/{ck}/") if base_url else "")
        return default_oracle_url

    mappings = load_mappings()
    a_name_l = attr_name.lower()
    a_tag_l = attr_tag.lower()

    matching = []
    for m in mappings:
        m_attr = str(m.get("attribute_name") or "").strip().lower()
        m_tag = str(m.get("tag") or m.get("meter_tag") or "").strip().lower()
        m_name = str(m.get("name") or "").strip().lower()
        if (
            (m_attr and (m_attr == a_name_l or (a_tag_l and m_attr == a_tag_l)))
            or (m_tag and ((a_tag_l and m_tag == a_tag_l) or m_tag == a_name_l))
            or (m_name and (m_name == a_name_l or (a_tag_l and m_name == a_tag_l)))
        ):
            matching.append(m)

    if matching:
        # Mapping already exists: ensure it is enabled and align/switch target endpoint(s)
        updated = False
        for m in matching:
            if not m.get("enabled", True):
                m["enabled"] = True
                updated = True
            t_types = [str(t).strip().lower() for t in (m.get("target_types") or ([m.get("target_type")] if m.get("target_type") else []))]
            
            # Determine updated target types respecting requested and explicitly disabled flags
            if requested_targets:
                new_targets = [t for t in requested_targets if t not in disabled_targets]
            else:
                new_targets = [t for t in t_types if t not in disabled_targets]

            if not new_targets:
                new_targets = ["oracle"]

            if set(t_types) != set(new_targets):
                m["target_types"] = list(new_targets)
                m["target_type"] = new_targets[0]
                primary_url = resolve_target_url(new_targets[0])
                m["target_endpoint_url"] = primary_url
                updated = True

            # Always sanitize any existing stored URLs to eliminate duplicate path segments
            for url_prop in ("target_endpoint_url", "target_endpoint_url_oracle", "target_endpoint_url_oracle_utility", "target_endpoint_url_dev", "target_endpoint_url_dev_utility", "target_endpoint_url_j5", "target_endpoint_url_j5dev"):
                if m.get(url_prop):
                    sanitized_prop = sanitize_endpoint_url(m[url_prop])
                    if sanitized_prop != m[url_prop]:
                        m[url_prop] = sanitized_prop
                        updated = True

            if default_oracle_url and m.get("target_endpoint_url_oracle") != default_oracle_url:
                m["target_endpoint_url_oracle"] = default_oracle_url
                updated = True
            if default_oracle_util_url and m.get("target_endpoint_url_oracle_utility") != default_oracle_util_url:
                m["target_endpoint_url_oracle_utility"] = default_oracle_util_url
                updated = True
            if default_oracle_prod_data_url and m.get("target_endpoint_url_oracle_production") != default_oracle_prod_data_url:
                m["target_endpoint_url_oracle_production"] = default_oracle_prod_data_url
                updated = True
            if default_dev_url and m.get("target_endpoint_url_dev") != default_dev_url:
                m["target_endpoint_url_dev"] = default_dev_url
                updated = True
            if default_dev_util_url and m.get("target_endpoint_url_dev_utility") != default_dev_util_url:
                m["target_endpoint_url_dev_utility"] = default_dev_util_url
                updated = True
            if default_dev_prod_data_url and m.get("target_endpoint_url_dev_production") != default_dev_prod_data_url:
                m["target_endpoint_url_dev_production"] = default_dev_prod_data_url
                updated = True
            if default_j5_url and m.get("target_endpoint_url_j5") != default_j5_url:
                m["target_endpoint_url_j5"] = default_j5_url
                updated = True
            if default_j5dev_url and m.get("target_endpoint_url_j5dev") != default_j5dev_url:
                m["target_endpoint_url_j5dev"] = default_j5dev_url
                updated = True
            expected_primary_url = resolve_target_url(m.get("target_type") or (m.get("target_types") or ["oracle"])[0])
            if expected_primary_url and m.get("target_endpoint_url") != expected_primary_url:
                m["target_endpoint_url"] = expected_primary_url
                updated = True
        if updated:
            save_mappings(mappings)
            add_log(
                "INFO",
                "PIPELINE",
                f"Updated existing mapping for [{attr_name}] destination(s) to {requested_targets}."
            )
        return matching[0]

    # Mapping does not exist: automatically create a new mapping ONLY for the requested target(s)
    target_types = [t for t in requested_targets if t not in disabled_targets]
    if not target_types:
        target_types = ["oracle"]

    primary_url = resolve_target_url(target_types[0])

    new_mapping = {
        "id": f"map-auto-{int(time.time())}-{uuid.uuid4().hex[:4]}",
        "name": str(attr.get("description") or attr_name).strip(),
        "attribute_name": attr_name,
        "af_server": "",
        "af_database": "",
        "element_path": target_path or "",
        "full_path": target_path or "",
        "target_type": target_types[0],
        "target_types": target_types,
        "target_endpoint_url": primary_url,
        "target_endpoint_url_oracle": default_oracle_url,
        "target_endpoint_url_oracle_utility": default_oracle_util_url,
        "target_endpoint_url_oracle_production": default_oracle_prod_data_url,
        "target_endpoint_url_dev": default_dev_url,
        "target_endpoint_url_dev_utility": default_dev_util_url,
        "target_endpoint_url_dev_production": default_dev_prod_data_url,
        "target_endpoint_url_j5": default_j5_url,
        "target_endpoint_url_j5dev": default_j5dev_url,
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
        f"Auto-created new attribute mapping for [{attr_name}] with destination(s) {target_types}.",
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

    # Auto-create/update attribute mapping for incoming push attributes
    if settings.get("pipeline", {}).get("auto_create_j5_mapping", True):
        for attr in attributes:
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

    # Step 2: Immediate Auto-Dispatch to Oracle ERP Cloud / Octave upon receipt
    erp_cfg = settings.get("oracle_erp", {})
    oracledev_cfg = settings.get("oracledev", {})
    j5_cfg = settings.get("j5_endpoint", {})
    j5dev_cfg = settings.get("j5dev_endpoint", {})
    auto_dispatch_enabled = settings.get("pipeline", {}).get("auto_dispatch", True) and settings.get("pipeline", {}).get("auto_dispatch_deliveries", True)

    has_target_attr = any(bool(get_requested_targets_from_attr(a)) for a in attributes)
    any_endpoint_enabled = (
        erp_cfg.get("enabled", False) or
        oracledev_cfg.get("enabled", False) or
        j5_cfg.get("enabled", False) or
        j5dev_cfg.get("enabled", False) or
        has_target_attr
    )

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
            "message": "Destination endpoints (Oracle ERP / Octave) are not enabled in settings. Delivery held in JSON staging.",
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
    configured destination endpoints (Oracle ORDS / ERP Cloud, Oracle Dev, Octave, or Octave Dev).
    """
    delivery = get_delivery_by_id(delivery_id)
    if not delivery:
        raise ValueError(f"Delivery record {delivery_id} not found in storage.")

    settings = load_settings()
    erp_cfg = settings.get("oracle_erp", {})
    oracledev_cfg = settings.get("oracledev", {})
    j5_cfg = settings.get("j5_endpoint", {})
    j5dev_cfg = settings.get("j5dev_endpoint", {})
    erp_client = OracleERPCloudClient(erp_cfg)
    oracledev_client = OracleERPCloudClient(oracledev_cfg)
    j5_client = J5Client(j5_cfg)
    j5dev_client = J5Client(j5dev_cfg)

    raw_skip_str = str(settings.get("pipeline", {}).get("skip_parameters", "j5, j5dev, oracle, oracledev") or "")
    user_skip_params = {
        p.strip().lower()
        for p in raw_skip_str.replace(";", ",").split(",")
        if p.strip()
    }
    skip_params_set = ALL_ROUTING_PARAM_KEYS | user_skip_params

    raw_payload_extra: Dict[str, Any] = {}
    if isinstance(delivery.get("raw_payload"), dict):
        raw_payload_extra = extract_extra_parameters(delivery.get("raw_payload"))

    now_iso = datetime.now(timezone.utc).isoformat()
    raw_attrs = delivery.get("attributes_summary", [])
    if not raw_attrs:
        raw_attrs = [{
            "name": delivery.get("notification_name") or "PI_Delivery",
            "value": 0,
            "timestamp": now_iso,
            "quality": "Good"
        }]

    # Ensure any attribute with target routing flags has a mapping created/updated before loading mappings.
    # Note: Retries of historical/queued deliveries must NEVER mutate the active mapping configuration!
    if not is_retry and settings.get("pipeline", {}).get("auto_create_j5_mapping", True):
        for attr in raw_attrs:
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
        requested_targets = get_requested_targets_from_attr(attr)
        disabled_targets = [str(d).strip().lower() for d in (attr.get("disabled_target_flags") or []) if d]

        # Merge extra parameters from raw_payload and attr["extra_fields"]
        merged_extra = dict(raw_payload_extra)
        if isinstance(attr.get("extra_fields"), dict):
            merged_extra.update(attr["extra_fields"])
        if merged_extra:
            attr = dict(attr)
            attr["extra_fields"] = merged_extra

        # Fallback: if value is missing/empty, find any parameter containing the word 'value'
        if attr.get("value") is None or str(attr.get("value")).strip() == "":
            attr = dict(attr)
            for k, v in attr.items():
                if "value" in str(k).lower() and v is not None and str(v).strip() != "":
                    attr["value"] = v
                    break
            if (attr.get("value") is None or str(attr.get("value")).strip() == "") and merged_extra:
                for k, v in merged_extra.items():
                    if "value" in str(k).lower() and v is not None and str(v).strip() != "":
                        attr["value"] = v
                        break

        # Check mappings: find all matching mappings (supports 1-to-many multicast)
        matching_mappings = [
            m for m in enabled_mappings
            if (
                (m.get("attribute_name") and m.get("attribute_name").strip().lower() in (attr_name_l, attr_tag) and (attr_name_l or attr_tag))
                or (attr_tag and m.get("tag") and str(m.get("tag")).strip().lower() == attr_tag)
                or (attr_tag and m.get("meter_tag") and str(m.get("meter_tag")).strip().lower() == attr_tag)
                or (attr_name_l and m.get("tag") and str(m.get("tag")).strip().lower() == attr_name_l)
                or (m.get("name") and str(m.get("name")).strip().lower() in (attr_name_l, attr_tag) and (attr_name_l or attr_tag))
            )
        ]

        # If no specific mapping matched, create fallback default mapping for direct PI delivery
        if not matching_mappings:
            raw_target = str(attr.get("target_endpoint_url") or "").strip().strip('"').strip("'")
            targets = []
            if requested_targets:
                targets = [t for t in requested_targets if t not in disabled_targets]
            elif raw_target:
                if "hxgnsmartcloud" in raw_target.lower():
                    targets.append("j5")
                elif "utility" in raw_target.lower():
                    targets.append("oracledev_utility" if "dev" in raw_target.lower() else "oracle_utility")
                elif "dev" in raw_target.lower():
                    targets.append("oracledev")
                else:
                    targets.append("oracle")
                targets = [t for t in targets if t not in disabled_targets]
            else:
                if erp_cfg.get("enabled", False) and "oracle" not in disabled_targets and attr.get("oracle") is not False:
                    targets.append("oracle")
                if oracledev_cfg.get("enabled", False) and "oracledev" not in disabled_targets and attr.get("oracledev") is not False:
                    targets.append("oracledev")
                if not targets:
                    targets = ["oracle"]
            matching_mappings = [{
                "target_types": targets,
                "target_endpoint_url": raw_target or None,
                "target_endpoint_url_oracle": attr.get("target_endpoint_url_oracle") or None,
                "target_endpoint_url_oracle_utility": attr.get("target_endpoint_url_oracle_utility") or None,
                "target_endpoint_url_dev": attr.get("target_endpoint_url_dev") or None,
                "target_endpoint_url_dev_utility": attr.get("target_endpoint_url_dev_utility") or None,
                "target_endpoint_url_j5": attr.get("target_endpoint_url_j5") or None,
                "target_endpoint_url_j5dev": attr.get("target_endpoint_url_j5dev") or None
            }]

        for m in matching_mappings:
            raw_target = str(attr.get("target_endpoint_url") or m.get("target_endpoint_url") or "").strip().strip('"').strip("'")
            target_types = list(m.get("target_types") or [])
            if not target_types:
                if m.get("target_type"):
                    target_types = [m.get("target_type")]
                elif requested_targets:
                    target_types = list(requested_targets)
                else:
                    if "hxgnsmartcloud" in raw_target.lower() or "tag=purchaseorder" in raw_target.lower():
                        target_types = ["j5"]
                    elif "dev" in raw_target.lower():
                        target_types = ["oracledev"]
                    else:
                        target_types = ["oracle"]
            # Only append historical requested_targets on fresh push.
            # On retries, adhere to the latest active mapping targets (e.g. if newer push or user removed j5).
            if not is_retry:
                for req_t in requested_targets:
                    if req_t not in [str(t).strip().lower() for t in target_types]:
                        target_types.append(req_t)

            # Strictly filter out any targets that were explicitly disabled in the push payload.
            # On retries, respect the active mapping targets (do not let historical disabled flags block new active targets).
            if not is_retry:
                target_types = [
                    t for t in target_types
                    if str(t).strip().lower() not in disabled_targets
                    and attr.get(str(t).strip().lower()) is not False
                ]

            # Compute transformed telemetry values
            scale = float(m.get("scale_factor", 1.0))
            raw_val = attr.get("value")
            scaled_val = raw_val
            try:
                if raw_val is not None and str(raw_val).strip() != "":
                    scaled_val = round(float(raw_val) * scale, int(m.get("round_decimals", 2)))
            except Exception:
                scaled_val = raw_val

            # The timestamp delivered to the destination must be the actual datetime when pidatapipeline received the POST request from PI AF
            received_time = delivery.get("received_at") or attr.get("received_at") or now_iso
            timestamp_val = format_ords_timestamp(received_time)
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

            # Build Oracle payload via schema parameter mappings (e.g. AnalysisTime -> TESTTIMESTAMP)
            ords_payload = build_destination_payload(
                target_type="oracle",
                source_attr=attr,
                mapping_rule=m,
                received_at=received_time,
                skip_params=skip_params_set
            )

            for t_type in target_types:
                t_lower = str(t_type).strip().lower()

                if t_lower in ("j5", "octave"):
                    if not is_retry and (t_lower in disabled_targets or attr.get("j5") is False):
                        continue
                    resolved_j5_url = sanitize_endpoint_url(attr.get("target_endpoint_url_j5") or j5_cfg.get("url") or m.get("target_endpoint_url_j5") or (raw_target if "hxgnsmartcloud" in raw_target.lower() else None) or DEFAULT_J5_URL)
                    if not j5_cfg.get("enabled", True) and not attr.get("j5"):
                        item_results.append({
                            "target_type": "j5",
                            "attribute_name": attr_name,
                            "target_endpoint": resolved_j5_url,
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": "Octave endpoint integration is disabled in settings.",
                            "message": "Octave integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    j5_payload = J5Client.build_j5_payload(attr, mapping=m, skip_params=skip_params_set, received_at=received_time)
                    target_url = resolved_j5_url
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

                elif t_lower in ("j5dev", "j5_dev", "jfdev", "octavedev", "octave_dev"):
                    if not is_retry and (t_lower in disabled_targets or attr.get("j5dev") is False):
                        continue
                    resolved_j5dev_url = sanitize_endpoint_url(attr.get("target_endpoint_url_j5dev") or j5dev_cfg.get("url") or m.get("target_endpoint_url_j5dev") or DEFAULT_J5_URL)
                    if not j5dev_cfg.get("enabled", True) and not attr.get("j5dev"):
                        item_results.append({
                            "target_type": "j5dev",
                            "attribute_name": attr_name,
                            "target_endpoint": resolved_j5dev_url,
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": "Octave Dev endpoint integration is disabled in settings.",
                            "message": "Octave Dev integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    j5dev_payload = J5Client.build_j5_payload(attr, mapping=m, skip_params=skip_params_set, received_at=received_time, target_type="j5dev")
                    target_url = resolved_j5dev_url
                    pub_res = j5dev_client.publish_data(j5dev_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": "j5dev",
                        "attribute_name": attr_name,
                        "target_endpoint": pub_res.get("target_endpoint"),
                        "status": pub_res.get("status"),
                        "http_code": pub_res.get("http_code"),
                        "payload": j5dev_payload,
                        "response": pub_res.get("response_body"),
                        "error": pub_res.get("error_detail"),
                        "message": pub_res.get("message")
                    })

                    if pub_res.get("status") == "SUCCESS":
                        any_succeeded = True
                    else:
                        all_succeeded = False

                elif t_lower in ("oracledev_production", "oracle_dev_production", "dev_production", "dev_daily_production", "oracledev_daily_production", "dev_daily_output"):
                    if not is_retry and (t_lower in disabled_targets or attr.get("oracledev_production") is False):
                        continue
                    prod_def_url = build_oracle_endpoint_url(oracledev_cfg.get("base_url"), oracledev_cfg.get("daily_production_resource_endpoint") or "/production_daily_output/")
                    if not oracledev_cfg.get("enabled", False) and not attr.get("oracledev_production") and not attr.get("oracledev"):
                        item_results.append({
                            "target_type": "oracledev_production",
                            "attribute_name": attr_name,
                            "target_endpoint": attr.get("target_endpoint_url_dev_production") or prod_def_url or m.get("target_endpoint_url_dev_production") or oracledev_cfg.get("base_url"),
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": "Oracle Dev Daily Production integration is disabled in settings.",
                            "message": "Oracle Dev Daily Production integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    target_url = sanitize_endpoint_url(attr.get("target_endpoint_url_dev_production") or prod_def_url or m.get("target_endpoint_url_dev_production") or None)
                    dev_ords_payload = build_destination_payload("oracledev_production", source_attr=attr, mapping_rule=m, received_at=received_time, skip_params=skip_params_set)
                    pub_res = oracledev_client.publish_data(dev_ords_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": "oracledev_production",
                        "attribute_name": attr_name,
                        "target_endpoint": pub_res.get("target_endpoint"),
                        "status": pub_res.get("status"),
                        "http_code": pub_res.get("http_code"),
                        "payload": dev_ords_payload,
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

                elif t_lower in ("oracledev_utility", "oracle_dev_utility", "dev_utility"):
                    if not is_retry and (t_lower in disabled_targets or attr.get("oracledev_utility") is False):
                        continue
                    if not oracledev_cfg.get("enabled", False) and not attr.get("oracledev_utility") and not attr.get("oracledev"):
                        util_def_url = build_oracle_endpoint_url(oracledev_cfg.get("base_url"), oracledev_cfg.get("utility_resource_endpoint") or "/production_utilities_consumption/")
                        item_results.append({
                            "target_type": "oracledev_utility",
                            "attribute_name": attr_name,
                            "target_endpoint": m.get("target_endpoint_url_dev_utility") or util_def_url or oracledev_cfg.get("base_url"),
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": "Oracle Dev Utility integration is disabled in settings.",
                            "message": "Oracle Dev Utility integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    util_def_url = build_oracle_endpoint_url(oracledev_cfg.get("base_url"), oracledev_cfg.get("utility_resource_endpoint") or "/production_utilities_consumption/")
                    target_url = sanitize_endpoint_url(attr.get("target_endpoint_url_dev_utility") or util_def_url or m.get("target_endpoint_url_dev_utility") or None)
                    dev_ords_payload = build_destination_payload("oracledev_utility", source_attr=attr, mapping_rule=m, received_at=received_time, skip_params=skip_params_set)
                    pub_res = oracledev_client.publish_data(dev_ords_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": "oracledev_utility",
                        "attribute_name": attr_name,
                        "target_endpoint": pub_res.get("target_endpoint"),
                        "status": pub_res.get("status"),
                        "http_code": pub_res.get("http_code"),
                        "payload": dev_ords_payload,
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

                elif t_lower in ("oracledev", "oracle_dev", "oracledev_effluent", "oracle_dev_effluent"):
                    if not is_retry and (t_lower in disabled_targets or attr.get("oracledev") is False):
                        continue
                    if not oracledev_cfg.get("enabled", False) and not attr.get("oracledev"):
                        eff_def_url = build_oracle_endpoint_url(oracledev_cfg.get("base_url"), oracledev_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/")
                        item_results.append({
                            "target_type": "oracledev",
                            "attribute_name": attr_name,
                            "target_endpoint": m.get("target_endpoint_url_dev") or m.get("target_endpoint_url_oracledev") or eff_def_url or oracledev_cfg.get("base_url"),
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

                    eff_def_url = build_oracle_endpoint_url(oracledev_cfg.get("base_url"), oracledev_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/")
                    target_url = sanitize_endpoint_url(attr.get("target_endpoint_url_dev") or eff_def_url or m.get("target_endpoint_url_dev") or m.get("target_endpoint_url_oracledev") or (raw_target if "dev" in raw_target.lower() else None) or None)
                    dev_ords_payload = build_destination_payload("oracledev", source_attr=attr, mapping_rule=m, received_at=received_time, skip_params=skip_params_set)
                    pub_res = oracledev_client.publish_data(dev_ords_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": "oracledev",
                        "attribute_name": attr_name,
                        "target_endpoint": pub_res.get("target_endpoint"),
                        "status": pub_res.get("status"),
                        "http_code": pub_res.get("http_code"),
                        "payload": dev_ords_payload,
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

                elif t_lower in ("oracle_production", "oracleproduction", "oracle_daily_production", "daily_production", "dailyproduction", "production_daily_output", "oracle_prod_production", "daily_output"):
                    if not is_retry and (t_lower in disabled_targets or attr.get("oracle_production") is False):
                        continue
                    prod_def_url = build_oracle_endpoint_url(erp_cfg.get("base_url"), erp_cfg.get("daily_production_resource_endpoint") or "/production_daily_output/")
                    if not erp_cfg.get("enabled", False) and not attr.get("oracle_production") and not attr.get("oracle"):
                        item_results.append({
                            "target_type": "oracle_production",
                            "attribute_name": attr_name,
                            "target_endpoint": attr.get("target_endpoint_url_oracle_production") or prod_def_url or m.get("target_endpoint_url_oracle_production") or erp_cfg.get("base_url"),
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": "Oracle ERP Daily Production integration is disabled in settings.",
                            "message": "Oracle ERP Daily Production integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    target_url = sanitize_endpoint_url(attr.get("target_endpoint_url_oracle_production") or prod_def_url or m.get("target_endpoint_url_oracle_production") or None)
                    pub_res = erp_client.publish_data(ords_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": "oracle_production",
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

                elif t_lower in ("oracle_utility", "oracleutility", "utility", "oracle_prod_utility"):
                    if not is_retry and (t_lower in disabled_targets or attr.get("oracle_utility") is False):
                        continue
                    if not erp_cfg.get("enabled", False) and not attr.get("oracle_utility") and not attr.get("oracle"):
                        util_def_url = build_oracle_endpoint_url(erp_cfg.get("base_url"), erp_cfg.get("utility_resource_endpoint") or "/production_utilities_consumption/")
                        item_results.append({
                            "target_type": "oracle_utility",
                            "attribute_name": attr_name,
                            "target_endpoint": m.get("target_endpoint_url_oracle_utility") or util_def_url or erp_cfg.get("base_url"),
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": "Oracle ERP Utility integration is disabled in settings.",
                            "message": "Oracle ERP Utility integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    util_def_url = build_oracle_endpoint_url(erp_cfg.get("base_url"), erp_cfg.get("utility_resource_endpoint") or "/production_utilities_consumption/")
                    target_url = sanitize_endpoint_url(attr.get("target_endpoint_url_oracle_utility") or util_def_url or m.get("target_endpoint_url_oracle_utility") or None)
                    pub_res = erp_client.publish_data(ords_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": "oracle_utility",
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

                elif t_lower.startswith("oracledev_") and t_lower not in ("oracledev_effluent", "oracle_dev_effluent"):
                    ckey = t_lower[len("oracledev_"):]
                    if not is_retry and (t_lower in disabled_targets or attr.get(t_lower) is False):
                        continue
                    custom_eps_list = get_oracle_custom_endpoints(settings)
                    ce_match = next((ce for ce in custom_eps_list if ce["key"] == ckey), None)
                    dev_res_path = ce_match["dev_path"] if ce_match else f"/{ckey}/"
                    custom_def_url = build_oracle_endpoint_url(oracledev_cfg.get("base_url"), dev_res_path)
                    url_prop = f"target_endpoint_url_dev_{ckey}"
                    if not oracledev_cfg.get("enabled", False) and not attr.get(t_lower) and not attr.get("oracledev"):
                        item_results.append({
                            "target_type": t_lower,
                            "attribute_name": attr_name,
                            "target_endpoint": attr.get(url_prop) or custom_def_url or m.get(url_prop) or oracledev_cfg.get("base_url"),
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": f"Oracle Dev ({ckey}) integration is disabled in settings.",
                            "message": f"Oracle Dev ({ckey}) integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    target_url = sanitize_endpoint_url(attr.get(url_prop) or custom_def_url or m.get(url_prop) or None)
                    dev_ords_payload = build_destination_payload(t_lower, source_attr=attr, mapping_rule=m, received_at=received_time, skip_params=skip_params_set)
                    pub_res = oracledev_client.publish_data(dev_ords_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": t_lower,
                        "attribute_name": attr_name,
                        "target_endpoint": pub_res.get("target_endpoint"),
                        "status": pub_res.get("status"),
                        "http_code": pub_res.get("http_code"),
                        "payload": dev_ords_payload,
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

                elif t_lower.startswith("oracle_") and t_lower not in ("oracle_erp", "oracle_effluent", "oracle_dev", "oracle_dev_effluent"):
                    ckey = t_lower[len("oracle_"):]
                    if not is_retry and (t_lower in disabled_targets or attr.get(t_lower) is False):
                        continue
                    custom_eps_list = get_oracle_custom_endpoints(settings)
                    ce_match = next((ce for ce in custom_eps_list if ce["key"] == ckey), None)
                    prod_res_path = ce_match["prod_path"] if ce_match else f"/{ckey}/"
                    custom_def_url = build_oracle_endpoint_url(erp_cfg.get("base_url"), prod_res_path)
                    url_prop = f"target_endpoint_url_oracle_{ckey}"
                    if not erp_cfg.get("enabled", False) and not attr.get(t_lower) and not attr.get("oracle"):
                        item_results.append({
                            "target_type": t_lower,
                            "attribute_name": attr_name,
                            "target_endpoint": attr.get(url_prop) or custom_def_url or m.get(url_prop) or erp_cfg.get("base_url"),
                            "status": "PENDING_SETUP",
                            "http_code": None,
                            "payload": {},
                            "response": None,
                            "error": f"Oracle ERP ({ckey}) integration is disabled in settings.",
                            "message": f"Oracle ERP ({ckey}) integration is disabled in settings."
                        })
                        is_pending_setup = True
                        all_succeeded = False
                        continue

                    target_url = sanitize_endpoint_url(attr.get(url_prop) or custom_def_url or m.get(url_prop) or None)
                    pub_res = erp_client.publish_data(ords_payload, target_endpoint=target_url)

                    item_results.append({
                        "target_type": t_lower,
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
                    # Oracle ORDS / ERP Cloud Production (Effluent)
                    if not is_retry and ("oracle" in disabled_targets or attr.get("oracle") is False):
                        continue
                    if not erp_cfg.get("enabled", False) and not attr.get("oracle"):
                        eff_def_url = build_oracle_endpoint_url(erp_cfg.get("base_url"), erp_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/")
                        item_results.append({
                            "target_type": "oracle",
                            "attribute_name": attr_name,
                            "target_endpoint": m.get("target_endpoint_url") or m.get("target_endpoint_url_oracle") or eff_def_url or (raw_target if "hxgnsmartcloud" not in raw_target.lower() and "dev" not in raw_target.lower() else None) or erp_cfg.get("base_url"),
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

                    eff_def_url = build_oracle_endpoint_url(erp_cfg.get("base_url"), erp_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/")
                    target_url = sanitize_endpoint_url(attr.get("target_endpoint_url_oracle") or eff_def_url or m.get("target_endpoint_url_oracle") or m.get("target_endpoint_url") or (raw_target if "hxgnsmartcloud" not in raw_target.lower() and "dev" not in raw_target.lower() else None) or None)
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

    # Summary of target endpoints used
    target_types_used = list(dict.fromkeys(r.get("target_type", "oracle").upper() for r in item_results))
    label_map = {
        "ORACLE": "ORACLE PROD",
        "ORACLE_UTILITY": "ORACLE PROD (UTILITY)",
        "ORACLE_PRODUCTION": "ORACLE PROD (DAILY PRODUCTION)",
        "ORACLEDEV": "ORACLE DEV",
        "ORACLEDEV_UTILITY": "ORACLE DEV (UTILITY)",
        "ORACLEDEV_PRODUCTION": "ORACLE DEV (DAILY PRODUCTION)",
        "J5": "OCTAVE",
        "J5DEV": "OCTAVE DEV"
    }
    for ce in get_oracle_custom_endpoints(settings):
        ck_upper = ce["key"].upper()
        lbl_upper = (ce.get("label") or ce["key"]).upper()
        label_map[f"ORACLE_{ck_upper}"] = f"ORACLE PROD ({lbl_upper})"
        label_map[f"ORACLEDEV_{ck_upper}"] = f"ORACLE DEV ({lbl_upper})"
    targets_label = " & ".join(label_map.get(t, t) for t in target_types_used) if target_types_used else "Endpoint"

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
    Scans staged deliveries for any in FAILED, PENDING_RETRY, or PENDING_ORACLE state and retries dispatching them.
    Only triggers on deliveries that failed or are pending; already dispatched deliveries are untouched.
    """
    settings = load_settings()
    erp_cfg = settings.get("oracle_erp", {})
    oracledev_cfg = settings.get("oracledev", {})
    j5_cfg = settings.get("j5_endpoint", {})
    j5dev_cfg = settings.get("j5dev_endpoint", {})
    auto_dispatch_enabled = settings.get("pipeline", {}).get("auto_dispatch", True) and settings.get("pipeline", {}).get("auto_dispatch_deliveries", True)
    any_enabled = (
        erp_cfg.get("enabled", False) or
        oracledev_cfg.get("enabled", False) or
        j5_cfg.get("enabled", False) or
        j5dev_cfg.get("enabled", False)
    )

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
            f"Scheduler retry cycle: Successfully forwarded {dispatched} previously failed/pending delivery(ies) to destination endpoint(s)."
        )

    return {
        "total_pending": len(pending),
        "dispatched": dispatched,
        "failed": failed,
        "errors": errors
    }

