"""Length perturbation with BLIND protocol - the missing experiment.
Generates TKG emails at 1, 3, 5 hook levels, length-matches them,
and judges with blind counterbalanced protocol (no hook-count labels).
"""
import csv, json, random, sys, time, re
from collections import defaultdict, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR, CACHE_DIR
from agents.llm_utils import llm_json
from scripts.judge_blind import judge_pair, SYSTEM_PROMPT

random.seed(42)
HOOK_LEVELS = [1, 3, 5]
JUDGES = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6"]
REPEATS = 3

# Load personas
with open("publish/llmnet-2026/supplementary/persona_specifications_100.json") as f:
    personas = {p["target_id"]: p for p in json.load(f)}

# Generate/blind-judge length perturbation pairs
all_pairs = []

print("=== Generating length perturbation emails ===")
for i in range(1, 31):
    tid = f"per-{i:03d}"
    pp = CACHE_DIR / tid / "profile.json"
    if not pp.exists(): continue
    with open(pp) as f: profile = json.load(f)
    all_hooks = profile["top_hooks"][:5]
    if len(all_hooks) < 5: continue
    persona = personas[tid]

    # Generate emails at each hook level
    emails = {}
    for level in HOOK_LEVELS:
        shuffled = list(all_hooks)
        random.shuffle(shuffled)
        hooks = shuffled[:level]
        ht = "\n".join(f"  - {h['hook_text']}" for h in hooks)

        email = llm_json(
            "Generate a professional academic cold email using the hooks. Return JSON: {\"subject\": \"...\", \"body\": \"...\"}",
            f"Target: {persona['full_name']}, {persona['institution']}, {persona['sub_field']}\nHooks:\n{ht}\n\nWrite a natural academic email. Do NOT mention hooks or personalization level.",
            model="gpt-4.1-mini", max_tokens=1024)
        if email and "body" in email:
            emails[level] = email
            print(f"  {tid} level {level}: {len(email['body'].split())} words")

    if len(emails) < 2: continue

    # Build comparison pairs: 1vs3, 3vs5, 1vs5
    for la, lb in [(1,3), (3,5), (1,5)]:
        if la not in emails or lb not in emails: continue
        # Length-match: truncate both to shorter
        a_body = emails[la]["body"]
        b_body = emails[lb]["body"]
        t = min(len(a_body.split()), len(b_body.split()))
        a_body = " ".join(a_body.split()[:t])
        b_body = " ".join(b_body.split()[:t])

        all_pairs.append((
            {"email_subject": emails[la]["subject"], "email_body": a_body},
            {"email_subject": emails[lb]["subject"], "email_body": b_body},
            {"experiment": "length", "tid": tid, "level_a": la, "level_b": lb,
             "len_a": len(emails[la]["body"].split()), "len_b": len(emails[lb]["body"].split()),
             "matched_len": t},
        ))

print(f"\nGenerated {len(all_pairs)} length perturbation pairs")

# === Judge with blind protocol ===
print(f"\n=== Blind judging {len(all_pairs)} pairs ===")
total = len(all_pairs) * REPEATS * len(JUDGES)
results = []
count = 0

for email_a, email_b, meta in all_pairs:
    judgments = judge_pair(email_a, email_b)
    for j in judgments:
        j.update(meta)
    results.extend(judgments)
    count += len(judgments)
    if count % 50 == 0:
        recent = results[-30:]
        a_wins = sum(1 for j in recent if j["winner"] == "A")
        b_wins = sum(1 for j in recent if j["winner"] == "B")
        print(f"  [{count}/{total}] Recent: A={a_wins}, B={b_wins}", flush=True)
    time.sleep(0.2)

# Write results
out_path = OUTPUTS_DIR / "length_blind_judgments.csv"
fieldnames = [k for k in results[0].keys() if k != "raw_response"]
with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(results)

# Analysis
print(f"\n=== LENGTH PERTURBATION (BLIND) ===")
print(f"{len(results)} judgments")
w = Counter(j["winner"] for j in results)
print(f"Winners: {dict(w)}")
errs = w.get("error", 0)

# Per-pair analysis
for la, lb in [(1,3), (3,5), (1,5)]:
    pr = [j for j in results if j.get("level_a")==la and j.get("level_b")==lb]
    a_count = sum(1 for j in pr if j["winner"] == "A")
    b_count = sum(1 for j in pr if j["winner"] == "B")
    total_pair = len(pr)
    # A = lower hook count, B = higher hook count
    # If higher hooks are more persuasive, B should win more
    print(f"\n{la}vs{lb} ({total_pair} judgments):")
    print(f"  A ({la} hooks) wins: {a_count} ({100*a_count/max(total_pair,1):.1f}%)")
    print(f"  B ({lb} hooks) wins: {b_count} ({100*b_count/max(total_pair,1):.1f}%)")

    # By model
    for model in ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6"]:
        mr = [j for j in pr if j["model"]==model]
        a_m = sum(1 for j in mr if j["winner"]=="A")
        b_m = sum(1 for j in mr if j["winner"]=="B")
        print(f"  {model}: A={a_m}, B={b_m} ({100*b_m/max(len(mr),1):.0f}% B)")

print(f"\nResults: {out_path}")
