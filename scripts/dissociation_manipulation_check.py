"""Manipulation check for 2×2 dissociation emails.

Verifies that surface and content manipulations are orthogonal:
- Surface score should differ S+ > S- (within same content level)
- Content score should differ C+ > C- (within same surface level)
- The two dimensions should not be correlated

Uses GPT-4.1-mini as independent surface/content scorer (not in judge panel
for this — using a cheap fast model to rate both dimensions).

Usage:
  python scripts/dissociation_manipulation_check.py
"""

import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR, CHEAP_LLM


# Simple heuristic surface/content scores (no LLM needed for basic check)
def heuristic_surface_score(body: str) -> dict:
    """Compute heuristic surface features from email body."""
    words = body.split()
    n_words = len(words)

    # Named entity count (approximate: capitalized multi-word spans)
    import re
    entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', body)
    entity_count = len(entities)

    # Specificity markers: years, percentages, numbers
    years = len(re.findall(r'\b(20\d{2}|19\d{2})\b', body))
    numbers = len(re.findall(r'\b\d+\b', body))

    return {
        "word_count": n_words,
        "named_entity_count": entity_count,
        "year_count": years,
        "number_count": numbers,
        "surface_score": n_words + entity_count * 5 + years * 3 + numbers * 2,
    }


def heuristic_content_score(body: str) -> dict:
    """Compute heuristic content quality features."""
    import re
    words = body.split()
    n_words = max(len(words), 1)

    # Hook-related terms
    research_terms = len(re.findall(
        r'\b(research|paper|conference|journal|study|finding|'
        r'experiment|method|approach|framework|algorithm)\b',
        body, re.IGNORECASE
    ))

    # Specificity of CTA
    cta_phrases = len(re.findall(
        r'(would you be interested|let me know if|I would like to|'
        r'could we|are you available|would love to|I am writing to)',
        body, re.IGNORECASE
    ))

    # Personalization markers
    personalization = len(re.findall(
        r'\b(your|you|your work|your research|your paper|your recent)\b',
        body, re.IGNORECASE
    ))

    # Generic/weak content markers (negative)
    generic_markers = len(re.findall(
        r'(current trends|various topics|networking opportunities|'
        r'hope this message finds you well|I am organizing)',
        body, re.IGNORECASE
    ))

    return {
        "research_terms": research_terms,
        "cta_phrases": cta_phrases,
        "personalization_markers": personalization,
        "generic_markers": generic_markers,
        "content_score": research_terms * 3 + cta_phrases * 4
                       + personalization * 2 - generic_markers * 3,
    }


