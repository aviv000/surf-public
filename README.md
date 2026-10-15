# Clean Text, Missed Threats: The SURF Audit of LLM Phishing-Triage Panels

Code and data for the IEEE ICC 2027 (CISS symposium) paper. SURF is a
2×2 surface×content dissociation protocol with placebo, context, and
generator-swap controls that audits LLM judges inside phishing-defense
pipelines. Headline: in the deployed pointwise format, four cross-family
judges label plain personalized phishing emails benign ~90% of the time
(100% on the explicit-call-to-action subset) against a 0% false-positive
rate on matched benign plain mail.

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
  title={Clean Text, Missed Threats: The SURF Audit of LLM Phishing-Triage Panels},
  author={Elbaz, Aviv and Marbel, Revital and Berger, Harel and Alt, Florian},
  booktitle={Proc. IEEE International Conference on Communications (ICC), CISS Symposium},
  year={2026}
},
  author={Elbaz, Aviv and Marbel, Revital and Berger, Harel and Alt, Florian},
  booktitle={CCNC},
  year={2026}
}
```

## Completeness update (2026-10-15)

All five controls are now complete at n=100. The original gaps: S+C+ cells
truncated at max_tokens=1024 (45/100), placebo paraphrases never generated
for 17 personas, and Claude generator-swap emails blocked by safety
refusals for 25 personas. Fixed with: scripts/regenerate_sc_plus.py,
scripts/complete_placebo.py, scripts/complete_crossgen.py (stimulus
framing + higher token limits + checkpointing).

| File | Description |
|------|-------------|
| `outputs/dissociation_emails_100.csv` | All 100 S+C+ cells regenerated |
| `outputs/n100/pointwise_2x2_extra.csv` | Completed pointwise 2x2 (n=100 per cell) |
| `outputs/n100/placebo_emails.csv` / `placebo_judgments.csv` | Placebo at n=100 (rates 97/67/51/77) |
| `outputs/claude_crossgen_clean.csv` / `claude_crossgen_judgments.csv` | Generator-swap at n=100 (100% surface preference, both judges) |

| `outputs/n100/pointwise_context_judgments.csv` | Pointwise context control (800 judgments; context does not restore pointwise detection) |
| `outputs/n100/pointwise_ablation_judgments.csv` | Pointwise entity ablation (400 judgments; stripped emails flagged more) |
| `scripts/pointwise_controls.py` | Runner for both controls |

## ICC 2027 update (2026-10-10)

Deployed-format pointwise experiment completed to the full 2x2 + a benign control:

| File | Description |
|------|-------------|
| `outputs/n100/pointwise_judgments.csv` | Original pointwise cells (S+C-, S-C+; 800 judgments) |
| `outputs/n100/pointwise_2x2_extra.csv` | Completed cells (S-C-, S+C+; 620 judgments; S+C+ n=55) |
| `outputs/n100/pointwise_benign_judgments.csv` | Benign control verdicts (400 judgments) |
| `outputs/n100/benign_emails.csv` | 100 matched legitimate plain academic emails (GPT-4.1 generated, no call to action) |
| `scripts/pointwise_complete_2x2.py` | Checkpointed/resumable runner for the extra cells + benign control |
| `scripts/judge_pointwise.py` | Original pointwise runner (prompt + parsing) |

Reproduce: `PYTHONUNBUFFERED=1 .venv/bin/python scripts/pointwise_complete_2x2.py --part A|B`.
Headline: ~90% false-negative rate on plain personalized phishing (100% on the
28 explicit-call-to-action personas) vs 0% false-positive rate on matched
benign plain mail; judges do flag plain generic scam templates (25-81%).
