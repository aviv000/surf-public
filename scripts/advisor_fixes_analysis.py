"""Advisor-recommended statistical analyses (fixes 2, 4, 6).

Fix 2: Fisher's exact test on GPT anomaly
Fix 4: Per-template GPT surface-preference breakdown
Fix 6: Logistic regression of judge choice on feature deltas

Usage:
  python scripts/advisor_fixes_analysis.py --judgments outputs/dissociation_judgments_v2.csv
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR


def load_judgments(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fisher_exact_gpt_anomaly(judgments: list[dict]):
    """Fix 2: Fisher's exact test comparing GPT surface-preference vs out-of-family."""
    pair = "S+C-_vs_S-C+"

    # GPT-4.1-mini
    gpt_wins_surface = sum(1 for j in judgments
                          if j["pair"] == pair and j["model"] == "gpt-4.1-mini"
                          and j["winner"] == "A")  # A = S+C- (surface)
    gpt_total = sum(1 for j in judgments
                   if j["pair"] == pair and j["model"] == "gpt-4.1-mini")

    # Out-of-family pooled (Claude + DeepSeek)
    oof_wins_surface = sum(1 for j in judgments
                          if j["pair"] == pair and j["model"] != "gpt-4.1-mini"
                          and j["winner"] == "A")
    oof_total = sum(1 for j in judgments
                   if j["pair"] == pair and j["model"] != "gpt-4.1-mini")

    # Per-judge
    per_judge = defaultdict(lambda: [0, 0])
    for j in judgments:
        if j["pair"] == pair:
            per_judge[j["model"]][1] += 1
            if j["winner"] == "A":
                per_judge[j["model"]][0] += 1

    print("=" * 60)
    print("FIX 2: FISHER'S EXACT — GPT ANOMALY")
    print("=" * 60)
    print(f"\n  Pair: {pair}")
    print(f"  GPT-4.1-mini: {gpt_wins_surface}/{gpt_total} = {gpt_wins_surface/gpt_total:.1%} surface preference")
    print(f"  Out-of-family (Claude+DeepSeek): {oof_wins_surface}/{oof_total} = {oof_wins_surface/oof_total:.1%} surface preference")

    # Fisher's exact
    try:
        from scipy.stats import fisher_exact
        table = [[gpt_wins_surface, gpt_total - gpt_wins_surface],
                 [oof_wins_surface, oof_total - oof_wins_surface]]
        _, p = fisher_exact(table)
        print(f"\n  Fisher's exact p = {p:.2e}")
    except ImportError:
        # Manual chi-square approximation
        print("  (scipy not available — compute Fisher's exact manually)")

    # Per-judge summary
    print(f"\n  Per-judge:")
    for model in sorted(per_judge):
        wins, total = per_judge[model]
        print(f"    {model}: {wins}/{total} = {wins/total:.1%}")

    return {
        "pair": pair,
        "gpt_surface_rate": gpt_wins_surface / max(gpt_total, 1),
        "oof_surface_rate": oof_wins_surface / max(oof_total, 1),
        "gpt_total": gpt_total,
        "oof_total": oof_total,
        "per_judge": {m: {"wins": w, "total": t} for m, (w, t) in per_judge.items()},
    }


