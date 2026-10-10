"""Pull Tally rating responses for an internal round.

Fetches submissions from the per-rater Tally forms (tally_urls.json in the
round package) and structures them into per-code ratings using the form's
question order (3 items + comments per email, aligned with key.json).

Usage:
  python scripts/pull_tally_round_responses.py --round 1
  python scripts/pull_tally_round_responses.py --round 1 --rater revital

Outputs (in the round directory):
  responses_raw.json      — raw API payloads per rater (audit trail)
  ratings_collected.json  — structured: rater → submissions → per-code scores
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

API_KEY = os.getenv("TALLY_API_KEY")
if not API_KEY:
    print("ERROR: TALLY_API_KEY not found in .env")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
ROUNDS_DIR = ROOT / "outputs" / "internal_rounds"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

RATING_ITEMS = [
    "Persuasiveness — How likely would you be to respond? (enter 1-7)",
    "Personalization — How personalized does this feel? (enter 1-7)",
    "Convincingness — How convincing is the pretext? (enter 1-7)",
]


def fetch_submissions(form_id: str) -> tuple[list[dict], dict]:
    """Fetch all submissions for a form (paginated). Returns (submissions, page_meta)."""
    all_subs = []
    page = 1
    while True:
        resp = requests.get(
            f"https://api.tally.so/forms/{form_id}/submissions",
            headers=HEADERS,
            params={"page": page, "limit": 50},
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"  ERROR {resp.status_code}: {resp.text[:300]}")
            sys.exit(1)
        data = resp.json()
        all_subs.extend(data.get("submissions", []))
        if not data.get("hasMore"):
            return all_subs, data
        page += 1


def question_ids(data: dict) -> list[str]:
    """Ordered list of question ids (one per input block, form order)."""
    ids = []
    for q in data.get("questions", []):
        if q.get("isDeleted"):
            continue
        if q.get("id"):
            ids.append(q["id"])
    return ids


def submission_values(sub: dict, qids: list[str]) -> list:
    """Extract answers aligned with the ordered question-id list.

    Live submissions carry a `responses` list of {questionId, answer}
    objects (verified 2026-08-31). Falls back to `fields`-shaped payloads.
    """
    table = {}
    raw = sub.get("responses") or sub.get("fields") or []
    if isinstance(raw, list):
        for r in raw:
            key = (r.get("questionId") or r.get("uuid")
                   or r.get("fieldUuid") or r.get("key"))
            table[key] = r.get("answer") if "answer" in r else r.get("value")
    elif isinstance(raw, dict):
        table = raw
    return [table.get(q) for q in qids]


def main():
    parser = argparse.ArgumentParser(
        description="Pull Tally rating responses for an internal round")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--rater", type=str, default=None)
    args = parser.parse_args()

    round_dir = ROUNDS_DIR / f"round-{args.round:03d}"
    urls_path = round_dir / "tally_urls.json"
    key_path = round_dir / "key.json"
    if not urls_path.exists() or not key_path.exists():
        print(f"ERROR: missing tally_urls.json or key.json in {round_dir}")
        sys.exit(1)

    urls = json.loads(urls_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8")).get("raters", {})

    raw = {}
    collected = {}
    pulled_at = datetime.now(timezone.utc).isoformat()

    for rater_id, form in urls.items():
        if rater_id in ("superseded", "_note"):
            continue
        if args.rater and rater_id != args.rater:
            continue
        form_id = form.get("id")
        codes = key.get(rater_id, {})
        print(f"[{rater_id}] form {form_id}: fetching submissions...")

        subs, meta = fetch_submissions(form_id)
        qids = question_ids(meta)
        n_expected = 4 * len(codes)
        if len(qids) != n_expected:
            print(f"  WARNING: {len(qids)} fields found, expected {n_expected} "
                  f"({len(codes)} emails × 4). Mapping may be misaligned.")

        raw[rater_id] = {"form_id": form_id, "meta": meta, "submissions": subs}

        structured = []
        code_list = list(codes.items())  # randomized order from key.json
        for sub in subs:
            vals = submission_values(sub, qids)
            ratings = {}
            for i, (code, meta_code) in enumerate(code_list):
                base = 4 * i
                if base + 3 >= len(vals):
                    break
                ratings[code] = {
                    "target_id": meta_code.get("target_id"),
                    "condition": meta_code.get("condition"),
                    "language": meta_code.get("language"),
                    "dosage": meta_code.get("dosage", "n/a"),
                    "depth": meta_code.get("depth", "n/a"),
                    "authenticity": vals[base],
                    "persuasion": vals[base + 1],
                    "personalization": vals[base + 2],
                    "comments": vals[base + 3],
                }
            structured.append({
                "submission_id": sub.get("submissionId"),
                "created_at": sub.get("createdAt"),
                "ratings": ratings,
            })
        collected[rater_id] = {
            "form_id": form_id,
            "n_submissions": len(structured),
            "submissions": structured,
        }

    raw_path = round_dir / "responses_raw.json"
    coll_path = round_dir / "ratings_collected.json"
    raw_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    coll_path.write_text(json.dumps(
        {"pulled_at": pulled_at, "raters": collected},
        indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nSummary:")
    total = 0
    for rater_id, c in collected.items():
        n = c["n_submissions"]
        total += n
        print(f"  {rater_id}: {n} submission(s) — "
              f"{'COMPLETE' if n >= 1 else 'pending'}")
    if args.rater is None and total == 0:
        print("  No responses yet.")
    print(f"\nSaved to {coll_path} and {raw_path}")


if __name__ == "__main__":
    main()
