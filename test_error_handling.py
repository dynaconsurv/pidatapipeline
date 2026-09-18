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


def test_pi_url_normalization_and_probing():
    from unittest.mock import patch, MagicMock

    print("\nTesting PI Web API URL normalization...")
    c1 = PIWebApiClient({"url": "pi-server.local"})
    assert c1.url == "https://pi-server.local/piwebapi", f"Got {c1.url}"

    c2 = PIWebApiClient({"url": "https://pi-server.local"})
    assert c2.url == "https://pi-server.local/piwebapi", f"Got {c2.url}"

    c3 = PIWebApiClient({"url": "https://pi-server.local/piwebapi/"})
    assert c3.url == "https://pi-server.local/piwebapi", f"Got {c3.url}"

    print("URL Normalization passed!")

    # Test 404 handling with simulated 404 response
    print("\nTesting PI Web API 404 handling with multi-probe diagnostics...")
    mock_404 = MagicMock()
    mock_404.status_code = 404
    mock_404.text = "Not Found"

    with patch("requests.Session.get", return_value=mock_404):
        res = c3.test_connection()
        assert res["success"] is False
        assert res["status_code"] == 404
        assert "404" in res["message"]
        assert "Troubleshooting Checklist" in res["error"]
        print("404 Diagnostics response passed:", res["message"])

    # Test 401 handling with simulated 401 response
    print("\nTesting PI Web API 401 authentication rejection...")
    mock_401 = MagicMock()
    mock_401.status_code = 401
    mock_401.text = "Unauthorized"
    mock_401.headers = {}
    mock_401.json.side_effect = Exception("Not JSON")

    with patch("requests.Session.get", return_value=mock_401):
        res = c3.test_connection()
        assert res["success"] is False
        assert res["status_code"] == 401
        assert "authentication failed" in res["message"]
        print("401 Authentication response passed:", res["message"])

    # Test 200 handling with simulated landing page response
    print("\nTesting PI Web API 200 discovery response...")
    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {
        "Links": {
            "Self": "https://pi-server.local/piwebapi",
            "AssetServers": "https://pi-server.local/piwebapi/assetservers"
        }
    }

    with patch("requests.Session.get", return_value=mock_200):
        res = c3.test_connection()
        assert res["success"] is True
        assert res["status_code"] == 200
        assert res["normalized_url"] == "https://pi-server.local/piwebapi"
        print("200 Discovery response passed:", res["message"])

    print("\n[ALL PI URL & MULTI-PROBE TESTS PASSED]")


if __name__ == "__main__":
    test_diagnostics()
    test_pi_url_normalization_and_probing()