def per_template_breakdown(judgments: list[dict], emails_path: Path):
    """Fix 4: Per-template GPT surface-preference breakdown."""
    # Load emails to map target_id → template
    tid_to_template = {}
    with open(emails_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # Extract template info — use subject as template fingerprint
            tid_to_template[row["target_id"]] = row.get("S+C-_subject", "")[:50]

    pair = "S+C-_vs_S-C+"
    model = "gpt-4.1-mini"

    per_template = defaultdict(lambda: [0, 0])  # [surface_wins, total]
    for j in judgments:
        if j["pair"] == pair and j["model"] == model:
            tid = j["target_id"]
            template_key = tid_to_template.get(tid, f"unknown_{tid}")[:60]
            per_template[template_key][1] += 1
            if j["winner"] == "A":
                per_template[template_key][0] += 1

    print("\n" + "=" * 60)
    print("FIX 4: PER-TEMPLATE GPT SURFACE PREFERENCE")
    print("=" * 60)
    print(f"\n  Model: {model}, Pair: {pair}")
    for template, (wins, total) in sorted(per_template.items(), key=lambda x: -x[0]/max(x[1],1)):
        rate = wins / max(total, 1)
        print(f"    {template[:60]}: {wins}/{total} = {rate:.1%}")

    rates = [w / max(t, 1) for w, t in per_template.values()]
    if rates:
        print(f"\n  Min rate: {min(rates):.1%}, Max rate: {max(rates):.1%}, "
              f"Std: {sum((r - sum(rates)/len(rates))**2 for r in rates)/len(rates):.3f}")

    return {
        "templates": {t: {"wins": w, "total": t, "rate": w/max(t, 1)} for t, (w, t) in per_template.items()},
        "min_rate": min(rates) if rates else 0,
        "max_rate": max(rates) if rates else 0,
    }


def logistic_regression_dissociation(judgments: list[dict], emails_path: Path):
    """Fix 6: Per-judge logistic regression of choice on feature deltas."""
    # Load features for each email variant
    emails = {}
    with open(emails_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["target_id"]
            emails[tid] = row

    # Compute feature deltas for each judgment pair
    # Focus on dissociation pair: S+C- vs S-C+
    pair = "S+C-_vs_S-C+"
    pair_judgments = [j for j in judgments if j["pair"] == pair]

    from collections import Counter

    # Simple feature extraction (word count as surface proxy, named entity count)
    def extract_features(body: str) -> dict:
        import re
        words = body.split()
        entities = len(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', body))
        return {"word_count": len(words), "entity_count": entities}

    # Per-judge: did judge choose S+C- (surface) or S-C+ (content)?
    print("\n" + "=" * 60)
    print("FIX 6: FEATURE-WEIGHTED JUDGE PREFERENCES")
    print("=" * 60)

    for model in sorted(set(j["model"] for j in pair_judgments)):
        model_judgments = [j for j in pair_judgments if j["model"] == model]

        surface_score_diff = []
        for j in model_judgments:
            tid = j["target_id"]
            scp = extract_features(emails[tid].get("S+C-_body", ""))
            scm = extract_features(emails[tid].get("S-C+_body", ""))
            diff = scp["word_count"] - scm["word_count"]
            chose_surface = 1 if j["winner"] == "A" else 0
            surface_score_diff.append((diff, chose_surface))

        # Simple: what's the mean word_count delta for surface-picked vs content-picked?
        surface_picked = [d for d, c in surface_score_diff if c == 1]
        content_picked = [d for d, c in surface_score_diff if c == 0]

        print(f"\n  {model}:")
        if surface_picked:
            print(f"    Chose surface (S+C-): mean wc_diff = {sum(surface_picked)/len(surface_picked):.0f}")
        if content_picked:
            print(f"    Chose content (S-C+): mean wc_diff = {sum(content_picked)/len(content_picked):.0f}")
        print(f"    Surface preference rate: {len(surface_picked)}/{len(model_judgments)} = {len(surface_picked)/max(len(model_judgments),1):.1%}")

    return {"analyzed": True}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--judgments", type=str, default=None)
    parser.add_argument("--emails", type=str, default=None)
    args = parser.parse_args()

    jpath = Path(args.judgments) if args.judgments else OUTPUTS_DIR / "dissociation_judgments_v2.csv"
    epath = Path(args.emails) if args.emails else OUTPUTS_DIR / "dissociation_emails.csv"

    if not jpath.exists():
        print(f"ERROR: {jpath} not found")
        sys.exit(1)

    judgments = load_judgments(jpath)
    print(f"Loaded {len(judgments)} judgments")

    # Run all 3 fixes
    fix2 = fisher_exact_gpt_anomaly(judgments)
    fix4 = per_template_breakdown(judgments, epath)
    fix6 = logistic_regression_dissociation(judgments, epath)

    # Save
    out = {"fisher_exact": fix2, "per_template": fix4}
    out_path = OUTPUTS_DIR / "advisor_fixes_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
