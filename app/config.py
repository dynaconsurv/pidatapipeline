"""
Configuration management for the PI-to-Oracle ERP Data Pipeline.
All configurations are persisted exclusively in JSON files (no database).
"""
from __future__ import annotations
import json
import os
import threading
import urllib.parse
from typing import Dict, Any, List, Optional


def sanitize_endpoint_url(url: Any) -> str:
    """
    Sanitizes an endpoint URL to remove duplicate consecutive path segments
    (e.g. /Final_Discharge_Effluent/Final_Discharge_Effluent/) and normalize slashes.
    """
    if not url or not isinstance(url, str):
        return ""
    u = str(url).strip().strip('"').strip("'")
    if not u:
        return ""
    if not (u.startswith("http://") or u.startswith("https://")):
        return u
    try:
        parsed = urllib.parse.urlsplit(u)
        raw_segments = [s for s in parsed.path.split("/") if s]
        deduped = []
        for s in raw_segments:
            if deduped and s.lower() == deduped[-1].lower():
                continue
            deduped.append(s)
        new_path = "/" + "/".join(deduped)
        if parsed.path.endswith("/") and not new_path.endswith("/"):
            new_path += "/"
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, new_path, parsed.query, parsed.fragment))
    except Exception:
        return u


CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config"))
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
MAPPINGS_FILE = os.path.join(CONFIG_DIR, "mappings.json")

_lock = threading.RLock()

