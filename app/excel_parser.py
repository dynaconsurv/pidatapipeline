"""
Excel (.xlsx) and CSV Bulk Telemetry Data Parser.
Parses historical telemetry logs (e.g. from PI System or plant historians)
for bulk upload into Oracle ORDS Cloud and Hexagon Octave.
Supports openpyxl with pure Python standard library fallback.
"""
import os
import io
import re
import csv
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, date, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union

TZ_UTC8 = timezone(timedelta(hours=8))


def format_iso_zulu(val: Any, allow_empty: bool = False, fallback: Optional[str] = None) -> str:
    """Format any date/time value into ISO 8601 string (YYYY-MM-DDTHH:MM:SSZ) in UTC+8 local clock time."""
    if val is None or str(val).strip() == "" or str(val).strip().lower() in ("none", "null"):
        if fallback is not None:
            return fallback
        if allow_empty:
            return ""
        return datetime.now(TZ_UTC8).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            val = val.astimezone(TZ_UTC8)
        return val.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Check for Excel serial date numbers (int, float, or numeric string e.g. 46326 or "46326")
    try:
        fval = float(val)
        if 20000 <= fval <= 100000:
            excel_epoch = datetime(1899, 12, 30)
            sec = round(fval * 86400)
            dt = excel_epoch + timedelta(seconds=sec)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        pass

    s = str(val).strip()
    if not s or s.lower() in ("none", "null"):
        if fallback is not None:
            return fallback
        if allow_empty:
            return ""
        return datetime.now(TZ_UTC8).strftime("%Y-%m-%dT%H:%M:%SZ")

    # If explicitly tagged with Z or timezone offset, convert to UTC+8
    if s.endswith("Z") or "+" in s[10:] or "-" in s[10:]:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(TZ_UTC8)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    # Common date string patterns (naive local clock time in Excel)
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y"
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(s, fmt)
            return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

    # Try ISO fromisoformat
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(TZ_UTC8)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    return s


def detect_column_roles(headers: List[str]) -> Dict[str, Optional[str]]:
    """
    Auto-detects column roles (timestamp, tag, description, value, uom)
    from table header names.
    """
    roles: Dict[str, Optional[str]] = {
        "timestamp": None,
        "tag": None,
        "description": None,
        "value": None,
        "uom": None
    }
    if not headers:
        return roles

    lower_to_orig = {str(h or "").strip().lower(): h for h in headers if h is not None}
    h_lowers = list(lower_to_orig.keys())

    # 1. Detect Timestamp
    for hl in h_lowers:
        if not roles["timestamp"] and any(k in hl for k in ("timestamp", "reading_time", "readingtime", "datetime", "date", "time")):
            roles["timestamp"] = lower_to_orig[hl]
            break

    # 2. Detect Tag
    for hl in h_lowers:
        if not roles["tag"]:
            if hl in ("tag", "tagname", "tag_name", "meter_tag", "point", "code", "tag name") or "tag" in hl:
                roles["tag"] = lower_to_orig[hl]
                break

    # 3. Detect Description
    for hl in h_lowers:
        if not roles["description"]:
            if any(k in hl for k in ("description", "desc", "attribute_desc", "item_name", "title")):
                roles["description"] = lower_to_orig[hl]
                break

    # 4. Detect UOM
    for hl in h_lowers:
        if not roles["uom"]:
            if any(k in hl for k in ("uom", "unit", "unitofmeasure", "units")):
                roles["uom"] = lower_to_orig[hl]
                break

    # 5. Detect Value (consumption, value, reading, rate, total, etc.)
    remaining = [hl for hl in h_lowers if lower_to_orig[hl] not in (roles["timestamp"], roles["tag"], roles["description"], roles["uom"])]

    for hl in remaining:
        if not roles["value"]:
            if any(k in hl for k in ("consumption", "value", "val", "reading", "total", "rate", "flow", "qty", "amount", "pressure", "temp", "electricity", "gas")):
                roles["value"] = lower_to_orig[hl]
                break

    # Fallback for Value: first remaining non-assigned column
    if not roles["value"] and remaining:
        roles["value"] = lower_to_orig[remaining[0]]

    return roles


