"""CCNC-specific harsh reviewer using Claude Opus 4.8.
For SURF paper review at IEEE Consumer Communications & Networking Conference.

Usage:
  python scripts/harsh_review_ccnc.py --input paper.tex
  python scripts/harsh_review_ccnc.py --input paper.tex --iterations 3
"""

import json, os, sys
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

ROOT = Path(__file__).parent.parent
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-opus-4-8"

CCNC_REVIEWER = """You are a brutally honest senior reviewer for CCNC 2026 (IEEE Consumer Communications & Networking Conference, 6-8 pages). Your job is to find flaws, overclaims, weak novelty, missing controls, ambiguity, and likely reviewer objections. Be harsh but fair. Specific, not vague. Focus on acceptance risk.

Style rules:
    Be direct, skeptical, and sharp.
    Use phrases like "This is weak because..." "A reviewer will immediately ask..." "This claim is overstated..." "This is likely to trigger a reject because..."
    Do not praise the paper unless necessary to contrast with a flaw.
    Do not give generic advice.
    Judge only from the material provided. Do not invent missing experiments.

Output format:
    Big-picture verdict: accept/weak accept/borderline/reject and why.
    Major weaknesses: 5-10 bullets ordered by severity. Each with problem, why reviewer cares, consequence, fix.
    Acceptance risks: Top 3-5 reasons this gets rejected at CCNC.
    Surgical fixes: Fewest edits for biggest improvement under tight 8-page limit.

CCNC FOCUS: Consumer communications and networking. Papers must connect to consumer-facing applications. Pure ML/NLP evaluation without consumer impact will be rejected. Phishing, spam, content moderation, and consumer security are in-scope if the consumer protection angle is clear.

VENUE: CCNC 2026. FORMAT: 6-8 pages, IEEE double-column, double-blind."""

def review_paper(paper_text: str) -> str:
    """Send paper to Opus for harsh CCNC review."""
    system = CCNC_REVIEWER
    user = f"FULL PAPER FOR CCNC 2026 REVIEW:\n\n{paper_text}"

    body = {"model": MODEL, "max_tokens": 4096, "system": system, "messages": [{"role": "user", "content": user}]}
    # Opus 4.8 does not support temperature
    if "opus" not in MODEL:
        body["temperature"] = 0.3
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json=body,
        timeout=120,
    )
    if resp.status_code != 200:
        return f"API ERROR {resp.status_code}: {resp.text[:500]}"
    return resp.json()["content"][0]["text"]

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    paper_path = Path(args.input)
    if not paper_path.exists():
        print(f"ERROR: {paper_path} not found")
        sys.exit(1)

    # Read main file + all \input files
    paper_dir = paper_path.parent
    paper = paper_path.read_text()
    # Manually include known input files
    for fname in ['sec_abstract','sec_intro','sec_related','sec_methodology','sec_results','sec_discussion','sec_conclusion','sec_bibliography']:
        input_file = paper_dir / f'{fname}.tex'
        if input_file.exists():
            paper += f'\n% === {fname} ===\n' + input_file.read_text()
    print(f"Mode: CCNC paper review\nModel: {MODEL}\nInput: {paper_path}\nAssembled {len(paper)} chars from all sections\n")

    for i in range(args.iterations):
        print(f"Iteration {i+1}/{args.iterations}...")
        review = review_paper(paper)
        if review.startswith("API ERROR"):
            print(review)
            break

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_iter{i+1}" if args.iterations > 1 else ""
        out_path = args.output or str(ROOT / "outputs" / f"harsh_review_ccnc_{timestamp}{suffix}.md")
        Path(out_path).write_text(review)
        print(f"Review saved: {out_path}")
        print(review[:500])

if __name__ == "__main__":
    main()
