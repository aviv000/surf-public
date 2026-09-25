"""Phase 0: Discovery Stability Check for Adversarial Judge Exploitation.

Extracts 6 new linguistic features, joins with existing 10 features + judgment data,
runs per-judge per-feature correlation stability across 5 random discovery/eval splits.

Usage:
  python scripts/phase0_discovery_stability.py
  python scripts/phase0_discovery_stability.py --seeds 10
  python scripts/phase0_discovery_stability.py --output outputs/phase0_results.json
"""

import csv
import json
import re
import sys
import random
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR

# ---------------------------------------------------------------------------
# 6 new feature extractors (all regex/lexicon, zero LLM)
# ---------------------------------------------------------------------------

FLATTERY_LEXICON = re.compile(
    r'\b(impressive|esteemed|leading|pioneer|excellent|outstanding|'
    r'remarkable|influential|prominent|distinguished|accomplished|'
    r'brilliant|innovative|groundbreaking|renowned|celebrated)\b',
    re.IGNORECASE
)

URGENCY_LEXICON = re.compile(
    r'\b(deadline|urgent|immediately|now|limited|today|soon|'
    r'expiring|critical|time.sensitive|crucial|pressing)\b',
    re.IGNORECASE
)

DEFERENCE_LEXICON = re.compile(
    r'(would appreciate|if you have time|at your convenience|'
    r'honored|grateful|thank you for considering|I understand if|'
    r'no pressure|whenever possible|should you be interested)',
    re.IGNORECASE
)


