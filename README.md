# All Signal, No Meaning: The SURF Audit of LLM Phishing-Triage Panels

Code and data for the IEEE ICC 2027 (CISS symposium) paper. SURF is a
controlled audit protocol for the LLM judges inside email-security
pipelines: pointwise risk verdicts, pairwise comparisons with placebo
calibration, feature-isolation controls, held-out reproduction, an
intent-rubric probe, and external-dataset robustness checks. Headline:
in the tested threat scenarios, four cross-family judges label
link-free personalized first-contact pretexts benign in 90-91% of
cases; appending one link flips three of four judges to near-total
flagging, also raising false positives on legitimate email.

## Data

All CSVs use N=100 per judge unless noted. External evaluation subsets
(DIDECO, SpaPhish, CLAIR) are derived from the cited public datasets.

| File | Description |
|------|-------------|
| `outputs/n100/merged_dissociation.csv` | 2x2 dissociation judgments, both orders per cell (2,300 rows incl. the Gemini order-arm refill) |
| `outputs/dissociation_emails_100.csv` | Generated stimuli (4 variants x 100 personas) |
| `outputs/n100/pointwise_judgments.csv` | Pointwise cells S+C-/S-C+ (800 judgments) |
| `outputs/n100/pointwise_2x2_extra.csv` | Completed pointwise cells S-C-/S+C+ |
| `outputs/n100/pointwise_benign_judgments.csv` / `benign_emails.csv` | Benign control (400 judgments; matched ask-free announcements) |
| `outputs/n100/link_control_*.csv` | Matched-link controls: one appended fictional-domain link (S-C+L, S-C-L) |
| `outputs/n100/benign_link_*.csv` | Benign-link control (the same link on benign mail) |
| `outputs/n100/context_judgments.csv` | Pairwise context control (recipient profile in the prompt) |
| `outputs/n100/pointwise_context_judgments.csv` | Pointwise context control (context does not restore pointwise detection) |
| `outputs/n100/pointwise_ablation_judgments.csv` | Pointwise entity ablation (stripped emails flagged more) |
| `outputs/n100/entity_ablation_judgments.csv` | Pairwise entity ablation (100/100 preference, all judges) |
| `outputs/n100/semantic_check.csv` | Semantic manipulation check (non-panel scorer ratings) |
| `outputs/n100/placebo_para_sims.csv` | Placebo-paraphrase embedding similarities (0.993 mean) |
| `outputs/n100/rubric_probe_emails.csv` / `rubric_probe_judgments.csv` | Intent-rubric probe (P0 vs P1, held-out + swapped-generator + outreach negatives) |
| `outputs/n100/heldout_emails.csv` / `heldout_judgments.csv` | Held-out reproduction (30 new personas, frozen prompts) |
| `outputs/n100/incontext_link_*.csv` | In-context link control (the flip is not an append artifact) |
| `outputs/n100/dideco_unified.csv` | DIDECO external slice (197 LLM-generated spear-phish, human intent labels) |
| `outputs/n100/spaphish_unified.csv` / `spaphish_legit_unified.csv` | SpaPhish external slices (26 link-free phishing; 100 link-free legitimate) |
| `outputs/n100/clair_fraud_unified.csv` / `clair_ham_unified.csv` | CLAIR external slices (100 link-free 419 fraud; 100 link-free ham) |
| `outputs/n100/external_dataset_judgments.csv` | All external-slice judgments (DIDECO, SpaPhish, CLAIR) |
| `outputs/n100/repeat_unified.csv` / `repeat_judgments.csv` | Repeat run of the four headline cells (1,400 judgments; test-retest agreement) |
| `outputs/n100/placebo_emails.csv` / `placebo_judgments.csv` | Placebo pair at n=100 |
| `outputs/claude_crossgen_*.csv` | Generator-swap control (Claude-generated stimuli) |
| `outputs/surf_icc_new_analyses.json` | Analysis outputs incl. order effects |
| `outputs/paper_audit_report.txt` | The audit report: every paper number regenerated from these CSVs |

## Analysis

```bash
pip install numpy scipy pandas statsmodels scikit-learn
python scripts/paper_audit.py
```

This is the reproducibility entry point: it regenerates every number
in the paper from the raw CSVs above (162/162 checks in the submitted
version, verified against this exact file set). Figure ground truth
can be re-verified with `scripts/verify_data_figures.py` (Gemini
vision transcription).

Requires Python 3.10+, numpy, scipy, pandas, statsmodels,
scikit-learn, and `config.py` at the repository root (output paths).

## Completeness (2026-10-27, submission build)

- All five core controls complete at n=100 (S+C+ regenerated, placebo
  completed, context stats corrected, ablation verified,
  generator-swap completed).
- Link controls: matched appended-link, benign-link, in-context link,
  and URL-appearance conditions (E1-E2).
- Rubric probe: pre-registered intent-aware policy (P0 vs P1) with
  held-out, swapped-generator, and outreach negatives.
- External robustness: DIDECO, SpaPhish, and CLAIR subsets judged with
  the frozen pointwise prompt; link-free filters described in the
  paper (Table IV) and enforced in `scripts/external_datasets.py`.
- Repeat run: four headline cells re-judged (test-retest agreement
  64-100%, pooled 93%).
- Gemini order-arm refill: the 75/25 collection imbalance closed
  (`scripts/gemini_order_refill.py`); both presentation orders now
  collected for every cell.

External datasets are cited in the paper and available from their
original sources: DIDECO (LREC 2026), SpaPhish (Mendeley Data,
DOI 10.17632/hz2d6gz7pc.5), CLAIR (ACL Data and Code Repository,
ADCR2008T001). The subset CSVs here are the evaluation subsets used
in the paper.

## Citation

```bibtex
@inproceedings{elbaz2026surf,
  title={All Signal, No Meaning: The SURF Audit of LLM Phishing-Triage Panels},
  author={Elbaz, Aviv and Marbel, Revital and Berger, Harel and Alt, Florian},
  booktitle={Proc. IEEE International Conference on Communications (ICC), CISS Symposium},
  year={2026}
}
```
