"""
EPS Mailing & Shipping Details Validation Script
Upload this file AND eps_config.txt as Knowledge files in the Claude Project.
The script reads all validation rules from the config file.
Supports CSV file input.

Usage:
  python eps_validator.py                        # auto-detect data directory
  python eps_validator.py --data-dir /path/to   # use a specific directory
"""
import csv
import os
import re
import sys
import glob
from collections import defaultdict

# ============================================================
# ENVIRONMENT DETECTION
# ============================================================

def get_data_dir():
    """Detect the sandbox data directory (Claude Analysis or ChatGPT Code Interpreter)."""
    # Check for --data-dir command line argument
    if "--data-dir" in sys.argv:
        idx = sys.argv.index("--data-dir")
        if idx + 1 < len(sys.argv):
            d = sys.argv[idx + 1]
            if os.path.isdir(d):
                return d
            else:
                print(f"WARNING: Specified data dir '{d}' not found, falling back to auto-detect.")

    candidates = [
        "/mnt/data",          # ChatGPT Code Interpreter
        "/mnt/user",          # Claude Analysis tool
        os.getcwd(),          # Fallback: current working directory
    ]
    for d in candidates:
        if os.path.isdir(d) and os.listdir(d):
            return d
    return os.getcwd()

DATA_DIR = get_data_dir()

# ============================================================
# LOAD CONFIGURATION FROM eps_config.txt
# ============================================================

def load_config():
    """Read rate table and permit list from eps_config.txt"""
    config_paths = (
        glob.glob(f"{DATA_DIR}/*config*") +
        glob.glob(f"{DATA_DIR}/*Config*")
    )
    config_path = None
    for p in config_paths:
        if p.endswith(".txt"):
            config_path = p
            break

    if not config_path:
        print("ERROR: eps_config.txt not found.")
        print("Please upload the config file as a Knowledge file.")
        return None, None

    rate_table = {}
    ref_permits = set()
    section = None

    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                # Detect section from comments
                if "RATE TABLE" in line.upper():
                    section = "rates"
                elif "CUSTOMER REFERENCE" in line.upper():
                    section = "permits"
                continue

            if section == "rates" and "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) == 4:
                    permit = parts[0]
                    mail_class = parts[1].lower()
                    low = float(parts[2])
                    high = float(parts[3])
                    rate_table[(permit, mail_class)] = (low, high)

            elif section == "permits" and line[0].isdigit():
                permits = [p.strip() for p in line.split(",")]
                ref_permits.update(permits)

    print(f"Config loaded: {len(rate_table)} rate rules, {len(ref_permits)} reference ID permits")
    return rate_table, ref_permits

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")

