# SURF: 2×2 Dissociation Protocol for Auditing Surface Bias in LLM-as-Judge Panels

Code and data for the CCNC 2027 paper.

## Data

All CSVs use N=100 per judge unless noted.

| File | Description |
|------|-------------|
| `outputs/n100/merged_dissociation.csv` | 2×2 dissociation judgments (4 judges × 4 pairs × 100 personas) |
| `outputs/n100/merged_introspection.csv` | Introspection probe ratings (content quality 1-10) |
| `outputs/n100/merged_doseresponse.csv` | Word-count manipulation sweep (6 ratios, 2,400 judgments) |
| `outputs/n100/consumer_demo.csv` | TKG threat-rating experiment |
| `outputs/dissociation_emails_100.csv` | Generated emails (4 variants × 100 personas) |
| `outputs/dissociation_emails_unique_cminus.csv` | Unique C− replication emails |

## Analysis

```bash
pip install numpy scipy
python scripts/analyze_n100.py
```

Outputs: win rates, bootstrap CIs, Cohen's κ, introspection gaps, dose-response curves.

Requires Python 3.10+, numpy, scipy.

## Citation

```bibtex
@inproceedings{elbaz2026surf,
  title={SURF: A 2×2 Dissociation Protocol for Auditing Surface Bias in LLM-as-Judge Panels},
  author={Elbaz, Aviv and Marbel, Revital and Berger, Harel and Alt, Florian},
  booktitle={CCNC},
  year={2026}
}
```
