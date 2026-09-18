"""
Test active mapping filtering in Last 5 Data Pulls.
Ensures inactive or removed mappings never appear in the dashboard.
"""
from app.pipeline import pipeline_engine
from app.config import load_mappings, save_mappings

def test_filtering():
    original_mappings = load_mappings()
    print(f"Total configured mappings: {len(original_mappings)}")

    # 1. Check with active mappings
    status1 = pipeline_engine.get_status()
    pulls1 = status1.get("last_5_pulls", [])
    print(f"Pulls with default mappings: {len(pulls1)} triggers")
    assert len(pulls1) <= 5
    if pulls1:
        trigger = pulls1[0]
        assert "triggered_at" in trigger
        assert "ingested_at" in trigger
        assert "items" in trigger
        assert "quality" in trigger
        print(f"  Trigger 1 has {len(trigger['items'])} active items: {[it['attribute_name'] for it in trigger['items']]}")

    # 2. Disable all mappings
    disabled_mappings = [{**m, "enabled": False} for m in original_mappings]
    save_mappings(disabled_mappings)
    status2 = pipeline_engine.get_status()
    pulls2 = status2.get("last_5_pulls", [])
    print(f"Triggers with all mappings DISABLED: {len(pulls2)}")
    assert len(pulls2) == 0, f"Expected 0 triggers when all disabled, got {len(pulls2)}"

    # 3. Enable only the first mapping
    active_target = original_mappings[0]["attribute_name"]
    one_active = [{**original_mappings[0], "enabled": True}] + [{**m, "enabled": False} for m in original_mappings[1:]]
    save_mappings(one_active)
    status3 = pipeline_engine.get_status()
    pulls3 = status3.get("last_5_pulls", [])
    print(f"Triggers with only '{active_target}' enabled: {len(pulls3)}")
    assert len(pulls3) > 0, "Expected at least 1 trigger with active target"
    assert len(pulls3) <= 5, f"Expected at most 5 triggers, got {len(pulls3)}"
    for tr in pulls3:
        for item in tr["items"]:
            assert item["attribute_name"].strip().lower() == active_target.strip().lower(), (
                f"Inactive attribute {item['attribute_name']} appeared in trigger!"
            )

    # 4. Remove all mappings completely
    save_mappings([])
    status_empty = pipeline_engine.get_status()
    pulls_empty = status_empty.get("last_5_pulls", [])
    print(f"Triggers with mappings completely removed: {len(pulls_empty)}")
    assert len(pulls_empty) == 0, f"Expected 0 triggers when mappings empty, got {len(pulls_empty)}"

    # 5. Restore original mappings
    save_mappings(original_mappings)
    status_restored = pipeline_engine.get_status()
    pulls_restored = status_restored.get("last_5_pulls", [])
    print(f"Triggers after restoring mappings: {len(pulls_restored)}")
    assert len(pulls_restored) <= 5

    print("\n[SUCCESS: All trigger-based inactive & removed mapping filtering tests passed!]")

if __name__ == "__main__":
    test_filtering()