DEFAULT_SETTINGS: Dict[str, Any] = {
    "pi_web_api": {
        "url": "https://pi-server.local/piwebapi",
        "auth_type": "basic",  # 'basic', 'bearer', 'oauth2', 'kerberos', 'anonymous'
        "username": "pi_service_user",
        "password": "",
        "bearer_token": "",
        "token_url": "",
        "client_id": "",
        "client_secret": "",
        "scope": "",
        "verify_ssl": False,
        "af_server": "PISRV01",
        "af_database": "Plant_Operations",
        "simulation_mode": False,  # Default to real connection testing; only simulates if user explicitly enables it
        "timeout_seconds": 10
    },
    "oracle_erp": {
        "enabled": True,
        "auth_type": "none",  # 'none', 'oauth2', 'basic', 'bearer'
        "base_url": "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int",
        "token_url": "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/oauth/token",
        "client_id": "",
        "client_secret": "",
        "scope": "",
        "username": "",
        "password": "",
        "bearer_token": "",
        "resource_endpoint": "/Final_Discharge_Effluent/",
        "utility_resource_endpoint": "/production_utilities_consumption/",
        "daily_production_resource_endpoint": "/production_daily_output/",
        "custom_endpoints": [],
        "http_method": "POST",
        "custom_headers": {
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        "timeout_seconds": 15
    },
    "oracledev": {
        "enabled": True,
        "auth_type": "none",  # 'none', 'oauth2', 'basic', 'bearer'
        "base_url": "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int",
        "token_url": "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/oauth/token",
        "client_id": "",
        "client_secret": "",
        "scope": "",
        "username": "",
        "password": "",
        "bearer_token": "",
        "resource_endpoint": "/Final_Discharge_Effluent/",
        "utility_resource_endpoint": "/production_utilities_consumption/",
        "daily_production_resource_endpoint": "/production_daily_output/",
        "custom_endpoints": [],
        "http_method": "POST",
        "custom_headers": {
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        "timeout_seconds": 15
    },
    "j5_endpoint": {
        "enabled": True,
        "auth_type": "basic",
        "url": "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=j5_pi_opslogbook",
        "username": "HIRUJR_JZNOT1742577235_TST",
        "password": "kah4YAH!bvm-vkt_jzd",
        "tenant_id": "JZNOT1742577235_TST",
        "timeout_seconds": 15
    },
    "j5dev_endpoint": {
        "enabled": True,
        "auth_type": "basic",
        "url": "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=j5_pi_opslogbook",
        "username": "HIRUJR_JZNOT1742577235_TST",
        "password": "kah4YAH!bvm-vkt_jzd",
        "tenant_id": "JZNOT1742577235_TST",
        "timeout_seconds": 15
    },
    "pipeline": {
        "interval_seconds": 120,
        "ingestion_mode": "endpoint",
        "auto_dispatch": True,
        "auto_create_j5_mapping": True,
        "skip_parameters": "j5, j5dev, oracle, oracledev, endpoint, environment",
        "auto_start": True,
        "max_history_items": 100
    },
    "endpoint_security": {
        "api_key_enabled": False,
        "api_key": "pi_sec_a7f92e48c12b45",
        "ip_whitelist_enabled": False,
        "allowed_ips": "10.60.2.20"
    }
}

DEFAULT_MAPPINGS: List[Dict[str, Any]] = [
    {
        "id": "map-final-discharge",
        "name": "Final Discharge Effluent 30 Min Average",
        "af_server": "PISRV01",
        "af_database": "Plant_Operations",
        "element_path": "Effluent\\Discharge",
        "attribute_name": "30 Min Average",
        "target_type": "oracle",
        "full_path": "\\\\PISRV01\\Plant_Operations\\Effluent\\Discharge|30 Min Average",
        "target_endpoint_url": "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/",
        "tag": "TAG2",
        "description": "DESCRIPTION2",
        "limit": "LIMIT2",
        "results": "RESULTS2",
        "target_field": "value",
        "meter_tag": "TAG2",
        "target_tag_field": "tag",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 2,
        "uom": "pH",
        "enabled": True
    },
    {
        "id": "map-boiler-press",
        "name": "Boiler 101 Steam Pressure",
        "af_server": "PISRV01",
        "af_database": "Plant_Operations",
        "element_path": "Unit 1\\Boilers\\Boiler-101",
        "attribute_name": "Steam Pressure",
        "full_path": "\\\\PISRV01\\Plant_Operations\\Unit 1\\Boilers\\Boiler-101|Steam Pressure",
        "target_endpoint_url": "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/",
        "tag": "BLR101_STM_PRESS",
        "description": "Boiler 101 Steam Pressure",
        "limit": "100.0",
        "results": "Normal",
        "target_field": "value",
        "meter_tag": "BLR101_STM_PRESS",
        "target_tag_field": "tag",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 2,
        "uom": "bar",
        "enabled": True
    },
    {
        "id": "map-turbine-flow",
        "name": "Turbine Feedwater Flow Rate",
        "af_server": "PISRV01",
        "af_database": "Plant_Operations",
        "element_path": "Unit 1\\Turbines\\Turbine-TG01",
        "attribute_name": "Feedwater Flow",
        "full_path": "\\\\PISRV01\\Plant_Operations\\Unit 1\\Turbines\\Turbine-TG01|Feedwater Flow",
        "target_endpoint_url": "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/",
        "tag": "TG01_FEED_FLOW",
        "description": "Turbine Feedwater Flow Rate",
        "limit": "500.0",
        "results": "Normal",
        "target_field": "value",
        "meter_tag": "TG01_FEED_FLOW",
        "target_tag_field": "tag",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 1,
        "uom": "m3/h",
        "enabled": True
    },
    {
        "id": "map-generator-power",
        "name": "Generator Active Power Output",
        "af_server": "PISRV01",
        "af_database": "Plant_Operations",
        "element_path": "Unit 1\\Generators\\Gen-01",
        "attribute_name": "Active Power",
        "full_path": "\\\\PISRV01\\Plant_Operations\\Unit 1\\Generators\\Gen-01|Active Power",
        "target_endpoint_url": "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/",
        "tag": "GEN01_ACT_PWR",
        "description": "Generator Active Power Output",
        "limit": "50.0",
        "results": "Normal",
        "target_field": "value",
        "meter_tag": "GEN01_ACT_PWR",
        "target_tag_field": "tag",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 3,
        "uom": "MW",
        "enabled": False
    },
    {
        "id": "map-pump-vibe",
        "name": "Cooling Pump 2A Vibration",
        "af_server": "PISRV01",
        "af_database": "Plant_Operations",
        "element_path": "Utilities\\Pumps\\Pump-2A",
        "attribute_name": "Vibration Overall",
        "full_path": "\\\\PISRV01\\Plant_Operations\\Utilities\\Pumps\\Pump-2A|Vibration Overall",
        "target_endpoint_url": "https://gda83ebb4f9065b-ecoatpdev1.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/",
        "tag": "PMP2A_VIB_RMS",
        "description": "Cooling Pump 2A Vibration",
        "limit": "4.5",
        "results": "Normal",
        "target_field": "value",
        "meter_tag": "PMP2A_VIB_RMS",
        "target_tag_field": "tag",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 2,
        "uom": "mm/s",
        "target_type": "oracle",
        "enabled": True
    },
    {
        "id": "map-j5-sample",
        "name": "J5 Inbound Telemetry Stream",
        "target_type": "j5",
        "af_server": "PISRV01",
        "af_database": "Plant_Operations",
        "element_path": "Effluent\\Discharge",
        "attribute_name": "Discharge Flow Rate",
        "full_path": "\\\\PISRV01\\Plant_Operations\\Effluent\\Discharge|Discharge Flow Rate",
        "target_endpoint_url": "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder",
        "tag": "purchaseorder",
        "description": "J5 Inbound Telemetry Message",
        "limit": "100.0",
        "results": "Normal",
        "target_field": "value",
        "meter_tag": "purchaseorder",
        "target_tag_field": "tag",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 2,
        "uom": "m3/h",
        "enabled": False
    }
]


def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_settings() -> Dict[str, Any]:
    ensure_config_dir()
    with _lock:
        if not os.path.exists(SETTINGS_FILE):
            save_settings(DEFAULT_SETTINGS)
            return DEFAULT_SETTINGS
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Merge in any missing top-level keys from defaults
                for k, v in DEFAULT_SETTINGS.items():
                    if k not in data:
                        data[k] = v
                    elif isinstance(v, dict):
                        for sub_k, sub_v in v.items():
                            if sub_k not in data[k]:
                                data[k][sub_k] = sub_v

                # Auto-migrate unconfigured legacy OAuth2 to ORDS Direct (none)
                erp = data.get("oracle_erp", {})
                if erp.get("auth_type") == "oauth2" and not erp.get("client_id") and not erp.get("client_secret"):
                    erp["auth_type"] = "none"
                    erp["enabled"] = True
                    if "your-pod" in erp.get("base_url", "") or not erp.get("base_url"):
                        erp["base_url"] = DEFAULT_SETTINGS["oracle_erp"]["base_url"]
                        erp["resource_endpoint"] = DEFAULT_SETTINGS["oracle_erp"]["resource_endpoint"]
                        erp["custom_headers"] = DEFAULT_SETTINGS["oracle_erp"]["custom_headers"]
                    save_settings(data)

                # Ensure resource paths are populated for Oracle Prod and Oracle Dev
                for sec_name in ("oracle_erp", "oracledev"):
                    sec = data.get(sec_name)
                    if isinstance(sec, dict):
                        if not sec.get("resource_endpoint"):
                            sec["resource_endpoint"] = "/Final_Discharge_Effluent/"
                        if not sec.get("utility_resource_endpoint"):
                            sec["utility_resource_endpoint"] = "/production_utilities_consumption/"
                        if not sec.get("daily_production_resource_endpoint"):
                            sec["daily_production_resource_endpoint"] = "/production_daily_output/"
                        if not isinstance(sec.get("custom_endpoints"), list):
                            sec["custom_endpoints"] = []

                sync_oracle_custom_endpoints(data)

                return data
        except Exception as e:
            print(f"Error loading settings.json: {e}. Returning defaults.")
            return DEFAULT_SETTINGS


def normalize_oracle_endpoint_key(raw_key: Any) -> str:
    """
    Normalizes an Oracle endpoint key/name/path into a clean lowercase slug
    (e.g. 'Boiler Steam Output' or '/boiler_steam_output/' -> 'boiler_steam_output').
    """
    import re
    s = str(raw_key or "").strip().strip("/").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    for prefix in ("oracledev_", "oracle_dev_", "oracle_", "dev_"):
        if s.startswith(prefix) and len(s) > len(prefix):
            s = s[len(prefix):]
    return s


def normalize_oracle_resource_path(raw_path: Any) -> str:
    """
    Normalizes an ORDS resource path so it starts and ends with '/'.
    """
    p = str(raw_path or "").strip()
    if not p:
        return "/"
    if not p.startswith("/"):
        p = "/" + p
    if not p.endswith("/"):
        p = p + "/"
    return p


BUILTIN_ORACLE_ENDPOINT_KEYS = frozenset({
    "effluent",
    "final_discharge_effluent",
    "utility",
    "utilities",
    "production_utilities_consumption",
    "production",
    "daily_production",
    "daily_production_data",
    "production_daily_output",
})


def sync_oracle_custom_endpoints(settings: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Ensures custom_endpoints in oracle_erp (Prod) and oracledev (Dev) are synchronized
    so that any custom endpoint added is present in both Prod and Dev.
    Returns a unified list of custom endpoint descriptors:
      [{"key": k, "label": label, "prod_path": p_path, "dev_path": d_path,
        "prod_target": f"oracle_{k}", "dev_target": f"oracledev_{k}"}]
    """
    if not isinstance(settings, dict):
        return []
    erp_sec = settings.setdefault("oracle_erp", {})
    dev_sec = settings.setdefault("oracledev", {})
    raw_prod = erp_sec.get("custom_endpoints") if isinstance(erp_sec.get("custom_endpoints"), list) else []
    raw_dev = dev_sec.get("custom_endpoints") if isinstance(dev_sec.get("custom_endpoints"), list) else []

    merged: Dict[str, Dict[str, str]] = {}
    order: List[str] = []

    for item in raw_prod:
        if not isinstance(item, dict):
            continue
        raw_k = item.get("key") or item.get("path") or item.get("label") or item.get("name")
        key = normalize_oracle_endpoint_key(raw_k)
        if not key or key in BUILTIN_ORACLE_ENDPOINT_KEYS:
            continue
        label = str(item.get("label") or item.get("name") or key.replace("_", " ").title()).strip()
        path = normalize_oracle_resource_path(item.get("path") or item.get("resource_endpoint") or f"/{key}/")
        if key not in merged:
            order.append(key)
            merged[key] = {"key": key, "label": label, "prod_path": path, "dev_path": path}
        else:
            merged[key]["label"] = label or merged[key]["label"]
            merged[key]["prod_path"] = path

    for item in raw_dev:
        if not isinstance(item, dict):
            continue
        raw_k = item.get("key") or item.get("path") or item.get("label") or item.get("name")
        key = normalize_oracle_endpoint_key(raw_k)
        if not key or key in BUILTIN_ORACLE_ENDPOINT_KEYS:
            continue
        label = str(item.get("label") or item.get("name") or key.replace("_", " ").title()).strip()
        path = normalize_oracle_resource_path(item.get("path") or item.get("resource_endpoint") or f"/{key}/")
        if key not in merged:
            order.append(key)
            merged[key] = {"key": key, "label": label, "prod_path": path, "dev_path": path}
        else:
            if not merged[key].get("label"):
                merged[key]["label"] = label
            merged[key]["dev_path"] = path

    prod_list: List[Dict[str, str]] = []
    dev_list: List[Dict[str, str]] = []
    unified: List[Dict[str, str]] = []
    for k in order:
        entry = merged[k]
        prod_list.append({"key": k, "label": entry["label"], "path": entry["prod_path"]})
        dev_list.append({"key": k, "label": entry["label"], "path": entry["dev_path"]})
        unified.append({
            "key": k,
            "label": entry["label"],
            "prod_path": entry["prod_path"],
            "dev_path": entry["dev_path"],
            "prod_target": f"oracle_{k}",
            "dev_target": f"oracledev_{k}",
        })

    erp_sec["custom_endpoints"] = prod_list
    dev_sec["custom_endpoints"] = dev_list
    return unified


def get_oracle_custom_endpoints(settings: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """
    Returns the synchronized list of custom Oracle endpoints across Prod & Dev.
    """
    if settings is None:
        settings = load_settings()
    return sync_oracle_custom_endpoints(settings)


def get_all_oracle_resource_segments(settings: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Returns all known and custom ORDS resource path segments (lowercase, stripped of '/')
    so URL builders can cleanly replace trailing resource segments on base URLs.
    """
    segs = [
        "final_discharge_effluent",
        "production_utilities_consumption",
        "production_daily_output",
    ]
    if settings is None:
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as sf:
                    settings = json.load(sf)
        except Exception:
            settings = None

    if isinstance(settings, dict):
        for sec_name in ("oracle_erp", "oracledev"):
            sec = settings.get(sec_name)
            if isinstance(sec, dict):
                for field in ("resource_endpoint", "utility_resource_endpoint", "daily_production_resource_endpoint"):
                    val = str(sec.get(field) or "").strip().strip("/").lower()
                    if val and val not in segs:
                        segs.append(val)
                for ce in (sec.get("custom_endpoints") or []):
                    if isinstance(ce, dict):
                        cpath = str(ce.get("path") or "").strip().strip("/").lower()
                        if cpath and cpath not in segs:
                            segs.append(cpath)
    return segs


def save_settings(settings: Dict[str, Any]) -> None:
    ensure_config_dir()
    sync_oracle_custom_endpoints(settings)
    for sec_key in ("oracle_erp", "oracledev"):
        sec = settings.get(sec_key)
        if isinstance(sec, dict) and sec.get("base_url"):
            sec["base_url"] = sanitize_endpoint_url(sec["base_url"])
    for j5_key in ("j5_endpoint", "j5dev_endpoint"):
        j5_sec = settings.get(j5_key)
        if isinstance(j5_sec, dict) and j5_sec.get("url"):
            j5_sec["url"] = sanitize_endpoint_url(j5_sec["url"])
    with _lock:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        if os.path.exists(MAPPINGS_FILE):
            try:
                with open(MAPPINGS_FILE, "r", encoding="utf-8") as mf:
                    mappings = json.load(mf)
                if isinstance(mappings, list) and sync_mappings_urls_with_settings(mappings, settings):
                    with open(MAPPINGS_FILE, "w", encoding="utf-8") as mf:
                        json.dump(mappings, mf, indent=2)
            except Exception as e:
                print(f"Warning: could not sync mappings.json on save_settings: {e}")


MAPPING_URL_PROPERTIES = (
    "target_endpoint_url",
    "target_endpoint_url_oracle",
    "target_endpoint_url_oracle_utility",
    "target_endpoint_url_oracle_production",
    "target_endpoint_url_dev",
    "target_endpoint_url_dev_utility",
    "target_endpoint_url_dev_production",
    "target_endpoint_url_j5",
    "target_endpoint_url_j5dev",
)


def _build_oracle_config_url(base_url: Any, resource_endpoint: Any, known_segments: Optional[List[str]] = None) -> str:
    b = sanitize_endpoint_url(base_url).rstrip("/")
    r = str(resource_endpoint or "/Final_Discharge_Effluent/").strip()
    if not r.startswith("/"):
        r = "/" + r
    if not r.endswith("/"):
        r = r + "/"
    if not b:
        return ""
    segs = known_segments or ("final_discharge_effluent", "production_utilities_consumption", "production_daily_output")
    for seg in segs:
        if seg and b.lower().endswith("/" + seg.lower()):
            b = b[:-(len(seg) + 1)].rstrip("/")
            break
    if b.lower().endswith(r.rstrip("/").lower()):
        return sanitize_endpoint_url(b + "/")
    return sanitize_endpoint_url(f"{b}{r}")


def sync_mappings_urls_with_settings(
    mappings: List[Dict[str, Any]],
    settings: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Synchronizes cached target_endpoint_url_* fields on mappings with the active
    endpoint URLs configured in settings.json so that updating an endpoint URL
    in Settings immediately takes effect across all existing mappings.
    """
    if not isinstance(mappings, list):
        return False
    if settings is None:
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as sf:
                    settings = json.load(sf)
            except Exception:
                settings = DEFAULT_SETTINGS
        else:
            settings = DEFAULT_SETTINGS

    custom_eps = sync_oracle_custom_endpoints(settings)
    all_segs = get_all_oracle_resource_segments(settings)

    erp_cfg = settings.get("oracle_erp", {}) if isinstance(settings, dict) else {}
    dev_cfg = settings.get("oracledev", {}) if isinstance(settings, dict) else {}
    j5_cfg = settings.get("j5_endpoint", {}) if isinstance(settings, dict) else {}
    j5dev_cfg = settings.get("j5dev_endpoint", {}) if isinstance(settings, dict) else {}

    oracle_url = _build_oracle_config_url(
        erp_cfg.get("base_url"),
        erp_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/",
        all_segs
    )
    oracle_util_url = _build_oracle_config_url(
        erp_cfg.get("base_url"),
        erp_cfg.get("utility_resource_endpoint") or "/production_utilities_consumption/",
        all_segs
    )
    oracle_prod_data_url = _build_oracle_config_url(
        erp_cfg.get("base_url"),
        erp_cfg.get("daily_production_resource_endpoint") or "/production_daily_output/",
        all_segs
    )
    dev_url = _build_oracle_config_url(
        dev_cfg.get("base_url"),
        dev_cfg.get("resource_endpoint") or "/Final_Discharge_Effluent/",
        all_segs
    )
    dev_util_url = _build_oracle_config_url(
        dev_cfg.get("base_url"),
        dev_cfg.get("utility_resource_endpoint") or "/production_utilities_consumption/",
        all_segs
    )
    dev_prod_data_url = _build_oracle_config_url(
        dev_cfg.get("base_url"),
        dev_cfg.get("daily_production_resource_endpoint") or "/production_daily_output/",
        all_segs
    )

    custom_prod_urls: Dict[str, str] = {}
    custom_dev_urls: Dict[str, str] = {}
    for ce in custom_eps:
        ckey = ce["key"]
        custom_prod_urls[ckey] = _build_oracle_config_url(erp_cfg.get("base_url"), ce["prod_path"], all_segs)
        custom_dev_urls[ckey] = _build_oracle_config_url(dev_cfg.get("base_url"), ce["dev_path"], all_segs)

    j5_url = sanitize_endpoint_url(
        j5_cfg.get("url") or "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder"
    )
    j5dev_url = sanitize_endpoint_url(
        j5dev_cfg.get("url") or "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=j5_pi_opslogbook"
    )

    def _resolve_primary(t_type: str) -> str:
        tl = str(t_type or "oracle").strip().lower()
        if tl in ("j5dev", "j5_dev", "jfdev", "octavedev", "octave_dev"):
            return j5dev_url
        if tl in ("j5", "octave"):
            return j5_url
        if tl in ("oracledev_production", "oracle_dev_production", "dev_production", "dev_daily_production"):
            return dev_prod_data_url
        if tl in ("oracledev_utility", "oracle_dev_utility", "dev_utility"):
            return dev_util_url
        if tl in ("oracledev", "oracle_dev", "oracledev_effluent", "oracle_dev_effluent"):
            return dev_url
        if tl in ("oracle_production", "oracleproduction", "oracle_daily_production", "daily_production", "production_daily_output"):
            return oracle_prod_data_url
        if tl in ("oracle_utility", "oracleutility", "utility", "oracle_prod_utility"):
            return oracle_util_url
        if tl.startswith("oracledev_"):
            ck = tl[len("oracledev_"):]
            if ck in custom_dev_urls:
                return custom_dev_urls[ck]
        if tl.startswith("oracle_"):
            ck = tl[len("oracle_"):]
            if ck in custom_prod_urls:
                return custom_prod_urls[ck]
        return oracle_url

    changed = False
    for m in mappings:
        if not isinstance(m, dict):
            continue
        if oracle_url and m.get("target_endpoint_url_oracle") != oracle_url:
            m["target_endpoint_url_oracle"] = oracle_url
            changed = True
        if oracle_util_url and m.get("target_endpoint_url_oracle_utility") != oracle_util_url:
            m["target_endpoint_url_oracle_utility"] = oracle_util_url
            changed = True
        if oracle_prod_data_url and m.get("target_endpoint_url_oracle_production") != oracle_prod_data_url:
            m["target_endpoint_url_oracle_production"] = oracle_prod_data_url
            changed = True
        if dev_url and m.get("target_endpoint_url_dev") != dev_url:
            m["target_endpoint_url_dev"] = dev_url
            changed = True
        if dev_util_url and m.get("target_endpoint_url_dev_utility") != dev_util_url:
            m["target_endpoint_url_dev_utility"] = dev_util_url
            changed = True
        if dev_prod_data_url and m.get("target_endpoint_url_dev_production") != dev_prod_data_url:
            m["target_endpoint_url_dev_production"] = dev_prod_data_url
            changed = True
        for ckey, cp_url in custom_prod_urls.items():
            prop = f"target_endpoint_url_oracle_{ckey}"
            if cp_url and m.get(prop) != cp_url:
                m[prop] = cp_url
                changed = True
        for ckey, cd_url in custom_dev_urls.items():
            prop = f"target_endpoint_url_dev_{ckey}"
            if cd_url and m.get(prop) != cd_url:
                m[prop] = cd_url
                changed = True
        if j5_url and m.get("target_endpoint_url_j5") != j5_url:
            m["target_endpoint_url_j5"] = j5_url
            changed = True
        if j5dev_url and m.get("target_endpoint_url_j5dev") != j5dev_url:
            m["target_endpoint_url_j5dev"] = j5dev_url
            changed = True

        t_types = m.get("target_types") or ([m.get("target_type")] if m.get("target_type") else ["oracle"])
        primary_type = t_types[0] if t_types else "oracle"
        expected_primary = _resolve_primary(primary_type)
        if expected_primary and m.get("target_endpoint_url") != expected_primary:
            m["target_endpoint_url"] = expected_primary
            changed = True

    return changed


def load_mappings() -> List[Dict[str, Any]]:
    ensure_config_dir()
    with _lock:
        if not os.path.exists(MAPPINGS_FILE):
            save_mappings(DEFAULT_MAPPINGS)
            return DEFAULT_MAPPINGS
        try:
            with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
                mappings = json.load(f)
                changed = False
                for m in mappings:
                    if not m.get("target_types"):
                        tt = m.get("target_type")
                        if tt:
                            m["target_types"] = [tt]
                        else:
                            url = str(m.get("target_endpoint_url") or "").lower()
                            m["target_types"] = ["j5"] if ("hxgnsmartcloud" in url or "tag=purchaseorder" in url) else ["oracle"]
                        changed = True
                    for u_prop in MAPPING_URL_PROPERTIES:
                        if m.get(u_prop):
                            sanitized = sanitize_endpoint_url(m[u_prop])
                            if sanitized != m[u_prop]:
                                m[u_prop] = sanitized
                                changed = True
                if sync_mappings_urls_with_settings(mappings):
                    changed = True
                if changed:
                    try:
                        with open(MAPPINGS_FILE, "w", encoding="utf-8") as wf:
                            json.dump(mappings, wf, indent=2)
                    except Exception:
                        pass
                return mappings
        except Exception as e:
            print(f"Error loading mappings.json: {e}. Returning defaults.")
            return DEFAULT_MAPPINGS


def save_mappings(mappings: List[Dict[str, Any]]) -> None:
    ensure_config_dir()
    for m in mappings:
        for u_prop in MAPPING_URL_PROPERTIES:
            if m.get(u_prop):
                m[u_prop] = sanitize_endpoint_url(m[u_prop])
    with _lock:
        with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2)


FIELD_MAPPINGS_FILE = os.path.join(CONFIG_DIR, "field_mappings.json")

DEFAULT_ORACLE_FIELD_MAPPINGS: List[Dict[str, Any]] = [
    {
        "id": "ora-ts",
        "source": "timestamp",
        "target": "timestamp",
        "transform": "receipt_time",
        "description": "Delivery receipt arrival timestamp (UTC Zulu)",
        "enabled": True
    },
    {
        "id": "ora-analysis-time",
        "source": "AnalysisTime",
        "target": "TESTTIMESTAMP",
        "transform": "timestamp_zulu",
        "description": "PI AF analysis event timestamp formatted to UTC Zulu",
        "enabled": True
    },
    {
        "id": "ora-tag",
        "source": "tag",
        "target": "tag",
        "transform": "string",
        "description": "PI meter tag name (or Tagname / Name)",
        "enabled": True
    },
    {
        "id": "ora-desc",
        "source": "description",
        "target": "description",
        "transform": "string",
        "description": "Telemetry attribute description",
        "enabled": True
    },
    {
        "id": "ora-val",
        "source": "value",
        "target": "value",
        "transform": "numeric_scaled",
        "description": "Telemetry reading value (scaled & rounded)",
        "enabled": True
    },
    {
        "id": "ora-limit",
        "source": "limit",
        "target": "limit",
        "transform": "string",
        "description": "Telemetry threshold limit",
        "enabled": True
    },
    {
        "id": "ora-res",
        "source": "results",
        "target": "results",
        "transform": "string",
        "description": "PASS / FAIL / Normal quality result",
        "enabled": False
    },
    {
        "id": "ora-uom",
        "source": "uom",
        "target": "uom",
        "transform": "string",
        "description": "Unit of measure",
        "enabled": True
    },
    {
        "id": "ora-hilimit",
        "source": "hilimit",
        "target": "hilimit",
        "transform": "string",
        "description": "High limit threshold",
        "enabled": True
    },
    {
        "id": "ora-lolimit",
        "source": "lolimit",
        "target": "lolimit",
        "transform": "string",
        "description": "Low limit threshold",
        "enabled": True
    }
]

DEFAULT_OCTAVE_FIELD_MAPPINGS: List[Dict[str, Any]] = [
    {
        "id": "oct-tag-msg",
        "source": "tag",
        "target": "messageTag",
        "transform": "string",
        "description": "Octave message routing tag",
        "enabled": True
    },
    {
        "id": "oct-tag",
        "source": "tag",
        "target": "tag",
        "transform": "string",
        "description": "Meter tag name",
        "enabled": True
    },
    {
        "id": "oct-desc",
        "source": "description",
        "target": "description",
        "transform": "string",
        "description": "Attribute description",
        "enabled": True
    },
    {
        "id": "oct-val-num",
        "source": "value",
        "target": "readingValue",
        "transform": "numeric_scaled",
        "description": "Numeric reading value",
        "enabled": True
    },
    {
        "id": "oct-val-str",
        "source": "value",
        "target": "value",
        "transform": "string",
        "description": "Reading value as string",
        "enabled": True
    },
    {
        "id": "oct-uom-long",
        "source": "uom",
        "target": "unitOfMeasure",
        "transform": "string",
        "description": "Unit of measure name",
        "enabled": True
    },
    {
        "id": "oct-uom-short",
        "source": "uom",
        "target": "uom",
        "transform": "string",
        "description": "Short unit of measure",
        "enabled": True
    },
    {
        "id": "oct-limit",
        "source": "limit",
        "target": "limit",
        "transform": "string",
        "description": "Threshold limit",
        "enabled": True
    },
    {
        "id": "oct-results",
        "source": "results",
        "target": "results",
        "transform": "string",
        "description": "Results string",
        "enabled": True
    },
    {
        "id": "oct-quality",
        "source": "quality",
        "target": "quality",
        "transform": "string",
        "description": "Data quality flag",
        "enabled": True
    },
    {
        "id": "oct-ts",
        "source": "timestamp",
        "target": "timestamp",
        "transform": "receipt_time",
        "description": "Delivery receipt timestamp (UTC Zulu)",
        "enabled": True
    },
    {
        "id": "oct-reading-ts",
        "source": "timestamp",
        "target": "readingTimestamp",
        "transform": "receipt_time",
        "description": "Reading timestamp (UTC Zulu)",
        "enabled": True
    },
    {
        "id": "oct-analysistime",
        "source": "AnalysisTime",
        "target": "AnalysisTime",
        "transform": "timestamp_zulu",
        "description": "PI AF analysis event timestamp formatted to UTC Zulu",
        "enabled": True
    }
]


DEFAULT_ORACLE_PROD_FIELD_MAPPINGS = DEFAULT_ORACLE_FIELD_MAPPINGS
DEFAULT_ORACLE_DEV_FIELD_MAPPINGS = [dict(x) for x in DEFAULT_ORACLE_FIELD_MAPPINGS]
DEFAULT_OCTAVE_PROD_FIELD_MAPPINGS = DEFAULT_OCTAVE_FIELD_MAPPINGS
DEFAULT_OCTAVE_DEV_FIELD_MAPPINGS = [dict(x) for x in DEFAULT_OCTAVE_FIELD_MAPPINGS]


def load_field_mappings() -> Dict[str, List[Dict[str, Any]]]:
    """
    Loads configurable parameter & schema mappings for destination payloads.
    Provides separate mapping lists for both Prod and Dev environments:
    - oracle_prod: Oracle Cloud Production
    - oracle_dev: Oracle Cloud Development / Test
    - octave_prod: Octave / J5 Inbound Message Production
    - octave_dev: Octave / J5 Inbound Message Development / Test
    Persists to config/field_mappings.json and syncs with config/settings.json.
    """
    ensure_config_dir()
    with _lock:
        data = None
        if os.path.exists(FIELD_MAPPINGS_FILE):
            try:
                with open(FIELD_MAPPINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"Error loading {FIELD_MAPPINGS_FILE}: {e}. Falling back.")

        if not data or not isinstance(data, dict):
            settings = load_settings()
            ora_prod_maps = settings.get("oracle_erp", {}).get("parameter_mappings")
            ora_dev_maps = settings.get("oracledev", {}).get("parameter_mappings")
            oct_prod_maps = settings.get("j5_endpoint", {}).get("parameter_mappings")
            oct_dev_maps = settings.get("j5dev_endpoint", {}).get("parameter_mappings")
            data = {
                "oracle_prod": ora_prod_maps or [dict(x) for x in DEFAULT_ORACLE_PROD_FIELD_MAPPINGS],
                "oracle_dev": ora_dev_maps or ora_prod_maps or [dict(x) for x in DEFAULT_ORACLE_DEV_FIELD_MAPPINGS],
                "octave_prod": oct_prod_maps or [dict(x) for x in DEFAULT_OCTAVE_PROD_FIELD_MAPPINGS],
                "octave_dev": oct_dev_maps or oct_prod_maps or [dict(x) for x in DEFAULT_OCTAVE_DEV_FIELD_MAPPINGS]
            }

        # Resolve environments with fallback preserving explicit lists
        ora_prod = data.get("oracle_prod") if data.get("oracle_prod") is not None else (data.get("oracle") if data.get("oracle") is not None else [dict(x) for x in DEFAULT_ORACLE_PROD_FIELD_MAPPINGS])
        ora_dev = data.get("oracle_dev") if data.get("oracle_dev") is not None else (data.get("oracle") if data.get("oracle") is not None else [dict(x) for x in DEFAULT_ORACLE_DEV_FIELD_MAPPINGS])
        oct_prod = data.get("octave_prod") if data.get("octave_prod") is not None else (data.get("octave") if data.get("octave") is not None else [dict(x) for x in DEFAULT_OCTAVE_PROD_FIELD_MAPPINGS])
        oct_dev = data.get("octave_dev") if data.get("octave_dev") is not None else (data.get("octave") if data.get("octave") is not None else [dict(x) for x in DEFAULT_OCTAVE_DEV_FIELD_MAPPINGS])

        result = {
            "oracle_prod": ora_prod,
            "oracle_dev": ora_dev,
            "octave_prod": oct_prod,
            "octave_dev": oct_dev,
            # Legacy backwards-compatible aliases
            "oracle": ora_prod,
            "octave": oct_prod
        }
        return result


def save_field_mappings(mappings_dict: Dict[str, List[Dict[str, Any]]]) -> None:
    """
    Saves configurable parameter and schema mappings for Prod and Dev to config/field_mappings.json.
    Also syncs with config/settings.json under oracle_erp, oracledev, j5_endpoint, and j5dev_endpoint.
    Preserves existing environment mappings if an incoming payload only updates one environment.
    """
    ensure_config_dir()
    existing = {}
    if os.path.exists(FIELD_MAPPINGS_FILE):
        try:
            with open(FIELD_MAPPINGS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    ora_prod = mappings_dict.get("oracle_prod")
    if ora_prod is None:
        ora_prod = mappings_dict.get("oracle")
    if ora_prod is None:
        ora_prod = existing.get("oracle_prod") if existing.get("oracle_prod") is not None else [dict(x) for x in DEFAULT_ORACLE_PROD_FIELD_MAPPINGS]
    ora_dev = mappings_dict.get("oracle_dev")
    if ora_dev is None:
        ora_dev = existing.get("oracle_dev") if existing.get("oracle_dev") is not None else (mappings_dict.get("oracle") if mappings_dict.get("oracle") is not None else [dict(x) for x in DEFAULT_ORACLE_DEV_FIELD_MAPPINGS])
    oct_prod = mappings_dict.get("octave_prod")
    if oct_prod is None:
        oct_prod = mappings_dict.get("octave")
    if oct_prod is None:
        oct_prod = existing.get("octave_prod") if existing.get("octave_prod") is not None else [dict(x) for x in DEFAULT_OCTAVE_PROD_FIELD_MAPPINGS]
    oct_dev = mappings_dict.get("octave_dev")
    if oct_dev is None:
        oct_dev = existing.get("octave_dev") if existing.get("octave_dev") is not None else (mappings_dict.get("octave") if mappings_dict.get("octave") is not None else [dict(x) for x in DEFAULT_OCTAVE_DEV_FIELD_MAPPINGS])
    to_save = {
        "oracle_prod": ora_prod,
        "oracle_dev": ora_dev,
        "octave_prod": oct_prod,
        "octave_dev": oct_dev,
        "oracle": ora_prod,
        "octave": oct_prod
    }
    with _lock:
        with open(FIELD_MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2)

        # Also update settings.json sections
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                if "oracle_erp" in settings and isinstance(settings["oracle_erp"], dict):
                    settings["oracle_erp"]["parameter_mappings"] = ora_prod
                if "oracledev" in settings and isinstance(settings["oracledev"], dict):
                    settings["oracledev"]["parameter_mappings"] = ora_dev
                if "j5_endpoint" in settings and isinstance(settings["j5_endpoint"], dict):
                    settings["j5_endpoint"]["parameter_mappings"] = oct_prod
                if "j5dev_endpoint" in settings and isinstance(settings["j5dev_endpoint"], dict):
                    settings["j5dev_endpoint"]["parameter_mappings"] = oct_dev
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Notice: Could not sync field_mappings into settings.json: {e}")


