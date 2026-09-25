"""Gmail Production Filter Eval — camera-ready experiment for LLMNet 2026.

Sends 36 synthetic phishing emails (12 targets × 3 conditions) via Resend API
through cs-review.org to a single Gmail inbox, then reads INBOX vs SPAM placement
via Gmail API.

Usage:
  python scripts/gmail_filter_eval.py --dry-run          # print all 36 without sending
  python scripts/gmail_filter_eval.py --send-first 3     # send first 3, poll placement
  python scripts/gmail_filter_eval.py                    # full run: send 36 + poll
"""

import argparse
import csv
import json
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from config import (
    OUTPUTS_DIR, TARGETS_CSV, CHEAP_LLM,
    MAILERSEND_API_KEY, GMAIL_MAIL_ADDRESS,
    GMAIL_APP_CLIENT_ID, GMAIL_APP_CLIENT_SECRET, GMAIL_REFRESH_TOKEN,
    SENDING_DOMAIN, TEST_MAILERSEND_DOMAIN, SEND_INTERVAL_SEC,
)
from agents.llm_utils import llm_json


# ---------------------------------------------------------------------------
# Sender name generation
# ---------------------------------------------------------------------------

PERSONA_SPECS_PATH = Path(__file__).parent.parent / "publish" / "llmnet-2026" / "supplementary" / "persona_specifications.json"

def sanitize_email_local(name: str) -> str:
    """Convert a name to a safe ASCII email local part.
    Removes diacritics, replaces spaces with dots, lowercases, strips non-ASCII.
    """
    import unicodedata
    # Normalize unicode: decompose accented chars into base + combining
    name = unicodedata.normalize("NFKD", name)
    # Keep only ASCII
    name = name.encode("ascii", "ignore").decode("ascii")
    # Replace spaces and dots with single dot
    name = name.replace(" ", ".").replace("..", ".").lower()
    # Remove any non-alphanumeric except dots
    name = "".join(c for c in name if c.isalnum() or c == ".")
    # Strip leading/trailing dots
    name = name.strip(".")
    if not name:
        name = "researcher"
    return name


HARDCODED_SENDERS = {
    "syn-001": ("James", "Whitman"),       # USA
    "syn-002": ("Erik", "Lindqvist"),      # Sweden
    "syn-003": ("Kenji", "Takahashi"),     # Japan
    "syn-004": ("Arjun", "Mehta"),         # India
    "syn-005": ("Klaus", "Fischer"),       # Germany
    "syn-006": ("Chidi", "Okonkwo"),       # Nigeria
    "syn-007": ("Tariq", "Hassan"),        # UAE
    "syn-008": ("Ricardo", "Oliveira"),    # Brazil
    "syn-009": ("Andres", "Tamm"),         # Estonia
    "syn-010": ("Min-Jun", "Kang"),        # South Korea
    "syn-011": ("Luc", "Devos"),           # Belgium
    "syn-012": ("Babak", "Rahimi"),        # Iran
}

def load_persona_countries():
    """Load target_id -> country mapping from persona specs."""
    if not PERSONA_SPECS_PATH.exists():
        return {}
    specs = json.loads(PERSONA_SPECS_PATH.read_text(encoding="utf-8"))
    return {s["target_id"]: s["country"] for s in specs}

def generate_sender_names_llm(persona_countries: dict) -> dict:
    """Use cheap LLM to generate country-appropriate sender names."""
    countries_list = "\n".join(f"  {tid}: {country}" for tid, country in sorted(persona_countries.items()))
    sys_prompt = (
        "You are helping generate sender identities for a security research experiment. "
        "Generate plausible academic researcher names — one per country — that sound like "
        "real professors or PhDs in computer science. These are NOT real people. "
        "Return a JSON object mapping target_id to an object with fields: "
        "sender_first (given name), sender_last (family name), sender_email_local "
        "(lowercase ascii, firstname.lastname format). Use the local naming conventions "
        "of each country. Do NOT use famous real researcher names."
    )
    user_prompt = (
        "Generate sender names for these target_id -> country pairs:\n\n"
        f"{countries_list}\n\n"
        "Return valid JSON only: {\"syn-001\": {\"sender_first\": \"...\", \"sender_last\": \"...\", \"sender_email_local\": \"...\"}, ...}"
    )

    result = llm_json(sys_prompt, user_prompt, model=CHEAP_LLM, max_tokens=1024)
    if result is None:
        return None
    # Validate structure
    for tid in persona_countries:
        if tid not in result or not isinstance(result[tid], dict):
            return None
        entry = result[tid]
        if not all(k in entry for k in ("sender_first", "sender_last", "sender_email_local")):
            return None
    return result

