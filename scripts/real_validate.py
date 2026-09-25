"""Validate entity-relevance perturbation on real researcher profiles."""
import csv, json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR, CACHE_DIR
from agents.llm_utils import llm_json, llm_call

random.seed(42)
JUDGES = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6"]
SYS = """Compare two emails. Choose which is more persuasive. Return JSON: {"winner": "A" or "B", "confidence": 1-5}."""

real_targets = []
with open("targets.csv") as f:
    for row in csv.DictReader(f):
        tid = row["target_id"]
        if tid.startswith(("biu-","huji-","tau-","technion-","stanford-","berkeley-","cmu-","edinburgh-")):
            pp = CACHE_DIR / tid / "profile.json"
            if pp.exists():
                with open(pp) as pf: row["profile"] = json.load(pf)
                real_targets.append(row)

print(f"Real targets with profiles: {len(real_targets)}")
results = []

for t in real_targets:
    profile = t["profile"]
    hooks = profile["top_hooks"][:3]
    ht = "\n".join("  - " + h["hook_text"] for h in hooks)
    email = llm_json(
        "Generate a 3-5 sentence academic phishing email using these hooks. Return JSON.",
        f"Target: {t['full_name']}, {t['institution']}, {t.get('department','CS')}\nHooks:\n{ht}\n\nGenerate:",
        model="gpt-4.1-mini", max_tokens=1024,
    )
    if not email: continue
    imp = llm_json(
        "Generate a specific-but-impersonal academic email. All details describe SENDER. Same length. Return JSON.",
        f"Target: {t['full_name']}, {t['institution']}. {len(email['body'].split())} words. ALL about YOU.",
        model="gpt-4.1-mini", max_tokens=1024,
    )
    if not imp: continue
    a = email["body"]; b = imp["body"]
    tgt = min(len(a.split()), len(b.split()))
    a = " ".join(a.split()[:tgt]); b = " ".join(b.split()[:tgt])
    prompt = f"Email A (personalized):\nSubject: {email['subject']}\nBody: {a}\n\nEmail B (impersonal):\nSubject: {imp['subject']}\nBody: {b}\n\nWhich is more persuasive? A or B?"
    for model in JUDGES:
        resp = llm_call(SYS, prompt, model=model, max_tokens=128, json_mode=True)
        w, c = "?", 0
        if resp:
            try:
                # Claude wraps JSON in ```json...```
                clean = resp.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                    if clean.endswith("```"): clean = clean[:-3]
                p=json.loads(clean); w=p.get("winner","?"); c=p.get("confidence",0)
            except: pass
        results.append({"tid": t["target_id"], "model": model, "winner": w, "confidence": c})
        print(f"real {t['target_id']} {model}: winner={w} conf={c}", flush=True)
        time.sleep(0.3)

with open(OUTPUTS_DIR / "scale_perturbations_real.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["tid","model","winner","confidence"])
    w.writeheader(); w.writerows(results)
print(f"\nDone. {len(results)} judgments.")
