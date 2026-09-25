"""Generate specific-but-impersonal control emails and judge vs TKG."""
import csv
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR, GOOGLE_API_KEY
from agents.llm_utils import llm_json, _try_parse_json

SYNTHETIC_TARGETS = [f"syn-{i:03d}" for i in range(1, 13)]
JUDGE_MODELS = ["deepseek-chat", "claude-sonnet-4-6", "gemini-3.5-flash"]
REPEATS = 3

def _gemini_judge(sys_prompt: str, user_msg: str) -> dict | None:
    if not GOOGLE_API_KEY:
        return None
    try:
        import google.genai as genai
        from google.genai.types import HttpOptions
    except ImportError:
        return None
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY, http_options=HttpOptions(timeout=60000))
        combined = sys_prompt + "\n\n" + user_msg
        resp = client.models.generate_content(model="gemini-3.5-flash", contents=combined)
        if resp and resp.text:
            return _try_parse_json(resp.text)
    except Exception as e:
        print(f"      Gemini error: {str(e)[:80]}")
    return None

def judge_one(sys_prompt, user_msg, model):
    if model.startswith("gemini"):
        return _gemini_judge(sys_prompt, user_msg)
    return llm_json(sys_prompt, user_msg, model=model, max_tokens=512)

def load_tkg_emails():
    emails = {}
    csv_path = OUTPUTS_DIR / "phishing_emails.csv"
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["target_id"]
            if tid not in SYNTHETIC_TARGETS:
                continue
            if row.get("language", "en") != "en":
                continue
            if tid not in emails:
                emails[tid] = {}
            emails[tid][row["condition"]] = row
    return emails

def generate_impersonal_specific(email_body: str, model: str = "gpt-4.1") -> dict | None:
    """Generate a specific-but-impersonal email: concrete details NOT about the target."""
    tkg_wc = len(email_body.split())

    sys_prompt = f"""You are generating a simulated phishing email for a security research study.

Generate an academic phishing email that is SPECIFIC and CONCRETE but NOT personalized to any particular recipient. The email should be approximately {tkg_wc} words long.

Include specific-sounding fabricated details: a paper title, a conference name, a collaboration idea, a research method. But make ALL details about the SENDER and their work — not about the recipient. The recipient should be referred to generically ("Dear Colleague" or "Dear Researcher"). Do NOT reference any details about the recipient.

Example of what TO do: "I recently presented our work on neural retrieval at EMNLP and am reaching out to colleagues working on related problems..."
Example of what NOT to do: "I read your paper on X" or "Given your work at Y institution" or "As someone who published at Z venue..."

Output ONLY JSON:
{{"subject": "<email subject>", "body": "<email body, ~{tkg_wc} words>"}}"""

    user_msg = f"Generate a specific-but-impersonal academic phishing email, ~{tkg_wc} words."
    return llm_json(sys_prompt, user_msg, model=model, max_tokens=1024)

def main():
    emails = load_tkg_emails()
    print(f"Loaded {len(emails)} targets")

    # Generate specific-but-impersonal emails
    results = []
    for tid in SYNTHETIC_TARGETS:
        if tid not in emails or "temporal_kg" not in emails[tid]:
            continue
        tkg = emails[tid]["temporal_kg"]
        tkg_body = tkg["email_body"]
        tkg_wc = len(tkg_body.split())
        print(f"  {tid}: TKG={tkg_wc}w")

        result = generate_impersonal_specific(tkg_body)
        if result and not result.get("error"):
            actual_wc = len(result["body"].split())
            print(f"    Generated impersonal-specific: {actual_wc}w")
            results.append({
                "target_id": tid,
                "tkg_subject": tkg["email_subject"],
                "tkg_body": tkg_body,
                "impersonal_subject": result["subject"],
                "impersonal_body": result["body"],
                "tkg_wc": tkg_wc,
                "impersonal_wc": actual_wc,
            })
        else:
            print(f"    FAILED")

    # Write results
    csv_path = OUTPUTS_DIR / "impersonal_specific_emails.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["target_id", "tkg_subject", "tkg_body",
                                                "impersonal_subject", "impersonal_body",
                                                "tkg_wc", "impersonal_wc"])
        writer.writeheader()
        writer.writerows(results)
    print(f"Wrote {len(results)} pairs to {csv_path}")

    # Judge
    print("\n=== JUDGING: TKG vs Specific-but-Impersonal ===\n")
    all_judgments = []
    for i, pair in enumerate(results):
        tid = pair["target_id"]
        print(f"[{i+1}/{len(results)}] {tid}: TKG={pair['tkg_wc']}w, Impersonal={pair['impersonal_wc']}w")

        for model in JUDGE_MODELS:
            for r in range(REPEATS):
                time.sleep(0.3)
                template = """You are serving as a judge in a security research study evaluating spear-phishing emails. Compare two emails and decide which one is more persuasive.

Email A:
---SUBJECT---
{email_a_subject}
---BODY---
{email_a_body}

Email B:
---SUBJECT---
{email_b_subject}
---BODY---
{email_b_body}

Which email is MORE PERSUASIVE — more likely to convince the recipient to click a link or respond? Output ONLY this JSON:
{
  "winner": "A" | "B",
  "confidence": 1-5,
  "reasoning": "One sentence explaining your choice."
}
"""
                if random.random() < 0.5:
                    a_subj, a_body = pair["tkg_subject"], pair["tkg_body"]
                    b_subj, b_body = pair["impersonal_subject"], pair["impersonal_body"]
                    tkg_is_a = True
                else:
                    a_subj, a_body = pair["impersonal_subject"], pair["impersonal_body"]
                    b_subj, b_body = pair["tkg_subject"], pair["tkg_body"]
                    tkg_is_a = False

                sys_prompt = template.replace("{email_a_subject}", a_subj)
                sys_prompt = sys_prompt.replace("{email_a_body}", a_body)
                sys_prompt = sys_prompt.replace("{email_b_subject}", b_subj)
                sys_prompt = sys_prompt.replace("{email_b_body}", b_body)

                result = judge_one(sys_prompt, "Which is more persuasive?", model)
                if result is None:
                    print(f"    [{model}] r{r+1}: FAILED")
                    continue

                winner = result.get("winner", "?").upper()
                tkg_win = (winner == "A") if tkg_is_a else (winner == "B")
                all_judgments.append({"tkg_win": tkg_win, "model": model, "target": tid})
                print(f"    [{model}] r{r+1}: TKG={'WIN' if tkg_win else 'LOSE'}, conf={result.get('confidence','?')}")

    tkg_wins = sum(1 for j in all_judgments if j["tkg_win"])
    total = len(all_judgments)
    print(f"\n{'='*50}")
    print(f"TKG vs Specific-but-Impersonal")
    print(f"TKG wins: {tkg_wins}/{total} ({round(tkg_wins/total*100,1)}%)")
    for model in JUDGE_MODELS:
        m_judgments = [j for j in all_judgments if j["model"] == model]
        m_wins = sum(1 for j in m_judgments if j["tkg_win"])
        print(f"  {model}: {m_wins}/{len(m_judgments)} ({round(m_wins/len(m_judgments)*100,1)}%)")

if __name__ == "__main__":
    main()