def get_sender_names():
    """Get sender names: LLM first, fallback to hardcoded."""
    persona_countries = load_persona_countries()
    if not persona_countries:
        print("WARNING: persona specs not found, using hardcoded senders")
        return HARDCODED_SENDERS

    print("Generating sender names via LLM...")
    llm_result = generate_sender_names_llm(persona_countries)
    if llm_result:
        print("  LLM generation OK")
        return {tid: (r["sender_first"], r["sender_last"]) for tid, r in llm_result.items()}

    print("  LLM generation failed, using hardcoded fallback")
    return HARDCODED_SENDERS


# ---------------------------------------------------------------------------
# Email loading
# ---------------------------------------------------------------------------

SYNTHETIC_TARGETS = [f"syn-{i:03d}" for i in range(1, 13)]

def load_emails():
    """Load phishing_emails.csv, filter synthetic targets + English only."""
    csv_path = OUTPUTS_DIR / "phishing_emails.csv"
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found. Run generator first:")
        print(f"  python agents/generator.py --all --condition all")
        sys.exit(1)

    emails = defaultdict(dict)
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["target_id"]
            if tid not in SYNTHETIC_TARGETS:
                continue
            if row.get("language", "en") != "en":
                continue
            emails[tid][row["condition"]] = row

    return emails


# ---------------------------------------------------------------------------
# MailerSend API sending
# ---------------------------------------------------------------------------

MAILERSEND_API = "https://api.mailersend.com/v1/email"

