"""Extract linguistic persuasion features from phishing emails and correlate
with LLM judge pairwise rankings. Provides an external, non-LLM anchor for validation.

Features extracted:
- Readability: Flesch-Kincaid, Flesch Reading Ease
- Sentiment: VADER compound score
- Personal pronoun density (you, your, I, we)
- Named entity count (persons, organizations, locations)
- Formal/academic register markers
- Call-to-action cue density

Usage:
  python scripts/linguistic_persuasion_features.py
  python scripts/linguistic_persuasion_features.py --correlate <judgments.csv>
"""

import csv
import json
import sys
import re
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR


# ---------------------------------------------------------------------------
# Feature extraction (no external deps required)
# ---------------------------------------------------------------------------

def syllable_count(word: str) -> int:
    """Simple syllable counter."""
    word = word.lower()
    count = 0
    vowels = "aeiouy"
    if word[0] in vowels:
        count += 1
    for i in range(1, len(word)):
        if word[i] in vowels and word[i-1] not in vowels:
            count += 1
    if word.endswith("e"):
        count -= 1
    if count == 0:
        count = 1
    return count


def flesch_reading_ease(text: str) -> float:
    """Flesch Reading Ease score."""
    sentences = max(len(re.split(r'[.!?]+', text)), 1)
    words = text.split()
    n_words = max(len(words), 1)
    syllables = sum(syllable_count(w) for w in words)
    return 206.835 - 1.015 * (n_words / sentences) - 84.6 * (syllables / n_words)


def flesch_kincaid_grade(text: str) -> float:
    """Flesch-Kincaid Grade Level."""
    sentences = max(len(re.split(r'[.!?]+', text)), 1)
    words = text.split()
    n_words = max(len(words), 1)
    syllables = sum(syllable_count(w) for w in words)
    return 0.39 * (n_words / sentences) + 11.8 * (syllables / n_words) - 15.59


def pronoun_density(text: str) -> dict:
    """Count personal pronouns."""
    text_lower = text.lower()
    words = text_lower.split()
    n_words = max(len(words), 1)
    patterns = {
        "first_person": r'\b(i|me|my|mine|myself|we|us|our|ours|ourselves)\b',
        "second_person": r'\b(you|your|yours|yourself|yourselves)\b',
        "third_person": r'\b(he|she|it|they|him|her|them|his|hers|its|their|theirs)\b',
    }
    densities = {}
    for name, pattern in patterns.items():
        count = len(re.findall(pattern, text_lower))
        densities[name] = count / n_words
    return densities


def named_entity_count(text: str) -> int:
    """Count capitalized multi-word phrases (proxy for named entities)."""
    # Match capitalized word sequences (2+ words)
    entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
    return len(entities)


def call_to_action_cues(text: str) -> int:
    """Count call-to-action cues."""
    cues = [
        r'\bclick\b', r'\breview\b', r'\bvisit\b', r'\bcheck\b', r'\bsee\b',
        r'\bopen\b', r'\bdownload\b', r'\brespond\b', r'\breply\b', r'\bconfirm\b',
        r'\bregister\b', r'\bsign up\b', r'\bjoin\b', r'\battend\b',
        r'\bwould you\b', r'\bcould you\b', r'\bplease\b',
    ]
    text_lower = text.lower()
    return sum(len(re.findall(c, text_lower)) for c in cues)


def academic_register_markers(text: str) -> dict:
    """Count academic/formal register markers."""
    markers = {
        "hedging": r'\b(perhaps|possibly|likely|may|might|could|seems|appears|suggests)\b',
        "formality": r'\b(furthermore|moreover|consequently|therefore|however|nevertheless|accordingly)\b',
        "technical_terms": r'\b(algorithm|framework|methodology|empirical|evaluation|implementation|architecture|protocol|infrastructure)\b',
    }
    text_lower = text.lower()
    words = text_lower.split()
    n_words = max(len(words), 1)
    return {k: len(re.findall(v, text_lower)) / n_words for k, v in markers.items()}


def word_count(text: str) -> int:
    return len(text.split())


def extract_features(email_body: str) -> dict:
    """Extract all linguistic features from an email body."""
    return {
        "word_count": word_count(email_body),
        "flesch_reading_ease": round(flesch_reading_ease(email_body), 1),
        "flesch_kincaid_grade": round(flesch_kincaid_grade(email_body), 1),
        "named_entity_count": named_entity_count(email_body),
        "cta_cue_count": call_to_action_cues(email_body),
        "pronoun_first": round(pronoun_density(email_body).get("first_person", 0), 4),
        "pronoun_second": round(pronoun_density(email_body).get("second_person", 0), 4),
        "hedging_density": round(academic_register_markers(email_body).get("hedging", 0), 4),
        "formality_density": round(academic_register_markers(email_body).get("formality", 0), 4),
    }


