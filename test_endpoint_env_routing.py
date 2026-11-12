"""
Comprehensive Test Suite for PI AF 'Endpoint' and 'Environment' Routing Parameters.

Validates the specification:
1. Endpoint=Oracle, Environment=Prod -> Oracle Cloud Prod ('oracle')
2. Endpoint=Oracle, Environment=Test -> Oracle Cloud Dev ('oracledev')
3. Endpoint=Octave, Environment=Prod -> Octave ('j5')
4. Endpoint=Octave, Environment=Test -> Octave Dev ('j5dev')
5. Endpoint=Oracle,Octave, Environment=Prod -> Oracle Cloud Prod & Octave ('oracle', 'j5')
6. Endpoint=Oracle,Octave, Environment=Test -> Oracle Cloud Dev & Octave Dev ('oracledev', 'j5dev')
7. Ensure 'Endpoint' and 'Environment' are never forwarded into destination payloads.
8. Ensure legacy flags (j5=true, oracle=true, oracledev=true, j5dev=true) remain fully backward compatible.
"""
import unittest
from app.delivery_handler import (
    resolve_endpoint_and_env_targets,
    extract_target_flags_and_urls,
    extract_direct_telemetry_record,
    parse_pi_notification_payload,
    extract_extra_parameters,
    ALL_ROUTING_PARAM_KEYS
)


