"""Automated harsh reviewer using Anthropic Opus 4.8.
Multi-mode: design review, results review, paper review.
Tracks issues across iterations.

Usage:
  python scripts/harsh_review.py --mode design --input design_doc.md
  python scripts/harsh_review.py --mode results --input results.csv --analysis analysis.md
  python scripts/harsh_review.py --mode paper --input paper.tex
  python scripts/harsh_review.py --mode paper --iterations 3
"""

import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

# Paths
ROOT = Path(__file__).parent.parent
DEFAULT_PAPER = ROOT / "publish" / "llmnet-2026-llm-as-judge" / "paper.tex"
DEFAULT_FIGURE = ROOT / "publish" / "llmnet-2026-llm-as-judge" / "figures" / "blind_comparison.pdf"

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-opus-4-8"

# ============================================================
# SYSTEM PROMPTS BY MODE
# ============================================================

BASE_REVIEWER_IDENTITY = """You are a brutally honest senior reviewer for a top-tier networking/security venue (LLMNet, IEEE LCN 2026 Special Track). Your job is not to be polite, encouraging, or generative; your job is to find flaws, overclaims, weak novelty, missing controls, ambiguity, and likely reviewer objections. Assume the paper is trying to survive a hostile program committee. Your critique must be:

    Harsh but fair.
    Specific, not vague.
    Focused on acceptance risk.
    Written like a reviewer who is looking for reasons to reject, but still grounded in the text.
    Sensitive to page limits, double-blind constraints, and venue fit.

Style rules:
    Be direct, skeptical, and sharp.
    Use phrases like:
        "This is weak because..."
        "A reviewer will immediately ask..."
        "This claim is overstated..."
        "This does not establish..."
        "This is likely to trigger a reject because..."
    Do not praise the paper unless it is necessary to contrast with a flaw.
    Do not give generic advice.
    Do not say "overall it is good" unless you immediately qualify it with major risks.
    Do not be verbose for its own sake: cut to the point.

Output format:
    Big-picture verdict: One paragraph on whether the work currently looks like an accept, weak accept, borderline, or reject, and why.
    Major weaknesses: 5-10 bullet points ordered by severity. Each with problem, why reviewer cares, likely consequence, concrete fix.
    Acceptance risks: Top 3-5 reasons this gets rejected.
    Surgical fixes: Fewest edits that produce the biggest improvement under tight page limit.

Important constraints:
    Judge only from the material provided.
    Do not invent missing experiments.
    Do not assume unseen appendices save weak claims.
    If the evidence is limited, say so plainly.
    If a claim is untestable or only exploratory, say that the work must stop presenting it as stronger than it is.

VENUE: LLMNet 2026 — IEEE LCN Special Track on Large Language Models and Networking.
This is a SPECIAL TRACK, not the main conference. The bar is competitive but the track explicitly welcomes evaluation methodology, benchmarks, datasets, human-in-the-loop frameworks, and ethical/bias considerations.
PAPER FORMAT: 6 pages excluding references, IEEE double-column, double-blind."""

DESIGN_SYSTEM = f"""{BASE_REVIEWER_IDENTITY}

MODE: EXPERIMENTAL DESIGN REVIEW. You are reviewing an experimental PLAN, not completed results. Your job: find design flaws BEFORE the authors spend money and time running experiments.

What to scrutinize:
    Statistical power — can the design actually answer the question?
    Confounds — what uncontrolled variables will pollute the results?
    Missing controls — what baseline/control condition is absent?
    Measurement validity — does the instrument measure what it claims to?
    Generalizability — what limits the scope of the conclusions?
    Internal consistency — do any design elements contradict each other?
    Resource feasibility — is the design scoped to what's achievable?

Output format (same as base: verdict, weaknesses, risks, fixes).
Focus on: what would make a reviewer reject this design if it were a pre-registration."""

RESULTS_SYSTEM = f"""{BASE_REVIEWER_IDENTITY}

MODE: RESULTS REVIEW. You are reviewing experimental RESULTS and their interpretation. The experiments are already run; you're judging whether the conclusions are supported.

What to scrutinize:
    Overclaimed conclusions — does the evidence support the strength of the claim?
    Statistical validity — are the right tests used? Are p-values/CIs interpreted correctly?
    Alternative explanations — what could explain these results other than the authors' interpretation?
    Missing analyses — what analysis should have been done but wasn't?
    Negative/null results handling — are null results properly distinguished from underpowered tests?
    Internal inconsistency — do any results contradict each other or the authors' claims?

Output format (same as base: verdict, weaknesses, risks, fixes).
Focus on: what interpretations are unsupported, what analyses are missing, what alternative explanations are unaddressed."""

