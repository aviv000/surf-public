"""Analyze 2×2 dissociation experiment results.

Computes:
- Win rates per pair, per judge
- Primary dissociation: S+C- vs S-C+ win rates
- Cross-family convergence: per-judge win rate comparison
- Confidence score analysis
- Saves Figure 1 data (per-judge feature convergence) and Figure 2 data (dissociation bar chart)

Usage:
  python scripts/analyze_dissociation.py
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


def analyze(judgments: list[dict]) -> dict:
    """Main analysis."""

    JUDGE_MODELS = sorted(set(j["model"] for j in judgments))
    PAIRS = sorted(set(j["pair"] for j in judgments))

    # ---- Win rates ----
    # per_pair[model][pair] = {"wins_A": N, "total": N, "rate": float}
    per_pair = defaultdict(lambda: defaultdict(lambda: {"wins_A": 0, "total": 0}))

    for j in judgments:
        pair = j["pair"]
        model = j["model"]
        winner = j["winner"]

        per_pair[model][pair]["total"] += 1
        if winner == "A":  # A = first variant in pair name
            per_pair[model][pair]["wins_A"] += 1

    # Compute rates
    win_rates = {}
    for model in JUDGE_MODELS:
        win_rates[model] = {}
        for pair in PAIRS:
            data = per_pair[model][pair]
            if data["total"] > 0:
                win_rates[model][pair] = {
                    "wins_A": data["wins_A"],
                    "total": data["total"],
                    "rate_A": round(data["wins_A"] / data["total"], 3),
                }

    # ---- Primary dissociation test ----
    dissociation = {}
    primary_pair = "S+C-_vs_S-C+"
    if primary_pair in PAIRS:
        for model in JUDGE_MODELS:
            data = per_pair[model][primary_pair]
            if data["total"] > 0:
                # A = S+C- (surface-dominant), B = S-C+ (content-dominant)
                dissociation[model] = {
                    "prefer_surface": data["wins_A"],
                    "prefer_content": data["total"] - data["wins_A"],
                    "total": data["total"],
                    "surface_win_rate": round(data["wins_A"] / data["total"], 3),
                }

    # ---- Cross-family convergence ----
    # Are per-judge win rates similar across models?
    convergence = {}
    for pair in PAIRS:
        rates = []
        for model in JUDGE_MODELS:
            if model in win_rates and pair in win_rates[model]:
                rates.append(win_rates[model][pair]["rate_A"])
        if rates:
            convergence[pair] = {
                "min_rate": min(rates),
                "max_rate": max(rates),
                "range": round(max(rates) - min(rates), 3),
                "mean": round(sum(rates) / len(rates), 3),
            }

    # ---- Confidence scores ----
    confidence = defaultdict(lambda: defaultdict(list))
    for j in judgments:
        confidence[j["model"]][j["pair"]].append(int(j.get("confidence", 3)))

    conf_summary = {}
    for model in JUDGE_MODELS:
        conf_summary[model] = {}
        for pair in PAIRS:
            vals = confidence[model][pair]
            if vals:
                conf_summary[model][pair] = {
                    "mean": round(sum(vals) / len(vals), 2),
                    "min": min(vals),
                    "max": max(vals),
                }

    # ---- Overall summary ----
    print("=" * 60)
    print("2×2 DISSOCIATION ANALYSIS")
    print("=" * 60)

    print("\n--- Win Rates (rate that first variant wins) ---")
    for pair in PAIRS:
        pair_label = pair.replace("_vs_", " vs ")
        print(f"\n  {pair_label}:")
        for model in JUDGE_MODELS:
            if model in win_rates and pair in win_rates[model]:
                wr = win_rates[model][pair]
                print(f"    {model}: {wr['wins_A']}/{wr['total']} = {wr['rate_A']:.1%}")

    print(f"\n--- Dissociation Test ({primary_pair}) ---")
    print(f"  H1: surface (S+C-) > content (S-C+) across all judges")
    for model in JUDGE_MODELS:
        if model in dissociation:
            d = dissociation[model]
            print(f"    {model}: surface {d['surface_win_rate']:.1%} "
                  f"({d['prefer_surface']}/{d['total']})")

    print("\n--- Cross-Family Convergence ---")
    for pair in PAIRS:
        if pair in convergence:
            c = convergence[pair]
            print(f"  {pair}: range={c['range']:.1%} (min={c['min_rate']:.1%}, max={c['max_rate']:.1%})")

    print("\n--- Confidence Scores ---")
    for model in JUDGE_MODELS:
        print(f"  {model}:")
        for pair in PAIRS:
            if pair in conf_summary[model]:
                cs = conf_summary[model][pair]
                print(f"    {pair}: mean={cs['mean']:.1f} [{cs['min']}-{cs['max']}]")

    # ---- Build results dict ----
    return {
        "win_rates": win_rates,
        "dissociation": dissociation,
        "convergence": convergence,
        "confidence": conf_summary,
        "judge_models": JUDGE_MODELS,
        "pairs": PAIRS,
        "total_judgments": len(judgments),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    path = Path(args.input) if args.input else OUTPUTS_DIR / "dissociation_judgments.csv"
    if not path.exists():
        print(f"ERROR: {path} not found. Run judge_dissociation.py first.")
        sys.exit(1)

    judgments = load_judgments(path)
    print(f"Loaded {len(judgments)} judgments")

    results = analyze(judgments)

    out_path = args.output or str(OUTPUTS_DIR / "dissociation_analysis.json")
    # Simplify for serialization
    serializable = {
        "win_rates": results["win_rates"],
        "dissociation": results["dissociation"],
        "convergence": results["convergence"],
        "total_judgments": results["total_judgments"],
    }
    with open(out_path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\nAnalysis saved: {out_path}")


if __name__ == "__main__":
    main()
