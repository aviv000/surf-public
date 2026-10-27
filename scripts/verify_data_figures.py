"""Vision verification of the two data figures (pointwise verdicts, forest
plot) against ground truth recomputed from the judgment CSVs.

The figures are Gemini-generated rasters, so their plotted values must be
re-verified against the data whenever the underlying CSVs change. This
script (a) recomputes the ground truth from the data and (b) sends the
figure to Gemini vision (gemini-2.5-pro) for value transcription, then
diffs the two.

Usage: .venv/bin/python scripts/verify_data_figures.py
Run from the repo root. Requires GEMINI_API_KEY in .env.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=True)  # stale shell keys burned us before

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402
from config import OUTPUTS_DIR  # noqa: E402

FIGDIR = ROOT / "publish" / "surf_icc2027" / "figures"
MODELS = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6", "gemini-2.5-flash"]
SHORT = {"gpt-4.1-mini": "GPT", "deepseek-chat": "DS",
         "claude-sonnet-4-6": "CL", "gemini-2.5-flash": "GE"}

CTA_RE = re.compile(r"(would you be interested|let me know if|I would like to|"
                    r"could we|are you available|would love to|I am writing to)", re.I)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return np.clip(c - m, 0, 1), np.clip(c + m, 0, 1)


def pointwise_ground_truth():
    """Benign-verdict rate (%) per judge x cell for the 7-group figure
    (includes the matched-link control cells from 2026-10-15)."""
    pt = pd.read_csv(OUTPUTS_DIR / "n100" / "pointwise_judgments.csv")
    extra = pd.read_csv(OUTPUTS_DIR / "n100" / "pointwise_2x2_extra.csv")
    ben = pd.read_csv(OUTPUTS_DIR / "n100" / "pointwise_benign_judgments.csv")
    link = pd.read_csv(OUTPUTS_DIR / "n100" / "link_control_judgments.csv")
    benlink = pd.read_csv(OUTPUTS_DIR / "n100" / "benign_link_judgments.csv")
    allpt = pd.concat([pt, extra], ignore_index=True)
    emails = pd.read_csv(OUTPUTS_DIR / "dissociation_emails_100.csv")
    cta_tids = set(emails[emails["S-C+_body"].astype(str)
                          .apply(lambda b: bool(CTA_RE.search(b)))]["target_id"])

    gt = {}
    for v in ["S+C+", "S+C-", "S-C+", "S-C-"]:
        for m in MODELS:
            sub = allpt[(allpt.model == m) & (allpt.variant == v)]
            k = int((sub.verdict == "benign").sum())
            gt[(v, SHORT[m])] = round(100 * k / len(sub))
    for v in ["S-C+link", "S-C-link"]:
        for m in MODELS:
            sub = link[(link.model == m) & (link.variant == v)]
            k = int((sub.verdict == "benign").sum())
            key = "S-C+L" if v == "S-C+link" else "S-C-L"
            gt[(key, SHORT[m])] = round(100 * k / len(sub))
    for m in MODELS:
        sub = ben[ben.model == m]
        k = int((sub.verdict == "benign").sum())
        gt[("Benign", SHORT[m])] = round(100 * k / len(sub))
    for m in MODELS:
        sub = benlink[benlink.model == m]
        k = int((sub.verdict == "benign").sum())
        gt[("Ben+L", SHORT[m])] = round(100 * k / len(sub))
    rb = pd.read_csv(OUTPUTS_DIR / "n100" / "rubric_probe_judgments.csv")
    for m in MODELS:
        sub = rb[(rb.model == m) & (rb.prompt == "P0") & (rb.cell == "H3") & (rb.variant == "none")]
        gt[("Outr.", SHORT[m])] = round(100 * int((sub.verdict == "benign").sum()) / len(sub))
    gt["cta"] = {"n": len(cta_tids), "benign_pct": {}}
    for m in MODELS:
        sub = allpt[(allpt.model == m) & (allpt.variant == "S-C+")
                    & (allpt.target_id.isin(cta_tids))]
        gt["cta"]["benign_pct"][SHORT[m]] = round(
            100 * int((sub.verdict == "benign").sum()) / len(sub))
    return gt


def vision_check(name, prompt):
    """Render the figure PDF and send it to Gemini vision for transcription."""
    png = f"/tmp/vf_{name}-1.png"
    subprocess.run(["pdftoppm", "-png", "-r", "200",
                    str(FIGDIR / f"{name}.pdf"), f"/tmp/vf_{name}"], check=True)
    with open(png, "rb") as f:
        img = f.read()
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[prompt, types.Part.from_bytes(data=img, mime_type="image/png")],
    )
    return resp.text


def rubric_ground_truth():
    """Rubric-probe figure (replaced the forest, 2026-10-23): TPR on
    link-free pretexts and FPR on legitimate outreach, P0 vs P1."""
    rb = pd.read_csv(OUTPUTS_DIR / "n100" / "rubric_probe_judgments.csv")
    held = pd.read_csv(OUTPUTS_DIR / "n100" / "heldout_judgments.csv")
    gt = {"tpr": {}, "fpr": {}}
    for m in MODELS:
        s = SHORT[m]
        sub = rb[rb.model == m]
        p1h = sub[(sub.prompt == "P1") & (sub.cell.isin(["H1", "H2"])) & (sub.variant == "none")]
        p0h1 = held[(held.model == m) & (held.variant == "S-C+")]
        p0h2 = sub[(sub.prompt == "P0") & (sub.cell == "H2") & (sub.variant == "none")]
        both_p0 = pd.concat([p0h1[["target_id", "verdict"]], p0h2[["target_id", "verdict"]]])
        gt["tpr"][(s, "P0")] = round(100 * int((both_p0.verdict != "benign").sum()) / len(both_p0))
        gt["tpr"][(s, "P1")] = round(100 * int((p1h.verdict != "benign").sum()) / len(p1h))
        h0 = sub[(sub.prompt == "P0") & (sub.cell == "H3") & (sub.variant == "none")]
        h1 = sub[(sub.prompt == "P1") & (sub.cell == "H3") & (sub.variant == "none")]
        gt["fpr"][(s, "P0")] = round(100 * int((h0.verdict != "benign").sum()) / len(h0))
        gt["fpr"][(s, "P1")] = round(100 * int((h1.verdict != "benign").sum()) / len(h1))
    return gt


PROMPT_POINTWISE = """You are checking a bar chart against its ground truth. The chart shows "benign-verdict rate" (y-axis 0 to ~108) per LLM judge across 9 x-axis groups: S+C+, S+C-, S-C+, S-C-, S-C+L, S-C-L, Benign, Ben+L, Outr. Four judges are distinguished by different hatch/fill patterns with a legend. Red-outlined OVERLAY bars on the S-C+ group represent a 28-persona SUBSET (100% benign) layered on top of the group's own bars - this layering is intentional, do not flag it.

