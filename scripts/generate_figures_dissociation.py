"""Generate LaTeX figures for the dissociation paper.

Figure 1: Per-judge feature importance convergence (bar chart)
Figure 2: 2×2 dissociation results (grouped bar chart)

Usage:
  python scripts/generate_figures_dissociation.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR


def fig1_feature_convergence():
    """Generate data for Figure 1: per-judge feature correlations."""
    # Load Phase 0 results
    phase0_path = OUTPUTS_DIR / "phase0_stability_results.json"
    if not phase0_path.exists():
        return None

    with open(phase0_path) as f:
        data = json.load(f)

    jaccard = data.get("jaccard_agreement", {})

    out_lines = []
    out_lines.append("% Figure 1 data: Per-judge feature importance (Pearson r from Phase 0)")
    out_lines.append("% Generated from phase0_stability_results.json")
    out_lines.append("")
    for model, info in jaccard.items():
        freqs = info.get("feature_frequencies", {})
        out_lines.append(f"% {model}:")
        for feat, count in sorted(freqs.items(), key=lambda x: -x[1]):
            out_lines.append(f"%   {feat}: {count}/5 seeds")

    # Generate LaTeX tikz/pgfplots data
    out_lines.append("")
    out_lines.append("% Table for paper:")
    out_lines.append(r"\begin{table}[h]")
    out_lines.append(r"\centering")
    out_lines.append(r"\caption{Per-judge top-3 features by correlation with win rate (Phase 0).}")
    out_lines.append(r"\label{tab:features}")
    out_lines.append(r"\begin{tabular}{lccc}")
    out_lines.append(r"\toprule")
    out_lines.append(r"\textbf{Feature} & \textbf{GPT-4.1-mini} & \textbf{DeepSeek} & \textbf{Claude} \\")
    out_lines.append(r"\midrule")

    # Top features across all judges
    all_features = set()
    for model, info in jaccard.items():
        for feat, count in info.get("feature_frequencies", {}).items():
            if count >= 3:
                all_features.add(feat)

    for feat in sorted(all_features):
        cells = []
        for model in jaccard:
            count = jaccard[model].get("feature_frequencies", {}).get(feat, 0)
            cells.append(f"{count}/5")
        out_lines.append(f"  {feat} & " + " & ".join(cells) + r" \\")

    out_lines.append(r"\bottomrule")
    out_lines.append(r"\end{tabular}")
    out_lines.append(r"\end{table}")

    return "\n".join(out_lines)


def fig2_dissociation():
    """Generate data for Figure 2: 2×2 dissociation bar chart."""
    analysis_path = OUTPUTS_DIR / "dissociation_analysis.json"
    judgments_path = OUTPUTS_DIR / "dissociation_judgments.csv"

    if not analysis_path.exists() and not judgments_path.exists():
        return "% Figure 2: Run judge_dissociation.py first"

    if not analysis_path.exists():
        return "% Figure 2: Run analyze_dissociation.py after judgments complete"

    with open(analysis_path) as f:
        data = json.load(f)

    win_rates = data.get("win_rates", {})
    dissociation = data.get("dissociation", {})
    judges = data.get("judge_models", [])

    out_lines = []
    out_lines.append("% Figure 2: 2×2 dissociation results")
    out_lines.append("")

    # Build LaTeX table
    out_lines.append(r"\begin{table}[h]")
    out_lines.append(r"\centering")
    out_lines.append(r"\caption{2$\times$2 dissociation results. Cells show win rate of the first variant.}")
    out_lines.append(r"\label{tab:dissociation}")
    out_lines.append(r"\begin{tabular}{lcccc}")
    out_lines.append(r"\toprule")
    out_lines.append(r"\textbf{Pair} & " + " & ".join(judges) + r" \\")
    out_lines.append(r"\midrule")

    pairs = ["S+C+_vs_S-C-", "S+C-_vs_S-C+", "S+C-_vs_S-C-", "S-C+_vs_S-C-"]
    pair_labels = {
        "S+C+_vs_S-C-": r"S+C+ vs S-C-",
        "S+C-_vs_S-C+": r"\textbf{S+C- vs S-C+}",
        "S+C-_vs_S-C-": r"S+C- vs S-C-",
        "S-C+_vs_S-C-": r"S-C+ vs S-C-",
    }

    for pair in pairs:
        label = pair_labels.get(pair, pair)
        cells = []
        for model in judges:
            wr = win_rates.get(model, {}).get(pair, {})
            rate = wr.get("rate_A", 0)
            n = wr.get("total", 0)
            cells.append(f"{rate:.1%}")
        out_lines.append(f"  {label} & " + " & ".join(cells) + r" \\")

    # Add human anchor row if available
    human_path = OUTPUTS_DIR / "human_anchor_results.json"
    if human_path.exists():
        with open(human_path) as f:
            human = json.load(f)
        h_rate = human.get("surface_preference", 0)
        out_lines.append(r"  \midrule")
        out_lines.append(f"  Human (N=3, 20 pairs) & \\multicolumn{{3}}{{c}}{{{h_rate:.0%} prefer S+C-}} \\\\")

    out_lines.append(r"\bottomrule")
    out_lines.append(r"\end{tabular}")
    out_lines.append(r"\end{table}")

    # Key finding summary
    out_lines.append("")
    out_lines.append("% Key finding:")
    for model in judges:
        if model in dissociation:
            d = dissociation[model]
            out_lines.append(f"% {model}: {d['surface_win_rate']:.1%} surface preference "
                           f"({d['prefer_surface']}/{d['total']})")

    return "\n".join(out_lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    fig1 = fig1_feature_convergence()
    fig2 = fig2_dissociation()

    out = []
    out.append("=" * 60)
    out.append("FIGURE 1: Feature Convergence")
    out.append("=" * 60)
    out.append(fig1 or "No data available")
    out.append("")
    out.append("=" * 60)
    out.append("FIGURE 2: Dissociation Results")
    out.append("=" * 60)
    out.append(fig2 or "No data available")

    out_text = "\n".join(out)
    print(out_text)

    out_path = args.output or str(OUTPUTS_DIR / "figures_dissociation.tex")
    with open(out_path, "w") as f:
        f.write(out_text)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
