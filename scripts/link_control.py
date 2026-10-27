"""Matched-link control (rounds 28/29 + ChatGPT v11 ask): insert ONE
neutral fictional-domain link into the S- cells and re-judge pointwise.

Falsification logic: if link-bearing S-C+ is still missed at ~90% while
link-bearing S+C- is flagged, link presence does not drive the miss; if
flag rates jump, the S+/S- pointwise gap is partly a link confound.
Either way the paper reports the result honestly.

Links are fictional domains (never resolvable), one link per email,
appended to the body; the S+ cells carry 18-20 links, so this matches
link PRESENCE, not density (disclosed if written into the paper).

Usage: .venv/bin/python scripts/link_control.py
Checkpointed and resumable.
Outputs: outputs/n100/link_control_emails.csv,
         outputs/n100/link_control_judgments.csv
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
OUT_E = N100 / "link_control_emails.csv"
OUT_J = N100 / "link_control_judgments.csv"

LINK_SCP = "More details about my current work: https://research-portal-updates.org/project."
LINK_SCM = "Registration and schedule: https://event-portal-updates.org/register."
LINK_BEN = "Registration and schedule: https://event-portal-updates.org/register."

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


def build_emails():
    src = pd.read_csv(OUTPUTS_DIR / "dissociation_emails_100.csv")
    rows = []
    for _, r in src.iterrows():
        rows.append({"target_id": r["target_id"],
                     "variant": "S-C+link",
                     "subject": r["S-C+_subject"],
                     "body": str(r["S-C+_body"]).rstrip() + "\n\n" + LINK_SCP})
        rows.append({"target_id": r["target_id"],
                     "variant": "S-C-link",
                     "subject": r["S-C-_subject"],
                     "body": str(r["S-C-_body"]).rstrip() + "\n\n" + LINK_SCM})
    pd.DataFrame(rows).to_csv(OUT_E, index=False)
    print(f"built {len(rows)} link-bearing emails -> {OUT_E}", flush=True)


def run_judgments():
    emails = pd.read_csv(OUT_E)
    done = load_done(OUT_J, lambda r: (r["target_id"], r["variant"], r["model"]))
    todo = [(row["target_id"], row["variant"], row["subject"], row["body"], m)
            for _, row in emails.iterrows()
            for m in JUDGE_MODELS
            if (row["target_id"], row["variant"], m) not in done]
    print(f"link control: {len(done)} done, {len(todo)} todo", flush=True)
    buf, count = [], 0
    for tid, variant, subj, body, model in todo:
        msg = f"Email:\nSubject: {subj}\nBody: {body}"
        res = judge_one(model, msg)
        if res:
            buf.append({"target_id": tid, "variant": variant, "model": model,
                        "risk": res["risk"], "verdict": res["verdict"]})
            count += 1
        if len(buf) >= 25:
            append_rows(OUT_J, ["target_id", "variant", "model", "risk", "verdict"], buf)
            print(f"link control: +{len(buf)} -> {count} completed", flush=True)
            buf = []
    if buf:
        append_rows(OUT_J, ["target_id", "variant", "model", "risk", "verdict"], buf)
        print(f"link control: +{len(buf)} -> {count} completed", flush=True)
    print("link control done", flush=True)


def run_benign():
    """Benign-link control: the same link appended to the 100 matched
    legitimate plain emails, re-judged pointwise (400 calls)."""
    OUT_BE = N100 / "benign_link_emails.csv"
    OUT_BJ = N100 / "benign_link_judgments.csv"
    if not OUT_BE.exists():
        src = pd.read_csv(N100 / "benign_emails.csv")
        rows = [{"target_id": r["target_id"],
                 "subject": r["subject"],
                 "body": str(r["body"]).rstrip() + "\n\n" + LINK_BEN}
                for _, r in src.iterrows()]
        pd.DataFrame(rows).to_csv(OUT_BE, index=False)
        print(f"built {len(rows)} benign-link emails -> {OUT_BE}", flush=True)
    emails = pd.read_csv(OUT_BE)
    done = load_done(OUT_BJ, lambda r: (r["target_id"], r["model"]))
    todo = [(row["target_id"], row["subject"], row["body"], m)
            for _, row in emails.iterrows()
            for m in JUDGE_MODELS
            if (row["target_id"], m) not in done]
    print(f"benign link: {len(done)} done, {len(todo)} todo", flush=True)
    buf, count = [], 0
    for tid, subj, body, model in todo:
        msg = f"Email:\nSubject: {subj}\nBody: {body}"
        res = judge_one(model, msg)
        if res:
            buf.append({"target_id": tid, "model": model,
                        "risk": res["risk"], "verdict": res["verdict"]})
            count += 1
        if len(buf) >= 25:
            append_rows(OUT_BJ, ["target_id", "model", "risk", "verdict"], buf)
            print(f"benign link: +{len(buf)} -> {count} completed", flush=True)
            buf = []
    if buf:
        append_rows(OUT_BJ, ["target_id", "model", "risk", "verdict"], buf)
        print(f"benign link: +{len(buf)} -> {count} completed", flush=True)
    print("benign link done", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["phish", "benign"], default="phish")
    args = ap.parse_args()
    if args.part == "benign":
        run_benign()
    else:
        if not OUT_E.exists():
            build_emails()
        run_judgments()
