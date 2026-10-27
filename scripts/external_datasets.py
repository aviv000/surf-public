"""External-validation slices (DeepSeek dataset review, user-approved):
run the frozen P0 judge prompt over public corpora.

- DIDECO (outputs/n100/dideco_unified.csv): 197 LLM-generated spear-
  phishing emails with human-annotated intent labels (104 link-free).
  Tests whether judge verdicts track human intent labels and whether
  the link-free blind spot replicates outside our generator.
- SpaPhish (datasets_do_not_commit/spaPhish/..., Mendeley hz2d6gz7pc):
  Spanish phishing corpus, 1,395 emails. --part gen extracts the
  link-free first-contact phishing subset (Label==1, url_count==0,
  no Re:/Fwd: subject; n=26) into outputs/n100/spaphish_unified.csv.
  --dataset spaphish_legit extracts 100 link-free first-contact
  LEGITIMATE emails (real mail FPR check, user-approved 2026-10-24).
- CLAIR (datasets_do_not_commit/clair/train.json, HF mirror of the
  Radev 2008 fraud-email collection): --dataset clair_fraud /
  clair_ham extract 100 link-free FRAUD / NOT_FRAUD emails each
  (quoted-printable decoded; real-mail checks, user-approved).
- Porto CMP: request-gated; slot ready, drop the CSV and add a registry
  entry.

Usage: .venv/bin/python scripts/external_datasets.py --part gen|judge|analyze [--dataset dideco|spaphish|spaphish_legit|clair_fraud|clair_ham]
"""
import argparse
import csv
import json
import quopri
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR  # noqa: E402

N100 = OUTPUTS_DIR / "n100"
OUT_J = N100 / "external_dataset_judgments.csv"
JUDGE_MODELS = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6",
                "gemini-2.5-flash"]
SPAPHISH_CSV = (Path(__file__).parent.parent / "datasets_do_not_commit" /
                "spaPhish" / "SpaPhish A Spanish Dataset for Phishing and Psycho" /
                "Spaphish dataset - DiB.csv")
CLAIR_JSON = (Path(__file__).parent.parent / "datasets_do_not_commit" /
              "clair" / "train.json")
UNIFIED = {"dideco": N100 / "dideco_unified.csv",
           "spaphish": N100 / "spaphish_unified.csv",
           "spaphish_legit": N100 / "spaphish_legit_unified.csv",
           "clair_fraud": N100 / "clair_fraud_unified.csv",
           "clair_ham": N100 / "clair_ham_unified.csv"}

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


def _is_reply(subj):
    s = str(subj).strip()
    return s.startswith(("Re:", "RE:", "Fwd:", "Fw:"))


def _has_link(text):
    return bool(re.search(r"https?://|www\.", str(text), re.I))


def gen_spaphish():
    """Extract the link-free first-contact phishing subset from SpaPhish."""
    out = N100 / "spaphish_unified.csv"
    df = pd.read_csv(SPAPHISH_CSV, encoding="utf-8", on_bad_lines="skip",
                     engine="python")
    ph = df[df.Label == 1].copy()
    lf = ph[ph.url_count == 0]
    # the url_count column undercounts: enforce link-free on the body too
    lf = lf[~lf.body.str.contains(r"https?://|www\.", regex=True, na=False)]
    lf = lf[~lf.subject.map(_is_reply)].reset_index(drop=True)
    rows = [{"email_idx": i, "subject": str(r.subject),
             "body": str(r.body),
             "has_attachment": int(r.attachments_count) > 0,
             "text": f"Subject: {r.subject}\nBody: {r.body}"}
            for i, r in lf.iterrows()]
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8")
    print(f"gen_spaphish: {len(rows)} link-free first-contact phishing "
          f"({sum(r['has_attachment'] for r in rows)} with attachments) "
          f"-> {out}", flush=True)


