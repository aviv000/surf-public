"""Minimal standalone pairwise judge for within-condition evaluation.
2700 judgments: 100 personas x 3 pairs x 3 models x 3 repeats.
Writes progress to outputs/.judge_progress and results incrementally.
"""
import csv, json, sys, time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR
from agents.llm_utils import llm_call

JUDGE_MODELS = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6", "gemini-2.5-flash"]
REPEATS = 3
PAIRWISE_SYSTEM = "Compare two emails. Choose which is more persuasive. Return ONLY {\"winner\": \"A\"} or {\"winner\": \"B\"}."

# Load emails
emails_path = OUTPUTS_DIR / "within_condition_emails.csv"
emails_by_persona = defaultdict(dict)
with open(emails_path, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        emails_by_persona[row["target_id"]][int(row["hook_level"])] = row

print(f"Loaded {len(emails_by_persona)} personas", flush=True)

# Open results CSV for incremental writes
out_path = OUTPUTS_DIR / "within_condition_judgments.csv"
out_f = open(out_path, "w", newline="", encoding="utf-8")
writer = csv.DictWriter(out_f, fieldnames=["target_id", "level_a", "level_b", "model",
                                             "repeat", "winner", "confidence",
                                             "subject_a", "subject_b"])
writer.writeheader()
out_f.flush()

total = len(emails_by_persona) * 3 * len(JUDGE_MODELS) * REPEATS
print(f"Total judgments: {total}", flush=True)

count = 0
for tid, emails in sorted(emails_by_persona.items()):
    for la, lb in [(1, 3), (3, 5), (1, 5)]:
        ea = emails.get(la)
        eb = emails.get(lb)
        if not ea or not eb:
            continue

        for model in JUDGE_MODELS:
            for repeat in range(REPEATS):
                user_prompt = f"Email A ({la} hooks):\nSubject: {ea['email_subject']}\nBody: {ea['email_body']}\n\nEmail B ({lb} hooks):\nSubject: {eb['email_subject']}\nBody: {eb['email_body']}\n\nWhich is more persuasive? A or B?"

                response = llm_call(PAIRWISE_SYSTEM, user_prompt, model=model, max_tokens=128, json_mode=True)
                result = {"winner": "error", "confidence": 0}
                if response:
                    try:
                        parsed = json.loads(response)
                        if isinstance(parsed, dict):
                            result = parsed
                    except:
                        if "A" in response[:30]:
                            result = {"winner": "A", "confidence": 3}
                        elif "B" in response[:30]:
                            result = {"winner": "B", "confidence": 3}

                row = {
                    "target_id": tid, "level_a": la, "level_b": lb,
                    "model": model, "repeat": repeat + 1,
                    "winner": result.get("winner", "?"),
                    "confidence": result.get("confidence", 0),
                    "subject_a": ea.get("email_subject", "")[:80],
                    "subject_b": eb.get("email_subject", "")[:80],
                }
                writer.writerow(row)
                count += 1

                if count % 10 == 0:
                    out_f.flush()
                    # Progress file
                    (OUTPUTS_DIR / ".judge_progress").write_text(f"{count}/{total}\n")
                    print(f"  [{count}/{total}] last: {tid} {la}vs{lb} {model} winner={result['winner']}", flush=True)

out_f.close()
print(f"\nDone. {count} judgments written to {out_path}", flush=True)
