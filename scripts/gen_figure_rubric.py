"""Generate the rubric-probe figure (rule 21): per-judge TPR on link-free
pretexts and FPR on the two negative classes, under the frozen prompt
(P0, open markers) and the intent-aware rubric (P1, filled markers).
Replaces the forest plot (reviewer round-32 fix 10: Table III carries
the pairwise numbers).

Ground truth (percent, per judge GPT/DS/CL/GE):
  P0 TPR:     0 /  7 /  7 / 13
  P1 TPR:     2 / 93 / 98 / 68
  P0 FPR-hard: 18 / 64 / 62 / 60
  P1 FPR-hard: 74 / 100 / 98 / 96
  P0 FPR-ann:  0 /  0 /  0 /  0
  P1 FPR-ann:  0 /  0 /  0 /  3

Usage: .venv/bin/python scripts/gen_figure_rubric.py
Output: publish/surf_icc2027/figures/rubric_probe.pdf
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env", override=True)

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402
from PIL import Image  # noqa: E402

OUT = REPO / "outputs" / "figures_restyle"
OUT.mkdir(parents=True, exist_ok=True)
FIGDIR = REPO / "publish" / "surf_icc2027" / "figures"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
IMG_MODEL = "models/gemini-nano-banana-2.1"
VISION_MODEL = "models/gemini-2.5-flash"

GROUND_TRUTH = """TPR panel: P0 GPT 0, DS 3, CL 3, GE 13; P1 GPT 2, DS 93, CL 98, GE 68.
FPR-outreach panel: P0 GPT 18, DS 64, CL 62, GE 60; P1 GPT 74, DS 100, CL 98, GE 96."""

PROMPT = """Style: pure white background, flat 2D chart, no shadows/gradients/3D/photo/watermark/title/caption. Clean sans-serif black text. Thin black frame and axes with light gray gridlines. 3:2 aspect, generous spacing.

Create a TWO-PANEL dot chart side by side for an academic security paper. Each panel has its own x-axis with the four judges in this exact order: GPT-4.1-mini, DeepSeek-Chat, Claude Sonnet 4.6, Gemini 2.5 Flash. Each panel has a y-axis "Flag rate (%)" with tick labels 0, 25, 50, 75, 100.

LEFT PANEL (small heading above it: "TPR: link-free pretexts"): CIRCLE markers with thin black outlines. P0 = open/white-filled circle, values GPT 0, DS 3, CL 3, GE 13. P1 = solid black circle, values GPT 2, DS 93, CL 98, GE 68. A thin gray vertical connector line joins each judge's P0 and P1 circles. A numeric value label sits above every marker; when two labels on the same judge would touch (values closer than 8 points), offset one label slightly ABOVE and one slightly BELOW its marker so they never overlap.

RIGHT PANEL (small heading above it: "FPR: legitimate outreach"): SQUARE markers with thin black outlines. P0 = open/white-filled square, values GPT 18, DS 64, CL 62, GE 60. P1 = solid black square, values GPT 74, DS 100, CL 98, GE 96. A thin gray vertical connector line joins each judge's P0 and P1 squares. A numeric value label sits above every marker; when two labels on the same judge would touch (values closer than 8 points), offset one label slightly ABOVE and one slightly BELOW its marker so they never overlap.

LEGEND (top center, one line, definitions only): open marker = frozen prompt (P0), solid marker = intent rubric (P1).

NOTE (one line, directly below the chart): "FPR on ask-free announcements stayed 0-3% for all models under both prompts and is not charted."

Zero-value markers sit exactly on the 0 line and are NOT omitted."""

VERIFY = f"""You are a hostile reviewer checking a chart against its ground truth.
1. Transcribe the four x-axis judge labels exactly.
2. Transcribe the y-axis label and the legend entries exactly.
3. For EVERY marker: judge, panel metric (TPR or FPR-outreach), P0-or-P1 (open vs solid), shape, and its value label number.
4. Confirm the note below the chart states that FPR on ask-free announcements stayed 0-3% and is not charted.
5. Report label typos, overlaps, truncated text, or style violations.

GROUND TRUTH (percent):
{GROUND_TRUTH}

Answer: list every transcribed marker, then per-metric MATCH/MISMATCH with deltas, then VERDICT: PASS or FAIL. If FAIL, list every specific fix needed."""


def generate():
    resp = client.models.generate_content(
        model=IMG_MODEL,
        contents=[PROMPT],
        config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
    )
    for part in resp.candidates[0].content.parts:
        if part.inline_data is not None and getattr(part.inline_data, "mime_type", "").startswith("image"):
            return part.inline_data.data
    raise RuntimeError("no image returned")


def verify(data):
    resp = client.models.generate_content(
        model=VISION_MODEL,
        contents=[VERIFY, types.Part.from_bytes(data=data, mime_type="image/png")],
    )
    return resp.text


def main():
    for attempt in range(1, 4):
        print(f"--- attempt {attempt}", flush=True)
        data = generate()
        png = OUT / f"rubric_probe_a{attempt}.png"
        png.write_bytes(data)
        verdict = verify(data)
        print(verdict, flush=True)
        if "VERDICT: PASS" in verdict:
            break
        if attempt < 3:
            global PROMPT
            PROMPT = PROMPT + "\n\nFIX THESE ISSUES FROM THE PREVIOUS ATTEMPT:\n" + verdict[-1500:]
            time.sleep(5)
    else:
        print("FAILED after 3 attempts", flush=True)
        sys.exit(1)

    img = Image.open(png).convert("RGB")
    pdf = OUT / "rubric_probe.pdf"
    img.save(pdf, "PDF", resolution=300.0)
    subprocess.run(["cp", str(pdf), str(FIGDIR / "rubric_probe.pdf")], check=True)
    print(f"saved {pdf} -> {FIGDIR / 'rubric_probe.pdf'}", flush=True)


if __name__ == "__main__":
    main()
