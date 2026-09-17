"""
Live server testing using uvicorn and requests.
"""
import threading
import time
import requests
import uvicorn
from app.main import app

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="warning")

def test_live():
    # Start server in background thread
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(1.5)

    base = "http://127.0.0.1:8099"
    print("Testing GET / ...")
    r_index = requests.get(f"{base}/", timeout=5)
    assert r_index.status_code == 200
    assert "AVEVA PI" in r_index.text
    print("  Index OK, HTML size:", len(r_index.text))

    print("Testing GET /api/dashboard ...")
    r_dash = requests.get(f"{base}/api/dashboard", timeout=5)
    assert r_dash.status_code == 200
    dash_json = r_dash.json()
    print("  Dashboard PI Status:", dash_json["pi_connection"]["status"])
    print("  Dashboard ERP Status:", dash_json["oracle_erp_connection"]["status"])
    print("  Dashboard Last 5 pulls:", len(dash_json["last_5_pulls"]))

    print("Testing GET /api/mappings ...")
    r_map = requests.get(f"{base}/api/mappings", timeout=5)
    assert r_map.status_code == 200
    print("  Mappings count:", len(r_map.json()))

    print("Testing GET /api/mappings/preview ...")
    r_prev = requests.get(f"{base}/api/mappings/preview", timeout=5)
    assert r_prev.status_code == 200
    print("  Preview payload items:", len(r_prev.json().get("items", [])))

    print("Testing POST /api/pipeline/run-now ...")
    r_run = requests.post(f"{base}/api/pipeline/run-now", timeout=10)
    assert r_run.status_code == 200
    print("  Run-now success:", r_run.json().get("success"))

    print("Testing GET /api/settings ...")
    r_set = requests.get(f"{base}/api/settings", timeout=5)
    assert r_set.status_code == 200
    print("  Settings keys:", list(r_set.json().keys()))

    print("Testing POST /api/settings/test-pi ...")
    r_pi = requests.post(f"{base}/api/settings/test-pi", json={}, timeout=5)
    assert r_pi.status_code == 200
    print("  PI test result success:", r_pi.json().get("success"))

    print("Testing POST /api/settings/test-erp ...")
    r_erp = requests.post(f"{base}/api/settings/test-erp", json={}, timeout=5)
    assert r_erp.status_code == 200
    print("  ERP test result status:", r_erp.json().get("status"))

    print("Testing GET /api/logs ...")
    r_logs = requests.get(f"{base}/api/logs", timeout=5)
    assert r_logs.status_code == 200
    print("  Logs count:", len(r_logs.json()))

    print("\n[ALL LIVE REST ENDPOINTS VERIFIED SUCCESSFULLY!]")

if __name__ == "__main__":
    test_live()