PAPER_SYSTEM = f"""{BASE_REVIEWER_IDENTITY}

MODE: FULL PAPER REVIEW. You are reviewing a complete paper submission.

What to do:
    Read the paper as if you are a skeptical expert reviewer.
    Identify:
        weak novelty,
        overclaimed results,
        missing controls or baselines,
        circular evaluation,
        statistical weakness,
        unclear threat model,
        weak networking relevance,
        ethical/dual-use concerns,
        writing and organization problems,
        any internal inconsistency,
        any figure/table/layout issue that would annoy reviewers,
        any claim that is too strong for the evidence.
    Prioritize issues that are most likely to hurt acceptance.
    When possible, give concrete fixes, but do not soften your tone.

Output format (same as base: verdict, weaknesses, risks, fixes).

When scoring, calibrate to a SPECIAL TRACK standard, not a main-conference standard. A borderline paper that makes a genuine methodological contribution to how LLM evaluation should be done in security contexts should be accepted for a track that explicitly invites evaluation frameworks. Reject only if the contribution is clearly insufficient even for a special track."""


def encode_pdf_base64(path):
    """Read PDF and encode as base64 for Anthropic API."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def build_user_message(mode, input_text, extra_text=None):
    """Build user message based on mode."""
    if mode == "design":
        msg = f"""I am planning an experiment for submission to LLMNet 2026 at IEEE LCN. Please review the experimental DESIGN critically BEFORE I run it.

=== EXPERIMENTAL DESIGN ===

{input_text}"""
        if extra_text:
            msg += f"\n\n=== ADDITIONAL CONTEXT ===\n\n{extra_text}"
        msg += "\n\n=== END OF DESIGN ===\n\nReview this experimental design. Be harsh. Focus on flaws that would cause rejection. Tell me what to fix BEFORE I run the experiment."

    elif mode == "results":
        msg = f"""I have experimental results for a paper submission to LLMNet 2026. Please review the RESULTS and their interpretation critically.

=== RESULTS ===

{input_text}"""
        if extra_text:
            msg += f"\n\n=== ANALYSIS / INTERPRETATION ===\n\n{extra_text}"
        msg += "\n\n=== END OF RESULTS ===\n\nReview these results. Be harsh. Focus on unsupported conclusions, missing analyses, and alternative explanations."

    elif mode == "paper":
        figure_b64 = None
        fig_path = DEFAULT_FIGURE
        if fig_path.exists():
            figure_b64 = encode_pdf_base64(fig_path)
            fig_note = "\n\n=== FIGURE: blind_comparison.pdf ===\n[Figure included as base64-encoded PDF]\n"
        else:
            fig_note = ""

        msg = f"""I am submitting a paper to LLMNet 2026 at IEEE LCN. Please review it critically.

=== PAPER (LaTeX source) ===

{input_text}{fig_note}

=== END OF SUBMISSION ===

