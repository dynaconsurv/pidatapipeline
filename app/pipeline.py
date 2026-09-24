"""
Data Pipeline Engine & Background Scheduler.
Orchestrates:
1. Extraction: Pulls configured attributes from AVEVA PI Web API.
2. Transformation: Formats and scales raw process values according to configured mappings.
3. Loading: Dispatches payload to Oracle ERP Cloud REST API (or preserves pending setup state).
4. Monitoring: Tracks health, latency, last 5 pulls, and next scheduled pull time.
"""
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import uuid

from app.config import load_settings, load_mappings
from app.pi_client import PIWebApiClient
from app.oracle_erp_client import OracleERPCloudClient
from app.storage import (
    record_pull_batch,
    record_publish_event,
    add_log,
    get_pull_history,
    get_publish_history,
    get_received_deliveries
)


class DataPipelineEngine:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.is_running = False
        self.is_paused = False
        self.interval_seconds = 30
        self.next_run_timestamp: Optional[float] = None
        self.last_run_timestamp: Optional[float] = None

        # Cached live statuses
        self.pi_status = {
            "status": "INITIALIZING",
            "message": "Initializing connection to AVEVA PI Web API...",
            "last_check": None,
            "latency_ms": None,
            "error": None
        }

        self.erp_status = {
            "status": "PENDING_SETUP",
            "message": "Pending connection setup: Oracle ERP Cloud credentials and endpoint not yet configured.",
            "last_check": None,
            "latency_ms": None,
            "error": None
        }

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self.is_running = True
            self.is_paused = False
            settings = load_settings()
            self.interval_seconds = max(5, int(settings.get("pipeline", {}).get("interval_seconds", 30)))
            self.next_run_timestamp = time.time() + 2  # First run in 2 seconds
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="PipelineWorker")
            self._thread.start()
            add_log("INFO", "PIPELINE", f"Data pipeline engine started. Interval: {self.interval_seconds}s")

    def stop(self):
        with self._lock:
            self.is_running = False
            self._stop_event.set()
            add_log("INFO", "PIPELINE", "Data pipeline engine stopped.")

    def pause(self):
        self.is_paused = True
        add_log("INFO", "PIPELINE", "Data pipeline scheduler paused.")

    def resume(self):
        self.is_paused = False
        self.next_run_timestamp = time.time() + 1
        add_log("INFO", "PIPELINE", "Data pipeline scheduler resumed.")

    def set_interval(self, seconds: int):
        self.interval_seconds = max(5, int(seconds))
        if self.next_run_timestamp:
            self.next_run_timestamp = min(self.next_run_timestamp, time.time() + self.interval_seconds)

    def _run_loop(self):
        while not self._stop_event.is_set():
            now = time.time()
            settings = load_settings()
            ingestion_mode = settings.get("pipeline", {}).get("ingestion_mode", "endpoint")

            if not self.is_paused and self.next_run_timestamp and now >= self.next_run_timestamp:
                try:
                    if ingestion_mode == "pull":
                        self.execute_cycle()
                    else:
                        from app.delivery_handler import dispatch_all_pending_deliveries
                        dispatch_all_pending_deliveries()
                except Exception as e:
                    add_log("ERROR", "PIPELINE", f"Pipeline execution cycle encountered an error: {str(e)}")
                finally:
                    self.last_run_timestamp = time.time()
                    self.interval_seconds = max(5, int(settings.get("pipeline", {}).get("interval_seconds", 30)))
                    self.next_run_timestamp = time.time() + self.interval_seconds

            time.sleep(1.0)

    def execute_cycle(self) -> Dict[str, Any]:
        """Runs a single extraction and dispatch cycle."""
        cycle_start = time.time()
        settings = load_settings()
        mappings = load_mappings()
        enabled_mappings = [m for m in mappings if m.get("enabled", True)]

        pi_cfg = settings.get("pi_web_api", {})
        erp_cfg = settings.get("oracle_erp", {})

        pi_client = PIWebApiClient(pi_cfg)
        erp_client = OracleERPCloudClient(erp_cfg)

        batch_id = f"batch-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Step 1: Pull from AVEVA PI Web API
        pull_items = []
        pi_failures = 0
        total_pi_latency = 0

        if not enabled_mappings:
            add_log("WARNING", "PIPELINE", "No enabled attribute mappings found. Skipping extraction.")
            batch_record = {
                "pull_id": batch_id,
                "timestamp": now_iso,
                "success": True,
                "count": 0,
                "duration_ms": 0,
                "error": "No enabled attribute mappings configured.",
                "items": []
            }
            record_pull_batch(batch_record)
            return {"batch_id": batch_id, "pull_count": 0, "status": "NO_MAPPINGS"}

        # Fast server probe: avoid multi-second repeated DNS timeouts if host is down
        conn_test = pi_client.test_connection()
        if not conn_test.get("success"):
            err_msg = conn_test.get("error") or conn_test.get("message") or "PI Web API host unreachable"
            for m in enabled_mappings:
                pull_items.append({
                    "attribute_name": m.get("attribute_name", "Unknown Attribute"),
                    "full_path": m.get("full_path", ""),
                    "web_id": m.get("web_id", ""),
                    "meter_tag": m.get("meter_tag") or m.get("attribute_name"),
                    "success": False,
                    "value": None,
                    "uom": m.get("uom", ""),
                    "timestamp": now_iso,
                    "quality": "Bad",
                    "status": "Unreachable",
                    "latency_ms": conn_test.get("latency_ms", 0),
                    "error": err_msg
                })
            pi_failures = len(enabled_mappings)
            total_pi_latency = conn_test.get("latency_ms", 0)
        else:
            for m in enabled_mappings:
                item_result = pi_client.fetch_attribute_value(m)
                item_result["meter_tag"] = m.get("meter_tag") or m.get("attribute_name")
                pull_items.append(item_result)
                if not item_result.get("success"):
                    pi_failures += 1
                if item_result.get("latency_ms"):
                    total_pi_latency += item_result["latency_ms"]

        avg_latency = round(total_pi_latency / max(1, len(pull_items)), 1)
        pi_pull_success = (pi_failures == 0)

        # Update PI status
        if conn_test.get("success"):
            is_sim = bool(pi_cfg.get("simulation_mode", False))
            if pi_pull_success:
                self.pi_status = {
                    "status": "SIMULATED" if is_sim else "CONNECTED",
                    "message": f"Simulating telemetry for {len(pull_items)} attributes (Offline Plant Simulator)" if is_sim else f"Successfully pulled {len(pull_items)} attributes from AVEVA PI Web API",
                    "last_check": now_iso,
                    "latency_ms": avg_latency or conn_test.get("latency_ms"),
                    "error": None
                }
            else:
                first_err = next((item.get("error") for item in pull_items if item.get("error")), "Attribute extraction issue")
                has_404 = any("404" in str(it.get("error")) or "not found" in str(it.get("error")).lower() for it in pull_items)
                if has_404:
                    friendly_err = (
                        f"PI Web API is ONLINE ({conn_test.get('latency_ms', avg_latency)}ms), but {pi_failures} of {len(pull_items)} mapped attribute path(s) were not found on this PI AF database (HTTP 404).\n"
                        f"• Action: Open the 'Mapping' page to browse your AF server and map your real attributes.\n"
                        f"• Server Response: {first_err}"
                    )
                    self.pi_status = {
                        "status": "WARNING",
                        "message": f"PI Web API connected, but {pi_failures} of {len(pull_items)} mapped attribute paths not found (HTTP 404)",
                        "last_check": now_iso,
                        "latency_ms": conn_test.get("latency_ms") or avg_latency,
                        "error": friendly_err
                    }
                else:
                    self.pi_status = {
                        "status": "PARTIAL_ERROR" if pi_failures < len(pull_items) else "FAILED",
                        "message": f"{pi_failures} of {len(pull_items)} attributes failed to pull from PI Web API",
                        "last_check": now_iso,
                        "latency_ms": conn_test.get("latency_ms") or avg_latency,
                        "error": first_err
                    }
                add_log("WARNING" if has_404 else "ERROR", "PI_WEB_API", self.pi_status["message"])
        else:
            self.pi_status = {
                "status": "FAILED",
                "message": "AVEVA PI Web API host unreachable or authentication failed",
                "last_check": now_iso,
                "latency_ms": None,
                "error": conn_test.get("error") or conn_test.get("message") or "Connection failed"
            }

        # Record batch to pull history
        batch_record = {
            "pull_id": batch_id,
            "timestamp": now_iso,
            "success": pi_pull_success,
            "count": len(pull_items),
            "duration_ms": round((time.time() - cycle_start) * 1000, 1),
            "error": self.pi_status.get("error"),
            "items": pull_items
        }
        record_pull_batch(batch_record)

        # Step 2: Build Oracle ERP Cloud payload
        erp_payload = self._build_erp_payload(pull_items, enabled_mappings)

        # Step 3: Dispatch to Oracle ERP Cloud
        publish_result = erp_client.publish_data(erp_payload)
        publish_result["publish_id"] = f"pub-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        publish_result["batch_id"] = batch_id
        record_publish_event(publish_result)

        # Update ERP status
        if publish_result["status"] == "PENDING_SETUP":
            self.erp_status = {
                "status": "PENDING_SETUP",
                "message": publish_result["message"],
                "last_check": now_iso,
                "latency_ms": None,
                "error": None
            }
        elif publish_result["status"] == "SUCCESS":
            self.erp_status = {
                "status": "CONNECTED",
                "message": f"Successfully posted {publish_result.get('record_count', 0)} readings to Oracle ERP Cloud",
                "last_check": now_iso,
                "latency_ms": publish_result.get("latency_ms"),
                "error": None
            }
            add_log("SUCCESS", "ORACLE_ERP", f"Published {publish_result.get('record_count')} items to ERP Cloud.")
        else:
            self.erp_status = {
                "status": "FAILED",
                "message": publish_result.get("message", "ERP Push Failed"),
                "last_check": now_iso,
                "latency_ms": publish_result.get("latency_ms"),
                "error": publish_result.get("error_detail")
            }
            add_log("ERROR", "ORACLE_ERP", f"ERP push failed: {publish_result.get('message')}", publish_result.get("error_detail"))

        self.last_run_timestamp = time.time()
        return {
            "batch_id": batch_id,
            "timestamp": now_iso,
            "pull": batch_record,
            "publish": publish_result,
            "cycle_duration_ms": round((time.time() - cycle_start) * 1000, 1)
        }

    def _build_erp_payload(self, pull_items: List[Dict[str, Any]], mappings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Transforms PI AF pulled items into standard Oracle ERP Cloud REST resource format.
        Follows Oracle Fusion Maintenance / Asset Meter Readings / Receipts structure:
        {
           "sourceSystem": "AVEVA_PI_SYSTEM",
           "batchTimestamp": "2026-09-17T09:28:00Z",
           "items": [
              {
                 "meterCode": "BLR101_STM_TEMP",
                 "readingValue": 541.2,
                 "readingTimestamp": "2026-09-17T09:27:58Z",
                 "unitOfMeasure": "deg C",
                 "sourceQuality": "Good"
              }, ...
           ]
        }
        """
        mapping_by_name = {m.get("attribute_name"): m for m in mappings}
        records = []
        now_ts = datetime.now(timezone.utc).isoformat()

        for item in pull_items:
            m = mapping_by_name.get(item.get("attribute_name"))
            if not m:
                continue

            target_val_field = m.get("target_field", "readingValue")
            target_tag_field = m.get("target_tag_field", "meterCode")
            meter_tag = m.get("meter_tag") or item.get("attribute_name")

            record = {
                target_tag_field: meter_tag,
                target_val_field: item.get("value"),
                "readingTimestamp": item.get("timestamp", now_ts),
                "unitOfMeasure": item.get("uom", ""),
                "piAttributePath": item.get("full_path", ""),
                "sourceQuality": item.get("quality", "Good")
            }
            records.append(record)

        return {
            "sourceSystem": "AVEVA_PI_DATA_PIPELINE",
            "batchTimestamp": now_ts,
            "itemCount": len(records),
            "items": records
        }

    def get_status(self) -> Dict[str, Any]:
        now = time.time()
        seconds_remaining = 0
        if self.next_run_timestamp and not self.is_paused:
            seconds_remaining = max(0, int(self.next_run_timestamp - now))

        next_run_iso = None
        if self.next_run_timestamp:
            next_run_iso = datetime.fromtimestamp(self.next_run_timestamp, tz=timezone.utc).isoformat()

        last_run_iso = None
        if self.last_run_timestamp:
            last_run_iso = datetime.fromtimestamp(self.last_run_timestamp, tz=timezone.utc).isoformat()

        settings = load_settings()

        # Determine currently enabled (active) mappings from config/mappings.json
        mappings = load_mappings()
        enabled_mappings = [m for m in mappings if m.get("enabled", True)]
        mapping_by_key = {}

        for m in enabled_mappings:
            attr_name = (m.get("attribute_name") or "").strip().lower()
            full_path = (m.get("full_path") or "").strip().lower()
            web_id = (m.get("web_id") or "").strip()
            if attr_name:
                mapping_by_key[attr_name] = m
            if full_path:
                mapping_by_key[full_path] = m
            if web_id:
                mapping_by_key[web_id] = m

        # Retrieve batches to construct the last 5 triggers containing ACTIVE mappings
        pulls = get_pull_history(limit=50)
        last_5_triggers = []

        if enabled_mappings:
            for batch in pulls:
                active_items = []
                seen_attrs_in_batch = set()

                for item in batch.get("items", []):
                    item_name = (item.get("attribute_name") or "").strip().lower()
                    item_path = (item.get("full_path") or "").strip().lower()
                    item_web_id = (item.get("web_id") or "").strip()

                    # Match active mapping definition (skip inactive or removed mappings)
                    matched_m = mapping_by_key.get(item_web_id) or mapping_by_key.get(item_path) or mapping_by_key.get(item_name)
                    if not matched_m:
                        continue

                    attr_ident = (matched_m.get("attribute_name") or item_name).strip().lower()
                    if attr_ident in seen_attrs_in_batch:
                        continue
                    seen_attrs_in_batch.add(attr_ident)

                    meter_tag = matched_m.get("meter_tag") or item.get("meter_tag") or matched_m.get("attribute_name")
                    active_items.append({
                        "attribute_name": matched_m.get("attribute_name") or item.get("attribute_name"),
                        "meter_tag": meter_tag,
                        "value": item.get("value"),
                        "raw_value": item.get("raw_value"),
                        "uom": item.get("uom") or matched_m.get("uom", ""),
                        "timestamp": item.get("timestamp") or batch.get("timestamp"),
                        "quality": item.get("quality", "Good"),
                        "status": item.get("status", "Online"),
                        "error": item.get("error")
                    })

                # If batch has no active items remaining, skip it
                if not active_items:
                    continue

                # Determine trigger-level quality
                qualities = [it.get("quality", "Good") for it in active_items]
                if not batch.get("success", True) or any(q in ("Bad", "Failed") for q in qualities):
                    overall_quality = "Bad" if all(q in ("Bad", "Failed") for q in qualities) else "Partial"
                elif any(q == "Questionable" for q in qualities):
                    overall_quality = "Questionable"
                else:
                    overall_quality = "Good"

                ingested_at = active_items[0].get("timestamp") or batch.get("timestamp")

                last_5_triggers.append({
                    "pull_id": batch.get("pull_id"),
                    "triggered_at": batch.get("timestamp"),
                    "ingested_at": ingested_at,
                    "duration_ms": batch.get("duration_ms", 0),
                    "success": batch.get("success", True),
                    "quality": overall_quality,
                    "meter_tags": [it["meter_tag"] for it in active_items if it.get("meter_tag")],
                    "items": active_items,
                    "items_count": len(active_items)
                })

                if len(last_5_triggers) >= 5:
                    break

        publishes = get_publish_history(limit=1)
        last_publish = publishes[0] if publishes else None

        # Retrieve recent 5 received deliveries staged from PI Notifications
        deliveries = get_received_deliveries(limit=5)
        all_deliveries = get_received_deliveries(limit=200)
        pending_deliveries = [
            d for d in all_deliveries
            if d.get("oracle_status") in ("FAILED", "PENDING_RETRY", "PENDING_ORACLE", "PENDING_SETUP")
        ]
        failed_deliveries = [
            d for d in all_deliveries
            if d.get("oracle_status") == "FAILED"
        ]

        delivery_info = {
            "endpoint_url": "/api/v1/delivery",
            "method": "POST",
            "style": "REST",
            "status": "LISTENING",
            "total_received": len(all_deliveries),
            "pending_oracle_count": len(pending_deliveries),
            "failed_count": len(failed_deliveries),
            "last_received_at": deliveries[0].get("received_at") if deliveries else None
        }

        return {
            "scheduler": {
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "interval_seconds": self.interval_seconds,
                "next_run_at": next_run_iso,
                "last_run_at": last_run_iso,
                "seconds_remaining": seconds_remaining
            },
            "ingestion_mode": settings.get("pipeline", {}).get("ingestion_mode", "endpoint"),
            "delivery_endpoint": delivery_info,
            "recent_5_deliveries": deliveries,
            "pi_connection": self.pi_status,
            "oracle_erp_connection": self.erp_status,
            "last_5_pulls": last_5_triggers,
            "last_publish": last_publish
        }

    def refresh_pi_connection_status(self, conn_result: Dict[str, Any]):
        """Update live PI connection status after an explicit connection test."""
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            if conn_result.get("success"):
                is_sim = conn_result.get("is_simulation", False)
                latency = conn_result.get("latency_ms")
                if self.pi_status.get("status") == "WARNING":
                    # Keep path warning context, but update verified latency and timestamp
                    self.pi_status["latency_ms"] = latency
                    self.pi_status["last_check"] = now_iso
                else:
                    self.pi_status = {
                        "status": "SIMULATED" if is_sim else "CONNECTED",
                        "message": conn_result.get("message") or "Successfully connected to AVEVA PI Web API",
                        "last_check": now_iso,
                        "latency_ms": latency,
                        "error": None
                    }
            elif conn_result.get("status_code") or conn_result.get("error"):
                self.pi_status = {
                    "status": "FAILED",
                    "message": conn_result.get("message") or "PI Web API connection test failed",
                    "last_check": now_iso,
                    "latency_ms": None,
                    "error": conn_result.get("error") or conn_result.get("message")
                }


# Global pipeline engine singleton
pipeline_engine = DataPipelineEngine()
