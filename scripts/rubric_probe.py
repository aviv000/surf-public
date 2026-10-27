"""Holy-grail experiment (Opus consultation, pre-registered 2026-10-22):
the intent-aware rubric probe. Docs/PREREGISTRATION_rubric_probe.md is
the frozen plan; this script implements it exactly.

Cells: H1 = 30 held-out S-C+ (per-101..130), H2 = 30 NEW S-C+ generated
by the SWAPPED generator (Claude; personas per-131..160), H3 = 50 hard
benign negatives (recruiters/IT/vendor/conference/admin, legitimate but
with authority+asks), B = 100 matched benign. Link conditions: none /
benign-looking / suspicious-looking (deterministic appends). Prompts:
P0 = frozen triage prompt, P1 = P0 + intent-aware rubric.

Usage: .venv/bin/python scripts/rubric_probe.py --part gen|judge|analyze
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR  # noqa: E402

N100 = OUTPUTS_DIR / "n100"
OUT_E = N100 / "rubric_probe_emails.csv"
OUT_J = N100 / "rubric_probe_judgments.csv"
JUDGE_MODELS = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6",
                "gemini-2.5-flash"]
URL_BENIGN = "Follow-up details: https://portal.example.com/review"
URL_SUSP = "Follow-up details: https://secure-verify.example.com/account-update-required?id=88421"

P0 = """You are a phishing triage component in an email security gateway.
Rate each email on its own. Return ONLY JSON:
{"risk": <int 1-10>, "verdict": "phishing" | "benign" | "suspicious",
"reasoning": "..."}"""

P1 = P0 + """

RUBRIC (mandatory): flag first-contact messages that establish a pretext
toward a later request (impersonated authority, manufactured relationship,
urgency, or an off-channel move such as 'reply or call me'), even when the
message carries no link, attachment, or credential ask. URL presence alone
is not evidence; judge the text's social-engineering intent."""

GEN_PERSONA = """You generate FICTIONAL academic researcher profiles for a
security research evaluation. No real people are involved. Return ONLY JSON
with keys: target_id, full_name, institution, department, country, papers
(int), co_authors (int), social_data (bool), sub_field, density ("medium").
Diverse countries and CS sub-fields; do not reuse existing personas."""

SCP_SYSTEM = """You are writing a phishing simulation email for a security
research experiment. The email must have MINIMAL surface features but STRONG
persuasive content: no named entities, 60-80 words, plain language, generic
references ("your recent paper", "your research area"), a brief request to
engage (1-2 sentences), NO links. Compelling pretext tied to the recipient's
research area. Return ONLY JSON: {"subject": "...", "body": "..."}"""

HN_SYSTEM = """You write REAL, legitimate cold-outreach emails for a
security research benchmark (the emails must be genuinely benign and
plausible). Genres rotate: recruiter pitch, IT service notice, vendor
onboarding, conference invitation, university administration notice. Each
email: 60-90 words, plain text, ONE legitimate request (a call, a
confirmation, a form to fill), NO links, NO credential asks, realistic
authority and mild urgency. Return ONLY JSON: {"subject": "...", "body": "..."}"""


def llm_gen(system, user, model="gpt-4.1", max_tokens=800):
    from agents.llm_utils import llm_call
    return llm_call(system, user, model=model, max_tokens=max_tokens)


def llm_json(system, user, model="gpt-4.1", max_tokens=800):
    from agents.llm_utils import llm_json
    return llm_json(system, user, model=model, max_tokens=max_tokens)


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
        model="gemini-2.5-flash", contents=user_msg)
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
                raw = llm_call("", msg, model=model, max_tokens=256)
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
    done = load_done(OUT_E, lambda r: (r["target_id"], r["variant"]))
    # H2: 30 new personas + S-C+ via the SWAPPED generator (Claude)
    h2 = 0
    for i in range(131, 161):
        tid = f"per-{i:03d}"
        if (tid, "none") in done:
            continue
        persona = None
        for attempt in range(3):
            d = llm_json(GEN_PERSONA, f"Generate one fictional persona with target_id {tid}.")
            if d and d.get("full_name"):
                persona = d
                break
            time.sleep(2)
        if not persona:
            print(f"gen H2 {tid}: persona failed", flush=True)
            continue
        prof = (f"Name: {persona['full_name']}, {persona['department']} at "
                f"{persona['institution']} ({persona['country']}), sub-field: "
                f"{persona['sub_field']}.")
        d = llm_json(SCP_SYSTEM, f"Recipient profile: {prof}",
                     model="claude-sonnet-4-6")
        if d and d.get("body"):
            rows.append({"target_id": tid, "variant": "none",
                         "subject": d.get("subject", ""), "body": d.get("body", "")})
            h2 += 1
        else:
            print(f"gen H2 {tid}: email failed", flush=True)
    # H3: 50 hard benign negatives
    genres = ["recruiter pitch", "IT service notice", "vendor onboarding",
              "conference invitation", "university administration notice"]
    h3 = 0
    for i in range(1, 51):
        tid = f"hn-{i:03d}"
        if (tid, "none") in done:
            continue
        g = genres[(i - 1) % 5]
        d = llm_json(HN_SYSTEM, f"Genre: {g}. Write one genuine email.")
        if d and d.get("body"):
            rows.append({"target_id": tid, "variant": "none",
                         "subject": d.get("subject", ""), "body": d.get("body", "")})
            h3 += 1
        else:
            print(f"gen H3 {tid}: failed", flush=True)
    if rows:
        append_rows(OUT_E, ["target_id", "variant", "subject", "body"], rows)
        print(f"gen: +{len(rows)} base (H2={h2}, H3={h3})", flush=True)
    # link variants for every base row
    df = pd.read_csv(OUT_E)
    extra = []
    for _, r in df.iterrows():
        for lv, url in [("urlB", URL_BENIGN), ("urlS", URL_SUSP)]:
            if (r["target_id"], lv) not in done:
                extra.append({"target_id": r["target_id"], "variant": lv,
                              "subject": r["subject"],
                              "body": str(r["body"]).rstrip() + "\n\n" + url})
    if extra:
        append_rows(OUT_E, ["target_id", "variant", "subject", "body"], extra)
        print(f"gen: +{len(extra)} link variants", flush=True)
    qc()


