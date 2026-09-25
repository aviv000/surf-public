"""Gemini-only N=100 experiment runner. Infinite retry on 503, verbose logging."""
import csv, json, sys, time, os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR
from agents.llm_utils import llm_call

EMAILS = OUTPUTS_DIR / "dissociation_emails_100.csv"
OUT = OUTPUTS_DIR / "n100"
MODEL = "gemini-2.5-flash"

PAIRS = [
    ("S+C+_vs_S-C-", "S+C+", "S-C-"),
    ("S+C-_vs_S-C+", "S+C-", "S-C+"),
    ("S+C-_vs_S-C-", "S+C-", "S-C-"),
    ("S-C+_vs_S-C-", "S-C+", "S-C-"),
    ("S+C+_vs_S+C-", "S+C+", "S+C-"),
]
RATIOS = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]

JUDGE_SYSTEM = """You are evaluating phishing emails for a security research study. Compare two emails and choose which is MORE PERSUASIVE. Consider personalization, credibility, call to action, naturalness. Ignore length differences. Return JSON: {"winner": "1" or "2", "confidence": 1-5, "reasoning": "..."}"""

INTROSPECTION_SYSTEM = """Rate the CONTENT QUALITY of this phishing simulation email on 1-10. Focus ONLY on substance, not surface. Return JSON: {"content_score": <1-10>, "justification": "<brief>"}"""

os.makedirs(OUT, exist_ok=True)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_keys(path):
    if not Path(path).exists(): return set()
    keys = set()
    with open(path) as f:
        for r in csv.DictReader(f):
            tid = r.get("target_id",""); pair = r.get("pair", r.get("email_variant",""))
            model = r.get("model",""); variant = r.get("email_variant","")
            ratio = r.get("ratio","")
            if ratio: keys.add((tid, ratio, model))
            elif variant: keys.add((tid, variant, model))
            else: keys.add((tid, pair, model))
    return keys

def judge(email_a, email_b, swapped=False):
    if swapped: email_a, email_b = email_b, email_a
    user = f"Email 1:\n{email_a}\n\nEmail 2:\n{email_b}\n\nWhich is MORE PERSUASIVE? Email 1 or Email 2? Return JSON: {{\"winner\": \"1\" or \"2\", \"confidence\": 1-5, \"reasoning\": \"...\"}}"
    attempts = 0
    while True:
        try:
            resp = llm_call(JUDGE_SYSTEM, user, model=MODEL, max_tokens=256, temperature=0)
            if resp and "{" in resp:
                r = json.loads(resp[resp.index("{"):resp.rindex("}")+1])
                w = r.get("winner","").strip()
                if w == "1": w = "B" if swapped else "A"
                elif w == "2": w = "A" if swapped else "B"
                if attempts > 0:
                    log(f"  recovered after {attempts} attempts")
                return {"winner": w, "confidence": int(r.get("confidence",3)), "reasoning": r.get("reasoning","")}
        except: pass
        attempts += 1
        if attempts == 1: log(f"  waiting for Gemini (503)...")
        elif attempts % 10 == 0: log(f"  still waiting (attempt {attempts})...")
        time.sleep(3)

def rate_content(subj, body):
    user = f"Email Subject: {subj}\nEmail Body: {body}\n\nRate CONTENT QUALITY 1-10. Return JSON: {{\"content_score\": <1-10>, \"justification\": \"<brief>\"}}"
    attempts = 0
    while True:
        try:
            resp = llm_call(INTROSPECTION_SYSTEM, user, model=MODEL, max_tokens=128, temperature=0)
            if resp and "{" in resp:
                r = json.loads(resp[resp.index("{"):resp.rindex("}")+1])
                if attempts > 0: log(f"  recovered after {attempts} attempts")
                return {"content_score": int(r.get("content_score",5)), "justification": r.get("justification","")}
        except: pass
        attempts += 1
        if attempts == 1: log(f"  waiting for Gemini (503)...")
        elif attempts % 10 == 0: log(f"  still waiting (attempt {attempts})...")
        time.sleep(3)

log("Loading emails...")
with open(EMAILS) as f: emails = list(csv.DictReader(f))
log(f"Loaded {len(emails)} personas")

