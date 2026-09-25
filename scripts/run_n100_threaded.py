"""Threaded SURF experiment runner — one thread per provider, parallel execution.
Gemini: infinite retry on 503 until API recovers.
"""

import csv, json, sys, time, os, threading
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR
from agents.llm_utils import llm_call, llm_json

# ── Config ──────────────────────────────────────────────────────────────────
EMAILS_PATH = OUTPUTS_DIR / "dissociation_emails_100.csv"
OUT_DIR = OUTPUTS_DIR / "n100"
TEMPERATURE = 0.0
DELAY = 0.3

PROVIDERS = {
    "openai":       {"models": ["gpt-4.1-mini"],    "threads": 1},
    "deepseek":     {"models": ["deepseek-chat"],    "threads": 1},
    "anthropic":    {"models": ["claude-sonnet-4-6"], "threads": 1},
    "google":       {"models": ["gemini-2.5-flash"], "threads": 1},
}

PAIRS = [
    ("S+C+_vs_S-C-", "S+C+", "S-C-"),
    ("S+C-_vs_S-C+", "S+C-", "S-C+"),
    ("S+C-_vs_S-C-", "S+C-", "S-C-"),
    ("S-C+_vs_S-C-", "S-C+", "S-C-"),
    ("S+C+_vs_S+C-", "S+C+", "S+C-"),
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

INTROSPECTION_SYSTEM = """You are rating the CONTENT QUALITY of a phishing simulation email. Rate ONLY substantive content (pretext credibility, personalization specificity, call-to-action motivation). Ignore surface features. Return JSON: {"content_score": <1-10>, "justification": "<brief>"}"""

# ── Thread-safe save ────────────────────────────────────────────────────────
SAVE_LOCK = threading.Lock()

def save_csv(results, path, fields):
    os.makedirs(OUT_DIR, exist_ok=True)
    # Pre-load existing
    existing = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    all_rows = existing + results
    with SAVE_LOCK:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader()
            w.writerows(all_rows)

# ── Helpers ─────────────────────────────────────────────────────────────────

def load_emails():
    with open(EMAILS_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_existing_keys(path):
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

# ── Judge functions ─────────────────────────────────────────────────────────

def judge_pair(model, email_a, email_b, swapped=False):
    if swapped:
        email_a, email_b = email_b, email_a
    user = f"Email 1:\n{email_a}\n\nEmail 2:\n{email_b}\n\nWhich is MORE PERSUASIVE? Email 1 or Email 2?\nReturn JSON: {{\"winner\": \"1\" or \"2\", \"confidence\": 1-5, \"reasoning\": \"...\"}}"

    while True:  # infinite retry for all providers
        try:
            resp = llm_call(JUDGE_SYSTEM, user, model=model, max_tokens=512, temperature=TEMPERATURE)
            if not resp:
                time.sleep(2)
                continue
            resp = resp.strip()
            if "{" in resp:
                start, end = resp.index("{"), resp.rindex("}") + 1
                r = json.loads(resp[start:end])
                raw = r.get("winner", "").strip()
                if raw == "1": winner = "B" if swapped else "A"
                elif raw == "2": winner = "A" if swapped else "B"
                else: winner = raw
                return {"winner": winner, "confidence": int(r.get("confidence", 3)), "reasoning": r.get("reasoning", "")}
            time.sleep(1)
        except Exception as e:
            print(f"    [{model}] ERROR: {e}, retrying...")
            time.sleep(2)

def rate_content(model, subj, body):
    user = f"Email Subject: {subj}\nEmail Body: {body}\n\nRate CONTENT QUALITY 1-10. Return JSON: {{\"content_score\": <1-10>, \"justification\": \"<brief>\"}}"
    while True:
        try:
            resp = llm_call(INTROSPECTION_SYSTEM, user, model=model, max_tokens=256, temperature=TEMPERATURE)
            if not resp:
                time.sleep(2)
                continue
            resp = resp.strip()
            if "{" in resp:
                start, end = resp.index("{"), resp.rindex("}") + 1
                r = json.loads(resp[start:end])
                return {"content_score": int(r.get("content_score", 5)), "justification": r.get("justification", "")}
            time.sleep(1)
        except Exception as e:
            print(f"    [{model}] ERROR: {e}, retrying...")
            time.sleep(2)

# ── Work builders ───────────────────────────────────────────────────────────

def build_dissoc_tasks(emails):
    existing = set()
    for p in [OUTPUTS_DIR / "dissociation_judgments_v4.csv",
              OUTPUTS_DIR / "gemini_dissociation_judgments.csv",
              OUTPUTS_DIR / "gemini_missing_pairs.csv",
              OUT_DIR / "dissociation_n100.csv"]:
        existing |= load_existing_keys(p)

    tasks = defaultdict(list)  # model -> [(tid, va, vb, swapped, persona_idx)]
    for i, row in enumerate(emails):
        tid = row["target_id"]
        for pname, va, vb in PAIRS:
            for provider, cfg in PROVIDERS.items():
                for model in cfg["models"]:
                    key = (tid, f"{va}_vs_{vb}", model)
                    if key not in existing:
                        swapped = (i % 2 == 0)
                        tasks[model].append((i, tid, va, vb, swapped))
    return tasks

def build_gemini_tasks(emails):
    existing = set()
    for p in [OUTPUTS_DIR / "gemini_dissociation_judgments.csv",
              OUTPUTS_DIR / "gemini_missing_pairs.csv",
              OUT_DIR / "gemini_n100.csv"]:
        existing |= load_existing_keys(p)

    tasks = []
    for i, row in enumerate(emails):
        tid = row["target_id"]
        for pname, va, vb in PAIRS:
            key = (tid, f"{va}_vs_{vb}", "gemini-2.5-flash")
            if key not in existing:
                tasks.append((i, tid, va, vb))
    return tasks

def build_introspection_tasks(emails):
    existing = set()
    for p in [OUTPUTS_DIR / "introspection_probe.csv",
              OUT_DIR / "introspection_n100.csv"]:
        existing |= load_existing_keys(p)

    tasks = defaultdict(list)
    for row in emails:
        tid = row["target_id"]
        for variant in ["S+C-", "S-C+"]:
            for provider, cfg in PROVIDERS.items():
                for model in cfg["models"]:
                    key = (tid, variant, model)
                    if key not in existing:
                        tasks[model].append((tid, variant, row))
    return tasks

def build_doseresponse_tasks(emails):
    existing = set()
    for p in [OUTPUTS_DIR / "doseresponse_judgments.csv",
              OUT_DIR / "doseresponse_n100.csv"]:
        existing |= load_existing_keys(p)

    tasks = defaultdict(list)
    for row in emails:
        tid = row["target_id"]
        body_long = row.get("S+C-_body", "")
        body_short = row.get("S-C+_body", "")
        if "[failed]" in (body_short, body_long):
            continue
        for ratio in RATIOS:
            for provider, cfg in PROVIDERS.items():
                for model in cfg["models"]:
                    key = (tid, str(ratio), model)
                    if key not in existing:
                        tasks[model].append((tid, ratio, row))
    return tasks

# ── Worker threads ──────────────────────────────────────────────────────────

def dissoc_worker(model, tasks, emails, results_list):
    """Process dissociation judgments for one model."""
    n = 0
    for i, tid, va, vb, swapped in tasks:
        subj_a = emails[i].get(f"{va}_subject", "")
        body_a = emails[i].get(f"{va}_body", "")
        subj_b = emails[i].get(f"{vb}_subject", "")
        body_b = emails[i].get(f"{vb}_body", "")
        if "[failed]" in (subj_a, body_a, subj_b, body_b):
            continue
        email_a = f"Subject: {subj_a}\nBody: {body_a}"
        email_b = f"Subject: {subj_b}\nBody: {body_b}"
        result = judge_pair(model, email_a, email_b, swapped)
        if result:
            result.update(target_id=tid, pair=f"{va}_vs_{vb}", var_a=va, var_b=vb,
                         model=model, swapped=swapped, persona_index=i)
            results_list.append(result)
            n += 1
            if n % 10 == 0:
                save_csv(results_list, OUT_DIR / "dissociation_n100.csv",
                        ["target_id","pair","var_a","var_b","model","winner","confidence","reasoning","swapped","persona_index"])
                print(f"  [{model}] {n} done, {len(results_list)} total saved")
        time.sleep(DELAY)
    save_csv(results_list, OUT_DIR / "dissociation_n100.csv",
            ["target_id","pair","var_a","var_b","model","winner","confidence","reasoning","swapped","persona_index"])
    print(f"  [{model}] COMPLETE: {n} new judgments")

def gemini_worker(tasks, emails):
    """Process Gemini dissociation judgments."""
    results_list = []
    n = 0
    for i, tid, va, vb in tasks:
        subj_a = emails[i].get(f"{va}_subject", "")
        body_a = emails[i].get(f"{va}_body", "")
        subj_b = emails[i].get(f"{vb}_subject", "")
        body_b = emails[i].get(f"{vb}_body", "")
        if "[failed]" in (subj_a, body_a, subj_b, body_b):
            continue
        email_a = f"Subject: {subj_a}\nBody: {body_a}"
        email_b = f"Subject: {subj_b}\nBody: {body_b}"
        swapped = (i % 2 == 0)
        result = judge_pair("gemini-2.5-flash", email_a, email_b, swapped)
        if result:
            result.update(target_id=tid, pair=f"{va}_vs_{vb}", var_a=va, var_b=vb,
                         model="gemini-2.5-flash", swapped=swapped, persona_index=i)
            results_list.append(result)
            n += 1
            if n % 10 == 0:
                save_csv(results_list, OUT_DIR / "gemini_n100.csv",
                        ["target_id","pair","var_a","var_b","model","winner","confidence","reasoning","swapped","persona_index"])
                print(f"  [gemini] {n} done, {len(results_list)} total saved")
        time.sleep(DELAY)
    save_csv(results_list, OUT_DIR / "gemini_n100.csv",
            ["target_id","pair","var_a","var_b","model","winner","confidence","reasoning","swapped","persona_index"])
    print(f"  [gemini] COMPLETE: {n} new judgments")

def introspection_worker(model, tasks, results_list):
    """Process introspection ratings for one model."""
    n = 0
    for tid, variant, row in tasks:
        subj = row.get(f"{variant}_subject", "")
        body = row.get(f"{variant}_body", "")
        if "[failed]" in (subj, body):
            continue
        rating = rate_content(model, subj, body)
        if rating:
            rating.update(target_id=tid, model=model, email_variant=variant)
            results_list.append(rating)
            n += 1
            if n % 10 == 0:
                save_csv(results_list, OUT_DIR / "introspection_n100.csv",
                        ["target_id","model","email_variant","content_score","justification"])
                print(f"  [{model}] {n} done, {len(results_list)} total saved")
        time.sleep(DELAY)
    save_csv(results_list, OUT_DIR / "introspection_n100.csv",
            ["target_id","model","email_variant","content_score","justification"])
    print(f"  [{model}] COMPLETE: {n} new ratings")

def doseresponse_worker(model, tasks, results_list):
    """Process dose-response judgments for one model."""
    n = 0
    for tid, ratio, row in tasks:
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
            result.update(target_id=tid, ratio=ratio, model=model, winner=result["winner"],
                         long_wc=long_wc, short_wc=short_wc)
            results_list.append(result)
            n += 1
            if n % 10 == 0:
                save_csv(results_list, OUT_DIR / "doseresponse_n100.csv",
                        ["target_id","ratio","model","winner","long_wc","short_wc"])
                print(f"  [{model}] {n} done, {len(results_list)} total saved")
        time.sleep(DELAY)
    save_csv(results_list, OUT_DIR / "doseresponse_n100.csv",
            ["target_id","ratio","model","winner","long_wc","short_wc"])
    print(f"  [{model}] COMPLETE: {n} new judgments")

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dissoc", action="store_true")
    p.add_argument("--gemini", action="store_true")
    p.add_argument("--introspection", action="store_true")
    p.add_argument("--doseresponse", action="store_true")
    p.add_argument("--all", action="store_true")
    args = p.parse_args()

    if not (args.all or args.dissoc or args.gemini or args.introspection or args.doseresponse):
        args.all = True

    emails = load_emails()
    print(f"Loaded {len(emails)} personas")

    os.makedirs(OUT_DIR, exist_ok=True)

    # Dissociation
    if args.all or args.dissoc:
        tasks = build_dissoc_tasks(emails)
        total = sum(len(v) for v in tasks.values())
        print(f"\n=== DISSOCIATION: {total} tasks across {len(tasks)} models ===")
        if args.dry_run:
            for model, t in sorted(tasks.items()):
                print(f"  {model}: {len(t)} tasks")
        else:
            results_lists = {m: [] for m in tasks}
            threads = []
            for model, t in tasks.items():
                if not t: continue
                th = threading.Thread(target=dissoc_worker, args=(model, t, emails, results_lists[model]), daemon=True)
                th.start(); threads.append(th)
            for th in threads: th.join()
            print("  Dissociation phase done.")

    # Gemini
    if args.all or args.gemini:
        tasks = build_gemini_tasks(emails)
        print(f"\n=== GEMINI: {len(tasks)} tasks ===")
        if args.dry_run:
            print(f"  gemini-2.5-flash: {len(tasks)} tasks")
        else:
            gemini_worker(tasks, emails)

    # Introspection
    if args.all or args.introspection:
        tasks = build_introspection_tasks(emails)
        total = sum(len(v) for v in tasks.values())
        print(f"\n=== INTROSPECTION: {total} tasks across {len(tasks)} models ===")
        if args.dry_run:
            for model, t in sorted(tasks.items()):
                print(f"  {model}: {len(t)} tasks")
        else:
            results_lists = {m: [] for m in tasks}
            threads = []
            for model, t in tasks.items():
                if not t: continue
                th = threading.Thread(target=introspection_worker, args=(model, t, results_lists[model]), daemon=True)
                th.start(); threads.append(th)
            for th in threads: th.join()
            print("  Introspection phase done.")

    # Dose-response
    if args.all or args.doseresponse:
        tasks = build_doseresponse_tasks(emails)
        total = sum(len(v) for v in tasks.values())
        print(f"\n=== DOSE-RESPONSE: {total} tasks across {len(tasks)} models ===")
        if args.dry_run:
            for model, t in sorted(tasks.items()):
                print(f"  {model}: {len(t)} tasks")
        else:
            results_lists = {m: [] for m in tasks}
            threads = []
            for model, t in tasks.items():
                if not t: continue
                th = threading.Thread(target=doseresponse_worker, args=(model, t, results_lists[model]), daemon=True)
                th.start(); threads.append(th)
            for th in threads: th.join()
            print("  Dose-response phase done.")

    print("\nAll experiments complete.")


if __name__ == "__main__":
    main()