# ---------------------------------------------------------------------------
# Correlation with judge results
# ---------------------------------------------------------------------------

def correlate_with_judgments(judgments_path: Path) -> dict:
    """Correlate linguistic features with pairwise win rates."""
    if not judgments_path.exists():
        print(f"Judgments file not found: {judgments_path}")
        return {}

    judgments = []
    with open(judgments_path, encoding="utf-8") as f:
        judgments = list(csv.DictReader(f))

    # Load emails
    emails_path = judgments_path.parent / "within_condition_emails.csv"
    if not emails_path.exists():
        emails_path = OUTPUTS_DIR / "within_condition_emails.csv"

    emails = {}
    if emails_path.exists():
        with open(emails_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row["target_id"], int(row.get("hook_level", 0)))
                emails[key] = row
                emails[row["email_body"]] = row  # fallback

    # Extract features for all emails
    email_features = {}
    for key, email in emails.items():
        if isinstance(key, tuple):
            body = email.get("email_body", "")
            if body and len(body) > 10:
                email_features[key] = extract_features(body)

    # Compute feature differences for each judgment pair
    results = {}
    for pair_name in [(1,3), (3,5), (1,5)]:
        la, lb = pair_name
        pair_judgments = [j for j in judgments
                         if int(j.get("level_a", 0)) == la and int(j.get("level_b", 0)) == lb]

        # Get feature diffs
        feature_diffs = defaultdict(list)
        for j in pair_judgments:
            tid = j["target_id"]
            fa = email_features.get((tid, la))
            fb = email_features.get((tid, lb))
            if fa and fb:
                for feat in fa:
                    feature_diffs[feat].append(fb[feat] - fa[feat])

        results[f"{la}_vs_{lb}"] = {
            feat: {
                "mean_diff": round(sum(vals) / max(len(vals), 1), 3),
                "direction": "higher_hooks_has_more" if sum(vals) / max(len(vals), 1) > 0 else "higher_hooks_has_less",
            }
            for feat, vals in feature_diffs.items() if vals
        }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--correlate", type=str, help="Path to judgments CSV")
    parser.add_argument("--emails", type=str, default="outputs/within_condition_emails.csv")
    args = parser.parse_args()

    if args.correlate:
        results = correlate_with_judgments(Path(args.correlate))
        print("Linguistic feature differences by hook level:")
        for pair, feats in sorted(results.items()):
            print(f"\n  {pair}:")
            for feat, data in sorted(feats.items()):
                print(f"    {feat}: mean_diff={data['mean_diff']} ({data['direction']})")
        return

    # Extract features from emails
    emails_path = Path(args.emails)
    if not emails_path.exists():
        print(f"ERROR: {emails_path} not found")
        sys.exit(1)

    with open(emails_path, encoding="utf-8") as f:
        all_emails = list(csv.DictReader(f))

    print(f"Extracting features from {len(all_emails)} emails...")
    results = []
    for email in all_emails:
        body = email.get("email_body", "")
        if not body or len(body) < 10:
            continue
        feats = extract_features(body)
        feats["target_id"] = email.get("target_id", "")
        feats["hook_level"] = email.get("hook_level", "")
        feats["error"] = email.get("error", "False")
        results.append(feats)

    out_path = OUTPUTS_DIR / "linguistic_features.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    # Summary stats by hook level
    print(f"\nWrote {len(results)} feature rows to {out_path}")
    print("\nMean features by hook level:")
    by_level = defaultdict(list)
    for r in results:
        by_level[int(r["hook_level"])].append(r)

    for level in [1, 3, 5]:
        items = by_level.get(level, [])
        if not items:
            continue
        print(f"\n  {level} hooks ({len(items)} emails):")
        for feat in ["flesch_reading_ease", "flesch_kincaid_grade",
                      "named_entity_count", "cta_cue_count",
                      "pronoun_second", "formality_density"]:
            vals = [r[feat] for r in items if feat in r]
            if vals:
                print(f"    {feat}: {sum(vals)/len(vals):.3f}")


if __name__ == "__main__":
    import argparse
    from collections import defaultdict
    main()
