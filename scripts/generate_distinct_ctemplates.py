"""Generate 10 distinct content-degraded (C-) email templates with surface variants.

Creates 10 different generic phishing templates, each with S+ and S- variant.
Assigns to personas in rotation (each template used for 5 personas).

Usage:
  python scripts/generate_distinct_ctemplates.py
"""

import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR, DEFAULT_LLM
from agents.llm_utils import llm_json


# 10 distinct generic pretext scenarios (NO personalization, all content-weak)
TEMPLATE_SCENARIOS = [
    "a generic workshop invitation on current trends in computer science",
    "a vague request to review a manuscript on an unspecified topic",
    "a generic conference participation solicitation with no specific theme",
    "a non-specific invitation to join a journal editorial board",
    "a generic collaboration inquiry with no research area mentioned",
    "a vague award nomination request requiring recipient response",
    "a generic seminar series invitation with no topic specified",
    "a non-specific request for feedback on an unspecified research proposal",
    "a generic call for papers announcement with no topic focus",
    "a vague networking event invitation for researchers",
]


SURFACE_INFLATE_SYSTEM = """You are creating a phishing simulation email for security research.

Write a surface-inflated email: 150-180 words, many named entities (fake but plausible
conference/journal/institution names, dates, venues, people), formal academic style,
specific-sounding details.

IMPORTANT: The content must be WEAK and GENERIC. No real personalization.
No specific research area. The pretext is: {scenario}

Return JSON: {{"subject": "...", "body": "..."}}"""


SURFACE_STRIP_SYSTEM = """You are creating a phishing simulation email for security research.

Write a surface-stripped email: 40-55 words, NO named entities, plain simple language,
short sentences, minimal call to action.

IMPORTANT: The content must be WEAK and GENERIC. No real personalization.
No specific research area. The pretext is: {scenario}

Return JSON: {{"subject": "...", "body": "..."}}"""


def main():
    print("Generating 10 distinct C- templates × 2 surface variants = 20 emails")

    templates = {}
    for i, scenario in enumerate(TEMPLATE_SCENARIOS):
        label = f"template_{i:02d}"
        print(f"\n[{i+1}/10] {label}: {scenario[:60]}...")

        # S+C-: surface-inflated, content-degraded
        sp_sys = SURFACE_INFLATE_SYSTEM.format(scenario=scenario)
        sp_user = f"Write this email. The scenario: {scenario}"
        sp = llm_json(sp_sys, sp_user, model=DEFAULT_LLM, max_tokens=512)
        time.sleep(0.5)

        # S-C-: surface-stripped, content-degraded
        ss_sys = SURFACE_STRIP_SYSTEM.format(scenario=scenario)
        ss_user = f"Write this email. The scenario: {scenario}"
        ss = llm_json(ss_sys, ss_user, model=DEFAULT_LLM, max_tokens=512)
        time.sleep(0.5)

        if sp and ss:
            templates[label] = {
                "S+C-_subject": sp.get("subject", ""),
                "S+C-_body": sp.get("body", ""),
                "S-C-_subject": ss.get("subject", ""),
                "S-C-_body": ss.get("body", ""),
            }
            print(f"  S+C-: {len(sp.get('body', '').split())}w, S-C-: {len(ss.get('body', '').split())}w")
        else:
            print(f"  FAILED")

    # Update dissociation_emails.csv: assign templates in rotation
    emails_path = OUTPUTS_DIR / "dissociation_emails.csv"
    with open(emails_path, encoding="utf-8") as f:
        emails = list(csv.DictReader(f))

    print(f"\nUpdating {len(emails)} persona rows with distinct C- templates...")

    for i, row in enumerate(emails):
        template_idx = i % 10
        label = f"template_{template_idx:02d}"
        if label in templates:
            for key in ["S+C-_subject", "S+C-_body", "S-C-_subject", "S-C-_body"]:
                row[key] = templates[label][key]
        else:
            print(f"  WARNING: {label} not found")

    # Save updated CSV
    fields = list(emails[0].keys())
    with open(emails_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(emails)

    print(f"Updated {emails_path}")
    print(f"Template assignments: {len(emails)} personas / 10 templates = {len(emails)//10} each")


if __name__ == "__main__":
    main()