def send_email_via_mailersend(
    target_id: str,
    condition: str,
    subject: str,
    body: str,
    sender_name: str,
    sender_email_local: str,
) -> dict | None:
    """Send one email via MailerSend API. Returns response or None on failure."""
    # Use cs-review.org if verified, fall back to test domain
    sending_domain = SENDING_DOMAIN if SENDING_DOMAIN else TEST_MAILERSEND_DOMAIN
    sender_email = f"{sender_email_local}@{sending_domain}"

    payload = {
        "from": {"email": sender_email, "name": sender_name},
        "to": [{"email": GMAIL_MAIL_ADDRESS, "name": "Target"}],
        "subject": subject,
        "text": body,
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                MAILERSEND_API,
                json=payload,
                headers={
                    "Authorization": f"Bearer {MAILERSEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if resp.status_code in (200, 201, 202):
                # MailerSend returns 202 Accepted with X-Message-Id header
                msg_id = resp.headers.get("X-Message-Id", "?")
                return {"id": msg_id}
            else:
                print(f"    MailerSend HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(5)
        except Exception as e:
            print(f"    Attempt {attempt+1}: {e}")
            time.sleep(5)
    return None


# ---------------------------------------------------------------------------
# Gmail API polling
# ---------------------------------------------------------------------------

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def get_gmail_credentials():
    """Build Google OAuth credentials from env vars + refresh token."""
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("ERROR: google-auth-oauthlib not installed.")
        print("  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

    creds = Credentials(
        None,  # access token — will be refreshed
        refresh_token=GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_APP_CLIENT_ID,
        client_secret=GMAIL_APP_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )
    from google.auth.transport.requests import Request
    creds.refresh(Request())
    return creds

def poll_gmail_placement():
    """Query Gmail API for all messages from cs-review.org, return id -> placement map."""
    creds = get_gmail_credentials()

    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: google-api-python-client not installed.")
        sys.exit(1)

    service = build("gmail", "v1", credentials=creds)

    # Search for messages from our domain
    results = service.users().messages().list(
        userId="me",
        q=f"from:{SENDING_DOMAIN}",
        maxResults=50,
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        print("  No messages found from cs-review.org")
        return {}

    placement = {}
    for msg in messages:
        msg_id = msg["id"]
        full_msg = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()

        label_ids = full_msg.get("labelIds", [])
        in_spam = "SPAM" in label_ids
        in_inbox = "INBOX" in label_ids

        # Extract Gmail category tab
        category = "UNKNOWN"
        for label in label_ids:
            if label.startswith("CATEGORY_"):
                category = label.replace("CATEGORY_", "")
                break

        # Extract X-Eval-Id from headers
        headers = full_msg.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "?")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "?")

        placement[msg_id] = {
            "in_spam": in_spam,
            "in_inbox": in_inbox,
            "category": category,
            "label_ids": label_ids,
            "subject": subject,
            "sender": sender,
        }

    return placement


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Gmail Production Filter Eval")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print all emails without sending")
    parser.add_argument("--send-first", type=int, default=0,
                        help="Send only first N emails (for testing)")
    parser.add_argument("--skip-poll", action="store_true",
                        help="Skip Gmail API polling after send")
    parser.add_argument("--poll-only", action="store_true",
                        help="Only poll Gmail API (skip sending)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for send ordering")
    args = parser.parse_args()

    random.seed(args.seed)

    # Validate env vars
    if not MAILERSEND_API_KEY:
        print("ERROR: MAILERSEND_API_KEY not set in .env")
        sys.exit(1)
    if not GMAIL_MAIL_ADDRESS:
        print("ERROR: GMAIL_MAIL_ADDRESS not set in .env")
        sys.exit(1)
    if not GMAIL_REFRESH_TOKEN and not args.dry_run and not args.skip_poll:
        print("ERROR: GMAIL_REFRESH_TOKEN not set in .env")
        print("  Run OAuth consent script first to get refresh token.")
        sys.exit(1)

    # Poll-only mode
    if args.poll_only:
        print("Polling Gmail API for messages from cs-review.org...")
        placement = poll_gmail_placement()
        print(f"\nFound {len(placement)} messages:")
        for msg_id, info in sorted(placement.items()):
            where = "SPAM" if info["in_spam"] else info.get("category", "INBOX")
            print(f"  [{where}] {info['subject'][:80]}  ({info['sender']})")
        sp_count = sum(1 for v in placement.values() if v["in_spam"])
        in_count = sum(1 for v in placement.values() if v["in_inbox"])
        from collections import Counter
        cat_counts = Counter(v.get("category", "?") for v in placement.values())
        print(f"\nINBOX: {in_count}, SPAM: {sp_count}")
        print(f"Categories: {dict(cat_counts)}")
        return

    # Load emails
    emails = load_emails()
    print(f"Loaded {len(emails)} targets")

    # Get sender names
    senders = get_sender_names()

    # Build sender_email_local with sanitization
    sender_emails = {}
    for tid, (first, last) in senders.items():
        local = sanitize_email_local(f"{first}.{last}")
        sender_emails[tid] = local

    # Build flat send list: all target × condition combos
    send_list = []
    for tid in sorted(SYNTHETIC_TARGETS):
        if tid not in emails:
            print(f"  WARNING: {tid} not found in phishing_emails.csv, skipping")
            continue
        if tid not in senders:
            print(f"  WARNING: {tid} has no sender name, skipping")
            continue
        for cond in ["baseline", "static_pii", "temporal_kg"]:
            if cond not in emails[tid]:
                print(f"  WARNING: {tid}/{cond} missing, skipping")
                continue
            email = emails[tid][cond]
            send_list.append({
                "target_id": tid,
                "condition": cond,
                "subject": email["email_subject"],
                "body": email["email_body"],
                "sender_first": senders[tid][0],
                "sender_last": senders[tid][1],
                "sender_email_local": sender_emails[tid],
            })

    print(f"Total emails to send: {len(send_list)}")

    # Randomize order
    random.shuffle(send_list)
    print(f"Send order randomized (seed={args.seed})")

    if args.dry_run:
        print("\n=== DRY RUN — not sending ===\n")
        for i, entry in enumerate(send_list):
            sender_email = f"{entry['sender_email_local']}@{SENDING_DOMAIN}"
            sender_name = f"{entry['sender_first']} {entry['sender_last']}"
            print(f"[{i+1:2d}/{len(send_list)}] {entry['target_id']}/{entry['condition']}")
            print(f"    From: {sender_name} <{sender_email}>")
            print(f"    To:   {GMAIL_MAIL_ADDRESS}")
            print(f"    Subj: {entry['subject'][:100]}")
            print()
        return

    # Limit sends if requested
    if args.send_first > 0:
        send_list = send_list[:args.send_first]
        print(f"Limited to first {len(send_list)} emails")

    # --- Phase 2: Send ---
    print(f"\n=== Sending {len(send_list)} emails ({SEND_INTERVAL_SEC}s intervals) ===\n")

    results = []
    send_start = datetime.now(timezone.utc)

    for i, entry in enumerate(send_list):
        sender_email = f"{entry['sender_email_local']}@{SENDING_DOMAIN}"
        sender_name = f"{entry['sender_first']} {entry['sender_last']}"

        sent_at = datetime.now(timezone.utc)
        print(f"[{i+1:2d}/{len(send_list)}] {entry['target_id']}/{entry['condition']} "
              f"from {sender_email} ... ", end="", flush=True)

        resp = send_email_via_mailersend(
            entry["target_id"], entry["condition"],
            entry["subject"], entry["body"],
            sender_name, entry["sender_email_local"],
        )

        if resp:
            resend_id = resp.get("id", "?")
            print(f"OK (id={resend_id})")
            results.append({
                "target_id": entry["target_id"],
                "condition": entry["condition"],
                "sender_name": sender_name,
                "sender_email": sender_email,
                "email_subject": entry["subject"],
                "sent_at": sent_at.isoformat(),
                "resend_id": resend_id,
                "placement_5min": None,
                "category_5min": None,
                "label_ids_5min": None,
                "placement_60min": None,
                "category_60min": None,
                "label_ids_60min": None,
            })
        else:
            print("FAILED")
            results.append({
                "target_id": entry["target_id"],
                "condition": entry["condition"],
                "sender_name": sender_name,
                "sender_email": sender_email,
                "email_subject": entry["subject"],
                "sent_at": sent_at.isoformat(),
                "resend_id": None,
                "placement_5min": None,
                "category_5min": None,
                "label_ids_5min": None,
                "placement_60min": None,
                "category_60min": None,
                "label_ids_60min": None,
            })

        # Wait between sends (skip after last)
        if i < len(send_list) - 1:
            print(f"  Waiting {SEND_INTERVAL_SEC}s...")
            time.sleep(SEND_INTERVAL_SEC)

    send_end = datetime.now(timezone.utc)
    duration_min = (send_end - send_start).total_seconds() / 60
    print(f"\nSend phase complete in {duration_min:.1f} min. "
          f"{sum(1 for r in results if r['resend_id'])}/{len(results)} sent successfully.")

    # --- Phase 3: Poll Gmail API ---
    if args.skip_poll:
        print("Skipping Gmail API poll (--skip-poll)")
    else:
        if not GMAIL_REFRESH_TOKEN:
            print("WARNING: GMAIL_REFRESH_TOKEN not set, skipping Gmail API poll")
        else:
            # Poll at +5min
            wait_sec = 300
            print(f"\nWaiting {wait_sec}s before first Gmail API poll...")
            time.sleep(wait_sec)

            print("Polling Gmail API (+5min)...")
            placement_5 = poll_gmail_placement()
            print(f"  Found {len(placement_5)} messages from cs-review.org")

            # Match by X-Eval-Id (via subject matching)
            for r in results:
                if r["resend_id"] is None:
                    continue
                for msg_id, info in placement_5.items():
                    if info["subject"] == r["email_subject"]:
                        r["placement_5min"] = "SPAM" if info["in_spam"] else info["category"]
                        r["category_5min"] = info["category"]
                        r["label_ids_5min"] = ",".join(info["label_ids"])
                        break

    # --- Write results ---
    out_path = OUTPUTS_DIR / "gmail_filter_eval_results.csv"
    fieldnames = [
        "target_id", "condition", "sender_name", "sender_email", "email_subject",
        "sent_at", "resend_id",
        "placement_5min", "category_5min", "label_ids_5min",
        "placement_60min", "category_60min", "label_ids_60min",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"\nResults written to {out_path}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print("GMAIL FILTER EVAL — RESULTS")
    print(f"{'='*60}")

    placement_key = "placement_5min"
    has_placement = any(r.get(placement_key) for r in results)

    if has_placement:
        by_cond = defaultdict(lambda: defaultdict(int))
        for r in results:
            placement = r.get(placement_key)
            if placement:
                by_cond[r["condition"]][placement] += 1

        for cond in ["baseline", "static_pii", "temporal_kg"]:
            cats = by_cond[cond]
            total = sum(cats.values())
            breakdown = ", ".join(f"{cat}={count}" for cat, count in sorted(cats.items()))
            print(f"  {cond} ({total}): {breakdown}")

        # Overall summary
        all_cats = defaultdict(int)
        for cond_data in by_cond.values():
            for cat, count in cond_data.items():
                all_cats[cat] += count
        total_all = sum(all_cats.values())
        breakdown_all = ", ".join(f"{cat}={count}" for cat, count in sorted(all_cats.items()))
        print(f"  TOTAL ({total_all}): {breakdown_all}")
    else:
        print("  Placement data not yet available. Re-run with --poll-only later.")
        print(f"  python scripts/gmail_filter_eval.py --poll-only")


if __name__ == "__main__":
    main()
