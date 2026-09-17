"""
Quick verification test for AVEVA PI to Oracle ERP Cloud Data Pipeline.
Tests genuine connection failure when URL is unreachable or placeholder.
"""
from app.config import load_settings, load_mappings
from app.pipeline import pipeline_engine
from app.pi_client import PIWebApiClient

def main():
    settings = load_settings()
    mappings = load_mappings()
    print("Simulation mode:", settings["pi_web_api"]["simulation_mode"])
    print("PI Web API URL:", settings["pi_web_api"]["url"])

    client = PIWebApiClient(settings["pi_web_api"])
    res = client.test_connection()
    print("\nPI test_connection result:")
    print("  Success:", res.get("success"))
    print("  Message:", res.get("message"))
    print("  Error:", res.get("error"))

    print("\nExecuting pipeline cycle...")
    result = pipeline_engine.execute_cycle()
    status = pipeline_engine.get_status()

    print("\nPipeline Engine PI Status:")
    print("  Status:", status["pi_connection"]["status"])
    print("  Message:", status["pi_connection"]["message"])
    print("  Error:", status["pi_connection"]["error"])
    print("  Last 5 pulls count:", len(status["last_5_pulls"]))

    print("\nOracle ERP Status:")
    print("  Status:", status["oracle_erp_connection"]["status"])
    print("  Message:", status["oracle_erp_connection"]["message"])

if __name__ == "__main__":
    main()
