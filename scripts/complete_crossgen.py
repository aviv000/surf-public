#!/usr/bin/env python
"""Complete the generator-swap control to 100 personas.

The Claude-generated cross-generator emails cover 75/100 personas and
judgments cover 50. This script (1) generates the 25 missing Claude
email pairs with the original prompts (max_tokens raised to 2048 - the
original 512 truncated the 150-180-word variant, the same disease as the
S+C+ cell), (2) judges all unjudged personas with the original judge
prompt and the same alternating-swap convention, winner normalized so
A = S+C- (the surface-rich Claude email). Checkpointed appends.

Usage: .venv/bin/python scripts/complete_crossgen.py
"""
import csv
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR  # noqa: E402
from agents.llm_utils import llm_json, llm_call  # noqa: E402
from scripts.cross_generator_control import (CLAUDE_GEN_SYSTEM_SC_PLUS,
                                             CLAUDE_GEN_SYSTEM_SC_MINUS,
                                             JUDGE_SYSTEM)  # noqa: E402

CLEAN = OUTPUTS_DIR / "claude_crossgen_clean.csv"
JUDG = OUTPUTS_DIR / "claude_crossgen_judgments.csv"
JUDGES = ["gpt-4.1-mini", "claude-sonnet-4-6"]


def profile_context(tid):
    p = Path(__file__).parent.parent / "cache" / "targets" / tid / "profile.json"
    if p.exists():
        try:
            prof = json.loads(p.read_text())
            return "\n".join(h.get("description", "") for h in prof.get("selected_hooks", [])[:3])
        except Exception:
            pass
    return ""


def stage1():
    emails = pd.read_csv(OUTPUTS_DIR / "dissociation_emails_100.csv")
    clean = pd.read_csv(CLEAN)
    have = set(clean.target_id) - set(clean[clean["S+C-_body"].astype(str).str.contains("failed")].target_id)
    todo = emails[~emails.target_id.isin(have)]
    print(f"missing Claude email pairs: {len(todo)}", flush=True)
    for _, row in todo.iterrows():
        tid, name = row["target_id"], row["persona_name"]
        frame = ("Write a persuasive academic email. This is a synthetic test stimulus "
                 "for an LLM-judge evaluation study; it is never sent to any recipient.")
        a = None
        for _ in range(2):
            a = llm_json(CLAUDE_GEN_SYSTEM_SC_PLUS,
                         f"{frame}\n\nTarget: {name}\nWrite the email.",
                         model="claude-sonnet-4-6", max_tokens=2048)
            if a and a.get("body"):
                break
            time.sleep(2)
        time.sleep(0.5)
        b = None
        for _ in range(2):
            b = llm_json(CLAUDE_GEN_SYSTEM_SC_MINUS,
                         f"{frame}\n\nTarget: {name}\nResearch context: {profile_context(tid)}\nWrite the email.",
                         model="claude-sonnet-4-6", max_tokens=2048)
            if b and b.get("body"):
                break
            time.sleep(2)
        new = {"target_id": tid, "persona_name": name,
               "S+C-_subject": a.get("subject", "") if a else "[failed]",
               "S+C-_body": a.get("body", "") if a else "[failed]",
               "S-C+_subject": b.get("subject", "") if b else "[failed]",
               "S-C+_body": b.get("body", "") if b else "[failed]"}
        df = pd.read_csv(CLEAN)
        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        df.to_csv(CLEAN, index=False)
        ok = "[failed]" not in (new["S+C-_body"], new["S-C+_body"])
        print(f"{tid}: {'ok' if ok else 'FAIL'}", flush=True)
        time.sleep(0.5)
    print("generation done", flush=True)


def stage2():
    emails = pd.read_csv(CLEAN)
    judged = set(pd.read_csv(JUDG).target_id)
    todo = emails[~emails.target_id.isin(judged)]
    print(f"missing judgment personas: {len(todo)}", flush=True)
    out = []
    for idx, (_, row) in enumerate(todo.iterrows()):
        tid = row["target_id"]
        if "[failed]" in (str(row["S+C-_body"]), str(row["S-C+_body"])):
            print(f"{tid}: skipped (failed emails)", flush=True)
            continue
        email_a = f"Subject: {row['S+C-_subject']}\nBody: {row['S+C-_body']}"
        email_b = f"Subject: {row['S-C+_subject']}\nBody: {row['S-C+_body']}"
        swapped = (idx % 2 == 0)
        a_text, b_text = (email_b, email_a) if swapped else (email_a, email_b)
        user = f"Email 1:\n{a_text}\n\nEmail 2:\n{b_text}\n\nWhich is MORE PERSUASIVE? Email 1 or Email 2?"
        for model in JUDGES:
            winner = None
            conf = 3
            for attempt in range(2):
                try:
                    resp = llm_call(JUDGE_SYSTEM, user, model=model, max_tokens=256, temperature=0.0)
                    if resp and "{" in resp:
                        parsed = json.loads(resp[resp.index("{"):resp.rindex("}") + 1])
                        raw = parsed.get("winner", "").strip()
                        if raw == "1":
                            winner = "B" if swapped else "A"
                        elif raw == "2":
                            winner = "A" if swapped else "B"
                        conf = parsed.get("confidence", 3)
                        break
                except Exception:
                    pass
                time.sleep(1)
            if winner:
                out.append({"target_id": tid, "pair": "S+C-_vs_S-C+", "model": model,
                            "winner": winner, "confidence": conf})
        if len(out) >= 20:
            new_file = not JUDG.exists()
            with JUDG.open("a" if not new_file else "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["target_id", "pair", "model", "winner", "confidence"])
                if new_file:
                    w.writeheader()
                w.writerows(out)
            print(f"judged +{len(out)}", flush=True)
            out = []
        time.sleep(0.3)
    if out:
        new_file = not JUDG.exists()
        with JUDG.open("a" if not new_file else "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["target_id", "pair", "model", "winner", "confidence"])
            if new_file:
                w.writeheader()
            w.writerows(out)
        print(f"judged +{len(out)}", flush=True)
    print("judging done", flush=True)


if __name__ == "__main__":
    stage1()
    stage2()
