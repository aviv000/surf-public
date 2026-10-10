"""Strategic research advisor using Opus 4.8. Not a harsh critic — a collaborative
advisor that understands the full data landscape and suggests novel approaches.

Usage:
  python scripts/research_advisor.py --context <situation_file.md>
  python scripts/research_advisor.py --data <phase0_results.json> --design <design.md>
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

ROOT = Path(__file__).parent.parent
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-opus-4-8"

ADVISOR_SYSTEM = """You are a senior research strategist advising a PhD student on getting accepted to LLMNet 2026 (IEEE LCN Special Track on Large Language Models and Networking). You are NOT a harsh reviewer — you are a COLLABORATIVE ADVISOR whose goal is to find a viable, novel contribution given the constraints.

Your job:
    1. Understand the current data landscape, experimental constraints, and timeline.
    2. Identify the STRONGEST viable contribution given what exists.
    3. Suggest creative pivots that the student may not have considered.
    4. Be honest about what WON'T work, but always offer alternatives.
    5. Prioritize contributions that are NOVEL and DEFENSIBLE, even if modest in scope.
    6. Frame suggestions in terms of what a reviewer would find compelling.

Constraints to respect:
    - 6-page IEEE double-column format
    - LLMNet is a special track — welcomes evaluation methodology, benchmarks, bias/ethics
    - Double-blind review
    - Deadline likely tight (days to weeks)
    - Student has existing infrastructure: 100 synthetic personas, KG→email pipeline,
      cross-family judge panel (GPT-4.1-mini, DeepSeek-Chat, Claude Sonnet 4.6),
      2,430 perturbation judgments across 5 experiments
    - API access: OpenAI, Anthropic, DeepSeek, Gemini
    - Key finding so far: All perturbation experiments show ceiling effects.
      Between-condition: 100% TKG wins. Entity-relevance: 95%.
      Profiler ablation: 96-97% across all arms.
      Length perturbation: 68-90% with massive order effects (30-40pt).
      Behavioral ratings: near-chance agreement (19.4%).
    - Phase 0 discovery check found all 3 judges have same top features (word_count, named_entity_count)
      — no anti-correlation → adversarial exploitation premise threatened.

Be creative. Think of angles the student hasn't considered. What's the SHARPEST, cleanest contribution that can be extracted from this data in a tight timeframe?

Output format:
    Assessment of current situation (2-3 sentences)
    Top 3-5 viable contribution angles, ranked by novelty+defensibility
    For each: what's the claim, what evidence exists, what needs generating, acceptance risk (low/med/high)
    Recommended path (pick one, justify)
    Concrete next 3 steps"""


def call_advisor(context: str) -> str:
    """Get strategic advice from Opus 4.8."""
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": MODEL,
        "max_tokens": 4096,
        "system": ADVISOR_SYSTEM,
        "messages": [
            {"role": "user", "content": context},
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
        return "\n".join(b["text"] for b in data["content"] if b["type"] == "text")
    return f"API ERROR {resp.status_code}: {resp.text[:500]}"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=str, help="Path to situation/context file")
    parser.add_argument("--data", type=str, nargs="*", help="Path(s) to data/results files")
    parser.add_argument("--design", type=str, help="Path to experimental design doc")
    parser.add_argument("--question", type=str, help="Specific question for advisor")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not found")
        sys.exit(1)

    # Build context
    parts = []
    if args.context:
        parts.append(Path(args.context).read_text(encoding="utf-8"))
    if args.design:
        parts.append(f"=== EXPERIMENTAL DESIGN ===\n{Path(args.design).read_text(encoding='utf-8')}")
    if args.data:
        for dp in args.data:
            path = Path(dp)
            if path.suffix == ".json":
                data = json.loads(path.read_text())
                # Summarize JSON
                summary = json.dumps(data, indent=2, default=str)
                if len(summary) > 6000:
                    summary = summary[:6000] + "\n... [truncated]"
                parts.append(f"=== DATA: {path.name} ===\n{summary}")
            else:
                text = path.read_text(encoding="utf-8")
                if len(text) > 6000:
                    text = text[:6000] + "\n... [truncated]"
                parts.append(f"=== DATA: {path.name} ===\n{text}")

    if args.question:
        parts.append(f"\n=== SPECIFIC QUESTION ===\n{args.question}")

    context = "\n\n".join(parts)
    print(f"Context: {len(context)} chars")
    print(f"\nConsulting {MODEL}...\n")

    start = datetime.now()
    advice = call_advisor(context)
    elapsed = (datetime.now() - start).total_seconds()
    print(f"Response in {elapsed:.0f}s\n")
    print("=" * 60)
    print(advice)
    print("=" * 60)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.output or str(ROOT / "outputs" / f"research_advice_{timestamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Research Advisor Report\n\n")
        f.write(f"- **Model**: {MODEL}\n")
        f.write(f"- **Date**: {datetime.now().isoformat()}\n\n")
        f.write("---\n\n")
        f.write(advice)
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
