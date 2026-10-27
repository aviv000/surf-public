#!/usr/bin/env python
"""Pointwise controls (DeepSeek pass 5): context + entity ablation.

Part C (context): re-judge the pointwise cells (S+C-, S-C+) WITH the
recipient profile in the prompt - does context restore pointwise
detection, not just pairwise ranking?
Part A (ablation): judge the entity-stripped S+C- emails pointwise -
does removing entities change the pointwise verdict/risk?

Both checkpointed and resumable; same judge prompt and parsing as the
original pointwise run.

Usage: .venv/bin/python scripts/pointwise_controls.py --part C|A
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR  # noqa: E402

JUDGE_MODELS = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6",
                "gemini-2.5-flash"]
N100 = OUTPUTS_DIR / "n100"
OUT_C = N100 / "pointwise_context_judgments.csv"
OUT_A = N100 / "pointwise_ablation_judgments.csv"

SYSTEM = """You are a phishing triage component in an email security gateway.
Rate each email on its own. Return ONLY JSON:
{"risk": <int 1-10>, "verdict": "phishing" | "benign" | "suspicious",
"reasoning": "..."}"""


def _gemini(user_msg):
    import google.genai as genai
    from google.genai.types import HttpOptions
    from config import GOOGLE_API_KEY
    if not GOOGLE_API_KEY:
        return None
    client = genai.Client(api_key=GOOGLE_API_KEY,
                          http_options=HttpOptions(timeout=60000))
    resp = client.models.generate_content(
        model="gemini-2.5-flash", contents=SYSTEM + "\n\n" + user_msg)
    if resp and resp.text:
        return _parse(resp.text)
    return None


def _parse(text):
    try:
        d = json.loads(text.strip().strip("```json").strip("```"))
        if isinstance(d, dict):
            return d
    except json.JSONDecodeError:
        pass
    d = {}
    m = re.search(r"[\"']risk[\"']\s*[:=]\s*(\d{1,2})", text, re.I)
    if not m:
        m = re.search(r"risk[^\d]{0,8}(\d{1,2})", text, re.I)
    if m:
        d["risk"] = int(m.group(1))
    low = text.lower()
    if re.search(r"\bphishing\b(?!.*not phishing)", low):
        d["verdict"] = "phishing"
    elif re.search(r"\bbenign\b", low):
        d["verdict"] = "benign"
    elif re.search(r"\bsuspicious\b", low):
        d["verdict"] = "suspicious"
    else:
        d["verdict"] = "suspicious"
    return d or None


def judge_one(model, msg):
    for attempt in range(2):
        try:
            if model == "gemini-2.5-flash":
                res = _gemini(msg)
            else:
                from agents.llm_utils import llm_call
                raw = llm_call(SYSTEM, msg, model=model, max_tokens=256)
                res = _parse(raw) if raw else None
        except Exception:
            res = None
        if res and isinstance(res.get("risk"), int) and res.get("verdict"):
            return res
        time.sleep(1)
    return None


def load_done(path, keyfunc):
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {keyfunc(r) for r in csv.DictReader(f)}


def append_rows(path, fieldnames, rows):
    new = not path.exists()
    with path.open("a" if not new else "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if new:
            w.writeheader()
        w.writerows(rows)


def part_context():
    emails = pd.read_csv(OUTPUTS_DIR / "dissociation_emails_100.csv")
    profiles = pd.read_csv(N100 / "persona_profiles.csv")
    prof = dict(zip(profiles["target_id"], profiles["profile"])) \
        if "profile" in profiles.columns else {}
    done = load_done(OUT_C, lambda r: (r["target_id"], r["variant"], r["model"]))
    todo = [(row["target_id"], v, subj, body, m)
            for _, row in emails.iterrows()
            for v, subj, body in [("S+C-", row["S+C-_subject"], row["S+C-_body"]),
                                  ("S-C+", row["S-C+_subject"], row["S-C+_body"])]
            for m in JUDGE_MODELS
            if (row["target_id"], v, m) not in done]
    print(f"part C: {len(done)} done, {len(todo)} todo", flush=True)
    buf, count = [], 0
    for tid, variant, subj, body, model in todo:
        profile = prof.get(tid, "")
        msg = (f"Recipient profile: {profile}\n\n"
               f"Email:\nSubject: {subj}\nBody: {body}")
        res = judge_one(model, msg)
        if res:
            buf.append({"target_id": tid, "variant": variant, "model": model,
                        "risk": res["risk"], "verdict": res["verdict"]})
            count += 1
        if len(buf) >= 25:
            append_rows(OUT_C, ["target_id", "variant", "model", "risk", "verdict"], buf)
            print(f"part C: +{len(buf)} -> {count} completed", flush=True)
            buf = []
    if buf:
        append_rows(OUT_C, ["target_id", "variant", "model", "risk", "verdict"], buf)
        print(f"part C: +{len(buf)} -> {count} completed", flush=True)
    print("part C done", flush=True)


def part_ablation():
    strip = pd.read_csv(N100 / "entity_ablation_emails.csv")
    done = load_done(OUT_A, lambda r: (r["target_id"], r["model"]))
    todo = [(row["target_id"], row["noentity_subject"], row["noentity_body"], m)
            for _, row in strip.iterrows() for m in JUDGE_MODELS
            if (row["target_id"], m) not in done]
    print(f"part A: {len(done)} done, {len(todo)} todo", flush=True)
    buf, count = [], 0
    for tid, subj, body, model in todo:
        msg = f"Email:\nSubject: {subj}\nBody: {body}"
        res = judge_one(model, msg)
        if res:
            buf.append({"target_id": tid, "model": model,
                        "risk": res["risk"], "verdict": res["verdict"]})
            count += 1
        if len(buf) >= 25:
            append_rows(OUT_A, ["target_id", "model", "risk", "verdict"], buf)
            print(f"part A: +{len(buf)} -> {count} completed", flush=True)
            buf = []
    if buf:
        append_rows(OUT_A, ["target_id", "model", "risk", "verdict"], buf)
        print(f"part A: +{len(buf)} -> {count} completed", flush=True)
    print("part A done", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["C", "A"])
    args = ap.parse_args()
    part_context() if args.part == "C" else part_ablation()
