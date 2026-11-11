"""
Payload Field & Parameter Schema Mapping Engine.
Dynamically transforms incoming AVEVA PI AF notification telemetry attributes
into destination payloads for Oracle ORDS Cloud and Hexagon Octave (J5).
Replaces hardcoded parameters with fully customizable schemas stored in config/field_mappings.json.
"""
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone

from app.config import load_field_mappings
from app.oracle_erp_client import format_ords_timestamp
from app.j5_client import format_j5_timestamp


def build_destination_payload(
    target_type: str,
    source_attr: Dict[str, Any],
    mapping_rule: Optional[Dict[str, Any]] = None,
    received_at: Optional[str] = None,
    skip_params: Optional[Set[str]] = None,
    field_mappings_override: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Builds destination payload for either Oracle or Octave by applying
    the configurable parameter mappings.

    Args:
        target_type: 'oracle', 'oracledev', 'oracle_utility', 'oracledev_utility', 'j5', or 'octave'
        source_attr: Dictionary of attribute telemetry from PI Notification
        mapping_rule: Point/tag mapping definition from config/mappings.json (scale factor, round decimals, etc.)
        received_at: Ingestion receipt arrival timestamp (ISO string)
        skip_params: Set of parameter names (lowercased) that should never be forwarded
        field_mappings_override: Optional parameter mappings list for testing or preview
    """
    mapping_rule = mapping_rule or {}
    skip_params = {str(p).strip().lower() for p in (skip_params or set()) if str(p).strip()}
    already_utc8 = bool(source_attr.get("_is_utc8_formatted", False))
    now_iso = datetime.now(timezone.utc).isoformat()
    received_time = received_at or source_attr.get("received_at") or source_attr.get("timestamp") or source_attr.get("record_at") or source_attr.get("RECORD_AT") or now_iso

    t_clean = str(target_type).strip().lower()
    if any(x in t_clean for x in ("oracledev", "dev_utility", "dev_production", "oracle_dev")):
        target_category = "oracle_dev"
        is_oracle = True
    elif any(x in t_clean for x in ("oracle", "ords", "erp")):
        target_category = "oracle_prod"
        is_oracle = True
    elif any(x in t_clean for x in ("j5dev", "octavedev", "j5_dev", "octave_dev")):
        target_category = "octave_dev"
        is_oracle = False
    else:
        target_category = "octave_prod"
        is_oracle = False

    # 1. Load active parameter mappings for target category
    if field_mappings_override is not None:
        schema_mappings = field_mappings_override
    else:
        all_field_maps = load_field_mappings()
        schema_mappings = all_field_maps.get(target_category) or all_field_maps.get(target_category.split("_")[0], [])

    # 2. Compute transformed telemetry values (scaling & rounding)
    scale = float(mapping_rule.get("scale_factor", 1.0))
    decimals = int(mapping_rule.get("round_decimals", 2))
    raw_val = source_attr.get("value")
    if raw_val is None or str(raw_val).strip() == "":
        for k, v in source_attr.items():
            if "value" in str(k).lower() and v is not None and str(v).strip() != "":
                raw_val = v
                break
        if (raw_val is None or str(raw_val).strip() == "") and isinstance(source_attr.get("extra_fields"), dict):
            for k, v in source_attr["extra_fields"].items():
                if "value" in str(k).lower() and v is not None and str(v).strip() != "":
                    raw_val = v
                    break
    scaled_val = raw_val
    try:
        if raw_val is not None and str(raw_val).strip() != "":
            scaled_val = round(float(raw_val) * scale, decimals)
    except Exception:
        scaled_val = raw_val

    # Standard attribute resolutions
    tag_val = (
        source_attr.get("tag")
        or (mapping_rule.get("tag") if mapping_rule.get("tag") is not None else (mapping_rule.get("meter_tag") or ""))
        or source_attr.get("name")
        or ""
    )
    desc_val = (
        source_attr.get("description")
        or (mapping_rule.get("description") if mapping_rule.get("description") is not None else (mapping_rule.get("name") or ""))
        or ""
    )
    limit_val = (
        source_attr.get("limit")
        or (mapping_rule.get("limit") if mapping_rule.get("limit") is not None else "")
        or ""
    )
    results_val = (
        source_attr.get("results")
        or source_attr.get("result")
        or (mapping_rule.get("results") if mapping_rule.get("results") is not None else "")
        or ""
    )
    uom_val = (
        source_attr.get("uom")
        or source_attr.get("UOM")
        or source_attr.get("unit")
        or (mapping_rule.get("uom") if mapping_rule.get("uom") is not None else (mapping_rule.get("unit") or ""))
        or ""
    )
    quality_val = source_attr.get("quality") or "Good"

    # 3. Build lower-cased lookup dictionary of all incoming values
    lower_sources: Dict[str, Any] = {}

    # Extra fields from PI notification
    extra_fields = source_attr.get("extra_fields")
    if isinstance(extra_fields, dict):
        for ek, ev in extra_fields.items():
            if ek is not None:
                lower_sources[str(ek).strip().lower()] = ev

    # Top-level attributes
    for k, v in source_attr.items():
        if k is not None and k != "extra_fields":
            lower_sources[str(k).strip().lower()] = v

    # Synthesized standard values take precedence for standard keys
    lower_sources["timestamp"] = received_time
    lower_sources["received_at"] = received_time
    lower_sources["record_at"] = lower_sources.get("record_at") or received_time
    lower_sources["recorded_at"] = lower_sources.get("recorded_at") or received_time
    lower_sources["tag"] = tag_val
    lower_sources["meter_tag"] = tag_val
    lower_sources["description"] = desc_val
    lower_sources["value"] = scaled_val
    lower_sources["readingvalue"] = scaled_val
    lower_sources["limit"] = limit_val
    lower_sources["results"] = results_val
    lower_sources["result"] = results_val
    lower_sources["uom"] = uom_val
    lower_sources["unit"] = uom_val
    lower_sources["quality"] = quality_val

    # 4. Map configured schema entries
    payload: Dict[str, Any] = {}
    consumed_source_keys: Set[str] = set()

    for m in schema_mappings:
        if not m.get("enabled", True):
            continue
        src_raw = str(m.get("source") or "").strip()
        tgt_raw = str(m.get("target") or "").strip()
        transform = str(m.get("transform") or "string").strip().lower()
        if not src_raw or not tgt_raw:
            continue
        if tgt_raw.lower().replace("_", "") in ("testresult", "testresults"):
            continue

        src_l = src_raw.lower()
        consumed_source_keys.add(src_l)

        # Look up value
        if src_l in lower_sources and lower_sources[src_l] is not None and str(lower_sources[src_l]).strip() != "":
            raw_v = lower_sources[src_l]
        elif "value" in src_l:
            # Fallback: check any parameter containing 'value' in lower_sources
            raw_v = None
            for lk, lv in lower_sources.items():
                if "value" in lk and lv is not None and str(lv).strip() != "":
                    raw_v = lv
                    break
        elif src_l in ("record_at", "recorded_at") or tgt_raw.lower() in ("record_at", "recorded_at"):
            raw_v = lower_sources.get(src_l) or received_time
        elif src_l in lower_sources:
            raw_v = lower_sources[src_l]
        else:
            # Not provided in incoming payload
            raw_v = None

        if tgt_raw.lower() in ("record_at", "recorded_at") and (raw_v is None or str(raw_v).strip() == ""):
            raw_v = received_time

        # Apply transformation
        if transform == "receipt_time":
            if is_oracle:
                payload[tgt_raw] = format_ords_timestamp(received_time, already_utc8=already_utc8)
            else:
                payload[tgt_raw] = format_j5_timestamp(received_time, already_utc8=already_utc8)
        elif transform == "timestamp_zulu":
            if raw_v is None or str(raw_v).strip() == "":
                continue
            if is_oracle:
                payload[tgt_raw] = format_ords_timestamp(raw_v, allow_empty=True, already_utc8=already_utc8)
            else:
                payload[tgt_raw] = format_j5_timestamp(raw_v, allow_empty=True, already_utc8=already_utc8)
        elif transform == "numeric_scaled":
            if raw_v is None or str(raw_v).strip() == "":
                payload[tgt_raw] = "" if is_oracle else None
            else:
                try:
                    payload[tgt_raw] = round(float(raw_v) * scale, decimals)
                except Exception:
                    payload[tgt_raw] = raw_v
        elif transform == "direct":
            payload[tgt_raw] = raw_v
        else:  # default 'string'
            payload[tgt_raw] = str(raw_v) if raw_v is not None else ""

    # 5. Octave special standard header
    if not is_oracle and "sourceSystem" not in payload:
        payload["sourceSystem"] = "AVEVA_PI_NOTIFICATION"

    # 6. Forward unmapped extra fields
    # Loop over extra_fields and source_attr
    unmapped_candidates: Dict[str, Any] = {}
    if isinstance(extra_fields, dict):
        for ek, ev in extra_fields.items():
            if ek is not None:
                unmapped_candidates[str(ek).strip()] = ev

    for ak, av in source_attr.items():
        if ak and ak != "extra_fields" and ak not in ("name", "target_flags", "disabled_target_flags", "_is_utc8_formatted"):
            if str(ak).strip() not in unmapped_candidates:
                unmapped_candidates[str(ak).strip()] = av

    for uk, uv in unmapped_candidates.items():
        uk_l = uk.lower()
        if uk_l in skip_params or uk_l == "_is_utc8_formatted":
            continue
        if uk_l.replace("_", "") in ("testresult", "testresults"):
            continue
        if is_oracle and uk_l == "quality":
            continue
        if uk_l in consumed_source_keys:
            continue
        if uk in payload:
            continue
        if uk_l in ("target_endpoint_url", "endpoint_url", "target_endpoint", "endpoint"):
            continue

        # Convert timestamp format if key contains 'time'
        if "time" in uk_l or "date" in uk_l or uk_l.endswith("_at") or uk_l.startswith("record"):
            if uk_l in ("record_at", "recorded_at") and (uv is None or str(uv).strip() == ""):
                uv = received_time
            if is_oracle:
                payload[uk] = format_ords_timestamp(uv, allow_empty=True, already_utc8=already_utc8)
            else:
                payload[uk] = format_j5_timestamp(uv, allow_empty=True, already_utc8=already_utc8)
            if uk_l in ("record_at", "recorded_at") and payload.get(uk) is None:
                payload[uk] = format_ords_timestamp(received_time, already_utc8=already_utc8) if is_oracle else format_j5_timestamp(received_time, already_utc8=already_utc8)
        else:
            if uv is None:
                payload[uk] = "" if is_oracle else None
            elif isinstance(uv, (str, int, float, bool)):
                payload[uk] = uv
            else:
                payload[uk] = str(uv)

    # Exclude TEST_RESULT / test_result from payload if present
    for pk in list(payload.keys()):
        if pk.lower().replace("_", "") in ("testresult", "testresults") or pk == "_is_utc8_formatted":
            payload.pop(pk, None)

    # Deduplicate RECORD_AT: ensure only ONE canonical RECORD_AT is present
    rec_val = None
    keys_to_clean = []
    for k in list(payload.keys()):
        if k.lower() in ("record_at", "recorded_at"):
            if rec_val is None and payload[k]:
                rec_val = payload[k]
            keys_to_clean.append(k)

    if rec_val or is_oracle:
        for k in keys_to_clean:
            payload.pop(k, None)
        payload["RECORD_AT"] = rec_val or format_ords_timestamp(received_time, already_utc8=already_utc8)

    # Suppress duplicate internal alias keys
    if "tag" in payload or "TAG" in payload:
        payload.pop("meter_tag", None)
    payload.pop("sheet", None)

    return payload