Review this paper. Be harsh. Focus on what would cause rejection."""

    return msg


def call_anthropic(system_prompt, user_message):
    """Call Anthropic API with content."""
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": MODEL,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                ],
            }
        ],
    }

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=body,
        timeout=180,
    )

    if resp.status_code == 200:
        data = resp.json()
        texts = [b["text"] for b in data["content"] if b["type"] == "text"]
        return "\n".join(texts)
    else:
        return f"API ERROR {resp.status_code}: {resp.text[:500]}"


def read_input(mode, input_path):
    """Read input file(s) based on mode."""
    path = Path(input_path)
    if not path.exists():
        print(f"ERROR: {path} not found")
        sys.exit(1)

    if path.suffix == ".csv":
        # For CSV, read as text with row count header
        with open(path) as f:
            lines = f.readlines()
        header = lines[0] if lines else ""
        n_rows = len(lines) - 1
        return f"[CSV: {path.name}, {n_rows} rows]\nHeader: {header}\nFirst 5 rows:\n" + "".join(lines[1:6]) + f"\n... ({n_rows - 5} more rows)"

    elif path.suffix in (".json",):
        import json as j
        with open(path) as f:
            data = j.load(f)
        text = j.dumps(data, indent=2)
        if len(text) > 8000:
            text = text[:8000] + "\n... [truncated]"
        return text

    else:
        return path.read_text(encoding="utf-8")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Multi-mode harsh reviewer (Opus 4.8)")
    parser.add_argument("--mode", type=str, required=True,
                        choices=["design", "results", "paper"],
                        help="Review mode")
    parser.add_argument("--input", type=str, default=None,
                        help="Primary input file")
    parser.add_argument("--analysis", type=str, default=None,
                        help="Secondary input (analysis/interpretation for results mode)")
    parser.add_argument("--extra", type=str, default=None,
                        help="Additional context file (design mode)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file for review")
    parser.add_argument("--iterations", type=int, default=1,
                        help="Number of review iterations (paper mode)")
    parser.add_argument("--continue-from", type=str, default=None,
                        help="Path to previous review to continue from")
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not found")
        sys.exit(1)

    # Resolve input path
    if args.input:
        input_path = args.input
    elif args.mode == "paper":
        input_path = str(DEFAULT_PAPER)
    else:
        print("ERROR: --input required for design/results mode")
        sys.exit(1)

    print(f"Mode: {args.mode}")
    print(f"Model: {MODEL}")
    print(f"Input: {input_path}")

    # Read primary input
    input_text = read_input(args.mode, input_path)
    print(f"Primary input: {len(input_text)} chars")

    # Read secondary input
    extra_text = None
    if args.analysis:
        extra_text = read_input(args.mode, args.analysis)
        print(f"Analysis: {len(extra_text)} chars")
    elif args.extra:
        extra_text = read_input(args.mode, args.extra)
        print(f"Extra: {len(extra_text)} chars")

    # Read previous review for continuation
    prev_review = None
    if args.continue_from:
        prev_path = Path(args.continue_from)
        if prev_path.exists():
            prev_review = prev_path.read_text(encoding="utf-8")
            print(f"Previous review: {len(prev_review)} chars")

    # Select system prompt
    system_prompts = {
        "design": DESIGN_SYSTEM,
        "results": RESULTS_SYSTEM,
        "paper": PAPER_SYSTEM,
    }
    system = system_prompts[args.mode]

    # Build user message
    user_msg = build_user_message(args.mode, input_text, extra_text)

    for iteration in range(args.iterations):
        if args.iterations > 1:
            print(f"\n{'='*60}")
            print(f"ITERATION {iteration+1}/{args.iterations}")
            print(f"{'='*60}")

        # Include previous review context
        if prev_review and iteration == 0:
            user_msg += f"\n\n=== PREVIOUS REVIEW (Address these issues) ===\n\n{prev_review}\n\n=== END PREVIOUS REVIEW ===\n\nThe authors have addressed some issues. Re-review. Note resolved vs remaining issues. Be equally harsh."

        print(f"\nCalling Anthropic API ({MODEL})...")
        start = datetime.now()
        review = call_anthropic(system, user_msg)
        elapsed = (datetime.now() - start).total_seconds()
        print(f"Response in {elapsed:.0f}s")

        # Save review
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode_prefix = args.mode
        out_path = args.output or str(ROOT / "outputs" / f"harsh_review_{mode_prefix}_{timestamp}.md")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"# Harsh Reviewer Report\n\n")
            f.write(f"- **Mode**: {args.mode}\n")
            f.write(f"- **Model**: {MODEL}\n")
            f.write(f"- **Date**: {datetime.now().isoformat()}\n")
            f.write(f"- **Input**: {input_path}\n")
            f.write(f"- **Iteration**: {iteration+1}/{args.iterations}\n\n")
            f.write("---\n\n")
            f.write(review)

        print(f"Review saved to: {out_path}")

        # Print summary
        print(f"\n{'='*60}")
        print("REVIEW (first 500 chars):")
        print(f"{'='*60}")
        print(review[:500])
        print("...")
        print(f"\nFull review: {out_path}")

        # For multi-iteration, feed previous review into next
        if args.iterations > 1 and iteration < args.iterations - 1:
            prev_review = review
            user_msg = build_user_message(args.mode, input_text, extra_text)
            user_msg += f"\n\n=== PREVIOUS REVIEW (Iteration {iteration+1}) ===\n\n{review}\n\n=== END PREVIOUS REVIEW ===\n\nThe authors have addressed some of the issues above. Please re-review the paper. Note which issues were resolved and which remain. Be equally harsh."


if __name__ == "__main__":
    main()
