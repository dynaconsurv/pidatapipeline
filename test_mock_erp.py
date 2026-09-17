"""
Verification script for Oracle ERP Cloud Mock Simulation Server and Pipeline Integration.
"""
import sys
import time
import requests
from app.mock_erp_server import mock_erp_manager
from app.oracle_erp_client import OracleERPCloudClient
from app.config import load_settings, save_settings

def run_verification():
    print("--- 1. Testing Mock ERP Manager Start on Port 8080 ---")
    mock_erp_manager.start()
    time.sleep(1.0)
    status = mock_erp_manager.get_status()
    print(f"Mock ERP Status: {status}")
    assert status["running"] is True, "Mock ERP should be running"
    assert status["port"] == 8080

    print("\n--- 2. Direct HTTP Requests to Mock Server (Port 8080) ---")
    # Health root
    resp = requests.get("http://127.0.0.1:8080/")
    print(f"GET / -> HTTP {resp.status_code}: {resp.json().get('service')}")
    assert resp.status_code == 200

    # OAuth 2.0 Token
    token_url = "http://127.0.0.1:8080/oauth2/v1/token"
    token_resp = requests.post(
        token_url,
        data={"grant_type": "client_credentials"},
        auth=requests.auth.HTTPBasicAuth(status["client_id"], status["client_secret"])
    )
    print(f"POST /oauth2/v1/token -> HTTP {token_resp.status_code}: {token_resp.json()}")
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    access_token = token_data["access_token"]
    assert access_token.startswith("orcl_jwt_")

    # FSCM REST OPTIONS probe
    fscm_url = "http://127.0.0.1:8080/fscmRestApi/resources/11.13.18.05/standardReceipts"
    options_resp = requests.options(fscm_url, headers={"Authorization": f"Bearer {access_token}"})
    print(f"OPTIONS {fscm_url} -> HTTP {options_resp.status_code}")
    assert options_resp.status_code == 200

    # FSCM REST POST ingestion
    sample_payload = {
        "items": [
            {
                "meterCode": "BLR101_STM_TEMP",
                "readingValue": 542.8,
                "uom": "deg C",
                "timestamp": "2026-09-17T18:00:00Z"
            }
        ]
    }
    post_resp = requests.post(
        fscm_url,
        json=sample_payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/vnd.oracle.adf.resourceitem+json",
            "REST-Framework-Version": "4"
        }
    )
    print(f"POST {fscm_url} -> HTTP {post_resp.status_code}: {post_resp.json()}")
    assert post_resp.status_code == 201
    assert "TransactionId" in post_resp.json()

    print("\n--- 3. Testing OracleERPCloudClient with Mock Config ---")
    erp_client = OracleERPCloudClient({
        "enabled": True,
        "auth_type": "oauth2",
        "base_url": "http://127.0.0.1:8080",
        "token_url": "http://127.0.0.1:8080/oauth2/v1/token",
        "client_id": status["client_id"],
        "client_secret": status["client_secret"],
        "scope": "urn:opc:resource:consumer::all",
        "resource_endpoint": "/fscmRestApi/resources/11.13.18.05/standardReceipts",
        "http_method": "POST",
        "dry_run": False,
        "timeout_seconds": 10
    })

    test_conn = erp_client.test_connection()
    print(f"Client test_connection() -> {test_conn}")
    assert test_conn["success"] is True
    assert test_conn["status"] == "CONNECTED"

    publish_result = erp_client.publish_data({
        "items": [
            {"meterCode": "GEN01_ACT_PWR", "readingValue": 128.45, "uom": "MW"}
        ]
    })
    print(f"Client publish_data() -> {publish_result}")
    assert publish_result["status"] == "SUCCESS"
    assert publish_result["http_code"] == 201

    print("\n--- 4. Inspecting Recorded Mock Transactions ---")
    txns = mock_erp_manager.get_status()["transactions_count"]
    print(f"Total Transactions in Mock ERP: {txns}")
    assert txns >= 2

    mock_erp_manager.stop()
    print("Mock ERP stopped successfully.")
    print("\nALL VERIFICATION CHECKS PASSED!")

if __name__ == "__main__":
    run_verification()