def gen_spaphish_legit():
    """100 link-free first-contact LEGITIMATE SpaPhish emails (real-mail FPR)."""
    out = N100 / "spaphish_legit_unified.csv"
    df = pd.read_csv(SPAPHISH_CSV, encoding="utf-8", on_bad_lines="skip",
                     engine="python")
    lg = df[df.Label == 0].copy()
    lf = lg[(lg.url_count == 0) &
            (~lg.body.str.contains(r"https?://|www\.", regex=True, na=False)) &
            (~lg.subject.map(_is_reply))]
    rng = np.random.RandomState(7)
    lf = lf.sample(n=min(100, len(lf)), random_state=rng).reset_index(drop=True)
    rows = [{"email_idx": i, "subject": str(r.subject),
             "body": str(r.body),
             "has_attachment": int(r.attachments_count) > 0,
             "text": f"Subject: {r.subject}\nBody: {r.body}"}
            for i, r in lf.iterrows()]
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8")
    print(f"gen_spaphish_legit: {len(rows)} link-free first-contact "
          f"legitimate emails -> {out}", flush=True)


def _b64(text):
    """Decode rows that are base64-encoded blobs (no spaces, b64 alphabet)."""
    import base64
    s = str(text).strip()
    if not s or " " in s[:300] or "\n\n" in s[:300]:
        return s
    compact = re.sub(r"\s", "", s)
    if len(compact) < 100 or not re.fullmatch(r"[A-Za-z0-9+/=]+", compact):
        return s
    try:
        dec = base64.b64decode(compact, validate=True).decode(
            "utf-8", "replace")
        if len(dec) > 100:
            return dec
    except Exception:
        pass
    return s


def _qp(text):
    s = str(text)
    for _ in range(3):  # some rows are double-encoded
        if "=\n" in s or re.search(r"=[0-9A-Fa-f]{2}", s):
            try:
                s = quopri.decodestring(s.encode("utf-8", "replace")).decode(
                    "utf-8", "replace")
            except Exception:
                break
        else:
            break
    return s


