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
        "enabled": False,  # Pending connection setup until user configures and activates it
        "auth_type": "oauth2",  # 'oauth2', 'basic', 'bearer'
        "base_url": "https://your-pod.fa.oraclecloud.com",
        "token_url": "https://idcs-your-instance.identity.oraclecloud.com/oauth2/v1/token",
        "client_id": "",
        "client_secret": "",
        "scope": "urn:opc:resource:consumer::all",
        "username": "",
        "password": "",
        "bearer_token": "",
        "resource_endpoint": "/fscmRestApi/resources/11.13.18.05/standardReceipts",
        "http_method": "POST",
        "custom_headers": {
            "Content-Type": "application/vnd.oracle.adf.resourceitem+json",
            "REST-Framework-Version": "4"
        },
        "timeout_seconds": 15
    },
    "pipeline": {
        "interval_seconds": 30,
        "auto_start": True,
        "max_history_items": 100
    }
}

DEFAULT_MAPPINGS: List[Dict[str, Any]] = [
    {
        "id": "map-boiler-temp",
        "name": "Boiler 101 Steam Temperature",
        "af_server": "PISRV01",
        "af_database": "Plant_Operations",
        "element_path": "Unit 1\\Boilers\\Boiler-101",
        "attribute_name": "Steam Temperature",
        "full_path": "\\\\PISRV01\\Plant_Operations\\Unit 1\\Boilers\\Boiler-101|Steam Temperature",
        "web_id": "F1AbE001_BoilerTemp",
        "target_field": "readingValue",
        "meter_tag": "BLR101_STM_TEMP",
        "target_tag_field": "meterCode",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 2,
        "uom": "deg C",
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
        "web_id": "F1AbE002_BoilerPress",
        "target_field": "readingValue",
        "meter_tag": "BLR101_STM_PRESS",
        "target_tag_field": "meterCode",
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
        "web_id": "F1AbE003_FeedFlow",
        "target_field": "readingValue",
        "meter_tag": "TG01_FEED_FLOW",
        "target_tag_field": "meterCode",
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
        "web_id": "F1AbE004_ActivePower",
        "target_field": "readingValue",
        "meter_tag": "GEN01_ACT_PWR",
        "target_tag_field": "meterCode",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 3,
        "uom": "MW",
        "enabled": True
    },
    {
        "id": "map-pump-vibe",
        "name": "Cooling Pump 2A Vibration",
        "af_server": "PISRV01",
        "af_database": "Plant_Operations",
        "element_path": "Utilities\\Pumps\\Pump-2A",
        "attribute_name": "Vibration Overall",
        "full_path": "\\\\PISRV01\\Plant_Operations\\Utilities\\Pumps\\Pump-2A|Vibration Overall",
        "web_id": "F1AbE005_PumpVibe",
        "target_field": "readingValue",
        "meter_tag": "PMP2A_VIB_RMS",
        "target_tag_field": "meterCode",
        "data_type": "number",
        "transformation": "direct",
        "scale_factor": 1.0,
        "round_decimals": 2,
        "uom": "mm/s",
        "enabled": True
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