def extract_new_features(email_body: str) -> dict:
    """Extract 6 new linguistic features from email body. Zero LLM calls."""
    words = email_body.split()
    n_words = max(len(words), 1)

    # Flattery density
    flattery_count = len(FLATTERY_LEXICON.findall(email_body))
    flattery_density = round(flattery_count / n_words, 4)

    # Urgency density
    urgency_count = len(URGENCY_LEXICON.findall(email_body))
    urgency_density = round(urgency_count / n_words, 4)

    # Question count
    question_count = email_body.count('?')

    # Deference density
    deference_count = len(DEFERENCE_LEXICON.findall(email_body))
    deference_density = round(deference_count / n_words, 4)

    # Greeting formality: 0=none, 1=Hi/Hey/Hello, 2=Dear Dr./Dear Professor
    first_line = email_body.strip().split('\n')[0].strip() if email_body.strip() else ''
    greeting_formality = 0
    if re.match(r'^(Dear\s+(Dr\.?|Professor|Prof\.?)\s+)', first_line, re.IGNORECASE):
        greeting_formality = 2
    elif re.match(r'^(Hi|Hey|Hello|Greetings)\b', first_line, re.IGNORECASE):
        greeting_formality = 1

    # Exclamation count
    exclamation_count = email_body.count('!')

    return {
        "flattery_density": flattery_density,
        "urgency_density": urgency_density,
        "question_count": question_count,
        "deference_density": deference_density,
        "greeting_formality": greeting_formality,
        "exclamation_count": exclamation_count,
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_emails(path: Path) -> list[dict]:
    """Load email CSV, return list of dicts with extracted features."""
    emails = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            body = row.get("email_body", "")
            if not body or len(body) < 10 or row.get("error", "") == "True":
                continue
            feats = extract_new_features(body)
            feats["target_id"] = row["target_id"]
            feats["hook_level"] = int(row.get("hook_level", 0))
            emails.append(feats)
    return emails


def load_existing_features(path: Path) -> dict:
    """Load existing linguistic_features.csv. Returns {(tid, hook_level): features}."""
    features = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["target_id"]
            level = int(row.get("hook_level", 0))
            features[(tid, level)] = {
                k: float(v) if k not in ("target_id", "hook_level", "error") else v
                for k, v in row.items()
            }
    return features


def load_judgments(path: Path) -> list[dict]:
    """Load length_blind_judgments.csv."""
    judgments = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            judgments.append(row)
    return judgments


# ---------------------------------------------------------------------------
# Per-judge per-persona win rate computation
# ---------------------------------------------------------------------------

def compute_win_rates(judgments: list[dict]) -> dict:
    """Compute per-judge per-persona win rate for higher-hook-count emails.

    Returns: {model: {tid: {hook_level: win_rate}}}
    win_rate = fraction of times this hook_level email won a pairwise comparison.
    """
    # For each judgment, record which hook level won
    judge_wins = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    # judge_wins[model][tid][winning_level] = [1/0 values]

    for j in judgments:
        model = j["model"]
        tid = j["tid"]
        level_a = int(j["level_a"])
        level_b = int(j["level_b"])
        winner = j["winner"]  # "A" or "B"

        winning_level = level_a if winner == "A" else level_b
        losing_level = level_b if winner == "A" else level_a

        # Record win for winning level
        judge_wins[model][tid][winning_level].append(1)
        judge_wins[model][tid][losing_level].append(0)

    # Compute win rates
    win_rates = {}
    for model, tids in judge_wins.items():
        win_rates[model] = {}
        for tid, levels in tids.items():
            win_rates[model][tid] = {}
            for level, outcomes in levels.items():
                if outcomes:
                    win_rates[model][tid][level] = sum(outcomes) / len(outcomes)

    return win_rates


# ---------------------------------------------------------------------------
# Feature merging
# ---------------------------------------------------------------------------

def merge_features(new_features: list[dict], existing_features: dict) -> dict:
    """Merge new and existing features. Returns {(tid, hook_level): {all 16 features}}."""
    merged = {}
    for feats in new_features:
        tid = feats["target_id"]
        level = feats["hook_level"]
        key = (tid, level)

        m = {
            "flattery_density": feats["flattery_density"],
            "urgency_density": feats["urgency_density"],
            "question_count": feats["question_count"],
            "deference_density": feats["deference_density"],
            "greeting_formality": feats["greeting_formality"],
            "exclamation_count": feats["exclamation_count"],
        }

        # Add existing features
        if key in existing_features:
            for k, v in existing_features[key].items():
                if k not in ("target_id", "hook_level", "error"):
                    m[k] = float(v) if not isinstance(v, (int, float)) else v

        merged[key] = m
    return merged


# ---------------------------------------------------------------------------
# Stability check
# ---------------------------------------------------------------------------

def discovery_split_stability(
    merged_features: dict,
    win_rates: dict,
    n_seeds: int = 5,
    discovery_frac: float = 0.5,
) -> dict:
    """Run stability check: re-split personas, compute per-judge per-feature Pearson r,
    measure Jaccard agreement on top-3 features per judge.

    Returns detailed results per seed.
    """
    # Get unique persona IDs
    all_tids = sorted(set(k[0] for k in merged_features.keys()))
    n_discovery = max(int(len(all_tids) * discovery_frac), 10)

    FEATURE_NAMES = [
        "flattery_density", "urgency_density", "question_count",
        "deference_density", "greeting_formality", "exclamation_count",
        "word_count", "flesch_reading_ease", "flesch_kincaid_grade",
        "named_entity_count", "cta_cue_count", "pronoun_first",
        "pronoun_second", "hedging_density", "formality_density",
    ]
    JUDGE_MODELS = list(win_rates.keys())

    seed_results = {}
    all_top_features = defaultdict(lambda: defaultdict(list))
    # all_top_features[seed]["gpt-4.1-mini"] = [feat1, feat2, feat3]

    for seed in range(n_seeds):
        rng = random.Random(seed)
        tids_shuffled = rng.sample(all_tids, len(all_tids))
        discovery_tids = set(tids_shuffled[:n_discovery])

        # Collect feature-value and win-rate pairs for discovery set
        # per judge: {feature_name: [(feature_val, win_rate), ...]}
        judge_data = defaultdict(lambda: defaultdict(list))

        for (tid, level), feats in merged_features.items():
            if tid not in discovery_tids:
                continue

            for model in JUDGE_MODELS:
                wr = win_rates.get(model, {}).get(tid, {}).get(level)
                if wr is None:
                    continue
                for fname in FEATURE_NAMES:
                    if fname in feats and feats[fname] is not None:
                        judge_data[model][fname].append((feats[fname], wr))

        # Compute Pearson r per judge per feature
        judge_corrs = {}
        for model in JUDGE_MODELS:
            judge_corrs[model] = {}
            for fname in FEATURE_NAMES:
                pairs = judge_data[model][fname]
                if len(pairs) < 10:
                    judge_corrs[model][fname] = None
                    continue
                xs = [p[0] for p in pairs]
                ys = [p[1] for p in pairs]
                r = pearson_r(xs, ys)
                judge_corrs[model][fname] = r

        # Select top-3 features per judge by absolute correlation
        top3 = {}
        for model in JUDGE_MODELS:
            valid = [(f, abs(r)) for f, r in judge_corrs[model].items() if r is not None]
            valid.sort(key=lambda x: x[1], reverse=True)
            top3[model] = [f for f, _ in valid[:3]]
            all_top_features[seed][model] = top3[model]

        seed_results[seed] = {
            "discovery_tids": sorted(discovery_tids),
            "correlations": judge_corrs,
            "top3": top3,
        }

    # Compute Jaccard agreement across seeds for each judge
    jaccard_results = {}
    for model in JUDGE_MODELS:
        top3_sets = {seed: set(all_top_features[seed][model]) for seed in range(n_seeds)}
        # Pairwise Jaccard
        pairwise_jaccards = []
        for i in range(n_seeds):
            for j in range(i + 1, n_seeds):
                s_i = top3_sets[i]
                s_j = top3_sets[j]
                if s_i and s_j:
                    jacc = len(s_i & s_j) / len(s_i | s_j)
                    pairwise_jaccards.append(jacc)

        # Per-feature selection frequency
        feature_freq = defaultdict(int)
        for seed in range(n_seeds):
            for feat in top3_sets[seed]:
                feature_freq[feat] += 1

        jaccard_results[model] = {
            "mean_jaccard": round(sum(pairwise_jaccards) / max(len(pairwise_jaccards), 1), 3),
            "pairwise_jaccards": pairwise_jaccards,
            "feature_frequencies": dict(feature_freq),
            "stable_intersection": [f for f, c in feature_freq.items() if c >= 3],
        }

    return {
        "n_seeds": n_seeds,
        "n_discovery": n_discovery,
        "n_total_personas": len(all_tids),
        "per_seed": {str(k): v for k, v in seed_results.items()},
        "jaccard_agreement": jaccard_results,
        "overall_verdict": "PASS" if all(
            jaccard_results[m]["mean_jaccard"] >= 0.5
            for m in JUDGE_MODELS
        ) else "FAIL — need more personas or feature pruning",
    }


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def pearson_r(xs: list, ys: list) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    std_x = (sum((x - mean_x) ** 2 for x in xs)) ** 0.5
    std_y = (sum((y - mean_y) ** 2 for y in ys)) ** 0.5
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--emails", type=str, default="outputs/within_condition_emails.csv")
    parser.add_argument("--features", type=str, default="outputs/linguistic_features.csv")
    parser.add_argument("--judgments", type=str, default="outputs/length_blind_judgments.csv")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    root = Path(__file__).parent.parent if "__file__" in dir() else Path.cwd()
    emails_path = root / args.emails
    features_path = root / args.features
    judgments_path = root / args.judgments

    print("=" * 60)
    print("PHASE 0: Discovery Stability Check")
    print("=" * 60)

    # Load data
    print(f"\nLoading emails: {emails_path}")
    new_features = load_emails(emails_path)
    print(f"  {len(new_features)} emails with new features")

    print(f"Loading existing features: {features_path}")
    existing = load_existing_features(features_path)
    print(f"  {len(existing)} existing feature rows")

    print(f"Loading judgments: {judgments_path}")
    judgments = load_judgments(judgments_path)
    print(f"  {len(judgments)} judgments")

    # Merge features
    merged = merge_features(new_features, existing)
    print(f"\nMerged features: {len(merged)} persona×level pairs")

    # Compute win rates
    win_rates = compute_win_rates(judgments)
    judge_models = list(win_rates.keys())
    print(f"Judge models: {judge_models}")
    for model in judge_models:
        n_personas = len(win_rates[model])
        n_rates = sum(len(levels) for levels in win_rates[model].values())
        print(f"  {model}: {n_personas} personas, {n_rates} win-rate data points")

    # Print feature distributions
    print("\nNew feature distributions (across all emails):")
    feature_names = [
        "flattery_density", "urgency_density", "question_count",
        "deference_density", "greeting_formality", "exclamation_count",
    ]
    for fname in feature_names:
        vals = [m[fname] for m in merged.values() if fname in m and m[fname] is not None]
        if vals:
            print(f"  {fname}: mean={sum(vals)/len(vals):.4f}, "
                  f"min={min(vals)}, max={max(vals)}, "
                  f"nonzero={sum(1 for v in vals if v > 0)}/{len(vals)}")

    # Run stability check
    print(f"\n{'='*60}")
    print(f"STABILITY CHECK: {args.seeds} seeds, 50/50 split")
    print(f"{'='*60}")

    results = discovery_split_stability(
        merged, win_rates, n_seeds=args.seeds, discovery_frac=0.5
    )

    print(f"\nOverall verdict: {results['overall_verdict']}")
    print(f"\nPer-judge Jaccard agreement:")
    for model, jr in results["jaccard_agreement"].items():
        print(f"\n  {model}:")
        print(f"    Mean Jaccard: {jr['mean_jaccard']}")
        print(f"    Pairwise: {jr['pairwise_jaccards']}")
        print(f"    Stable features (in ≥3/{args.seeds} seeds): {jr['stable_intersection']}")
        print(f"    Feature frequencies:")
        for feat, count in sorted(jr["feature_frequencies"].items(), key=lambda x: -x[1]):
            print(f"      {feat}: {count}/{args.seeds}")

    # Print top features per judge (first seed)
    first_seed = results["per_seed"]["0"]
    print(f"\nTop-3 features per judge (seed 0):")
    for model in judge_models:
        top3 = first_seed["top3"][model]
        corrs = first_seed["correlations"][model]
        print(f"\n  {model}:")
        for feat in top3:
            r = corrs.get(feat, 0)
            print(f"    {feat}: r={r:.3f}")

    # Save results
    out_path = args.output or str(root / "outputs" / "phase0_stability_results.json")
    # Convert to serializable format
    serializable = {
        "overall_verdict": results["overall_verdict"],
        "n_seeds": results["n_seeds"],
        "n_discovery": results["n_discovery"],
        "n_total_personas": results["n_total_personas"],
        "jaccard_agreement": results["jaccard_agreement"],
        "per_seed_summary": {
            seed: {
                "top3": data["top3"],
            }
            for seed, data in results["per_seed"].items()
        },
    }
    with open(out_path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\nResults saved to: {out_path}")

    # Exit code
    if "FAIL" in results["overall_verdict"]:
        print("\n⚠️  Stability check FAILED. Consider: more personas, feature pruning, or larger discovery set.")
        sys.exit(1)
    else:
        print("\n✅ Stability check PASSED. Proceed to Phase 1.")
        sys.exit(0)


if __name__ == "__main__":
    main()
