"""Generate regime-gap figure for LLMNet 2026b paper.

Figure: Content discrimination across regimes (high-surface vs low-surface)
with per-judge bars and 95% bootstrap CIs.

Usage:
  python scripts/generate_paper_figure.py
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Data from v2 analysis
# High-surface: S+C+ vs S+C- (cross-regime control)
# Low-surface: S-C+ vs S-C- (content effect, surface stripped)
# Dissociation: S+C- vs S-C+ (surface vs content conflict)

judges = ['Claude\nSonnet 4.6', 'DeepSeek\nChat', 'GPT-4.1\nMini']
n_judges = len(judges)

# Win rates (content preference)
high_surface = [56.0, 54.0, 56.0]  # S+C+ vs S+C- (C+ wins)
low_surface = [100.0, 100.0, 100.0]  # S-C+ vs S-C- (C+ wins)
dissociation = [86.0, 78.0, 62.0]  # S-C+ vs S+C- (content wins)

# Bootstrap CIs [low, high] as deltas from point estimate
high_cis = [(56-41, 71-56), (54-39, 69-54), (56-40, 72-56)]  # from earlier analysis
low_cis = [(0, 0), (0, 0), (0, 0)]  # [100-100]
dissoc_cis = [(86-76, 94-86), (78-66, 88-78), (62-48, 76-62)]

fig, ax = plt.subplots(figsize=(4.5, 3.2))

x = np.arange(n_judges)
width = 0.22

# High-surface bars
bars1 = ax.bar(x - width, high_surface, width, label='High-surface regime\n(S+C+ vs S+C-)',
               color='#E8A87C', edgecolor='#C47F53', linewidth=0.5)
# Low-surface bars
bars2 = ax.bar(x, low_surface, width, label='Low-surface regime\n(S-C+ vs S-C-)',
               color='#95B8D1', edgecolor='#6B8FA3', linewidth=0.5)
# Dissociation bars
bars3 = ax.bar(x + width, dissociation, width, label='Dissociation\n(S-C+ vs S+C-)',
               color='#B8D995', edgecolor='#8CA36B', linewidth=0.5)

# Add CIs as error bars
for i in range(n_judges):
    ax.errorbar(x[i] - width, high_surface[i],
                yerr=[[high_cis[i][0]], [high_cis[i][1]]],
                fmt='none', ecolor='#C47F53', capsize=3, linewidth=0.8)
    ax.errorbar(x[i] + width, dissociation[i],
                yerr=[[dissoc_cis[i][0]], [dissoc_cis[i][1]]],
                fmt='none', ecolor='#8CA36B', capsize=3, linewidth=0.8)

# Chance line
ax.axhline(y=50, color='gray', linestyle='--', linewidth=0.7, alpha=0.5)
ax.text(2.4, 51, 'chance', fontsize=7, color='gray', va='bottom')

# Labels
ax.set_ylabel('Content preference (%)', fontsize=9)
ax.set_xticks(x)
ax.set_xticklabels(judges, fontsize=8)
ax.set_ylim(0, 108)
ax.legend(fontsize=7, loc='lower right', framealpha=0.9)

# Title
ax.set_title('Content discrimination by regime and judge', fontsize=10, fontweight='bold')

# Grid
ax.yaxis.grid(True, alpha=0.3)
ax.set_axisbelow(True)

plt.tight_layout()
out_path = '/mnt/data/git/spear-phishing-llm/publish/llmnet-2026-llm-as-judge/figures/regime_gap.pdf'
plt.savefig(out_path, dpi=150, bbox_inches='tight')
print(f'Figure saved: {out_path}')