def _parse_with_openpyxl(file_source: Any) -> Dict[str, Any]:
    """Parse workbook using openpyxl."""
    import openpyxl
    if isinstance(file_source, bytes):
        wb = openpyxl.load_workbook(io.BytesIO(file_source), data_only=True)
    else:
        wb = openpyxl.load_workbook(file_source, data_only=True)

    sheets_data = []
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        if sheet.max_row < 1:
            continue

        raw_headers = [sheet.cell(1, c).value for c in range(1, sheet.max_column + 1)]
        headers = [str(h or "").strip() for h in raw_headers if h is not None and str(h).strip()]
        if not headers:
            continue

        col_count = len(headers)
        detected_roles = detect_column_roles(headers)

        rows = []
        for r in range(2, sheet.max_row + 1):
            row_dict = {}
            has_val = False
            for c in range(1, col_count + 1):
                cell_val = sheet.cell(r, c).value
                if cell_val is not None:
                    has_val = True
                h_name = headers[c - 1]
                if isinstance(cell_val, (datetime, date)):
                    row_dict[h_name] = format_iso_zulu(cell_val)
                elif (h_name == detected_roles.get("timestamp") or "time" in h_name.lower() or "date" in h_name.lower()) and cell_val is not None:
                    try:
                        fval = float(cell_val)
                        if 20000 <= fval <= 100000:
                            row_dict[h_name] = format_iso_zulu(fval)
                        else:
                            row_dict[h_name] = cell_val
                    except (ValueError, TypeError):
                        row_dict[h_name] = cell_val
                else:
                    row_dict[h_name] = cell_val
            if has_val:
                rows.append(row_dict)

        sheets_data.append({
            "name": sheet_name,
            "headers": headers,
            "detected_columns": detected_roles,
            "total_rows": len(rows),
            "rows": rows
        })

    return {"sheets": sheets_data}


def _parse_xlsx_stdlib(file_source: Any) -> Dict[str, Any]:
    """
    Pure Python standard library fallback parser for .xlsx (uses zipfile and xml.etree.ElementTree).
    Guarantees full .xlsx parsing capability even if openpyxl is not installed.
    """
    if isinstance(file_source, (str, bytes)):
        bio = io.BytesIO(file_source) if isinstance(file_source, bytes) else open(file_source, "rb")
    else:
        bio = file_source

    with zipfile.ZipFile(bio, "r") as z:
        # Load shared strings
        shared_strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in tree.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                t = si.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                shared_strings.append(t.text if t is not None and t.text else "")

        # Find sheets in workbook.xml
        wb_tree = ET.fromstring(z.read("xl/workbook.xml"))
        sheets_elem = wb_tree.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets")
        sheets_info = []
        if sheets_elem is not None:
            for s in sheets_elem.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"):
                sheets_info.append(s.attrib.get("name", "Sheet1"))

        sheets_data = []
        sheet_idx = 1
        for sname in sheets_info:
            target_xml = f"xl/worksheets/sheet{sheet_idx}.xml"
            sheet_idx += 1
            if target_xml not in z.namelist():
                continue

            stree = ET.fromstring(z.read(target_xml))
            sheet_data = stree.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData")
            if sheet_data is None:
                continue

            xml_rows = sheet_data.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row")
            if not xml_rows:
                continue

            parsed_matrix = []
            for r_node in xml_rows:
                row_cells = {}
                for c_node in r_node.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                    r_ref = c_node.attrib.get("r", "")
                    col_letters = "".join(filter(str.isalpha, r_ref))
                    t_type = c_node.attrib.get("t", "")
                    v_node = c_node.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                    raw_text = v_node.text if v_node is not None else ""

                    if t_type == "s" and raw_text.isdigit():
                        idx = int(raw_text)
                        val = shared_strings[idx] if idx < len(shared_strings) else raw_text
                    else:
                        val = raw_text

                    # Try numeric float parsing
                    if val is not None and t_type != "s":
                        try:
                            if "." in str(val):
                                val = float(val)
                            else:
                                val = int(val)
                        except ValueError:
                            pass
                    row_cells[col_letters] = val
                if row_cells:
                    parsed_matrix.append(row_cells)

            if not parsed_matrix:
                continue

            # First row is headers
            first_row_map = parsed_matrix[0]
            sorted_cols = sorted(first_row_map.keys(), key=lambda x: (len(x), x))
            headers = [str(first_row_map.get(col) or "").strip() for col in sorted_cols if str(first_row_map.get(col) or "").strip()]

            detected_roles = detect_column_roles(headers)
            ts_col_name = detected_roles.get("timestamp")

            rows = []
            for r_map in parsed_matrix[1:]:
                row_dict = {}
                for idx, col in enumerate(sorted_cols):
                    if idx < len(headers):
                        h_name = headers[idx]
                        cell_raw = r_map.get(col, "")
                        if (h_name == ts_col_name or "time" in h_name.lower() or "date" in h_name.lower()) and cell_raw is not None and str(cell_raw).strip() != "":
                            try:
                                fval = float(cell_raw)
                                if 20000 <= fval <= 100000:
                                    cell_raw = format_iso_zulu(fval)
                            except (ValueError, TypeError):
                                pass
                        row_dict[h_name] = cell_raw
                if any(v != "" and v is not None for v in row_dict.values()):
                    rows.append(row_dict)
            sheets_data.append({
                "name": sname,
                "headers": headers,
                "detected_columns": detected_roles,
                "total_rows": len(rows),
                "rows": rows
            })

        return {"sheets": sheets_data}


