#!/usr/bin/env python
"""Regenerate the 45 missing S+C+ variants (truncated in the original run).

Root cause of the original 45 failures: generate_variant ran with
max_tokens=1024; S+C+ is the longest variant (~170 words + 14 entities),
so outputs truncated -> unparseable JSON -> empty cells for per-006..050.
This script regenerates ONLY the empty S+C+ cells with max_tokens=2048,
updating dissociation_emails_100.csv in place (checkpointed per row).

Usage: .venv/bin/python scripts/regenerate_sc_plus.py
"""
import csv
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR, DEFAULT_LLM  # noqa: E402
from agents.llm_utils import llm_json  # noqa: E402
from scripts.generate_dissociation_emails import _sc_plus_prompt, _get_persona_context  # noqa: E402

EMAILS_100 = OUTPUTS_DIR / "dissociation_emails_100.csv"


def load_bases():
    """Same base-email selection as generate_dissociation_emails.load_personas."""
    emails = {}
    with open(OUTPUTS_DIR / "within_condition_emails.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["target_id"]
            level = int(row.get("hook_level", 0))
            body = row.get("email_body", "")
            if body and len(body) > 10 and row.get("error", "") != "True":
                emails.setdefault(tid, {})[level] = {
                    "subject": row["email_subject"],
                    "body": body,
                }
    bases = {}
    for tid, entry in emails.items():
        base = entry.get(3) or entry.get(1) or entry.get(5)
        if base:
            bases[tid] = base
    return bases


def main():
    df = pd.read_csv(EMAILS_100)
    bases = load_bases()
    missing = df[df["S+C+_body"].isna() | (df["S+C+_body"].astype(str).str.strip() == "")]
    print(f"missing S+C+ cells: {len(missing)}", flush=True)

    fixed = 0
    for _, row in missing.iterrows():
        tid = row["target_id"]
        base = bases.get(tid)
        if base is None:
            print(f"{tid}: no base email found, skip", flush=True)
            continue
        persona = {"target_id": tid, "persona_name": row["persona_name"],
                   "base_subject": base["subject"], "base_body": base["body"]}
        system, user = _sc_plus_prompt(persona)
        res = None
        for attempt in range(3):
            try:
                res = llm_json(system, user, model=DEFAULT_LLM, max_tokens=2048)
            except Exception:
                res = None
            if res and res.get("subject") and res.get("body"):
                break
            time.sleep(1)
        if res and res.get("subject") and res.get("body"):
            df.loc[df["target_id"] == tid, "S+C+_subject"] = res["subject"]
            df.loc[df["target_id"] == tid, "S+C+_body"] = res["body"]
            fixed += 1
            df.to_csv(EMAILS_100, index=False)
            print(f"{tid}: regenerated ({len(res['body'].split())}w) [{fixed}/{len(missing)}]", flush=True)
        else:
            print(f"{tid}: STILL FAILED", flush=True)
    print(f"done: {fixed}/{len(missing)} regenerated", flush=True)


if __name__ == "__main__":
    main()
