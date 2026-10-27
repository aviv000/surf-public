"""Merge v4 + n100 data into clean N=100 datasets for analysis.
Run after all experiments complete.
"""
import csv
from pathlib import Path
from collections import defaultdict
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR

OUT = OUTPUTS_DIR / "n100"

def merge_dissociation():
    """Merge v4 judgments (per-001 to per-050) with n100 (per-051 to per-100)."""
    # Load v4, filter to our 100 personas
    v4 = OUTPUTS_DIR / "dissociation_judgments_v4.csv"
    with open(v4) as f:
        v4_rows = list(csv.DictReader(f))

    # Our persona set
    emails = OUTPUTS_DIR / "dissociation_emails_100.csv"
    with open(emails) as f:
        our_tids = set(r["target_id"] for r in csv.DictReader(f))

    v4_filtered = [r for r in v4_rows if r["target_id"] in our_tids]
    print(f"v4: {len(v4_rows)} total, {len(v4_filtered)} matching our 100 personas")

    # Load n100
    n100_rows = []
    n100_path = OUT / "dissociation_n100.csv"
    if n100_path.exists():
        with open(n100_path) as f:
            n100_rows = list(csv.DictReader(f))
    print(f"n100: {len(n100_rows)} rows")

    # Dedup: prefer n100 over v4 for same (tid, pair, model)
    seen = set()
    merged = []
    for r in n100_rows:
        key = (r["target_id"], r["pair"], r["model"])
        seen.add(key)
        merged.append(r)
    for r in v4_filtered:
        key = (r["target_id"], r["pair"], r["model"])
        if key not in seen:
            seen.add(key)
            merged.append(r)

    out_path = OUT / "merged_dissociation.csv"
    fields = ["target_id","pair","var_a","var_b","model","winner","confidence","reasoning","swapped","persona_index"]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(merged)
    print(f"Merged: {len(merged)} judgments -> {out_path}")

    # Per-pair per-model counts
    counts = defaultdict(lambda: defaultdict(int))
    for r in merged:
        counts[r["pair"]][r["model"]] += 1
    for pair in sorted(counts):
        total = sum(counts[pair].values())
        print(f"  {pair}: {total}")

    return merged

def merge_introspection():
    """Merge introspection: existing + n100 non-Gemini + Gemini."""
    existing = OUTPUTS_DIR / "introspection_probe.csv"
    n100 = OUT / "introspection_n100.csv"
    gemini = OUT / "introspection_gemini.csv"

    rows = []
    seen = set()
    for p in [existing, n100, gemini]:
        if not p.exists(): continue
        with open(p) as f:
            for r in csv.DictReader(f):
                key = (r["target_id"], r["email_variant"], r["model"])
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
    out_path = OUT / "merged_introspection.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["target_id","model","email_variant","content_score","justification"])
        w.writeheader()
        w.writerows(rows)
    print(f"Introspection merged: {len(rows)} ratings -> {out_path}")
    return rows

def merge_doseresponse():
    """Merge dose-response: existing + n100 non-Gemini + Gemini."""
    existing = OUTPUTS_DIR / "doseresponse_judgments.csv"
    n100 = OUT / "doseresponse_n100.csv"
    gemini = OUT / "doseresponse_gemini.csv"

    rows = []
    seen = set()
    for p in [existing, n100, gemini]:
        if not p.exists(): continue
        with open(p) as f:
            for r in csv.DictReader(f):
                key = (r["target_id"], r["ratio"], r["model"])
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
    out_path = OUT / "merged_doseresponse.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["target_id","ratio","model","winner","long_wc","short_wc"])
        w.writeheader()
        w.writerows(rows)
    print(f"Dose-response merged: {len(rows)} judgments -> {out_path}")
    return rows

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true")
    p.add_argument("--dissoc", action="store_true")
    p.add_argument("--intro", action="store_true")
    p.add_argument("--dr", action="store_true")
    args = p.parse_args()
    if args.all or args.dissoc: merge_dissociation()
    if args.all or args.intro: merge_introspection()
    if args.all or args.dr: merge_doseresponse()
