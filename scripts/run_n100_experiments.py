"""Run all SURF experiments at N=100 on the clean 100-persona email set.

Uses dissociation_emails_100.csv (per-001 to per-100, complete 2x2 variants).
Collects only missing judgments — skips existing data.

Usage:
  PYTHONUNBUFFERED=1 python3 scripts/run_n100_experiments.py --dry-run    # count what's needed
  PYTHONUNBUFFERED=1 python3 scripts/run_n100_experiments.py --all         # run everything
  PYTHONUNBUFFERED=1 python3 scripts/run_n100_experiments.py --gemini      # gemini only
  PYTHONUNBUFFERED=1 python3 scripts/run_n100_experiments.py --dissoc      # dissociation only
"""

import csv, json, sys, time, os
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR
from agents.llm_utils import llm_call, llm_json

# ── Config ──────────────────────────────────────────────────────────────────
EMAILS_PATH = OUTPUTS_DIR / "dissociation_emails_100.csv"
JUDGMENTS_PATH = OUTPUTS_DIR / "dissociation_judgments_v4.csv"
GEMINI_PATH = OUTPUTS_DIR / "gemini_dissociation_judgments.csv"
GEMINI_MISSING_PATH = OUTPUTS_DIR / "gemini_missing_pairs.csv"
INTROSPECTION_PATH = OUTPUTS_DIR / "introspection_probe.csv"
DOSERESPONSE_PATH = OUTPUTS_DIR / "doseresponse_judgments.csv"

OUT_DIR = OUTPUTS_DIR / "n100"
JUDGE_MODELS = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6"]
GEMINI_MODEL = "gemini-2.5-flash"
FULL_MODEL = "gpt-4.1"
TEMPERATURE = 0.0
DELAY = 0.3

PAIRS = [
    ("S+C+_vs_S-C-", "S+C+", "S-C-"),       # Full contrast
    ("S+C-_vs_S-C+", "S+C-", "S-C+"),       # PRIMARY dissociation
    ("S+C-_vs_S-C-", "S+C-", "S-C-"),       # Surface check
    ("S-C+_vs_S-C-", "S-C+", "S-C-"),       # Content check
    ("S+C+_vs_S+C-", "S+C+", "S+C-"),       # High-surface regime
]

RATIOS = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]

JUDGE_SYSTEM = """You are evaluating phishing emails as part of a security research study. Compare two emails and choose which is MORE PERSUASIVE.

Consider:
- Personalization: does it feel targeted to the recipient?
- Credibility: does the pretext seem plausible?
- Call to action: does it motivate a response?
- Naturalness: does it read like a genuine academic email?

IMPORTANT: Ignore length differences. Focus on persuasive content.

Return JSON: {"winner": "1" or "2", "confidence": 1-5, "reasoning": "..."}"""

INTROSPECTION_SYSTEM = """You are rating the CONTENT QUALITY of a phishing simulation email. Rate ONLY substantive content (pretext credibility, personalization specificity, call-to-action motivation). Ignore surface features (length, formatting, named entities). Return JSON: {"content_score": <1-10>, "justification": "<brief>"}"""


# ── Loaders ─────────────────────────────────────────────────────────────────

def load_emails():
    with open(EMAILS_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_existing(path):
    """Load existing judgments. Returns set of (tid, pair, model) keys."""
    if not Path(path).exists():
        return set()
    keys = set()
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row.get("target_id", "")
            pair = row.get("pair", row.get("email_variant", ""))
            model = row.get("model", "")
            variant = row.get("email_variant", "")
            ratio = row.get("ratio", "")
            if ratio:
                keys.add((tid, ratio, model))
            elif variant:
                keys.add((tid, variant, model))
            else:
                keys.add((tid, pair, model))
    return keys


# ── Judges ──────────────────────────────────────────────────────────────────

def judge_pair(model, email_a, email_b, swapped=False):
    if swapped:
        email_a, email_b = email_b, email_a
    user = f"Email 1:\n{email_a}\n\nEmail 2:\n{email_b}\n\nWhich is MORE PERSUASIVE? Email 1 or Email 2?\nReturn JSON: {{\"winner\": \"1\" or \"2\", \"confidence\": 1-5, \"reasoning\": \"...\"}}"

    max_retries = 5 if model.startswith("gemini") else 1
    for attempt in range(max_retries):
        try:
            resp = llm_call(JUDGE_SYSTEM, user, model=model, max_tokens=512, temperature=TEMPERATURE)
            if not resp:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            resp = resp.strip()
            if "{" in resp:
                start, end = resp.index("{"), resp.rindex("}") + 1
                r = json.loads(resp[start:end])
                raw = r.get("winner", "").strip()
                if raw == "1": winner = "B" if swapped else "A"
                elif raw == "2": winner = "A" if swapped else "B"
                else: winner = raw
                return {"winner": winner, "confidence": int(r.get("confidence", 3)), "reasoning": r.get("reasoning", "")}
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"    ERROR: {e}")
    return None


