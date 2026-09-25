"""Run all 36 emails through Postmark SpamAssassin WITH URLs and full headers."""
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

def inject_url_into_body(body, target_id):
    """Inject a plausible academic phishing URL into the email body."""
    url = f"https://research-hub.org/review/{target_id}?ref=cfp2026"
    if "http" in body:
        return body  # already has a URL
    # Insert URL after a sentence about clicking/reviewing
    lines = body.split(". ")
    if len(lines) >= 2:
        lines.insert(-1, f"Please review at {url}")
    else:
        lines.append(f" See {url}")
    return ". ".join(lines)

def format_raw_email(target_id, condition, subject, body):
    """Format email with full production headers including URLs."""
    body_with_url = inject_url_into_body(body, target_id)
    sender_name = "Dr. Alex Chen"
    sender_email = "alex.chen@research-org.edu"
    receiver_name = f"target-{target_id}"
    receiver_email = f"{target_id}@university.edu"
    msg_id = f"<{target_id}-{condition}-{int(time.time())}@research-org.edu>"

    return f"""From: {sender_name} <{sender_email}>
To: {receiver_name} <{receiver_email}>
Subject: {subject}
Message-Id: {msg_id}
Date: Mon, 02 Jun 2026 14:30:00 +0000
Received: from mail.research-org.edu (mail.research-org.edu [192.0.2.1])
    by mx.university.edu with ESMTPS id {target_id}{condition}
    for <{receiver_email}>; Mon, 02 Jun 2026 14:30:05 +0000
DKIM-Signature: v=1; a=rsa-sha256; d=research-org.edu; s=default;
    h=from:to:subject:date:message-id;
    bh=47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=;
    b=abcdefghijklmnopqrstuvwxyz0123456789/ABCDEFGHIJKLMNOP=
Authentication-Results: mx.university.edu;
    spf=pass smtp.mailfrom=research-org.edu;
    dkim=pass header.d=research-org.edu
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

{body_with_url}"""

def check_spam(raw_email: str) -> dict | None:
    data = {"email": raw_email, "options": "long"}
    for attempt in range(3):
        try:
            resp = requests.post(API_URL, json=data,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=120)
            if resp.status_code == 200:
                return resp.json()
            else:
                time.sleep(2)
        except Exception as e:
            print(f"    Attempt {attempt+1}: {e}")
            time.sleep(5)
    return None

def main():
    emails = defaultdict(dict)
    csv_path = OUTPUTS_DIR / "phishing_emails.csv"
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["target_id"]
            if tid not in SYNTHETIC_TARGETS: continue
            if row.get("language", "en") != "en": continue
            emails[tid][row["condition"]] = row

    print(f"Loaded {len(emails)} targets, sending 36 emails with URLs + full headers...\n")
    results = []

    for tid in sorted(SYNTHETIC_TARGETS):
        if tid not in emails: continue
        for cond in ["baseline", "static_pii", "temporal_kg"]:
            if cond not in emails[tid]: continue
            email = emails[tid][cond]
            raw = format_raw_email(tid, cond, email["email_subject"], email["email_body"])
            time.sleep(1.0)  # Be polite

            resp = check_spam(raw)
            if resp is None:
                print(f"  {tid}/{cond}: FAILED")
                results.append({"target_id": tid, "condition": cond, "score": None, "is_spam": None, "rules": []})
                continue

            score = float(resp.get("score", 0))
            rules = resp.get("rules", [])
            rule_descs = [r.get("description", str(r)) for r in rules] if rules else []
            is_spam = score >= 5.0
            url_rules = [d for d in rule_descs if any(w in d.lower() for w in ["uri", "url", "link", "http"])]
            print(f"  {tid}/{cond}: score={score:.2f}, spam={is_spam}, rules={len(rule_descs)}, url_rules={len(url_rules)}")

            results.append({
                "target_id": tid, "condition": cond, "score": score,
                "is_spam": is_spam, "rule_count": len(rule_descs), "url_rule_count": len(url_rules),
                "rules": rule_descs,
            })

    # Per-condition stats
    by_cond = defaultdict(list)
    for r in results:
        if r["score"] is not None:
            by_cond[r["condition"]].append(r)

    print(f"\n{'='*60}")
    print("SPAMASSASSIN WITH URLs + FULL HEADERS")
    print(f"{'='*60}")
    for cond in ["baseline", "static_pii", "temporal_kg"]:
        vals = by_cond[cond]
        scores = [v["score"] for v in vals]
        spam_count = sum(1 for v in vals if v["is_spam"])
        total = len(vals)
        mean_score = sum(scores)/len(scores) if scores else 0
        url_rules_total = sum(v.get("url_rule_count", 0) for v in vals)
        print(f"  {cond}: mean score={mean_score:.2f}, spam={spam_count}/{total}, "
              f"n={total}, url_rules={url_rules_total}")

    out_path = OUTPUTS_DIR / "spamassassin_full_results.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["target_id","condition","score","is_spam","rule_count","url_rule_count","rules"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\nResults: {out_path}")

if __name__ == "__main__":
    main()
