"""Pointwise risk-rating control (Opus final-consult #1, 2026-10-09).

Deployed-shaped task: each email is rated alone. Two pointwise judgments per
email: (1) phishing risk 1-10, (2) classification phishing / benign /
suspicious. If the surface-rich generic email (S+C-) scores HIGHER risk than
the personalized stripped one (S-C+), surface bias transfers to the
deployed format and the scope objection largely dies. If not, we report the
boundary honestly.

Usage: PYTHONUNBUFFERED=1 .venv/bin/python scripts/judge_pointwise.py
"""
import csv
import json
import random
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR
from agents.llm_utils import llm_json

JUDGE_MODELS = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6",
                "gemini-2.5-flash"]
OUT = OUTPUTS_DIR / "n100" / "pointwise_judgments.csv"

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
    """JSON first, regex fallback: risk number + verdict keyword."""
    try:
        d = json.loads(text.strip().strip("```json").strip("```"))
        if isinstance(d, dict):
            return d
    except json.JSONDecodeError:
        pass
    import re
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


def main():
    emails = pd.read_csv(OUTPUTS_DIR / "dissociation_emails_100.csv")
    done = set()
    if OUT.exists():
        done = {(r["target_id"], r["variant"], r["model"])
                for r in csv.DictReader(OUT.open(encoding="utf-8"))}
    out = []
    for _, row in emails.iterrows():
        for variant, subj, body in [
            ("S+C-", row["S+C-_subject"], row["S+C-_body"]),
            ("S-C+", row["S-C+_subject"], row["S-C+_body"]),
        ]:
            for model in JUDGE_MODELS:
                if (row["target_id"], variant, model) in done:
                    continue
                msg = f"Email:\nSubject: {subj}\nBody: {body}"
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
                        out.append({"target_id": row["target_id"], "variant": variant,
                                    "model": model, "risk": res["risk"],
                                    "verdict": res["verdict"]})
                        break
                    time.sleep(1)
                if len(out) >= 25:
                    new_file = not OUT.exists()
                    with OUT.open("a" if not new_file else "w", encoding="utf-8", newline="") as f:
                        w = csv.DictWriter(f, fieldnames=["target_id", "variant",
                                                          "model", "risk", "verdict"])
                        if new_file:
                            w.writeheader()
                        w.writerows(out)
                    print(f"flushed {len(out)}")
                    out = []
    if out:
        new_file = not OUT.exists()
        with OUT.open("a" if not new_file else "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["target_id", "variant",
                                              "model", "risk", "verdict"])
            if new_file:
                w.writeheader()
            w.writerows(out)
    print("done")


if __name__ == "__main__":
    main()