def gen_clair(label):
    """100 link-free CLAIR emails (label FRAUD or NOT_FRAUD), decoded."""
    out = UNIFIED["clair_fraud" if label == "FRAUD" else "clair_ham"]
    rows_raw = []
    with open(CLAIR_JSON, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows_raw.append(json.loads(line))
            except Exception:
                pass
    keep = [r for r in rows_raw if r.get("label") == label]
    keep = [r for r in keep if not _has_link(_b64(_qp(r.get("text", ""))))]
    keep = [r for r in keep
            if not re.search(r"=[0-9A-Fa-f]{2}", _b64(_qp(r.get("text", ""))))]
    rng = np.random.RandomState(7)
    rng.shuffle(keep)
    keep = keep[:min(100, len(keep))]
    rows = [{"email_idx": i, "subject": "(none)",
             "body": _b64(_qp(r["text"])), "text": _b64(_qp(r["text"]))}
            for i, r in enumerate(keep)]
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8")
    print(f"gen_clair[{label}]: {len(rows)} link-free emails -> {out}",
          flush=True)


def judge(dataset="dideco"):
    src = UNIFIED[dataset]
    emails = pd.read_csv(src)
    if "email_idx" not in emails.columns:
        emails = emails.reset_index().rename(columns={"index": "email_idx"})
    done = load_done(OUT_J, lambda r: (r["dataset"], r["email_idx"], r["model"]))
    todo = [(int(r.email_idx), str(r.text), m)
            for _, r in emails.iterrows()
            for m in JUDGE_MODELS
            if (dataset, int(r.email_idx), m) not in done]
    print(f"judge[{dataset}]: {len(done)} done, {len(todo)} todo", flush=True)
    buf, count = [], 0
    for idx, text, model in todo:
        if dataset == "dideco":
            msg = f"Email:\nSubject: (none)\nBody: {text}"
        elif dataset in ("clair_fraud", "clair_ham"):
            msg = f"Email:\nSubject: (none)\nBody: {text}"
        else:
            msg = f"Email:\n{text}"
        res = judge_one(model, msg)
        if res:
            buf.append({"dataset": dataset, "email_idx": idx, "model": model,
                        "risk": res["risk"], "verdict": res["verdict"]})
            count += 1
        if len(buf) >= 25:
            append_rows(OUT_J, ["dataset", "email_idx", "model", "risk", "verdict"], buf)
            print(f"judge[{dataset}]: +{len(buf)} -> {count} completed", flush=True)
            buf = []
    if buf:
        append_rows(OUT_J, ["dataset", "email_idx", "model", "risk", "verdict"], buf)
        print(f"judge[{dataset}]: +{len(buf)} -> {count} completed", flush=True)
    print(f"judge[{dataset}] done", flush=True)


def analyze_spaphish():
    j = pd.read_csv(OUT_J)
    sub = j[j.dataset == "spaphish"]
    emails = pd.read_csv(N100 / "spaphish_unified.csv")
    m = sub.merge(emails, on="email_idx")
    SHORT = {"gpt-4.1-mini": "GPT", "deepseek-chat": "DS",
             "claude-sonnet-4-6": "CL", "gemini-2.5-flash": "GE"}
    print(f"=== SpaPhish: link-free first-contact phishing (n={len(emails)}) ===")
    for model in JUDGE_MODELS:
        s = SHORT[model]
        mm = m[m.model == model]
        fl = (mm.verdict != "benign").mean() * 100
        fl_clean = (mm[~mm.has_attachment].verdict != "benign").mean() * 100
        print(f"  {s}: flagged {fl:.0f}% ({len(mm)} judged) | "
              f"attachment-free {fl_clean:.0f}% | risk {mm.risk.mean():.2f}")
    fl = (m.verdict != "benign").mean() * 100
    print(f"  pooled: flagged {fl:.0f}% | risk {m.risk.mean():.2f}")


def analyze_external(dataset):
    j = pd.read_csv(OUT_J)
    j = j[j.dataset == dataset]
    emails = pd.read_csv(UNIFIED[dataset])
    m = j.merge(emails, on="email_idx")
    SHORT = {"gpt-4.1-mini": "GPT", "deepseek-chat": "DS",
             "claude-sonnet-4-6": "CL", "gemini-2.5-flash": "GE"}
    print(f"=== {dataset}: n={len(emails)} ===")
    for model in JUDGE_MODELS:
        s = SHORT[model]
        mm = m[m.model == model]
        fl = (mm.verdict != "benign").mean() * 100
        print(f"  {s}: flagged {fl:.0f}% ({len(mm)} judged) | risk {mm.risk.mean():.2f}")
    print(f"  pooled: flagged {(m.verdict != 'benign').mean() * 100:.0f}% | "
          f"risk {m.risk.mean():.2f}")


def analyze():
    j = pd.read_csv(OUT_J)
    emails = pd.read_csv(N100 / "dideco_unified.csv").reset_index().rename(
        columns={"index": "email_idx"})
    m = j[j.dataset == "dideco"].merge(emails, on="email_idx")
    SHORT = {"gpt-4.1-mini": "GPT", "deepseek-chat": "DS",
             "claude-sonnet-4-6": "CL", "gemini-2.5-flash": "GE"}
    print("=== DIDECO: judge verdicts vs human intent labels ===")
    for model in JUDGE_MODELS:
        s = SHORT[model]
        sub = m[m.model == model]
        fl = (sub.verdict != "benign").mean() * 100
        fl_lf = (sub[~sub.has_link].verdict != "benign").mean() * 100
        fl_lk = (sub[sub.has_link].verdict != "benign").mean() * 100
        print(f"  {s}: flagged {fl:.0f}% | link-free {fl_lf:.0f}% | link-bearing {fl_lk:.0f}%")
    print("risk by n_intents (pooled):")
    for lo, hi in [(1, 2), (3, 4), (5, 9)]:
        sub = m[(m.n_intents >= lo) & (m.n_intents <= hi)]
        print(f"  {lo}-{hi} intents: flagged {(sub.verdict != 'benign').mean() * 100:.0f}%, risk {sub.risk.mean():.2f}")
    analyze_spaphish()
    for ds in ("spaphish_legit", "clair_fraud", "clair_ham"):
        if UNIFIED[ds].exists():
            analyze_external(ds)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["gen", "judge", "analyze"], default="judge")
    ap.add_argument("--dataset", choices=["dideco", "spaphish", "spaphish_legit",
                                          "clair_fraud", "clair_ham"],
                    default="dideco")
    args = ap.parse_args()
    if args.part == "gen":
        {"spaphish": gen_spaphish,
         "spaphish_legit": gen_spaphish_legit,
         "clair_fraud": lambda: gen_clair("FRAUD"),
         "clair_ham": lambda: gen_clair("NOT_FRAUD")}[args.dataset]()
    elif args.part == "judge":
        judge(args.dataset)
    else:
        analyze()
