"""Deterministic placeholder check for generated emails.

Checks a round package's emails.csv (or any email CSV) for template
artifacts: [Sender Name], <subject>, {{name}}, "your name", etc.

Usage:
  python scripts/check_email_placeholders.py --round 1
  python scripts/check_email_placeholders.py --emails outputs/some_emails.csv

Exit code 0 = clean, 1 = artifacts found.
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agents.email_qa import check_email  # noqa: E402

ROUNDS_DIR = ROOT / "outputs" / "internal_rounds"


def scan_rows(rows: list[dict]) -> list[dict]:
    findings = []
    for row in rows:
        hits = check_email(row.get("email_subject", ""), row.get("email_body", ""))
        if hits:
            findings.append({
                "target_id": row.get("target_id"),
                "condition": row.get("condition"),
                "language": row.get("language"),
                "hits": hits,
                "subject": row.get("email_subject", ""),
            })
    return findings


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic placeholder check for generated emails")
    parser.add_argument("--round", type=int, default=None)
    parser.add_argument("--emails", type=str, default=None)
    args = parser.parse_args()

    if args.emails:
        emails_path = Path(args.emails)
    elif args.round:
        emails_path = ROUNDS_DIR / f"round-{args.round:03d}" / "emails.csv"
    else:
        print("ERROR: pass --round N or --emails path")
        sys.exit(2)

    if not emails_path.exists():
        print(f"ERROR: {emails_path} not found")
        sys.exit(2)

    with open(emails_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    findings = scan_rows(rows)
    if not findings:
        print(f"CLEAN: {len(rows)} emails, no placeholder artifacts")
        sys.exit(0)

    print(f"FOUND {len(findings)} email(s) with placeholder artifacts:\n")
    for f in findings:
        print(f"- {f['target_id']} | {f['condition']} | {f['language']}")
        print(f"  subject: {f['subject'][:90]}")
        print(f"  artifacts: {', '.join(f['hits'])}")
        print()
    sys.exit(1)


if __name__ == "__main__":
    main()