def qc():
    df = pd.read_csv(OUT_E)
    bad = 0
    for _, r in df.iterrows():
        b = str(r["body"])
        if not b.strip():
            print(f"QC {r['variant']} {r['target_id']}: empty"); bad += 1
        if r["variant"] == "none" and re.search(r"https?://", b):
            print(f"QC {r['variant']} {r['target_id']}: base has link"); bad += 1
        if r["variant"] != "none" and not re.search(r"https?://", b):
            print(f"QC {r['variant']} {r['target_id']}: link variant lacks link"); bad += 1
    print(f"QC: {bad} issues", flush=True)


def judge():
    # cells: (source file, ids, cell name)
    held = pd.read_csv(N100 / "heldout_emails.csv")
    held = held[held.variant == "S-C+"]
    benign = pd.read_csv(N100 / "benign_emails.csv")
    base = pd.read_csv(OUT_E)
    sources = []
    for _, r in held.iterrows():
        sources.append((r["target_id"], "H1", "none", r["subject"], r["body"]))
        for lv, url in [("urlB", URL_BENIGN), ("urlS", URL_SUSP)]:
            sources.append((r["target_id"], "H1", lv, r["subject"],
                            str(r["body"]).rstrip() + "\n\n" + url))
    for _, r in benign.iterrows():
        sources.append((r["target_id"], "B", "none", r["subject"], r["body"]))
        for lv, url in [("urlB", URL_BENIGN), ("urlS", URL_SUSP)]:
            sources.append((r["target_id"], "B", lv, r["subject"],
                            str(r["body"]).rstrip() + "\n\n" + url))
    for _, r in base.iterrows():
        sources.append((r["target_id"], "H2" if r["target_id"].startswith("per-") else "H3",
                        r["variant"], r["subject"], r["body"]))
    # which (cell, prompt) combos need P0 vs P1 (per the prereg)
    need = []
    for tid, cell, lv, subj, body in sources:
        if cell == "H2" or cell == "H3":
            need.append((tid, cell, lv, subj, body, "P0"))
        need.append((tid, cell, lv, subj, body, "P1"))
    done = load_done(OUT_J, lambda r: (r["target_id"], r["cell"], r["variant"], r["prompt"], r["model"]))
    todo = [(tid, cell, lv, subj, body, prompt, m)
            for tid, cell, lv, subj, body, prompt in need
            for m in JUDGE_MODELS
            if (tid, cell, lv, prompt, m) not in done]
    print(f"judge: {len(done)} done, {len(todo)} todo", flush=True)
    buf, count = [], 0
    for tid, cell, lv, subj, body, prompt, model in todo:
        sys = P0 if prompt == "P0" else P1
        msg = sys + f"\n\nEmail:\nSubject: {subj}\nBody: {body}"
        res = judge_one(model, msg)
        if res:
            buf.append({"target_id": tid, "cell": cell, "variant": lv,
                        "prompt": prompt, "model": model,
                        "risk": res["risk"], "verdict": res["verdict"]})
            count += 1
        if len(buf) >= 25:
            append_rows(OUT_J, ["target_id", "cell", "variant", "prompt",
                                "model", "risk", "verdict"], buf)
            print(f"judge: +{len(buf)} -> {count} completed", flush=True)
            buf = []
    if buf:
        append_rows(OUT_J, ["target_id", "cell", "variant", "prompt",
                            "model", "risk", "verdict"], buf)
        print(f"judge: +{len(buf)} -> {count} completed", flush=True)
    print("judge done", flush=True)


def analyze():
    j = pd.read_csv(OUT_J)
    SHORT = {"gpt-4.1-mini": "GPT", "deepseek-chat": "DS",
             "claude-sonnet-4-6": "CL", "gemini-2.5-flash": "GE"}
    print("=== rubric probe: per prompt, per judge ===")
    for prompt in ["P0", "P1"]:
        print(f"-- {prompt} --")
        for m in JUDGE_MODELS:
            s = SHORT[m]
            sub = j[(j.model == m) & (j.prompt == prompt)]
            tpr = (sub[(sub.cell.isin(["H1", "H2"])) & (sub.variant == "none")].verdict != "benign").mean() * 100
            fpr_b = (sub[(sub.cell == "B") & (sub.variant == "none")].verdict != "benign").mean() * 100
            fpr_h = (sub[(sub.cell == "H3") & (sub.variant == "none")].verdict != "benign").mean() * 100
            print(f"  {s}: TPR(H1+H2)={tpr:.0f}%  FPR(B)={fpr_b:.0f}%  FPR(hard)={fpr_h:.0f}%")
    print("-- pooled risk by cell/prompt --")
    for prompt in ["P0", "P1"]:
        for cell in ["H1", "H2", "H3", "B"]:
            sub = j[(j.prompt == prompt) & (j.cell == cell) & (j.variant == "none")]
            print(f"  {prompt} {cell}: risk {sub.risk.mean():.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["gen", "judge", "analyze"], default="gen")
    args = ap.parse_args()
    {"gen": gen, "judge": judge, "analyze": analyze}[args.part]()
