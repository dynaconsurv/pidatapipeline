"""
Configuration management for the PI-to-Oracle ERP Data Pipeline.
All configurations are persisted exclusively in JSON files (no database).
"""
import json
import os
import threading
from typing import Dict, Any, List

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
        "url": "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder",
        "username": "HIRUJR_JZNOT1742577235_TST",
        "password": "kah4YAH!bvm-vkt_jzd",
        "timeout_seconds": 15
    },
    "pipeline": {
        "interval_seconds": 120,
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

                return data
        except Exception as e:
            print(f"Error loading settings.json: {e}. Returning defaults.")
            return DEFAULT_SETTINGS


def save_settings(settings: Dict[str, Any]) -> None:
    ensure_config_dir()
    with _lock:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)


def load_mappings() -> List[Dict[str, Any]]:
    ensure_config_dir()
    with _lock:
        if not os.path.exists(MAPPINGS_FILE):
            save_mappings(DEFAULT_MAPPINGS)
            return DEFAULT_MAPPINGS
        try:
            with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading mappings.json: {e}. Returning defaults.")
            return DEFAULT_MAPPINGS


def save_mappings(mappings: List[Dict[str, Any]]) -> None:
    ensure_config_dir()
    with _lock:
        with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2)
