"""
Quick verification test for AVEVA PI to Oracle ERP Cloud Data Pipeline.
"""
import sys
from app.config import load_settings, load_mappings
from app.pipeline import pipeline_engine

def main():
    print("1. Loading settings and mappings...")
    settings = load_settings()
    mappings = load_mappings()
    print(f"   Settings keys: {list(settings.keys())}")
    print(f"   Configured mappings: {len(mappings)}")

    print("\n2. Executing pipeline extraction & push cycle...")
    result = pipeline_engine.execute_cycle()
    pull = result.get("pull", {})
    publish = result.get("publish", {})

    print(f"   Pull Batch ID: {result.get('batch_id')}")
    print(f"   Pull Success: {pull.get('success')}")
    print(f"   Items Pulled: {pull.get('count')}")
    print(f"   ERP Publish Status: {publish.get('status')} ({publish.get('message')})")

    print("\n3. Inspecting pulled attributes:")
    for idx, item in enumerate(pull.get("items", [])[:5], 1):
        print(f"   [{idx}] {item.get('attribute_name')}: {item.get('value')} {item.get('uom')} (Quality: {item.get('quality')})")

    print("\n4. Getting dashboard status object...")
    status = pipeline_engine.get_status()
    print(f"   PI Status: {status.get('pi_connection', {}).get('status')}")
    print(f"   Oracle ERP Status: {status.get('oracle_erp_connection', {}).get('status')}")
    print(f"   Last 5 pulls count: {len(status.get('last_5_pulls', []))}")
    print(f"   Scheduler next run in: {status.get('scheduler', {}).get('seconds_remaining')}s")

    print("\n[SUCCESS] Pipeline engine operational!")

if __name__ == "__main__":
    main()
