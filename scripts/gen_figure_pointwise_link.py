"""Regenerate the pointwise-verdicts figure with the matched-link cells
(user-approved after the link-control experiment, 2026-10-15).

Seven groups x four judges (benign-verdict rate, Wilson CIs), red CTA
overlay on S-C+ (28 personas, 100% benign). Gemini nano-banana
generation + vision verification against the ground truth below.

Usage: .venv/bin/python scripts/gen_figure_pointwise_link.py
Output: outputs/figures_restyle/pointwise_link.png/.pdf then copies to
publish/surf_icc2027/figures/pointwise_verdicts.pdf
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

GROUND_TRUTH = """S+C+: GPT 92, DS 29, CL 37, GE 89
S+C-: GPT 91, DS 12, CL 9, GE 64
S-C+: GPT 91, DS 91, CL 90, GE 91
S-C-: GPT 75, DS 63, CL 66, GE 19
S-C+L: GPT 43, DS 2, CL 0, GE 3
S-C-L: GPT 0, DS 0, CL 0, GE 0
Benign: GPT 100, DS 100, CL 100, GE 100
Ben+L: GPT 7, DS 2, CL 0, GE 13
Outr.: GPT 82, DS 36, CL 38, GE 40
Red outlines ONLY on the S-C+ group (28 explicit-call-to-action personas, 100% benign for every judge)."""

PROMPT = """Style rules: pure white background, flat 2D chart, no shadows/gradients/3D/photo elements/watermark/title/caption. Clean sans-serif black text. Thin black chart frame and axes. Light gray gridlines or none.

Create a grouped bar chart, 3:2 aspect, for an academic security paper.

X AXIS: nine groups in this exact order: S+C+, S+C-, S-C+, S-C-, S-C+L, S-C-L, Benign, Ben+L, Outr. Use exact labels with the minus signs as shown. The group labels sit under the axis.

Y AXIS: "Benign-verdict rate" with tick labels 0, 25, 50, 75, 100.

FOUR JUDGES per group, bars in this exact order, each judge with a distinct hatch pattern on white fill with thin black edges, and a black error-bar (Wilson 95% CI) with small caps:
1. GPT-4.1-mini (hatch: diagonal lines //) - exact bar heights (%): S+C+ 92, S+C- 91, S-C+ 91, S-C- 75, S-C+L 43, S-C-L 0, Benign 100, Ben+L 7
2. DeepSeek-Chat (hatch: back-diagonal \\\\) - S+C+ 29, S+C- 12, S-C+ 91, S-C- 63, S-C+L 2, S-C-L 0, Benign 100, Ben+L 2
3. Claude Sonnet 4.6 (hatch: crosshatch xx) - S+C+ 37, S+C- 9, S-C+ 90, S-C- 66, S-C+L 0, S-C-L 0, Benign 100, Ben+L 0
4. Gemini 2.5 Flash (hatch: dots ..) - S+C+ 89, S+C- 64, S-C+ 91, S-C- 19, S-C+L 3, S-C-L 0, Benign 100, Ben+L 13

RED OUTLINE OVERLAY: thin (hairline) red-outlined bars (same hatches, no fill color) drawn ON TOP of the four S-C+ bars only, at 100% height each. The red outlines represent a SUBSET (28 personas) of the S-C+ group; the S-C+ group's own bars stay at their listed heights. This layering is intentional and correct.

LEGEND (top left, two columns): the four judge names with their hatch samples, plus one line "red outline: 28 explicit-call-to-action personas (100% benign)".

Zero-height bars: draw nothing (no visible mark)."""

VERIFY = f"""You are a hostile reviewer checking a chart against its ground truth.
SEMANTICS NOTE (do not flag this): the red-outlined bars are an OVERLAY representing a SUBSET of the S-C+ group (28 personas with an explicit call to action, 100% benign). They are drawn at 100% height ON TOP of the S-C+ group's own bars, which stay at 90-91%. The layering is intentional: overlay = subset, underlying bar = full group.
1. Transcribe the nine x-axis group labels exactly.
2. Transcribe the legend entries exactly (judge names + the red-outline note).
3. For every NON-overlay bar, report group, judge (by hatch pattern), and height as a percentage read from the y-axis.
4. Confirm the red-outlined bars sit ONLY on the S-C+ group, at 100% height, thinner than the main bars.
5. Report any label typos, overlaps, truncated text, or style violations (shadows/gradients/3D/extra text).

GROUND TRUTH (benign-verdict % for the main bars):
{GROUND_TRUTH}

Answer: list all transcribed values, then per-group MATCH/MISMATCH with deltas, then VERDICT: PASS or FAIL. If FAIL, list every specific fix needed."""


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
        png = OUT / f"pointwise_link_a{attempt}.png"
        png.write_bytes(data)
        verdict = verify(data)
        print(verdict, flush=True)
        if "VERDICT: PASS" in verdict:
            break
        if attempt < 3:
            print("regenerating with fixes...", flush=True)
            global PROMPT
            PROMPT = PROMPT + "\n\nFIX THESE ISSUES FROM THE PREVIOUS ATTEMPT:\n" + verdict[-1500:]
            time.sleep(5)
    else:
        print("FAILED after 3 attempts", flush=True)
        sys.exit(1)

    # trim whitespace and export 300-DPI PDF
    img = Image.open(png).convert("RGB")
    img.save(OUT / "pointwise_link.png")
    pdf = OUT / "pointwise_link.pdf"
    img.save(pdf, "PDF", resolution=300.0)
    subprocess.run(["cp", str(pdf), str(FIGDIR / "pointwise_verdicts.pdf")], check=True)
    print(f"saved {pdf} -> {FIGDIR / 'pointwise_verdicts.pdf'}", flush=True)


if __name__ == "__main__":
    main()
