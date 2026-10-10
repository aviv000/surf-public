"""Generate human rating form for the dissociation test.

Extracts S+C- vs S-C+ pairs (the primary dissociation pair) for human rating.
Outputs a simple text file that human raters can fill in.

Usage:
  python scripts/human_anchor_dissociation.py --pairs 20
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=20)
    parser.add_argument("--input", type=str, default=None)
    args = parser.parse_args()

    emails_path = Path(args.input) if args.input else OUTPUTS_DIR / "dissociation_emails.csv"
    if not emails_path.exists():
        print(f"ERROR: {emails_path} not found")
        sys.exit(1)

    with open(emails_path, encoding="utf-8") as f:
        emails = list(csv.DictReader(f))

    # Select first N personas
    emails = emails[:args.pairs]

    out_lines = []
    out_lines.append("=" * 70)
    out_lines.append("HUMAN ANCHOR RATING — DISSOCIATION PAIRS (S+C- vs S-C+)")
    out_lines.append("=" * 70)
    out_lines.append("")
    out_lines.append(f"Pairs to rate: {len(emails)}")
    out_lines.append("")
    out_lines.append("INSTRUCTIONS:")
    out_lines.append("  For each pair, read both emails and answer:")
    out_lines.append("  'Which email is MORE PERSUASIVE? A or B?'")
    out_lines.append("  Do NOT overthink. Go with your instinct as a potential recipient.")
    out_lines.append("  You do not need to justify your choice.")
    out_lines.append("")

    for i, row in enumerate(emails):
        tid = row["target_id"]
        name = row["persona_name"]

        # Randomize A/B assignment
        import random
        rng = random.Random(i)
        swap = rng.choice([True, False])

        if swap:
            body_a = row["S-C+_body"]
            subj_a = row["S-C+_subject"]
            body_b = row["S+C-_body"]
            subj_b = row["S+C-_subject"]
            a_type = "S-C+ (surface-stripped, content-strengthened)"
            b_type = "S+C- (surface-inflated, content-degraded)"
        else:
            body_a = row["S+C-_body"]
            subj_a = row["S+C-_subject"]
            body_b = row["S-C+_body"]
            subj_b = row["S-C+_subject"]
            a_type = "S+C- (surface-inflated, content-degraded)"
            b_type = "S-C+ (surface-stripped, content-strengthened)"

        out_lines.append(f"\n{'─'*70}")
        out_lines.append(f"PAIR {i+1}: {name} ({tid})")
        out_lines.append(f"{'─'*70}")
        out_lines.append(f"\nEMAIL A:")
        out_lines.append(f"  Subject: {subj_a}")
        out_lines.append(f"  {body_a}")
        out_lines.append(f"\nEMAIL B:")
        out_lines.append(f"  Subject: {subj_b}")
        out_lines.append(f"  {body_b}")
        out_lines.append(f"\n  YOUR CHOICE (A or B): ___")
        out_lines.append(f"  Confidence (1-5): ___")

    out_lines.append(f"\n{'='*70}")
    out_lines.append("AFTER RATING: Compute results")
    out_lines.append(f"  A is S+C- (surface-inflated): S+C-_preferred = count where A chosen")
    out_lines.append(f"  B is S+C- (surface-inflated): S+C-_preferred = count where B chosen")
    out_lines.append(f"  Human prefers S+C- (surface) = ___ / {len(emails)}")
    out_lines.append(f"  Human prefers S-C+ (content) = ___ / {len(emails)}")
    out_lines.append(f"{'='*70}")

    out_text = "\n".join(out_lines)

    out_path = OUTPUTS_DIR / "human_anchor_dissociation.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_text)

    print(f"Generated {len(emails)} rating pairs")
    print(f"Output: {out_path}")
    print(f"\nFirst pair preview:")
    # Print first pair for quick review
    for line in out_text.split("\n")[13:30]:
        print(line)


if __name__ == "__main__":
    main()
