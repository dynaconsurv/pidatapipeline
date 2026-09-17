"""
Test error handling and diagnostic reporting for PI Web API and Oracle ERP Cloud.
"""
from app.pi_client import PIWebApiClient
from app.oracle_erp_client import OracleERPCloudClient
from app.storage import get_pull_history, get_publish_history, get_logs

def test_diagnostics():
    print("Testing PI Web API unreachable host handling...")
    bad_pi_client = PIWebApiClient({
        "url": "https://nonexistent-pi-host-test.internal/piwebapi",
        "simulation_mode": False,
        "verify_ssl": False,
        "timeout_seconds": 2
    })
    res = bad_pi_client.test_connection()
    print(f"PI Bad host success: {res.get('success')} | Message: {res.get('message')}")
    assert res.get("success") is False
    assert "error" in res

    print("\nTesting Oracle ERP Cloud connection without configuration...")
    unconfigured_erp = OracleERPCloudClient({"enabled": False})
    res_erp = unconfigured_erp.test_connection()
    print(f"ERP Pending status: {res_erp.get('status')} | Message: {res_erp.get('message')}")
    assert res_erp.get("status") == "PENDING_SETUP"

    print("\nTesting Oracle ERP Cloud with invalid host...")
    bad_erp = OracleERPCloudClient({
        "enabled": True,
        "auth_type": "basic",
        "base_url": "https://invalid-erp-instance.oraclecloud.com",
        "username": "test_user",
        "password": "test_password",
        "resource_endpoint": "/fscmRestApi/resources/11.13.18.05/standardReceipts",
        "timeout_seconds": 2
    })
    res_bad_erp = bad_erp.test_connection()
    print(f"ERP Bad host status: {res_bad_erp.get('status')} | Message: {res_bad_erp.get('message')}")
    assert res_bad_erp.get("status") == "FAILED"

    print("\nChecking JSON storage files...")
    pulls = get_pull_history()
    publishes = get_publish_history()
    logs = get_logs()
    print(f"Pulls stored: {len(pulls)}")
    print(f"Publishes stored: {len(publishes)}")
    print(f"Logs stored: {len(logs)}")
    assert len(pulls) > 0
    assert len(publishes) > 0

    print("\n[ALL DIAGNOSTIC TESTS PASSED]")

if __name__ == "__main__":
    test_diagnostics()