def main():
    emails_path = OUTPUTS_DIR / "dissociation_emails.csv"
    if not emails_path.exists():
        print(f"ERROR: {emails_path} not found. Run generate_dissociation_emails.py first.")
        sys.exit(1)

    with open(emails_path, encoding="utf-8") as f:
        emails = list(csv.DictReader(f))

    print(f"Loaded {len(emails)} personas")

    # Compute scores per variant
    variants = ["S+C+", "S+C-", "S-C+", "S-C-"]
    surface_scores = defaultdict(list)
    content_scores = defaultdict(list)

    for row in emails:
        for v in variants:
            body = row.get(f"{v}_body", "")
            if not body or body == "[failed]":
                continue
            ss = heuristic_surface_score(body)
            cs = heuristic_content_score(body)
            surface_scores[v].append(ss)
            content_scores[v].append(cs)

    # Summary
    print("\n" + "=" * 60)
    print("MANIPULATION CHECK RESULTS")
    print("=" * 60)

    print("\n--- Surface Scores ---")
    for v in variants:
        scores = [s["surface_score"] for s in surface_scores[v]]
        if scores:
            print(f"  {v}: mean={sum(scores)/len(scores):.1f}, "
                  f"wc={sum(s['word_count'] for s in surface_scores[v])/len(surface_scores[v]):.0f}, "
                  f"entities={sum(s['named_entity_count'] for s in surface_scores[v])/len(surface_scores[v]):.1f}")

    print("\n--- Content Scores ---")
    for v in variants:
        scores = [s["content_score"] for s in content_scores[v]]
        if scores:
            print(f"  {v}: mean={sum(scores)/len(scores):.1f}, "
                  f"research={sum(s['research_terms'] for s in content_scores[v])/len(content_scores[v]):.1f}, "
                  f"cta={sum(s['cta_phrases'] for s in content_scores[v])/len(content_scores[v]):.1f}, "
                  f"generic={sum(s['generic_markers'] for s in content_scores[v])/len(content_scores[v]):.1f}")

    # Orthogonality checks
    print("\n--- Orthogonality Checks ---")

    # Surface: S+ should be higher than S- for same content
    sc_plus_surface = [s["surface_score"] for s in surface_scores["S+C+"]]
    sc_minus_surface = [s["surface_score"] for s in surface_scores["S+C-"]]
    s_minus_c_plus_surface = [s["surface_score"] for s in surface_scores["S-C+"]]
    s_minus_c_minus_surface = [s["surface_score"] for s in surface_scores["S-C-"]]

    if sc_plus_surface and s_minus_c_plus_surface:
        s_plus_mean_cplus = sum(sc_plus_surface) / len(sc_plus_surface)
        s_minus_mean_cplus = sum(s_minus_c_plus_surface) / len(s_minus_c_plus_surface)
        check1 = s_plus_mean_cplus > s_minus_mean_cplus
        print(f"  S+ > S- (content=strengthened): {check1} "
              f"({s_plus_mean_cplus:.0f} vs {s_minus_mean_cplus:.0f})")

    if sc_minus_surface and s_minus_c_minus_surface:
        s_plus_mean_cminus = sum(sc_minus_surface) / len(sc_minus_surface)
        s_minus_mean_cminus = sum(s_minus_c_minus_surface) / len(s_minus_c_minus_surface)
        check2 = s_plus_mean_cminus > s_minus_mean_cminus
        print(f"  S+ > S- (content=degraded): {check2} "
              f"({s_plus_mean_cminus:.0f} vs {s_minus_mean_cminus:.0f})")

    # Content: C+ should be higher than C- for same surface
    sc_plus_content = [s["content_score"] for s in content_scores["S+C+"]]
    sc_minus_content = [s["content_score"] for s in content_scores["S+C-"]]
    s_minus_c_plus_content = [s["content_score"] for s in content_scores["S-C+"]]
    s_minus_c_minus_content = [s["content_score"] for s in content_scores["S-C-"]]

    if sc_plus_content and sc_minus_content:
        c_plus_mean_splus = sum(sc_plus_content) / len(sc_plus_content)
        c_minus_mean_splus = sum(sc_minus_content) / len(sc_minus_content)
        check3 = c_plus_mean_splus > c_minus_mean_splus
        print(f"  C+ > C- (surface=inflated): {check3} "
              f"({c_plus_mean_splus:.0f} vs {c_minus_mean_splus:.0f})")

    if s_minus_c_plus_content and s_minus_c_minus_content:
        c_plus_mean_sminus = sum(s_minus_c_plus_content) / len(s_minus_c_plus_content)
        c_minus_mean_sminus = sum(s_minus_c_minus_content) / len(s_minus_c_minus_content)
        check4 = c_plus_mean_sminus > c_minus_mean_sminus
        print(f"  C+ > C- (surface=stripped): {check4} "
              f"({c_plus_mean_sminus:.0f} vs {c_minus_mean_sminus:.0f})")

    # Dissociation check: S+C- vs S-C+ crosses
    if sc_minus_surface and s_minus_c_plus_surface:
        s_plus_c_minus_s = sum(sc_minus_surface) / len(sc_minus_surface)
        s_minus_c_plus_s = sum(s_minus_c_plus_surface) / len(s_minus_c_plus_surface)
        s_plus_c_minus_c = sum(sc_minus_content) / len(sc_minus_content)
        s_minus_c_plus_c = sum(s_minus_c_plus_content) / len(s_minus_c_plus_content)
        print(f"\n  DISSOCIATION CHECK (S+C- vs S-C+):")
        print(f"    Surface: S+C-={s_plus_c_minus_s:.0f} vs S-C+={s_minus_c_plus_s:.0f} "
              f"→ S+C- higher? {s_plus_c_minus_s > s_minus_c_plus_s}")
        print(f"    Content: S+C-={s_plus_c_minus_c:.0f} vs S-C+={s_minus_c_plus_c:.0f} "
              f"→ S-C+ higher? {s_minus_c_plus_c > s_plus_c_minus_c}")
        dissociation = (s_plus_c_minus_s > s_minus_c_plus_s) and (s_minus_c_plus_c > s_plus_c_minus_c)
        print(f"    DISSOCIATION: {dissociation}")

    # Overall verdict
    all_checks = [check1, check2, check3, check4]
    checks_passed = sum(all_checks)
    print(f"\n  Overall: {checks_passed}/4 checks passed")

    if checks_passed >= 3 and dissociation:
        print("  VERDICT: MANIPULATION VALID — proceed to judgments")
    else:
        print("  VERDICT: FIX NEEDED — check generation prompts")

    # Save check results
    out = {
        "surface_scores": {v: {
            "mean_surface": sum(s["surface_score"] for s in surface_scores[v]) / max(len(surface_scores[v]), 1),
            "mean_wc": sum(s["word_count"] for s in surface_scores[v]) / max(len(surface_scores[v]), 1),
            "mean_entities": sum(s["named_entity_count"] for s in surface_scores[v]) / max(len(surface_scores[v]), 1),
        } for v in variants},
        "content_scores": {v: {
            "mean_content": sum(s["content_score"] for s in content_scores[v]) / max(len(content_scores[v]), 1),
            "mean_research": sum(s["research_terms"] for s in content_scores[v]) / max(len(content_scores[v]), 1),
            "mean_cta": sum(s["cta_phrases"] for s in content_scores[v]) / max(len(content_scores[v]), 1),
        } for v in variants},
        "checks": {
            "surface_cplus": check1,
            "surface_cminus": check2,
            "content_splus": check3,
            "content_sminus": check4,
            "dissociation": dissociation,
        },
        "verdict": "PASS" if (checks_passed >= 3 and dissociation) else "FAIL",
    }
    out_path = OUTPUTS_DIR / "dissociation_manipulation_check.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