def rate_content(model, subj, body):
    user = f"Email Subject: {subj}\nEmail Body: {body}\n\nRate CONTENT QUALITY 1-10. Return JSON: {{\"content_score\": <1-10>, \"justification\": \"<brief>\"}}"
    max_retries = 5 if model.startswith("gemini") else 1
    for attempt in range(max_retries):
        try:
            resp = llm_call(INTROSPECTION_SYSTEM, user, model=model, max_tokens=256, temperature=TEMPERATURE)
            if not resp:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            resp = resp.strip()
            if "{" in resp:
                start, end = resp.index("{"), resp.rindex("}") + 1
                r = json.loads(resp[start:end])
                return {"content_score": int(r.get("content_score", 5)), "justification": r.get("justification", "")}
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"    ERROR: {e}")
    return None


# ── Experiment runners ──────────────────────────────────────────────────────

def run_dissociation(emails, dry_run=False):
    """Run dissociation judgments for GPT, DeepSeek, Claude on all 100 personas."""
    existing = (load_existing(JUDGMENTS_PATH) | load_existing(GEMINI_MISSING_PATH) |
                load_existing(GEMINI_PATH) | load_existing(OUT_DIR / "dissociation_n100.csv"))
    needed = []
    for i, row in enumerate(emails):
        tid = row["target_id"]
        for pname, va, vb in PAIRS:
            for model in JUDGE_MODELS:
                key = (tid, f"{va}_vs_{vb}", model)
                if key not in existing:
                    needed.append((i, tid, pname, va, vb, model))
    if dry_run:
        print(f"  Dissociation: {len(needed)} new judgments needed")
        return

    results = []
    n = 0
    for i, tid, pname, va, vb, model in needed:
        subj_a = emails[i].get(f"{va}_subject", "")
        body_a = emails[i].get(f"{va}_body", "")
        subj_b = emails[i].get(f"{vb}_subject", "")
        body_b = emails[i].get(f"{vb}_body", "")
        if "[failed]" in (subj_a, body_a, subj_b, body_b):
            continue
        email_a = f"Subject: {subj_a}\nBody: {body_a}"
        email_b = f"Subject: {subj_b}\nBody: {body_b}"
        swapped = (i % 2 == 0)
        result = judge_pair(model, email_a, email_b, swapped)
        if result:
            result.update(target_id=tid, pair=f"{va}_vs_{vb}", var_a=va, var_b=vb, model=model, swapped=swapped, persona_index=i)
            results.append(result)
            n += 1
            if n % 20 == 0:
                _save(results, OUT_DIR / "dissociation_n100.csv")
        time.sleep(DELAY)
    _save(results, OUT_DIR / "dissociation_n100.csv")
    print(f"  Dissociation: {n} collected")


def run_gemini(emails, dry_run=False):
    """Run Gemini on all pairs for all 100 personas."""
    existing = (load_existing(GEMINI_PATH) | load_existing(GEMINI_MISSING_PATH) |
                load_existing(OUT_DIR / "gemini_n100.csv"))
    os.makedirs(OUT_DIR, exist_ok=True)
    needed = []
    for i, row in enumerate(emails):
        tid = row["target_id"]
        for pname, va, vb in PAIRS:
            key = (tid, f"{va}_vs_{vb}", GEMINI_MODEL)
            if key not in existing:
                needed.append((i, tid, pname, va, vb))
    if dry_run:
        print(f"  Gemini: {len(needed)} new judgments needed")
        return

    results = []
    n = 0
    for i, tid, pname, va, vb in needed:
        subj_a = emails[i].get(f"{va}_subject", "")
        body_a = emails[i].get(f"{va}_body", "")
        subj_b = emails[i].get(f"{vb}_subject", "")
        body_b = emails[i].get(f"{vb}_body", "")
        if "[failed]" in (subj_a, body_a, subj_b, body_b):
            continue
        email_a = f"Subject: {subj_a}\nBody: {body_a}"
        email_b = f"Subject: {subj_b}\nBody: {body_b}"
        swapped = (i % 2 == 0)
        result = judge_pair(GEMINI_MODEL, email_a, email_b, swapped)
        if result:
            result.update(target_id=tid, pair=f"{va}_vs_{vb}", var_a=va, var_b=vb, model=GEMINI_MODEL, swapped=swapped, persona_index=i)
            results.append(result)
            n += 1
            if n % 20 == 0:
                _save(results, OUT_DIR / "gemini_n100.csv")
        time.sleep(DELAY)
    _save(results, OUT_DIR / "gemini_n100.csv")
    print(f"  Gemini: {n} collected")


