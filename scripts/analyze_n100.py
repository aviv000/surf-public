"""Compute all paper statistics from merged N=100 data."""
import csv, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR

OUT = OUTPUTS_DIR / "n100"

def load(path):
    with open(path) as f: return list(csv.DictReader(f))

def bootstrap_ci(judgments, n_resamples=10000):
    """95% CI clustered at persona level.
    judgments: list of (persona_id, winner_is_A) tuples.
    Resamples whole personas (with replacement), not individual judgments.
    """
    # Group by persona
    by_persona = defaultdict(list)
    for pid, win in judgments:
        by_persona[pid].append(win)

    persona_rates = np.array([np.mean(wins) for wins in by_persona.values()])
    n_personas = len(persona_rates)
    if n_personas == 0: return [0, 0]

    # Resample personas with replacement
    samples = np.random.choice(persona_rates, size=(n_resamples, n_personas), replace=True)
    means = samples.mean(axis=1) * 100
    return np.percentile(means, [2.5, 97.5])

def cohen_kappa(table):
    a, b = table[0]; c, d = table[1]
    n = a + b + c + d
    if n == 0: return None
    po = (a + d) / n
    pe = ((a+b)*(a+c) + (c+d)*(b+d)) / (n*n)
    if pe == 1: return None
    return (po - pe) / (1 - pe)

# ── 1. Dissociation ─────────────────────────────────────────────────────────
print("=" * 60)
print("1. DISSOCIATION WIN RATES")
print("=" * 60)
dissoc = load(OUT / "merged_dissociation.csv")
pairs = sorted(set(r["pair"] for r in dissoc))
models = sorted(set(r["model"] for r in dissoc))

for pair in pairs:
    print(f"\n{pair}:")
    for model in models:
        rows = [r for r in dissoc if r["pair"] == pair and r["model"] == model]
        wins_a = sum(1 for r in rows if r["winner"] == "A")
        total = len(rows)
        if total == 0: continue
        rate = wins_a / total * 100
        ci = bootstrap_ci([(r["target_id"], 1 if r["winner"] == "A" else 0) for r in rows])
        bt = binomtest(wins_a, total, p=0.5, alternative="two-sided")
        p_str = f"p<0.001" if bt.pvalue < 0.001 else f"p={bt.pvalue:.2f}"
        sig = "***" if bt.pvalue < 0.001 else "**" if bt.pvalue < 0.01 else "*" if bt.pvalue < 0.05 else "ns"
        print(f"  {model}: {rate:.0f}% [{ci[0]:.0f}–{ci[1]:.0f}] {p_str} {sig} (N={total})")

# ── 2. Agreement ────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("2. INTER-JUDGE AGREEMENT")
print("=" * 60)
non_gemini = [m for m in models if "gemini" not in m]
for pair in pairs:
    print(f"\n{pair}:")
    for i, m1 in enumerate(non_gemini):
        for m2 in non_gemini[i+1:]:
            tids = sorted(set(r["target_id"] for r in dissoc if r["pair"] == pair))
            m1_a = sum(1 for tid in tids for r in dissoc if r["pair"]==pair and r["model"]==m1 and r["target_id"]==tid and r["winner"]=="A")
            m2_a = sum(1 for tid in tids for r in dissoc if r["pair"]==pair and r["model"]==m2 and r["target_id"]==tid and r["winner"]=="A")
            both_a = sum(1 for tid in tids
                        for r1 in dissoc if r1["pair"]==pair and r1["model"]==m1 and r1["target_id"]==tid and r1["winner"]=="A"
                        for r2 in dissoc if r2["pair"]==pair and r2["model"]==m2 and r2["target_id"]==tid and r2["winner"]=="A")
            both_b = sum(1 for tid in tids
                        for r1 in dissoc if r1["pair"]==pair and r1["model"]==m1 and r1["target_id"]==tid and r1["winner"]=="B"
                        for r2 in dissoc if r2["pair"]==pair and r2["model"]==m2 and r2["target_id"]==tid and r2["winner"]=="B")
            agree = (both_a + both_b) / len(tids) * 100 if tids else 0
            table = [[both_a, m1_a - both_a], [m2_a - both_a, both_b]]
            k = cohen_kappa(table)
            k_str = f"{k:.2f}" if k is not None else "---"
            print(f"  {m1} vs {m2}: {agree:.0f}% (k={k_str})")

# ── 3. Introspection ────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("3. INTROSPECTION")
print("=" * 60)
intro_path = OUT / "merged_introspection.csv"
if not intro_path.exists():
    print("  Not yet merged (waiting for Gemini)")
else:
    intro = load(intro_path)
    for model in sorted(set(r["model"] for r in intro)):
        sc_minus = [int(r["content_score"]) for r in intro if r["model"] == model and r["email_variant"] == "S+C-"]
        sc_plus = [int(r["content_score"]) for r in intro if r["model"] == model and r["email_variant"] == "S-C+"]
        if not sc_minus or not sc_plus: continue
        gap = np.mean(sc_plus) - np.mean(sc_minus)
        print(f"\n{model}:")
        print(f"  S+C- mean: {np.mean(sc_minus):.1f}, S-C+ mean: {np.mean(sc_plus):.1f}, gap: {gap:+.1f}")
        model_dissoc = [r for r in dissoc if r["model"] == model and r["pair"] == "S+C-_vs_S-C+"]
        inconsistent = 0; total = 0
        for r in model_dissoc:
            tid = r["target_id"]
            ratings = [x for x in intro if x["target_id"] == tid and x["model"] == model]
            if len(ratings) < 2: continue
            sc_minus_score = int([x for x in ratings if x["email_variant"] == "S+C-"][0]["content_score"])
            sc_plus_score = int([x for x in ratings if x["email_variant"] == "S-C+"][0]["content_score"])
            chose_surface = r["winner"] == "A"
            if sc_plus_score >= sc_minus_score and chose_surface: inconsistent += 1
            total += 1
        if total > 0:
            print(f"  Inconsistent: {inconsistent}/{total} ({inconsistent/total*100:.0f}%)")
        surf = sum(1 for r in model_dissoc if r["winner"]=="A")
        print(f"  Surface pref: {surf}/{len(model_dissoc)} ({surf/max(len(model_dissoc),1)*100:.0f}%)")

# ── 4. Dose-response ────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("4. DOSE-RESPONSE")
print("=" * 60)
dr_path = OUT / "merged_doseresponse.csv"
if dr_path.exists():
    dr = load(dr_path)
    for model in sorted(set(r["model"] for r in dr)):
        print(f"\n{model}:")
        for ratio in sorted(set(r["ratio"] for r in dr), key=float):
            rows = [r for r in dr if r["model"] == model and r["ratio"] == ratio]
            wins_long = sum(1 for r in rows if r["winner"] == "A")
            total = len(rows)
            if total > 0:
                print(f"  {ratio}: {wins_long}/{total} = {wins_long/total*100:.0f}%")

print("\nANALYSIS COMPLETE")