def _parse_csv(file_source: Any) -> Dict[str, Any]:
    """Parse CSV format."""
    if isinstance(file_source, bytes):
        text = file_source.decode("utf-8-sig", errors="replace")
    elif isinstance(file_source, str) and os.path.exists(file_source):
        with open(file_source, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    else:
        text = str(file_source)

    reader = csv.reader(io.StringIO(text))
    rows_raw = list(reader)
    if not rows_raw:
        return {"sheets": []}

    headers = [str(h or "").strip() for h in rows_raw[0] if str(h or "").strip()]
    detected_roles = detect_column_roles(headers)

    rows = []
    for r_vals in rows_raw[1:]:
        row_dict = {}
        for idx, h_name in enumerate(headers):
            val = r_vals[idx].strip() if idx < len(r_vals) else ""
            row_dict[h_name] = val
        if any(v != "" for v in row_dict.values()):
            rows.append(row_dict)

    return {
        "sheets": [{
            "name": "CSV Data",
            "headers": headers,
            "detected_columns": detected_roles,
            "total_rows": len(rows),
            "rows": rows
        }]
    }



def _is_excel_process_running() -> bool:
    """Check if Microsoft Excel is currently running on the system."""
    try:
        import subprocess
        out = subprocess.check_output('tasklist /FI "IMAGENAME eq EXCEL.EXE" /NH', shell=True).decode()
        return "EXCEL.EXE" in out.upper()
    except Exception:
        return False


def _parse_with_excel_com(file_source: Any) -> Optional[Dict[str, Any]]:
    """
    Parses Excel file using Windows Excel COM automation.
    Supports Microsoft Purview Information Protection / RMS sensitivity-labeled files.
    Guarantees user's existing open Excel workbooks are NEVER closed or terminated.
    """
    try:
        import win32com.client
    except ImportError:
        return None

    was_excel_already_running = _is_excel_process_running()

    temp_path = None
    if isinstance(file_source, str) and os.path.exists(file_source):
        file_path = os.path.abspath(file_source)
    else:
        bio = file_source if isinstance(file_source, io.BytesIO) else io.BytesIO(file_source)
        data = bio.getvalue()
        if not data:
            return None
        import tempfile
        tf = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tf.write(data)
        tf.close()
        temp_path = tf.name
        file_path = os.path.abspath(temp_path)

    excel = None
    wb = None
    try:
        import pythoncom
        pythoncom.CoInitialize()
        if was_excel_already_running:
            # Connect to existing session safely without interfering with user windows
            try:
                excel = win32com.client.GetObject(Class="Excel.Application")
            except Exception:
                excel = win32com.client.Dispatch("Excel.Application")
        else:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            excel.ScreenUpdating = False

        wb = excel.Workbooks.Open(file_path, ReadOnly=True)
        sheets = []
        for sheet in wb.Sheets:
            s_name = sheet.Name
            used = sheet.UsedRange
            if not used:
                continue
            vals = used.Value
            if not vals or len(vals) < 2:
                continue
            headers = [str(h or "").strip() for h in vals[0] if str(h or "").strip()]
            roles = detect_column_roles(headers)
            rows = []
            for r_raw in vals[1:]:
                row_dict = {}
                for idx, h_name in enumerate(headers):
                    v = r_raw[idx] if idx < len(r_raw) else ""
                    if v is None:
                        row_dict[h_name] = ""
                    elif hasattr(v, "strftime"):
                        row_dict[h_name] = format_iso_zulu(v)
                    else:
                        row_dict[h_name] = v
                if any(v != "" for v in row_dict.values()):
                    rows.append(row_dict)
            sheets.append({
                "name": s_name,
                "headers": headers,
                "detected_columns": roles,
                "total_rows": len(rows),
                "rows": rows
            })
        return {"sheets": sheets} if sheets else None
    except Exception:
        return None
    finally:
        # 1. Close ONLY the specific temporary workbook that was opened
        if wb:
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                pass
        # 2. ABSOLUTE PROTECTION: Never quit Excel if the user had Excel open!
        if excel:
            if not was_excel_already_running:
                try:
                    excel.Quit()
                except Exception:
                    pass
            del excel
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def parse_telemetry_file(file_source: Any, filename: str = "") -> Dict[str, Any]:
    """
    Parses an uploaded .xlsx or .csv telemetry data file.
    Returns sheets metadata, headers, auto-detected roles, and row lists.
    """
    fn_lower = filename.lower() if filename else ""
    res = None
    if fn_lower.endswith(".csv"):
        res = _parse_csv(file_source)
    else:
        # Try openpyxl first
        try:
            import openpyxl
            res = _parse_with_openpyxl(file_source)
        except ImportError:
            pass
        except Exception as e:
            print(f"openpyxl failed: {e}. Falling back to stdlib zip/xml parser.")

        if res is None:
            # Fallback to stdlib zipfile/xml parser
            try:
                res = _parse_xlsx_stdlib(file_source)
            except Exception:
                pass

        if res is None:
            # Fallback to Windows Excel COM automation (handles RMS / sensitivity-labeled workbooks)
            try:
                res = _parse_with_excel_com(file_source)
            except Exception:
                pass

        if res is None:
            # Fallback to text/csv
            try:
                res = _parse_csv(file_source)
            except Exception as e:
                raise ValueError(f"Could not parse file '{filename}': {str(e)}")

    sheets = res.get("sheets") or []
    sheet_names = [s.get("name") for s in sheets if s.get("name")]
    active_sheet = sheet_names[0] if sheet_names else ""
    detected_columns = sheets[0].get("detected_columns", {}) if sheets else {}
    raw_headers = sheets[0].get("headers", []) if sheets else []
    sample_rows = sheets[0].get("rows", [])[:5] if sheets else []
    total_rows = sum(s.get("total_rows", len(s.get("rows", []))) for s in sheets)

    res["sheet_names"] = sheet_names
    res["active_sheet"] = active_sheet
    res["detected_columns"] = detected_columns
    res["raw_headers"] = raw_headers
    res["sample_rows"] = sample_rows
    res["total_rows"] = total_rows
    return res


def extract_standard_telemetry_row(
    row: Dict[str, Any],
    col_mapping: Dict[str, str],
    sheet_name: str = ""
) -> Dict[str, Any]:
    """
    Converts a raw row dict into standardized telemetry attribute record
    based on the configured column mapping:
    - timestamp
    - tag
    - description
    - value
    - uom
    """
    ts_col = col_mapping.get("timestamp")
    tag_col = col_mapping.get("tag")
    desc_col = col_mapping.get("description")
    val_col = col_mapping.get("value")
    uom_col = col_mapping.get("uom")

    raw_ts = row.get(ts_col) if ts_col else None
    ts_val = format_iso_zulu(raw_ts)

    raw_tag = row.get(tag_col) if tag_col else ""
    tag_val = str(raw_tag).strip() if raw_tag is not None else ""

    raw_desc = row.get(desc_col) if desc_col else ""
    desc_val = str(raw_desc).strip() if raw_desc is not None else ""

    raw_uom = row.get(uom_col) if uom_col else ""
    uom_val = str(raw_uom).strip() if raw_uom is not None else ""

    # Value extraction & numeric cleaning
    val_val = None
    if val_col and val_col in row:
        val_candidate = row.get(val_col)
        if val_candidate is not None:
            if isinstance(val_candidate, (int, float)):
                val_val = val_candidate
            else:
                s_val = str(val_candidate).strip().replace(",", "")
                try:
                    val_val = float(s_val) if "." in s_val else int(s_val)
                except ValueError:
                    val_val = s_val

    # Fallback for value if val_col missed
    if val_val is None:
        for k, v in row.items():
            if "value" in str(k).lower() and v is not None and str(v).strip() != "":
                val_val = v
                break

    # If tag is empty, use sheet_name or description
    if not tag_val:
        tag_val = desc_val or sheet_name or "METER_UPLOAD"

    record = {
        "timestamp": ts_val,
        "RECORD_AT": ts_val,
        "tag": tag_val,
        "description": desc_val,
        "value": val_val,
        "uom": uom_val,
        "quality": "Good",
        "_is_utc8_formatted": True
    }

    # Pass along any additional columns present in the raw row as extra fields
    extra = {}
    known_cols = {ts_col, tag_col, desc_col, val_col, uom_col, "sheet", "meter_tag", "name", "record_at", "recorded_at"}
    for k, v in row.items():
        if k and k not in known_cols and str(k).lower() not in ("sheet", "quality", "limit", "results"):
            k_lower = str(k).lower()
            if "time" in k_lower or "date" in k_lower or k_lower.endswith("_at") or k_lower.startswith("record"):
                if k_lower in ("record_at", "recorded_at"):
                    formatted_v = format_iso_zulu(v, fallback=ts_val)
                else:
                    formatted_v = format_iso_zulu(v, allow_empty=True)
            else:
                formatted_v = v
            if k_lower in ("record_at", "recorded_at") and (formatted_v is None or str(formatted_v).strip() == ""):
                formatted_v = ts_val
            extra[k] = formatted_v
            record[k] = formatted_v

    if extra:
        record["extra_fields"] = extra

    return record


def parse_upload_request_body(body: bytes, content_type: str = "", query_filename: str = "") -> Tuple[bytes, str]:
    """
    Zero-dependency multipart and binary stream parser.
    Extracts raw file bytes and filename without requiring 'python-multipart'.
    Works seamlessly across all Python distributions and portable environments.
    """
    if not body:
        return b"", query_filename or "uploaded_file"

    ct_lower = (content_type or "").lower()

    # Case 1: Direct binary stream (application/octet-stream or spreadsheet mime types)
    if "multipart/form-data" not in ct_lower:
        return body, query_filename or "uploaded_file"

    # Case 2: Multipart form-data
    m = re.search(r'boundary=([^;]+)', content_type, re.IGNORECASE)
    if not m:
        return body, query_filename or "uploaded_file"

    boundary_str = m.group(1).strip('"\' \t')
    delimiter = b'--' + boundary_str.encode('utf-8')
    parts = body.split(delimiter)

    for part in parts:
        if b'filename=' in part:
            header_end = part.find(b'\r\n\r\n')
            sep_len = 4
            if header_end == -1:
                header_end = part.find(b'\n\n')
                sep_len = 2
            if header_end != -1:
                headers = part[:header_end].decode('utf-8', errors='ignore')
                fn_match = re.search(r'filename=["\']?([^"\';\r\n]+)', headers)
                filename = fn_match.group(1).strip('"\'') if fn_match else (query_filename or "uploaded_file")
                file_bytes = part[header_end + sep_len:]
                if file_bytes.endswith(b'\r\n'):
                    file_bytes = file_bytes[:-2]
                elif file_bytes.endswith(b'\n'):
                    file_bytes = file_bytes[:-1]
                return file_bytes, filename

    return body, query_filename or "uploaded_file"