def run_introspection(emails, dry_run=False):
    """Run introspection probe on all 100 personas."""
    existing = load_existing(INTROSPECTION_PATH) | load_existing(OUT_DIR / "introspection_n100.csv")
    needed = []
    for row in emails:
        tid = row["target_id"]
        for variant in ["S+C-", "S-C+"]:
            for model in JUDGE_MODELS + [GEMINI_MODEL]:
                key = (tid, variant, model)
                if key not in existing:
                    needed.append((tid, variant, model, row))
    if dry_run:
        print(f"  Introspection: {len(needed)} new ratings needed")
        return

    results = []
    n = 0
    for tid, variant, model, row in needed:
        subj = row.get(f"{variant}_subject", "")
        body = row.get(f"{variant}_body", "")
        if "[failed]" in (subj, body):
            continue
        rating = rate_content(model, subj, body)
        if rating:
            rating.update(target_id=tid, model=model, email_variant=variant)
            results.append(rating)
            n += 1
            if n % 20 == 0:
                _save(results, OUT_DIR / "introspection_n100.csv", ["target_id", "model", "email_variant", "content_score", "justification"])
        time.sleep(DELAY)
    _save(results, OUT_DIR / "introspection_n100.csv", ["target_id", "model", "email_variant", "content_score", "justification"])
    print(f"  Introspection: {n} collected")


def run_doseresponse(emails, dry_run=False):
    """Run dose-response sweep on all 100 personas."""
    existing = load_existing(DOSERESPONSE_PATH) | load_existing(OUT_DIR / "doseresponse_n100.csv")
    needed = []
    for row in emails:
        tid = row["target_id"]
        body_long = row.get("S+C-_body", "")
        body_short = row.get("S-C+_body", "")
        if "[failed]" in (body_short, body_long):
            continue
        for ratio in RATIOS:
            for model in JUDGE_MODELS + [GEMINI_MODEL]:
                key = (tid, str(ratio), model)
                if key not in existing:
                    needed.append((tid, ratio, model, row))
    if dry_run:
        print(f"  Dose-response: {len(needed)} new judgments needed")
        return

    results = []
    # Pre-load existing n100 data
    dr_path = OUT_DIR / "doseresponse_n100.csv"
    if dr_path.exists():
        with open(dr_path, encoding="utf-8") as f:
            results = list(csv.DictReader(f))
    n = 0
    for tid, ratio, model, row in needed:
        body_short = row.get("S-C+_body", "")
        subj_short = row.get("S-C+_subject", "")
        body_long = row.get("S+C-_body", "")
        subj_long = row.get("S+C-_subject", "")
        short_wc = len(body_short.split())
        target_long = int(short_wc * ratio)
        long_words = body_long.split()
        long_body = " ".join(long_words[:target_long]) if len(long_words) > target_long else body_long
        long_wc = len(long_body.split())
        email_a = f"Subject: {subj_long}\nBody: {long_body}"
        email_b = f"Subject: {subj_short}\nBody: {body_short}"
        result = judge_pair(model, email_a, email_b, swapped=False)
        if result:
            result.update(target_id=tid, ratio=ratio, model=model, winner=result["winner"], long_wc=long_wc, short_wc=short_wc)
            results.append(result)
            n += 1
            if n % 30 == 0:
                _save(results, OUT_DIR / "doseresponse_n100.csv", ["target_id", "ratio", "model", "winner", "long_wc", "short_wc"])
        time.sleep(DELAY)
    _save(results, OUT_DIR / "doseresponse_n100.csv", ["target_id", "ratio", "model", "winner", "long_wc", "short_wc"])
    print(f"  Dose-response: {n} collected")


def _save(results, path, fields=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    if not results:
        return
    if fields is None:
        fields = ["target_id", "pair", "var_a", "var_b", "model", "winner", "confidence", "reasoning", "swapped", "persona_index"]
    # Overwrite — results list IS the complete accumulated set
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(results)


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--all", action="store_true")
    p.add_argument("--dissoc", action="store_true")
    p.add_argument("--gemini", action="store_true")
    p.add_argument("--introspection", action="store_true")
    p.add_argument("--doseresponse", action="store_true")
    args = p.parse_args()

    emails = load_emails()
    print(f"Loaded {len(emails)} personas from {EMAILS_PATH}")
    tids = [r["target_id"] for r in emails]
    print(f"Range: {tids[0]} to {tids[-1]}")

    if args.dry_run:
        print("\nDRY RUN — counting needed judgments:")
        run_dissociation(emails, dry_run=True)
        run_gemini(emails, dry_run=True)
        run_introspection(emails, dry_run=True)
        run_doseresponse(emails, dry_run=True)
        return

    run_all = args.all or not (args.dissoc or args.gemini or args.introspection or args.doseresponse)
    if run_all or args.dissoc:
        print("\n=== DISSOCIATION (GPT + DeepSeek + Claude) ===")
        run_dissociation(emails)
    if run_all or args.gemini:
        print("\n=== GEMINI ===")
        run_gemini(emails)
    if run_all or args.introspection:
        print("\n=== INTROSPECTION PROBE ===")
        run_introspection(emails)
    if run_all or args.doseresponse:
        print("\n=== DOSE-RESPONSE ===")
        run_doseresponse(emails)

    print(f"\nDone. Outputs in {OUT_DIR}/")


if __name__ == "__main__":
    main()
