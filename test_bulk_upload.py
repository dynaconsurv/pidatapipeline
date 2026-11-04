"""
Unit tests for Bulk Historical Telemetry Upload endpoints and parser.
"""
import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.main import (
    bulk_upload_load_sample,
    bulk_upload_preview_payload,
    bulk_upload_dispatch_chunk,
    bulk_upload_download_sample,
    bulk_upload_parse
)
from app.excel_parser import (
    parse_telemetry_file,
    extract_standard_telemetry_row,
    detect_column_roles,
    parse_upload_request_body
)


class TestBulkUpload(unittest.TestCase):

    def test_sample_file_download_endpoint(self):
        resp = bulk_upload_download_sample()
        self.assertIsNotNone(resp)
        self.assertTrue(resp.path.endswith("Cloud Utility updated.xlsx"))

    def test_load_sample_endpoint(self):
        data = bulk_upload_load_sample()
        self.assertTrue(data.get("success"))
        self.assertIn("Natural gas", data.get("sheet_names", []))
        self.assertIn("Electricity", data.get("sheet_names", []))
        self.assertGreater(data.get("total_rows", 0), 40)

        # Check detected columns
        detected = data.get("detected_columns", {})
        self.assertIn(detected.get("timestamp"), ("Timestamp", "SourceTime"))
        self.assertEqual(detected.get("tag"), "Tag")
        self.assertEqual(detected.get("description"), "Description")
        self.assertEqual(detected.get("value"), "Natural Gas.Total Daily Consumption")

    def test_preview_payload_endpoint(self):
        sample_row = {
            "Timestamp": "2026-10-01 00:00:00",
            "Natural Gas.Total Daily Consumption": 1250.75,
            "Description": "Natural Gas Meter 01",
            "Tag": "G01",
            "UOM": "MMBTU"
        }
        col_mapping = {
            "timestamp": "Timestamp",
            "tag": "Tag",
            "description": "Description",
            "value": "Natural Gas.Total Daily Consumption",
            "uom": "UOM"
        }
        data = bulk_upload_preview_payload({
            "target_type": "oracle_utility",
            "row": sample_row,
            "column_mapping": col_mapping
        })
        self.assertTrue(data.get("success"))
        dest_payload = data.get("destination_payload", {})
        self.assertIn("tag", dest_payload)
        self.assertEqual(dest_payload["tag"], "G01")
        self.assertEqual(dest_payload["value"], 1250.75)
        self.assertEqual(dest_payload["timestamp"], "2026-10-01T00:00:00Z")
        self.assertNotIn("AnalysisTime", dest_payload)
        self.assertNotIn("TESTTIMESTAMP", dest_payload)
        self.assertNotIn("TEST_RESULT", dest_payload)

    def test_dispatch_chunk_dry_run(self):
        rows = [
            {
                "Timestamp": "2026-10-01 00:00:00",
                "Natural Gas.Total Daily Consumption": 100.5,
                "Description": "Natural Gas Meter 01",
                "Tag": "G01",
                "UOM": "MMBTU"
            },
            {
                "Timestamp": "2026-10-02 00:00:00",
                "Natural Gas.Total Daily Consumption": 110.2,
                "Description": "Natural Gas Meter 01",
                "Tag": "G01",
                "UOM": "MMBTU"
            }
        ]
        col_mapping = {
            "timestamp": "Timestamp",
            "tag": "Tag",
            "description": "Description",
            "value": "Natural Gas.Total Daily Consumption",
            "uom": "UOM"
        }
        data = bulk_upload_dispatch_chunk({
            "target_type": "oracle_utility",
            "dry_run": True,
            "stage_history": False,
            "column_mapping": col_mapping,
            "rows": rows
        })
        self.assertEqual(data.get("total"), 2)
        self.assertEqual(data.get("succeeded"), 2)
        self.assertEqual(data.get("failed"), 0)
        results = data.get("results", [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["status"], "SUCCESS")

    def test_zero_dependency_multipart_and_binary_parser(self):
        # Test multipart
        boundary = "----WebKitFormBoundaryX"
        content_type = f"multipart/form-data; boundary={boundary}"
        raw_csv = b"Timestamp,Tag,Value\n2026-10-01,T01,100\n"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="test.csv"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
        ).encode("utf-8") + raw_csv + f"\r\n--{boundary}--\r\n".encode("utf-8")

        extracted_bytes, filename = parse_upload_request_body(body, content_type)
        self.assertEqual(filename, "test.csv")
        self.assertEqual(extracted_bytes, raw_csv)

        # Test direct binary stream
        extracted_bytes2, filename2 = parse_upload_request_body(raw_csv, "application/octet-stream", "custom.csv")
        self.assertEqual(filename2, "custom.csv")
        self.assertEqual(extracted_bytes2, raw_csv)

    def test_bulk_upload_parse_endpoint_zero_dependency(self):
        # Mock FastAPI Request to ensure it works WITHOUT python-multipart
        raw_csv = b"Timestamp,Tag,Value\n2026-10-01,T01,100\n"
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="telemetry.csv"\r\n\r\n'
        ).encode("utf-8") + raw_csv + f"\r\n--{boundary}--\r\n".encode("utf-8")

        mock_req = MagicMock()
        mock_req.headers = {"content-type": f"multipart/form-data; boundary={boundary}"}
        mock_req.body = AsyncMock(return_value=body)
        # Mock form() raising RuntimeError like when python-multipart is NOT installed
        mock_req.form = AsyncMock(side_effect=RuntimeError("Form data requires 'python-multipart' to be installed"))

        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(bulk_upload_parse(mock_req))
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("filename"), "telemetry.csv")
            self.assertGreater(res.get("total_rows", 0), 0)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
