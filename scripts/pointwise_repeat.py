"""Repeat run of the four headline pointwise cells (round-33 weakness 10,
user-approved 2026-10-24): S-C+ (100), S-C+L (100), Benign (100), and
the 50 legitimate-outreach negatives, all four judges, frozen P0 prompt.
Reports per-judge test-retest agreement on binary verdicts and risk
shift against the original runs.

Cells -> originals:
  SCP  (S-C+)      outputs/dissociation_emails_100.csv ->
                   outputs/n100/pointwise_2x2_extra.csv variant S-C+
  SCPL (S-C+link)  outputs/n100/link_control_emails.csv variant S-C+link ->
                   outputs/n100/link_control_judgments.csv
  B    (Benign)    outputs/n100/benign_emails.csv ->
                   outputs/n100/pointwise_benign_judgments.csv
  OUT  (Outreach)  outputs/n100/rubric_probe_emails.csv variant none,
                   target not starting with per- ->
                   outputs/n100/rubric_probe_judgments.csv cell H3 prompt P0

Usage: .venv/bin/python scripts/pointwise_repeat.py --part gen|judge|analyze
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

N100 = OUTPUTS_DIR / "n100"
OUT_E = N100 / "repeat_unified.csv"
OUT_J = N100 / "repeat_judgments.csv"
OUT_R = N100 / "repeat_run_report.txt"
JUDGE_MODELS = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6",
                "gemini-2.5-flash"]

P0 = """You are a phishing triage component in an email security gateway.
Rate each email on its own. Return ONLY JSON:
{"risk": <int 1-10>, "verdict": "phishing" | "benign" | "suspicious",
"reasoning": "..."}"""


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


def _gemini(user_msg):
    import google.genai as genai
    from google.genai.types import HttpOptions
    from config import GOOGLE_API_KEY
    if not GOOGLE_API_KEY:
        return None
    client = genai.Client(api_key=GOOGLE_API_KEY,
                          http_options=HttpOptions(timeout=60000))
    resp = client.models.generate_content(
        model="gemini-2.5-flash", contents=P0 + "\n\n" + user_msg)
    if resp and resp.text:
        return _parse(resp.text)
    return None


def judge_one(model, msg):
    for attempt in range(2):
        try:
            if model == "gemini-2.5-flash":
                res = _gemini(msg)
            else:
                from agents.llm_utils import llm_call
                raw = llm_call(P0, msg, model=model, max_tokens=256)
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


def gen():
    rows = []
    idx = 0
    diss = pd.read_csv(OUTPUTS_DIR / "dissociation_emails_100.csv")
    for _, r in diss.iterrows():
        rows.append({"email_idx": idx, "cell": "SCP", "target_id": r.target_id,
                     "subject": r["S-C+_subject"], "body": r["S-C+_body"],
                     "text": f"Subject: {r['S-C+_subject']}\nBody: {r['S-C+_body']}"})
        idx += 1
    lc = pd.read_csv(N100 / "link_control_emails.csv")
    lc = lc[lc.variant == "S-C+link"]
    for _, r in lc.iterrows():
        rows.append({"email_idx": idx, "cell": "SCPL", "target_id": r.target_id,
                     "subject": r.subject, "body": r.body,
                     "text": f"Subject: {r.subject}\nBody: {r.body}"})
        idx += 1
    bn = pd.read_csv(N100 / "benign_emails.csv")
    for _, r in bn.iterrows():
        rows.append({"email_idx": idx, "cell": "B", "target_id": r.target_id,
                     "subject": r.subject, "body": r.body,
                     "text": f"Subject: {r.subject}\nBody: {r.body}"})
        idx += 1
    rp = pd.read_csv(N100 / "rubric_probe_emails.csv")
    out = rp[(rp.variant == "none") & (~rp.target_id.str.startswith("per-"))]
    for _, r in out.iterrows():
        rows.append({"email_idx": idx, "cell": "OUT", "target_id": r.target_id,
                     "subject": r.subject, "body": r.body,
                     "text": f"Subject: {r.subject}\nBody: {r.body}"})
        idx += 1
    pd.DataFrame(rows).to_csv(OUT_E, index=False, encoding="utf-8")
    counts = pd.DataFrame(rows).groupby("cell").size().to_dict()
    print(f"gen: {len(rows)} emails -> {OUT_E} (cells: {counts})", flush=True)


def judge():
    emails = pd.read_csv(OUT_E)
    done = load_done(OUT_J, lambda r: (r["email_idx"], r["model"]))
    todo = [(int(r.email_idx), str(r.text), m)
            for _, r in emails.iterrows()
            for m in JUDGE_MODELS
            if (int(r.email_idx), m) not in done]
    print(f"judge: {len(done)} done, {len(todo)} todo", flush=True)
    buf, count = [], 0
    for idx, text, model in todo:
        msg = f"Email:\n{text}"
        res = judge_one(model, msg)
        if res:
            buf.append({"email_idx": idx, "model": model,
                        "risk": res["risk"], "verdict": res["verdict"]})
            count += 1
        if len(buf) >= 25:
            append_rows(OUT_J, ["email_idx", "model", "risk", "verdict"], buf)
            print(f"judge: +{len(buf)} -> {count} completed", flush=True)
            buf = []
    if buf:
        append_rows(OUT_J, ["email_idx", "model", "risk", "verdict"], buf)
        print(f"judge: +{len(buf)} -> {count} completed", flush=True)
    print("judge done", flush=True)


ORIG = {
    "SCP": ("outputs/n100/pointwise_judgments.csv",
            lambda df: df[df.variant == "S-C+"][["target_id", "model", "risk",
                                                 "verdict"]]),
    "SCPL": ("outputs/n100/link_control_judgments.csv",
             lambda df: df[df.variant == "S-C+link"][["target_id", "model",
                                                      "risk", "verdict"]]),
    "B": ("outputs/n100/pointwise_benign_judgments.csv",
          lambda df: df[["target_id", "model", "risk", "verdict"]]),
    "OUT": ("outputs/n100/rubric_probe_judgments.csv",
            lambda df: df[(df.cell == "H3") & (df.prompt == "P0") &
                          (df.variant == "none")][["target_id", "model", "risk",
                                                   "verdict"]]),
}


def analyze():
    emails = pd.read_csv(OUT_E)
    j = pd.read_csv(OUT_J)
    SHORT = {"gpt-4.1-mini": "GPT", "deepseek-chat": "DS",
             "claude-sonnet-4-6": "CL", "gemini-2.5-flash": "GE"}
    lines = []
    print("=== REPEAT RUN: test-retest agreement (binary verdict) ===")
    lines.append("cell per-judge agreement % (risk mean abs diff)")
    pooled_agr, pooled_n = [], []
    for cell in ("SCP", "SCPL", "B", "OUT"):
        path, prep = ORIG[cell]
        orig = prep(pd.read_csv(path))
        sub = j.merge(emails[["email_idx", "cell", "target_id"]],
                      on="email_idx")
        sub = sub[sub.cell == cell]
        for model in JUDGE_MODELS:
            s = SHORT[model]
            a = sub[sub.model == model]
            o = orig[orig.model == model]
            m = a.merge(o, on="target_id", suffixes=("_rep", "_orig"))
            if not len(m):
                print(f"  {cell} {s}: no overlap ({len(a)} rep, {len(o)} orig)")
                continue
            agr = (m.verdict_rep == m.verdict_orig).mean() * 100
            rdiff = (m.risk_rep - m.risk_orig).abs().mean()
            print(f"  {cell} {s}: agreement {agr:.0f}% ({len(m)} paired) | "
                  f"risk shift {rdiff:.2f}")
            lines.append(f"{cell} {s}: {agr:.0f}% ({len(m)}) risk {rdiff:.2f}")
            pooled_agr.append((m.verdict_rep == m.verdict_orig).sum())
            pooled_n.append(len(m))
    tot = sum(pooled_agr) / sum(pooled_n) * 100
    print(f"  POOLED agreement: {tot:.0f}% over {sum(pooled_n)} paired")
    lines.append(f"POOLED: {tot:.0f}% over {sum(pooled_n)} paired")
    OUT_R.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report -> {OUT_R}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["gen", "judge", "analyze"],
                    default="judge")
    args = ap.parse_args()
    {"gen": gen, "judge": judge, "analyze": analyze}[args.part]()