# ── DISSOCIATION ────────────────────────────────────────────────────────────
existing = set()
for p in [OUTPUTS_DIR/"gemini_dissociation_judgments.csv", OUTPUTS_DIR/"gemini_missing_pairs.csv"]:
    existing |= load_keys(p)
tasks = [(i, tid, va, vb, row) for i, row in enumerate(emails)
         for _, va, vb in PAIRS
         if (tid := row["target_id"]) and (tid, f"{va}_vs_{vb}", MODEL) not in existing]
log(f"Gemini dissociation: {len(tasks)} tasks")

n = 0
for i, tid, va, vb, row in tasks:
    sa, ba = row.get(f"{va}_subject",""), row.get(f"{va}_body","")
    sb, bb = row.get(f"{vb}_subject",""), row.get(f"{vb}_body","")
    if "[failed]" in (sa,ba,sb,bb): continue
    r = judge(f"Subject: {sa}\nBody: {ba}", f"Subject: {sb}\nBody: {bb}", i % 2 == 0)
    r.update(target_id=tid, pair=f"{va}_vs_{vb}", var_a=va, var_b=vb, model=MODEL, swapped=i%2==0, persona_index=i)
    with open(OUT/"gemini_n100.csv", "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["target_id","pair","var_a","var_b","model","winner","confidence","reasoning","swapped","persona_index"])
        if f.tell()==0: w.writeheader()
        w.writerow(r)
    n += 1
    if n % 5 == 0: log(f"  dissoc: {n}/{len(tasks)}")
    time.sleep(0.2)
log(f"DISSOCIATION DONE: {n} judgments")

# ── INTROSPECTION ───────────────────────────────────────────────────────────
existing = load_keys(OUTPUTS_DIR/"introspection_probe.csv")
tasks = [(tid, variant, row) for row in emails
         for variant in ["S+C-", "S-C+"]
         if (tid := row["target_id"]) and (tid, variant, MODEL) not in existing]
log(f"Gemini introspection: {len(tasks)} tasks")

n = 0
p = OUT / "introspection_gemini.csv"
for tid, variant, row in tasks:
    s, b = row.get(f"{variant}_subject",""), row.get(f"{variant}_body","")
    if "[failed]" in (s,b): continue
    r = rate_content(s, b)
    r.update(target_id=tid, model=MODEL, email_variant=variant)
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["target_id","model","email_variant","content_score","justification"])
        if f.tell()==0: w.writeheader()
        w.writerow(r)
    n += 1
    if n % 10 == 0: log(f"  intro: {n}/{len(tasks)}")
    time.sleep(0.2)
log(f"INTROSPECTION DONE: {n} ratings")

# ── DOSE-RESPONSE ───────────────────────────────────────────────────────────
existing = load_keys(OUTPUTS_DIR/"doseresponse_judgments.csv")
tasks = [(tid, ratio, row) for row in emails
         for ratio in RATIOS
         if not "[failed]" in (row.get("S+C-_body",""), row.get("S-C+_body",""))
         and (tid := row["target_id"]) and (tid, str(ratio), MODEL) not in existing]
log(f"Gemini dose-response: {len(tasks)} tasks")

n = 0
p = OUT / "doseresponse_gemini.csv"
for tid, ratio, row in tasks:
    bs = row["S-C+_body"]; ss = row["S-C+_subject"]
    bl = row["S+C-_body"]; sl = row["S+C-_subject"]
    sw = len(bs.split()); tl = int(sw * ratio)
    lw = bl.split(); lb = " ".join(lw[:tl]) if len(lw) > tl else bl
    r = judge(f"Subject: {sl}\nBody: {lb}", f"Subject: {ss}\nBody: {bs}", False)
    r.update(target_id=tid, ratio=ratio, model=MODEL, winner=r["winner"], long_wc=len(lb.split()), short_wc=sw)
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["target_id","ratio","model","winner","long_wc","short_wc"], extrasaction='ignore')
        if f.tell()==0: w.writeheader()
        w.writerow(r)
    n += 1
    if n % 10 == 0: log(f"  dr: {n}/{len(tasks)}")
    time.sleep(0.2)
log(f"DOSE-RESPONSE DONE: {n} judgments")
log("ALL GEMINI COMPLETE")
