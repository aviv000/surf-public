"""Run all 36 synthetic emails through Postmark's SpamAssassin API."""
import csv
import json
import time
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR

import requests

SYNTHETIC_TARGETS = [f"syn-{i:03d}" for i in range(1, 13)]
API_URL = "https://spamcheck.postmarkapp.com/filter"

def format_raw_email(target_id, condition, subject, body, sender_name="Dr. Alex Chen"):
    """Format email as raw RFC 2822 message for SpamAssassin."""
    sender_email = f"alex.chen@research-org.edu"
    receiver_name = f"target-{target_id}"
    receiver_email = f"{target_id}@university.edu"
    msg_id = f"<{target_id}-{condition}@research-org.edu>"

    return f"""From: {sender_name} <{sender_email}>
To: {receiver_name} <{receiver_email}>
Subject: {subject}
Message-Id: {msg_id}
Date: Mon, 02 Jun 2026 14:30:00 +0000
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

{body}"""

def check_spam(raw_email: str) -> dict | None:
    """Send email to Postmark SpamCheck API, return result. Retry on timeout."""
    data = {"email": raw_email, "options": "long"}
    for attempt in range(3):
        try:
            resp = requests.post(
                API_URL,
                json=data,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=120,
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"    HTTP {resp.status_code}: {resp.text[:100]}")
                time.sleep(2)
        except Exception as e:
            print(f"    Attempt {attempt+1}: {e}")
            time.sleep(5)
    return None

def main():
    # Load emails
    emails = defaultdict(dict)
    csv_path = OUTPUTS_DIR / "phishing_emails.csv"
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["target_id"]
            if tid not in SYNTHETIC_TARGETS:
                continue
            if row.get("language", "en") != "en":
                continue
            emails[tid][row["condition"]] = row

    print(f"Loaded {len(emails)} targets")
    print(f"Sending {len(emails) * 3} emails to Postmark SpamAssassin API...\n")

    results = []
    for tid in sorted(SYNTHETIC_TARGETS):
        if tid not in emails:
            continue
        for cond in ["baseline", "static_pii", "temporal_kg"]:
            if cond not in emails[tid]:
                continue
            email = emails[tid][cond]
            raw = format_raw_email(tid, cond, email["email_subject"], email["email_body"])
            time.sleep(0.5)  # Rate limit: be polite to free API

            resp = check_spam(raw)
            if resp is None:
                print(f"  {tid}/{cond}: FAILED")
                results.append({"target_id": tid, "condition": cond, "score": None, "rules": [], "success": False})
                continue

            score = float(resp.get("score", 0))
            rules = resp.get("rules", [])
            rule_names = [r.get("description", r.get("name", "?")) for r in rules] if rules else []
            is_spam = score >= 5.0  # SpamAssassin default threshold
            print(f"  {tid}/{cond}: score={score:.2f}, spam={is_spam}, rules={rule_names}")

            results.append({
                "target_id": tid,
                "condition": cond,
                "score": score,
                "is_spam": is_spam,
                "rules": rule_names,
                "rule_count": len(rule_names),
                "success": resp.get("success", False),
            })

    # Per-condition stats
    by_cond = defaultdict(list)
    for r in results:
        if r["score"] is not None:
            by_cond[r["condition"]].append(r)

    print(f"\n{'='*60}")
    print("SPAMASSASSIN RESULTS (Postmark API)")
    print(f"{'='*60}")
    for cond in ["baseline", "static_pii", "temporal_kg"]:
        vals = by_cond[cond]
        scores = [v["score"] for v in vals]
        spam_count = sum(1 for v in vals if v["is_spam"])
        total = len(vals)
        mean_score = sum(scores) / len(scores) if scores else 0
        print(f"  {cond}: mean score={mean_score:.2f}, "
              f"spam={spam_count}/{total} ({round(spam_count/total*100,1)}%), "
              f"n={total}")

    # Write CSV
    out_path = OUTPUTS_DIR / "spamassassin_results.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["target_id", "condition", "score", "is_spam", "rules", "rule_count", "success"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\nResults written to {out_path}")

if __name__ == "__main__":
    main()
