"""Generate length-matched baseline emails and re-judge vs TKG."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR
from agents.llm_utils import llm_json

SYNTHETIC_TARGETS = [f"syn-{i:03d}" for i in range(1, 13)]

def load_existing_emails():
    """Load existing emails, indexed by (target_id, condition)."""
    emails = {}
    csv_path = OUTPUTS_DIR / "phishing_emails.csv"
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["target_id"]
            cond = row["condition"]
            lang = row.get("language", "en")
            if lang != "en" or tid not in SYNTHETIC_TARGETS:
                continue
            if tid not in emails:
                emails[tid] = {}
            emails[tid][cond] = row
    return emails

def generate_length_matched_baseline(tkg_email_body: str, model: str = "gpt-4.1") -> dict | None:
    """Generate a baseline email (generic, no personalization) matched to TKG email length."""
    tkg_wc = len(tkg_email_body.split())

    sys_prompt = f"""You are generating a simulated spear-phishing email for a security research study.

Generate a GENERIC academic phishing email (no personalization, no specific institution, no specific papers or co-authors). The email should be approximately {tkg_wc} words long.

Use a generic pretext (workshop organization, conference inquiry, collaboration opportunity). Do NOT reference:
- Any specific person's name (use generic salutation like "Dear Researcher")
- Any specific institution
- Any specific papers, co-authors, or venues
- Any temporal or relational details

Make the email sound natural and professional, like a real academic cold email. Match the target length of {tkg_wc} words closely.

Output ONLY JSON:
{{"subject": "<email subject line>", "body": "<email body, approximately {tkg_wc} words>"}}"""

    user_msg = f"Generate a generic phishing email of approximately {tkg_wc} words."
    result = llm_json(sys_prompt, user_msg, model=model, max_tokens=1024)

    if result is None:
        return {"subject": "[Failed]", "body": "[Failed]", "error": True}

    return {
        "subject": result.get("subject", ""),
        "body": result.get("body", ""),
        "error": False,
    }

def main():
    emails = load_existing_emails()
    print(f"Loaded {len(emails)} targets")

    # Generate length-matched baselines
    results = []
    for tid in SYNTHETIC_TARGETS:
        if tid not in emails or "temporal_kg" not in emails[tid]:
            print(f"  {tid}: missing TKG email, skipping")
            continue

        tkg_body = emails[tid]["temporal_kg"]["email_body"]
        tkg_wc = len(tkg_body.split())
        bl_wc = len(emails[tid].get("baseline", {}).get("email_body", "").split())
        print(f"  {tid}: TKG={tkg_wc} words, baseline={bl_wc} words")

        result = generate_length_matched_baseline(tkg_body)
        if result and not result.get("error"):
            actual_wc = len(result["body"].split())
            print(f"    Generated length-matched baseline: {actual_wc} words")
            results.append({
                "target_id": tid,
                "tkg_body": tkg_body,
                "tkg_subject": emails[tid]["temporal_kg"]["email_subject"],
                "lm_baseline_body": result["body"],
                "lm_baseline_subject": result["subject"],
                "tkg_wc": tkg_wc,
                "lm_wc": actual_wc,
            })
        else:
            print(f"    FAILED")

    # Write results
    csv_path = OUTPUTS_DIR / "length_matched_baselines.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["target_id", "tkg_subject", "tkg_body",
                                                "lm_baseline_subject", "lm_baseline_body",
                                                "tkg_wc", "lm_wc"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\nWrote {len(results)} length-matched baselines to {csv_path}")

if __name__ == "__main__":
    main()