TASKS:
1. Transcribe the legend entries exactly.
2. Transcribe the x-axis group labels exactly.
3. For EVERY bar, estimate its height as a percentage (read against the y-axis gridlines). List them as: group, judge, height%.
4. Note any red-outlined overlay bars on the S-C+ group, and their heights.
5. Note any text annotations at the bottom of the figure.

EXPECTED GROUND TRUTH (benign rates %):
{gt}
Red outlines only on S-C+ (28 CTA personas), 100% benign for every judge.
Answer format: list every transcribed value, then a per-group MATCH/MISMATCH verdict with any numeric deltas, then VERDICT: PASS or FAIL."""

PROMPT_FOREST = """You are checking a TWO-PANEL dot chart against its ground truth. Left panel = TPR on link-free pretexts (circles), right panel = FPR on legitimate outreach (squares); open markers = P0 (frozen prompt), solid = P1 (intent rubric); numeric labels above markers. Per-judge rows (4 judges) with 3 markers each: primary (dark), placebo (mid-gray), context (light) at different x positions = rates (%), x-axis 0-100%, with error bars (95% CIs), a dashed 50% reference line, and some markers carrying an asterisk. The three series use different shapes (circle/square/triangle) and there are numeric value labels above the markers.

TASKS:
1. Transcribe the judge row labels (left side) exactly.
2. Transcribe the legend entries exactly.
3. For EVERY marker: judge, series (primary/placebo/context), value label number, shape, and whether it has an asterisk.

EXPECTED GROUND TRUTH (rates %):
{gt}
Expected: TPR panel open 0/7/7/13, solid 2/93/98/68 (GPT/DS/CL/GE);
FPR panel open 18/64/62/60, solid 74/100/98/96.
Answer format: list every transcribed marker, then per-series MATCH/MISMATCH verdict with any numeric deltas, then VERDICT: PASS or FAIL."""


def main():
    gt2 = pointwise_ground_truth()
    gt3 = rubric_ground_truth()
    print("Ground truth (Fig 2, pointwise verdicts):")
    for v in ["S+C+", "S+C-", "S-C+", "S-C-", "S-C+L", "S-C-L", "Benign", "Ben+L", "Outr."]:
        print(f"  {v}: " + " ".join(f"{m}={gt2[(v, m)]}" for m in ["GPT", "DS", "CL", "GE"]))
    print(f"  CTA overlay: n={gt2['cta']['n']} "
          f"{gt2['cta']['benign_pct']}")
    print("Ground truth (rubric figure):")
    for s in ["tpr", "fpr"]:
        for p in ["P0", "P1"]:
            print(f"  {s} {p}: " + " ".join(f"{m}={gt3[s][(m, p)]}" for m in ["GPT", "DS", "CL", "GE"]))

    print("\n===== pointwise_verdicts (Gemini vision) =====")
    print(vision_check("pointwise_verdicts", PROMPT_POINTWISE.format(gt=gt2)))
    print("\n===== rubric_probe (Gemini vision) =====")
    print(vision_check("rubric_probe", PROMPT_FOREST.format(gt=gt3)))


if __name__ == "__main__":
    main()