class TestEndpointEnvRouting(unittest.TestCase):

    def test_routing_param_keys_contain_endpoint_and_environment(self):
        self.assertIn("endpoint", ALL_ROUTING_PARAM_KEYS)
        self.assertIn("environment", ALL_ROUTING_PARAM_KEYS)
        self.assertIn("env", ALL_ROUTING_PARAM_KEYS)

    def test_oracle_prod(self):
        source = {"Endpoint": "Oracle", "Environment": "Prod"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(enabled, ["oracle"])
        self.assertIn("oracledev", disabled)
        self.assertIn("oracle_utility", disabled)
        self.assertIn("oracledev_utility", disabled)
        self.assertIn("j5", disabled)
        self.assertIn("j5dev", disabled)

    def test_oracle_effluent_prod(self):
        source = {"Endpoint": "Oracle_Effluent", "Environment": "Prod"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(enabled, ["oracle"])
        self.assertIn("oracledev", disabled)
        self.assertIn("oracle_utility", disabled)
        self.assertIn("oracledev_utility", disabled)
        self.assertIn("j5", disabled)
        self.assertIn("j5dev", disabled)

    def test_oracle_effluent_test(self):
        source = {"Endpoint": "Oracle_Effluent", "Environment": "Test"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(enabled, ["oracledev"])
        self.assertIn("oracle", disabled)
        self.assertIn("oracle_utility", disabled)
        self.assertIn("oracledev_utility", disabled)
        self.assertIn("j5", disabled)
        self.assertIn("j5dev", disabled)

    def test_oracle_utility_prod(self):
        source = {"Endpoint": "Oracle_Utility", "Environment": "Prod"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(enabled, ["oracle_utility"])
        self.assertIn("oracle", disabled)
        self.assertIn("oracledev", disabled)
        self.assertIn("oracledev_utility", disabled)
        self.assertIn("j5", disabled)
        self.assertIn("j5dev", disabled)

    def test_oracle_utility_test(self):
        source = {"Endpoint": "Oracle_Utility", "Environment": "Test"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(enabled, ["oracledev_utility"])
        self.assertIn("oracle", disabled)
        self.assertIn("oracledev", disabled)
        self.assertIn("oracle_utility", disabled)
        self.assertIn("j5", disabled)
        self.assertIn("j5dev", disabled)

    def test_oracle_utility_octave_prod(self):
        source = {"Endpoint": "Oracle_Utility,Octave", "Environment": "Prod"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(set(enabled), {"oracle_utility", "j5"})
        self.assertIn("oracledev_utility", disabled)
        self.assertIn("oracle", disabled)
        self.assertIn("oracledev", disabled)
        self.assertIn("j5dev", disabled)

    def test_oracle_utility_octave_test(self):
        source = {"Endpoint": "Oracle_Utility,Octave", "Environment": "Test"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(set(enabled), {"oracledev_utility", "j5dev"})
        self.assertIn("oracle_utility", disabled)
        self.assertIn("oracle", disabled)
        self.assertIn("oracledev", disabled)
        self.assertIn("j5", disabled)

    def test_oracle_effluent_octave_prod(self):
        source = {"Endpoint": "Oracle_Effluent,Octave", "Environment": "Prod"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(set(enabled), {"oracle", "j5"})
        self.assertIn("oracledev", disabled)
        self.assertIn("oracle_utility", disabled)
        self.assertIn("oracledev_utility", disabled)
        self.assertIn("j5dev", disabled)

    def test_oracle_effluent_octave_test(self):
        source = {"Endpoint": "Oracle_Effluent,Octave", "Environment": "Test"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(set(enabled), {"oracledev", "j5dev"})
        self.assertIn("oracle", disabled)
        self.assertIn("oracle_utility", disabled)
        self.assertIn("oracledev_utility", disabled)
        self.assertIn("j5", disabled)

    def test_oracle_test(self):
        source = {"Endpoint": "Oracle", "Environment": "Test"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(enabled, ["oracledev"])
        self.assertIn("oracle", disabled)
        self.assertIn("j5", disabled)
        self.assertIn("j5dev", disabled)

    def test_octave_prod(self):
        source = {"Endpoint": "Octave", "Environment": "Prod"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(enabled, ["j5"])
        self.assertIn("j5dev", disabled)
        self.assertIn("oracle", disabled)
        self.assertIn("oracledev", disabled)

    def test_octave_test(self):
        source = {"Endpoint": "Octave", "Environment": "Test"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(enabled, ["j5dev"])
        self.assertIn("j5", disabled)
        self.assertIn("oracle", disabled)
        self.assertIn("oracledev", disabled)

    def test_oracle_octave_prod(self):
        source = {"Endpoint": "Oracle,Octave", "Environment": "Prod"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(set(enabled), {"oracle", "j5"})
        self.assertIn("oracledev", disabled)
        self.assertIn("j5dev", disabled)

    def test_oracle_octave_test(self):
        source = {"Endpoint": "Oracle,Octave", "Environment": "Test"}
        enabled, urls, disabled = resolve_endpoint_and_env_targets(source)
        self.assertEqual(set(enabled), {"oracledev", "j5dev"})
        self.assertIn("oracle", disabled)
        self.assertIn("j5", disabled)

    def test_whitespace_and_delimiter_variations(self):
        # Comma with space
        en1, _, _ = resolve_endpoint_and_env_targets({"endpoint": "Oracle, Octave", "env": "prod"})
        self.assertEqual(set(en1), {"oracle", "j5"})

        # Reverse order
        en2, _, _ = resolve_endpoint_and_env_targets({"endpoint": "Octave, Oracle", "env": "Test"})
        self.assertEqual(set(en2), {"oracledev", "j5dev"})

        # Slash delimiter
        en3, _, _ = resolve_endpoint_and_env_targets({"endpoint": "Oracle/Octave", "environment": "Dev"})
        self.assertEqual(set(en3), {"oracledev", "j5dev"})

        # Semicolon delimiter
        en4, _, _ = resolve_endpoint_and_env_targets({"endpoint": "Oracle;Octave", "environment": "Production"})
        self.assertEqual(set(en4), {"oracle", "j5"})

        # Omitted Environment defaults to Prod
        en5, _, _ = resolve_endpoint_and_env_targets({"endpoint": "Oracle"})
        self.assertEqual(en5, ["oracle"])

    def test_extract_extra_parameters_skips_endpoint_and_env(self):
        payload = {
            "Tagname": "SC4025.Ammoniacal Nitrogen",
            "Value": 12.5,
            "Endpoint": "Oracle,Octave",
            "Environment": "Test",
            "HILIMIT": "10.0",
            "LOLIMIT": "0.0",
            "custom_note": "Calibrated"
        }
        extra = extract_extra_parameters(payload)
        self.assertNotIn("Endpoint", extra)
        self.assertNotIn("endpoint", extra)
        self.assertNotIn("Environment", extra)
        self.assertNotIn("environment", extra)
        self.assertIn("HILIMIT", extra)
        self.assertIn("LOLIMIT", extra)
        self.assertIn("custom_note", extra)

    def test_direct_telemetry_record_parsing_with_endpoint_env(self):
        item = {
            "Tagname": "SC4025.Ammoniacal Nitrogen",
            "Value": "0.0",
            "HILIMIT": "10.0",
            "LOLIMIT": "0.0",
            "Endpoint": "Oracle,Octave",
            "Environment": "Test"
        }
        record = extract_direct_telemetry_record(item)
        self.assertIsNotNone(record)
        self.assertEqual(set(record.get("target_flags", [])), {"oracledev", "j5dev"})
        self.assertTrue(record.get("oracledev"))
        self.assertTrue(record.get("j5dev"))
        self.assertFalse(record.get("oracle"))
        self.assertFalse(record.get("j5"))
        self.assertNotIn("Endpoint", record.get("extra_fields", {}))
        self.assertNotIn("Environment", record.get("extra_fields", {}))
        self.assertEqual(record.get("extra_fields", {}).get("HILIMIT"), "10.0")
        self.assertEqual(record.get("extra_fields", {}).get("LOLIMIT"), "0.0")

    def test_parse_pi_notification_payload_top_level_endpoint_env(self):
        raw_body = {
            "Notification": "Effluent_Monitor",
            "Endpoint": "Oracle",
            "Environment": "Test",
            "Items": [
                {"Name": "Turbidity", "Value": 4.2},
                {"Name": "pH", "Value": 7.1}
            ]
        }
        notif_name, ev_type, path, attributes = parse_pi_notification_payload(raw_body)
        self.assertEqual(len(attributes), 2)
        for attr in attributes:
            self.assertEqual(attr.get("target_flags"), ["oracledev"])
            self.assertTrue(attr.get("oracledev"))
            self.assertFalse(attr.get("oracle"))

    def test_backward_compatibility_legacy_flags(self):
        # Legacy j5=true
        source_j5 = {"j5": "true"}
        en_j5, _, dis_j5 = extract_target_flags_and_urls(source_j5)
        self.assertEqual(en_j5, ["j5"])

        # Legacy oracle=true
        source_ora = {"oracle": "yes"}
        en_ora, _, _ = extract_target_flags_and_urls(source_ora)
        self.assertEqual(en_ora, ["oracle"])

        # Legacy oracledev=yes
        source_dev = {"oracledev": "yes"}
        en_dev, _, _ = extract_target_flags_and_urls(source_dev)
        self.assertEqual(en_dev, ["oracledev"])

    def test_build_oracle_endpoint_url_utility_and_effluent(self):
        from app.oracle_erp_client import build_oracle_endpoint_url
        base = "https://gda83ebb4f9065b-ecoatpprod.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int"
        
        # Effluent url
        eff_url = build_oracle_endpoint_url(base, "/Final_Discharge_Effluent/")
        self.assertEqual(eff_url, "https://gda83ebb4f9065b-ecoatpprod.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/")
        
        # Utility url
        util_url = build_oracle_endpoint_url(base, "/production_utilities_consumption/")
        self.assertEqual(util_url, "https://gda83ebb4f9065b-ecoatpprod.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/production_utilities_consumption/")

        # Base with trailing Final_Discharge_Effluent switched to utility
        base_with_eff = "https://gda83ebb4f9065b-ecoatpprod.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/Final_Discharge_Effluent/"
        switched_util_url = build_oracle_endpoint_url(base_with_eff, "/production_utilities_consumption/")
        self.assertEqual(switched_util_url, "https://gda83ebb4f9065b-ecoatpprod.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/production_utilities_consumption/")

        # Daily Production Data url (/production_daily_output/)
        daily_prod_url = build_oracle_endpoint_url(base_with_eff, "/production_daily_output/")
        self.assertEqual(daily_prod_url, "https://gda83ebb4f9065b-ecoatpprod.adb.ap-singapore-1.oraclecloudapps.com/ords/pims_int/production_daily_output/")

    def test_oracle_daily_production_prod_and_test(self):
        en_prod, _, dis_prod = resolve_endpoint_and_env_targets({"Endpoint": "Oracle_Production", "Environment": "Prod"})
        self.assertEqual(en_prod, ["oracle_production"])
        self.assertIn("oracledev_production", dis_prod)

        en_test, _, dis_test = resolve_endpoint_and_env_targets({"Endpoint": "Daily_Production", "Environment": "Test"})
        self.assertEqual(en_test, ["oracledev_production"])
        self.assertIn("oracle_production", dis_test)

        en_path, _, _ = resolve_endpoint_and_env_targets({"Endpoint": "production_daily_output", "Environment": "Prod"})
        self.assertEqual(en_path, ["oracle_production"])

    def test_analysistime_and_time_parameter_conversion(self):
        from app.oracle_erp_client import format_ords_timestamp
        
        # UTC timestamp (ending in Z) converted to UTC+8 (+8 hours) and microseconds stripped
        res1 = format_ords_timestamp("2026-10-30T08:49:43.1234567Z", allow_empty=True)
        self.assertEqual(res1, "2026-10-30T16:49:43Z")

        # 7:00 AM local time sent as 23:00:00Z UTC by PI AF stays 07:00:00Z
        res_7am = format_ords_timestamp("2026-11-04T23:00:00Z", allow_empty=True)
        self.assertEqual(res_7am, "2026-11-05T07:00:00Z")

        # Space separated format (naive local clock time stays as-is)
        res2 = format_ords_timestamp("2026-10-30 08:49:43", allow_empty=True)
        self.assertEqual(res2, "2026-10-30T08:49:43Z")

        # Timezone offset +08:00 stays in UTC+8 (16:49:43)
        res3 = format_ords_timestamp("2026-10-30T16:49:43+08:00", allow_empty=True)
        self.assertEqual(res3, "2026-10-30T16:49:43Z")

        # Null / None preserved
        res4 = format_ords_timestamp(None, allow_empty=True)
        self.assertIsNone(res4)
        res5 = format_ords_timestamp("null", allow_empty=True)
        self.assertIsNone(res5)

    def test_delivery_receipt_timestamp_vs_af_analysistime(self):
        from app.delivery_handler import process_incoming_delivery, dispatch_delivery_to_oracle
        from app.storage import get_delivery_by_id
        
        # Simulate incoming PI notification with SourceTime, AnalysisTime, and custom EventTime
        incoming_payload = {
            "Tagname": "SC4025.Ammoniacal Nitrogen",
            "Value": "15.4",
            "SourceTime": "2026-10-30 08:49:43.500",  # PI AF SourceTime
            "EventTime": "2026-11-04T23:00:00.1234567Z",  # 7:00 AM Nov 5 local in UTC
            "TestTimestamp": None,
            "Endpoint": "Oracle",
            "Environment": "Test"
        }
        res = process_incoming_delivery(incoming_payload, client_ip="10.60.2.20")
        deliv_id = res["delivery_id"]
        
        deliv = get_delivery_by_id(deliv_id)
        self.assertIsNotNone(deliv)
        
        # Run dispatch (mock/simulation mode or catching pub result)
        dispatch_res = dispatch_delivery_to_oracle(deliv_id)
        dispatches = dispatch_res.get("dispatches", [])
        self.assertTrue(len(dispatches) > 0)
        
        sent_payload = dispatches[0].get("payload", {})
        
        # 1. 'timestamp' parameter must NOT be sent
        self.assertNotIn("timestamp", sent_payload)
        
        # 2. 'SourceTime' is mapped to Oracle parameter 'RECORD_AT'
        self.assertEqual(sent_payload.get("RECORD_AT"), "2026-10-30T08:49:43Z")
        self.assertNotIn("SourceTime", sent_payload)
        
        # 3. 'EventTime' (23:00:00Z UTC) must be converted to UTC+8 (07:00:00Z)
        self.assertEqual(sent_payload.get("EventTime"), "2026-11-05T07:00:00Z")
        
        # 4. 'TestTimestamp' must be None / null
        self.assertIsNone(sent_payload.get("TestTimestamp"))

    def test_octave_parameter_mapping(self):
        from app.field_mapper import build_destination_payload
        
        sample_attr = {
            "name": "Discharge Effluent",
            "tag": "SC4025.Ammoniacal Nitrogen",
            "value": "15.42",
            "uom": "mg/L",
            "limit": "20.0",
            "results": "PASS",
            "quality": "Good",
            "AnalysisTime": "2026-10-30 08:49:43.123",
            "extra_fields": {
                "Operator": "Plant_Ops"
            }
        }
        
        oct_payload = build_destination_payload(
            target_type="octave",
            source_attr=sample_attr,
            received_at="2026-11-02T16:00:00Z"
        )
        
        # Verify Octave default mappings (timestamp & readingTimestamp excluded)
        self.assertEqual(oct_payload.get("sourceSystem"), "AVEVA_PI_NOTIFICATION")
        self.assertEqual(oct_payload.get("messageTag"), "SC4025.Ammoniacal Nitrogen")
        self.assertEqual(oct_payload.get("tag"), "SC4025.Ammoniacal Nitrogen")
        self.assertEqual(oct_payload.get("readingValue"), 15.42)
        self.assertEqual(oct_payload.get("value"), "15.42")
        self.assertEqual(oct_payload.get("unitOfMeasure"), "mg/L")
        self.assertEqual(oct_payload.get("uom"), "mg/L")
        self.assertNotIn("timestamp", oct_payload)
        self.assertNotIn("readingTimestamp", oct_payload)
        self.assertEqual(oct_payload.get("AnalysisTime"), "2026-10-30T08:49:43Z")
        self.assertEqual(oct_payload.get("Operator"), "Plant_Ops")

    def test_custom_oracle_parameter_mapping_override(self):
        from app.field_mapper import build_destination_payload
        
        custom_mappings = [
            {"source": "tag", "target": "METER_CODE", "transform": "string", "enabled": True},
            {"source": "AnalysisTime", "target": "ANALYSIS_UTC", "transform": "timestamp_zulu", "enabled": True},
            {"source": "value", "target": "READING", "transform": "numeric_scaled", "enabled": True}
        ]
        
        sample_attr = {
            "tag": "FLOW_METER_01",
            "value": "100.5",
            "AnalysisTime": "2026-10-30 08:49:43.000"
        }
        
        payload = build_destination_payload(
            target_type="oracle",
            source_attr=sample_attr,
            field_mappings_override=custom_mappings
        )
        
        self.assertEqual(payload.get("METER_CODE"), "FLOW_METER_01")
        self.assertEqual(payload.get("ANALYSIS_UTC"), "2026-10-30T08:49:43Z")
        self.assertEqual(payload.get("READING"), 100.5)
        self.assertNotIn("AnalysisTime", payload)
        self.assertNotIn("tag", payload)

    def test_separate_prod_and_dev_parameter_mappings(self):
        from app.config import load_field_mappings, save_field_mappings
        from app.field_mapper import build_destination_payload
        
        # Load and temporarily configure different mappings for Prod vs Dev
        original_maps = load_field_mappings()
        try:
            modified = dict(original_maps)
            # Dev has a special test column 'DEV_TEST_COL'
            modified["oracle_dev"] = [
                {"source": "tag", "target": "DEV_TAG", "transform": "string", "enabled": True},
                {"source": "AnalysisTime", "target": "DEV_ANALYSIS_TS", "transform": "timestamp_zulu", "enabled": True}
            ]
            # Prod keeps standard column names
            modified["oracle_prod"] = [
                {"source": "tag", "target": "tag", "transform": "string", "enabled": True},
                {"source": "AnalysisTime", "target": "TESTTIMESTAMP", "transform": "timestamp_zulu", "enabled": True}
            ]
            save_field_mappings(modified)
            
            sample_attr = {
                "tag": "EFFLUENT_PUMP",
                "AnalysisTime": "2026-10-30 08:49:43.000"
            }
            
            # 1. Oracle Prod payload respects oracle_prod mappings
            prod_payload = build_destination_payload("oracle", sample_attr)
            self.assertEqual(prod_payload.get("tag"), "EFFLUENT_PUMP")
            self.assertEqual(prod_payload.get("TESTTIMESTAMP"), "2026-10-30T08:49:43Z")
            self.assertNotIn("DEV_TAG", prod_payload)
            self.assertNotIn("DEV_ANALYSIS_TS", prod_payload)
            
            # 2. Oracle Dev payload respects oracle_dev mappings
            dev_payload = build_destination_payload("oracledev", sample_attr)
            self.assertEqual(dev_payload.get("DEV_TAG"), "EFFLUENT_PUMP")
            self.assertEqual(dev_payload.get("DEV_ANALYSIS_TS"), "2026-10-30T08:49:43Z")
            self.assertNotIn("TESTTIMESTAMP", dev_payload)
            self.assertNotIn("tag", dev_payload)
            
        finally:
            save_field_mappings(original_maps)

    def test_octave_dev_url_sync_when_settings_changed(self):
        import json
        from unittest.mock import patch
        from app.config import load_settings, save_settings, load_mappings, save_mappings
        from app.delivery_handler import process_incoming_delivery, dispatch_delivery_to_oracle

        orig_settings = load_settings()
        orig_mappings = load_mappings()
        try:
            old_placeholder_url = "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=purchaseorder"
            new_octave_dev_url = "https://dataflow-inbound-message-prd-ase1.eam.hxgnsmartcloud.com/api/message?tag=j5_pi_opslogbook"

            # Simulate existing mapping created when Octave Dev still had placeholder URL
            stale_mapping = {
                "id": "map-auto-test-j5dev",
                "name": "Bleaching Filter F7202ab Differential Pressure.Alarm",
                "attribute_name": "Bleaching Filter F7202ab Differential Pressure.Alarm",
                "tag": "Bleaching Filter F7202ab Differential Pressure.Alarm",
                "meter_tag": "Bleaching Filter F7202ab Differential Pressure.Alarm",
                "target_type": "j5dev",
                "target_types": ["j5dev"],
                "target_endpoint_url": old_placeholder_url,
                "target_endpoint_url_j5": old_placeholder_url,
                "target_endpoint_url_j5dev": old_placeholder_url,
                "enabled": True
            }
            save_mappings([stale_mapping])

            # Now user configures the new Octave Dev URL in Settings
            updated_settings = json.loads(json.dumps(orig_settings))
            updated_settings.setdefault("j5dev_endpoint", {})["enabled"] = True
            updated_settings["j5dev_endpoint"]["url"] = new_octave_dev_url
            updated_settings.setdefault("pipeline", {})["auto_dispatch"] = False
            save_settings(updated_settings)

            # 1. Verify mappings.json was synced to the new Octave Dev URL
            synced_mappings = load_mappings()
            self.assertEqual(len(synced_mappings), 1)
            self.assertEqual(synced_mappings[0]["target_endpoint_url_j5dev"], new_octave_dev_url)
            self.assertEqual(synced_mappings[0]["target_endpoint_url"], new_octave_dev_url)

            # 2. Verify incoming Octave Test delivery dispatches to the new Octave Dev URL
            payload = {
                "Tagname": "Bleaching Filter F7202ab Differential Pressure.Alarm",
                "Value": "Active",
                "Endpoint": "Octave",
                "Environment": "Test"
            }
            with patch("app.j5_client.J5Client.publish_data") as mock_pub:
                mock_pub.return_value = {
                    "status": "SUCCESS",
                    "http_code": 200,
                    "target_endpoint": new_octave_dev_url,
                    "response_body": {"status": "ok"},
                    "error_detail": None,
                    "message": "OK"
                }
                res = process_incoming_delivery(payload, client_ip="10.60.2.20")
                dispatch_res = dispatch_delivery_to_oracle(res["delivery_id"])
                self.assertTrue(mock_pub.called)
                called_kwargs = mock_pub.call_args.kwargs
                self.assertEqual(called_kwargs.get("target_endpoint"), new_octave_dev_url)
                dispatches = dispatch_res.get("dispatches", [])
                self.assertEqual(len(dispatches), 1)
                self.assertEqual(dispatches[0].get("target_type"), "j5dev")
                self.assertEqual(dispatches[0].get("target_endpoint"), new_octave_dev_url)
        finally:
            save_settings(orig_settings)
            save_mappings(orig_mappings)

    def test_dynamic_custom_oracle_endpoints_prod_and_dev(self):
        """
        Verify that adding a custom Oracle endpoint adds it to both Prod and Dev,
        routes PI AF Endpoint + Environment (Prod / Test) to the custom Prod/Dev URLs,
        and dispatches to the correct ORDS resource path.
        """
        import json
        from unittest.mock import patch
        from app.config import load_settings, save_settings, load_mappings, save_mappings, get_oracle_custom_endpoints
        from app.delivery_handler import process_incoming_delivery, dispatch_delivery_to_oracle

        orig_settings = load_settings()
        orig_mappings = load_mappings()
        try:
            updated_settings = json.loads(json.dumps(orig_settings))
            updated_settings.setdefault("oracle_erp", {})["enabled"] = True
            updated_settings["oracle_erp"]["base_url"] = "https://prod-ords.example.com/ords/pims_int"
            updated_settings["oracle_erp"]["custom_endpoints"] = [
                {"key": "steam_boiler_output", "label": "Steam Boiler Output", "path": "/steam_boiler_output/"}
            ]
            updated_settings.setdefault("oracledev", {})["enabled"] = True
            updated_settings["oracledev"]["base_url"] = "https://dev-ords.example.com/ords/pims_int"
            updated_settings["oracledev"]["custom_endpoints"] = []
            updated_settings.setdefault("pipeline", {})["auto_dispatch"] = False
            save_settings(updated_settings)

            # 1. Verify adding to oracle_erp automatically synced to oracledev as well
            reloaded = load_settings()
            self.assertEqual(len(reloaded["oracle_erp"]["custom_endpoints"]), 1)
            self.assertEqual(len(reloaded["oracledev"]["custom_endpoints"]), 1)
            self.assertEqual(reloaded["oracledev"]["custom_endpoints"][0]["key"], "steam_boiler_output")
            self.assertEqual(reloaded["oracledev"]["custom_endpoints"][0]["path"], "/steam_boiler_output/")

            custom_eps = get_oracle_custom_endpoints(reloaded)
            self.assertEqual(len(custom_eps), 1)
            self.assertEqual(custom_eps[0]["prod_target"], "oracle_steam_boiler_output")
            self.assertEqual(custom_eps[0]["dev_target"], "oracledev_steam_boiler_output")

            # 2. Verify PI AF Endpoint + Environment routing for Prod and Test
            en_prod, _, dis_prod = resolve_endpoint_and_env_targets({"Endpoint": "Steam Boiler Output", "Environment": "Prod"})
            self.assertEqual(en_prod, ["oracle_steam_boiler_output"])
            self.assertIn("oracledev_steam_boiler_output", dis_prod)

            en_dev, _, dis_dev = resolve_endpoint_and_env_targets({"Endpoint": "steam_boiler_output", "Environment": "Test"})
            self.assertEqual(en_dev, ["oracledev_steam_boiler_output"])
            self.assertIn("oracle_steam_boiler_output", dis_dev)

            # 3. Verify end-to-end dispatch to Dev custom endpoint
            payload_dev = {
                "Tagname": "BOILER_01.STEAM_FLOW",
                "Value": "42.5",
                "Endpoint": "Steam Boiler Output",
                "Environment": "Test"
            }
            expected_dev_url = "https://dev-ords.example.com/ords/pims_int/steam_boiler_output/"
            with patch("app.oracle_erp_client.OracleERPCloudClient.publish_data") as mock_ora:
                mock_ora.return_value = {
                    "status": "SUCCESS",
                    "http_code": 201,
                    "target_endpoint": expected_dev_url,
                    "response_body": {"status": "created"},
                    "error_detail": None,
                    "message": "Created"
                }
                res = process_incoming_delivery(payload_dev, client_ip="10.60.2.20")
                dispatch_res = dispatch_delivery_to_oracle(res["delivery_id"])
                self.assertTrue(mock_ora.called)
                called_kwargs = mock_ora.call_args.kwargs
                self.assertEqual(called_kwargs.get("target_endpoint"), expected_dev_url)
                dispatches = dispatch_res.get("dispatches", [])
                self.assertEqual(len(dispatches), 1)
                self.assertEqual(dispatches[0].get("target_type"), "oracledev_steam_boiler_output")
        finally:
            save_settings(orig_settings)
            save_mappings(orig_mappings)


if __name__ == "__main__":
    unittest.main()
