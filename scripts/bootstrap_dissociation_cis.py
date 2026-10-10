"""Compute bootstrap CIs for all dissociation win-rate cells.

Clusters at persona level (effective N = 50).
Reports 95% bootstrap CIs for per-cell win rates and between-judge differences.

Usage:
  python scripts/bootstrap_dissociation_cis.py
"""

import csv
import json
import sys
import random
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR

N_BOOTSTRAP = 10000
SEED = 42


def load_judgments(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def bootstrap(persona_rows: dict, n_bootstrap: int = N_BOOTSTRAP) -> dict:
    """Bootstrap CIs clustered at persona level.

    persona_rows: {tid: {model: {pair: (wins_A, total)}}}
    Returns: {model: {pair: {"rate": float, "ci_low": float, "ci_high": float}}}
    """
    rng = random.Random(SEED)
    tids = sorted(persona_rows.keys())
    n = len(tids)

    # Compute per-cell distributions across bootstrap resamples
    # per model, per pair: list of win rates from bootstrap
    boot_rates = defaultdict(lambda: defaultdict(list))

    models = set()
    pairs = set()
    for tid_data in persona_rows.values():
        for model, pair_data in tid_data.items():
            models.add(model)
            for pair in pair_data:
                pairs.add(pair)

    for _ in range(n_bootstrap):
        # Resample personas with replacement
        sampled = rng.choices(tids, k=n)

        # Aggregate wins across resampled personas
        agg_wins = defaultdict(lambda: defaultdict(int))
        agg_total = defaultdict(lambda: defaultdict(int))

        for tid in sampled:
            for model in models:
                for pair in pairs:
                    wins, total = persona_rows[tid].get(model, {}).get(pair, (0, 0))
                    agg_wins[model][pair] += wins
                    agg_total[model][pair] += total

        for model in models:
            for pair in pairs:
                total = agg_total[model][pair]
                rate = agg_wins[model][pair] / total if total > 0 else 0.0
                boot_rates[model][pair].append(rate)

    # Compute CIs
    results = {}
    for model in sorted(models):
        results[model] = {}
        for pair in sorted(pairs):
            rates = sorted(boot_rates[model][pair])
            # Observed rate (mean of bootstrap)
            obs = sum(rates) / len(rates)
            ci_low = rates[int(0.025 * len(rates))]
            ci_high = rates[int(0.975 * len(rates))]
            results[model][pair] = {
                "rate": round(obs, 3),
                "ci_low": round(ci_low, 3),
                "ci_high": round(ci_high, 3),
            }

    return results


def main():
    path = OUTPUTS_DIR / "dissociation_judgments_merged.csv"
    if not path.exists():
        print(f"ERROR: {path} not found")
        sys.exit(1)

    judgments = load_judgments(path)
    print(f"Loaded {len(judgments)} judgments")

    # Aggregate per persona per model per pair
    persona_rows = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))
    # persona_rows[tid][model][pair] = [wins_A, total]

    for j in judgments:
        tid = j["target_id"]
        model = j["model"]
        pair = j["pair"]
        winner = j["winner"]

        persona_rows[tid][model][pair][1] += 1  # total
        if winner == "A":
            persona_rows[tid][model][pair][0] += 1  # wins_A

    # Convert to tuples
    persona_tuples = defaultdict(lambda: defaultdict(dict))
    for tid, tid_data in persona_rows.items():
        for model, pair_data in tid_data.items():
            for pair, (wins, total) in pair_data.items():
                persona_tuples[tid][model][pair] = (wins, total)

    # Bootstrap
    results = bootstrap(persona_tuples)

    print("\n" + "=" * 60)
    print("BOOTSTRAP 95% CIs (clustered at persona, N=50, 10K resamples)")
    print("=" * 60)

    for model in sorted(results):
        print(f"\n{model}:")
        for pair in sorted(results[model]):
            r = results[model][pair]
            print(f"  {pair}: {r['rate']:.1%} [{r['ci_low']:.1%}–{r['ci_high']:.1%}]")

    # Between-judge comparison for dissociation pair
    print("\n--- Between-Judge Differences (S+C- vs S-C+) ---")
    pair = "S+C-_vs_S-C+"
    judges = sorted(results.keys())
    for i, j1 in enumerate(judges):
        for j2 in judges[i+1:]:
            r1 = results[j1].get(pair, {}).get("rate", 0)
            r2 = results[j2].get(pair, {}).get("rate", 0)
            diff = abs(r1 - r2)
            print(f"  {j1} vs {j2}: Δ={diff:.1%}")

    # Save
    out_path = OUTPUTS_DIR / "dissociation_bootstrap_cis.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