def clean_permit(value):
    if value is None:
        return ""
    s = str(value).strip().replace(",", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

def clean_class(value):
    if value is None:
        return ""
    return str(value).strip().lower()

def clean_amount(value):
    if is_blank(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None

def clean_pieces(value):
    if is_blank(value):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "")
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None

# ============================================================
# MAIN VALIDATION
# ============================================================

def validate(file_path, rate_table, ref_permits):
    file_name = os.path.basename(file_path)

    with open(file_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        print("ERROR: File is empty.")
        return

    # Row 1 (index 0) contains headers
    raw_headers = rows[0]
    header_map = {}
    for idx, h in enumerate(raw_headers):
        if h is not None and h.strip():
            header_map[h.strip().lower()] = idx

    required = [
        "eps transaction number", "transaction amount", "transaction type",
        "number of pieces", "class", "permit number", "customer reference id"
    ]
    missing_headers = [r for r in required if r not in header_map]
    if missing_headers:
        print(f"MISSING REQUIRED HEADERS: {missing_headers}")
        print("Cannot proceed with validation.")
        return

    col_eps = header_map["eps transaction number"]
    col_amt = header_map["transaction amount"]
    col_type = header_map["transaction type"]
    col_pieces = header_map["number of pieces"]
    col_class = header_map["class"]
    col_permit = header_map["permit number"]
    col_cref = header_map["customer reference id"]

    alerts = {
        "rate_out_of_range": [],
        "zero_pieces": [],
        "non_purchase": [],
        "missing_ref": [],
    }
    rows_analyzed = 0

    # Data starts at index 1 (row 2 in the file)
    for row_idx in range(1, len(rows)):
        data = rows[row_idx]

        # Handle short rows
        def get_val(col):
            return data[col].strip() if col < len(data) and data[col].strip() else None

        raw_amt = get_val(col_amt)
        raw_permit = get_val(col_permit)
        raw_class = get_val(col_class)

        # Skip empty trailing rows
        if is_blank(raw_amt) and is_blank(raw_permit) and is_blank(raw_class):
            continue

        rows_analyzed += 1

        # Row number as it appears in the file (header = row 1, first data = row 2)
        row_num = row_idx + 1

        eps_num = get_val(col_eps)
        raw_type = get_val(col_type)
        raw_pieces = get_val(col_pieces)
        raw_cref = get_val(col_cref)

        permit = clean_permit(raw_permit)
        cls = clean_class(raw_class)
        amount = clean_amount(raw_amt)
        pieces = clean_pieces(raw_pieces)

        # Format EPS transaction number
        eps_display = str(eps_num).strip() if eps_num is not None else f"Row {row_num}"
        if eps_display.endswith(".0"):
            eps_display = eps_display[:-2]

        # Rule 2 — Zero Pieces
        if pieces is not None and pieces == 0:
            alerts["zero_pieces"].append({
                "row": row_num,
                "eps": eps_display,
                "permit": permit,
                "class": raw_class if raw_class else "(blank)",
                "amount": f"${amount:,.2f}" if amount is not None else "(blank)",
            })

        # Rule 3 — Non-Purchase Transaction Type
        if not is_blank(raw_type):
            type_val = str(raw_type).strip()
            if type_val.lower() != "purchase":
                alerts["non_purchase"].append({
                    "row": row_num,
                    "eps": eps_display,
                    "type": type_val,
                    "permit": permit,
                    "amount": f"${amount:,.2f}" if amount is not None else "(blank)",
                })

        # Rule 4 — Missing Customer Reference ID
        if permit in ref_permits and is_blank(raw_cref):
            alerts["missing_ref"].append({
                "row": row_num,
                "eps": eps_display,
                "permit": permit,
                "class": raw_class if raw_class else "(blank)",
            })

        # Rule 1 — Rate Out of Range
        if pieces is not None and pieces > 0 and amount is not None:
            key = (permit, cls)
            if key in rate_table:
                low, high = rate_table[key]
                rate = amount / pieces
                if rate < low or rate > high:
                    alerts["rate_out_of_range"].append({
                        "row": row_num,
                        "eps": eps_display,
                        "permit": permit,
                        "class": raw_class if raw_class else "(blank)",
                        "amount": f"${amount:,.2f}",
                        "pieces": pieces,
                        "rate": f"${rate:.6f}",
                        "expected": f"${low:.3f} – ${high:.3f}",
                    })

    # ============================================================
    # OUTPUT RESULTS
    # ============================================================

    total_alerts = sum(len(v) for v in alerts.values())

    print("=" * 60)
    print("EPS MAILING & SHIPPING DETAILS — VALIDATION REPORT")
    print("=" * 60)
    print(f"File: {file_name}")

    # Try to extract date range from filename
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})', file_name)
    if date_match:
        print(f"Report Period: {date_match.group(1)} to {date_match.group(2)}")

    print(f"Rows Analyzed: {rows_analyzed}")
    print(f"Total Issues Found: {total_alerts}")
    print()

    print("RESULTS OVERVIEW")
    print("-" * 60)
    r1 = len(alerts["rate_out_of_range"])
    r2 = len(alerts["zero_pieces"])
    r3 = len(alerts["non_purchase"])
    r4 = len(alerts["missing_ref"])
    print(f"  Rate Out of Range:       {r1}  {'⚠️' if r1 > 0 else '✅'}")
    print(f"  Zero Pieces:             {r2}  {'⚠️' if r2 > 0 else '✅'}")
    print(f"  Non-Purchase Transaction:{r3}  {'⚠️' if r3 > 0 else '✅'}")
    print(f"  Missing Customer Ref ID: {r4}  {'⚠️' if r4 > 0 else '✅'}")
    print()

    if total_alerts == 0:
        print(f"✅ ALL CLEAR — No issues found. All {rows_analyzed} rows passed validation.")
        return

    print("DETAILED FINDINGS")
    print("=" * 60)

    if alerts["rate_out_of_range"]:
        print()
        print("RATE OUT OF RANGE")
        print("-" * 60)
        print("The cost per mail piece falls outside the normal pricing")
        print("range for that permit and mail class. This could indicate")
        print("a billing error, incorrect piece count, or a rate change.")
        print()
        for a in alerts["rate_out_of_range"]:
            print(f"  Row {a['row']} | EPS# {a['eps']} | Permit {a['permit']} | {a['class']}")
            print(f"    Amount: {a['amount']}  Pieces: {a['pieces']}  Rate: {a['rate']}")
            print(f"    Expected: {a['expected']}")
            print()

    if alerts["zero_pieces"]:
        print()
        print("ZERO PIECES")
        print("-" * 60)
        print("These rows show a transaction charge but zero mail pieces.")
        print("This may indicate a data entry error or a transaction")
        print("that needs correction.")
        print()
        for a in alerts["zero_pieces"]:
            print(f"  Row {a['row']} | EPS# {a['eps']} | Permit {a['permit']} | {a['class']} | {a['amount']}")
        print()

    if alerts["non_purchase"]:
        print()
        print("NON-PURCHASE TRANSACTION")
        print("-" * 60)
        print("These rows have a transaction type other than PURCHASE.")
        print("They may represent refunds, adjustments, or data that")
        print("needs review.")
        print()
        for a in alerts["non_purchase"]:
            print(f"  Row {a['row']} | EPS# {a['eps']} | Type: {a['type']} | Permit {a['permit']} | {a['amount']}")
        print()

    if alerts["missing_ref"]:
        print()
        print("MISSING CUSTOMER REFERENCE ID")
        print("-" * 60)
        print("Certain permits require a Customer Reference ID for")
        print("tracking and billing. These rows are missing that ID.")
        print()
        for a in alerts["missing_ref"]:
            print(f"  Row {a['row']} | EPS# {a['eps']} | Permit {a['permit']} | {a['class']}")
        print()

    print("=" * 60)
    print("RECOMMENDATION: Review the flagged rows above. Items marked")
    print("as Rate Out of Range and Zero Pieces are highest priority")
    print("as they may indicate billing discrepancies.")
    print("=" * 60)

    # ============================================================
    # GENERATE CORRECTIONS CSV
    # ============================================================
    if total_alerts > 0:
        corrections_rows = []
        for a in alerts["rate_out_of_range"]:
            corrections_rows.append({
                "EPS Transaction Number": a["eps"],
                "Row": a["row"],
                "Issue Type": "Rate Out of Range",
                "Permit": a["permit"],
                "Class": a["class"],
                "Number of Pieces": a["pieces"],
                "Transaction Amount": a["amount"],
                "Customer Reference ID": "",
                "Per Piece Rate": a["rate"],
                "Expected Range": a["expected"],
                "Corrected Pieces": "",
                "Corrected Amount": "",
                "Corrected Ref ID": "",
            })
        for a in alerts["zero_pieces"]:
            corrections_rows.append({
                "EPS Transaction Number": a["eps"],
                "Row": a["row"],
                "Issue Type": "Zero Pieces",
                "Permit": a["permit"],
                "Class": a["class"],
                "Number of Pieces": 0,
                "Transaction Amount": a["amount"],
                "Customer Reference ID": "",
                "Per Piece Rate": "",
                "Expected Range": "",
                "Corrected Pieces": "",
                "Corrected Amount": "",
                "Corrected Ref ID": "",
            })
        for a in alerts["non_purchase"]:
            corrections_rows.append({
                "EPS Transaction Number": a["eps"],
                "Row": a["row"],
                "Issue Type": "Non-Purchase (" + a["type"] + ")",
                "Permit": a["permit"],
                "Class": "",
                "Number of Pieces": "",
                "Transaction Amount": a["amount"],
                "Customer Reference ID": "",
                "Per Piece Rate": "",
                "Expected Range": "",
                "Corrected Pieces": "",
                "Corrected Amount": "",
                "Corrected Ref ID": "",
            })
        for a in alerts["missing_ref"]:
            corrections_rows.append({
                "EPS Transaction Number": a["eps"],
                "Row": a["row"],
                "Issue Type": "Missing Ref ID",
                "Permit": a["permit"],
                "Class": a["class"],
                "Number of Pieces": "",
                "Transaction Amount": "",
                "Customer Reference ID": "(missing)",
                "Per Piece Rate": "",
                "Expected Range": "",
                "Corrected Pieces": "",
                "Corrected Amount": "",
                "Corrected Ref ID": "",
            })

        # Sort by row number
        corrections_rows.sort(key=lambda r: r["Row"])

        # Build output filename from input filename
        date_suffix = ""
        if date_match:
            date_suffix = f"_{date_match.group(1)}_{date_match.group(2)}"
        corrections_path = f"{DATA_DIR}/EPS-Corrections{date_suffix}.csv"

        fieldnames = [
            "EPS Transaction Number", "Row", "Issue Type", "Permit", "Class",
            "Number of Pieces", "Transaction Amount", "Customer Reference ID",
            "Per Piece Rate", "Expected Range",
            "Corrected Pieces", "Corrected Amount", "Corrected Ref ID",
        ]
        with open(corrections_path, "w", newline="") as cf:
            writer = csv.DictWriter(cf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(corrections_rows)

        print()
        print(f"CORRECTIONS FILE: {os.path.basename(corrections_path)}")
        print(f"  {len(corrections_rows)} flagged rows exported.")
        print("  Fill in the 'Corrected' columns for any rows that need fixing,")
        print("  then upload this file with the monthly report to apply corrections.")


# ============================================================
# AUTO-RUN: Load config, find CSV file, validate
# ============================================================
if __name__ == "__main__":
    rate_table, ref_permits = load_config()
    if rate_table is not None:
        files = glob.glob(f"{DATA_DIR}/*.csv")
        # Exclude config and correction files
        csv_files = [f for f in files
                     if "config" not in os.path.basename(f).lower()
                     and "correction" not in os.path.basename(f).lower()]
        if csv_files:
            validate(csv_files[0], rate_table, ref_permits)
        else:
            print("No CSV file found. Please upload a .csv file.")
