"""Build KGs and profiles for 100 personas from generated specs.

Usage:
  python scripts/build_100_kgs.py --all        # build all KGs + profiles
  python scripts/build_100_kgs.py --batch 0 10  # build batch 0-9
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CACHE_DIR, ANTHROPIC_API_KEY
from agents.llm_utils import llm_json, llm_call

PERSONA_SPEC = Path(__file__).parent.parent / "publish" / "llmnet-2026" / "supplementary" / "persona_specifications_100.json"

KG_SYSTEM = """You are constructing a synthetic academic knowledge graph for a fictional researcher.
Generate realistic academic and social data matching the persona specification.

Academic graph: Person, Paper, Venue, Institution nodes with AFFILIATED_WITH, AUTHORED, PUBLISHED_AT, CO_AUTHOR edges.
Social graph: Person, SocialProfile, LifeEvent, Interest, Location, Education, Teaching, Organization nodes with appropriate edges.

The persona details:
- Name, institution, department, country (from spec)
- Paper count + co-author count (from spec)
- Sub-field for generating plausible paper titles
- Social data presence (from spec): if true, include social media, life events, interests, locations

Generate the complete graph as JSON matching the project's graph schema (graph_node.json, graph_edge.json, social_node.json, social_edge.json).
Paper titles and venues should be realistic for the sub-field. Co-authors should have realistic names for the persona's country.
If social_data is false, generate only academic graph (graph.json).
If social_data is true, generate both academic and social graphs."""


def build_kg_for_persona(persona: dict) -> bool:
    """Build KG (graph.json + social_graph.json) for one persona."""
    tid = persona["target_id"]
    target_dir = CACHE_DIR / tid
    target_dir.mkdir(parents=True, exist_ok=True)

    graph_path = target_dir / "graph.json"
    social_path = target_dir / "social_graph.json"

    if graph_path.exists() and social_path.exists():
        return True  # already built

    user_prompt = f"""Persona to construct:
- target_id: {tid}
- full_name: {persona['full_name']}
- institution: {persona['institution']}
- department: {persona['department']}
- country: {persona['country']}
- papers: {persona['papers']}
- co_authors: {persona['co_authors']}
- sub_field: {persona['sub_field']}
- social_data: {persona['social_data']}

Return JSON with keys: "graph" (academic nodes+edges) and "social_graph" (social nodes+edges, only if social_data=true)."""

    result = llm_json(KG_SYSTEM, user_prompt, model="claude-sonnet-4-6", max_tokens=8192)

    if result is None:
        print(f"  {tid}: LLM FAILED")
        return False

    # Save academic graph
    academic = result.get("graph", result)
    if isinstance(academic, dict):
        academic = [academic]
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(academic, f, indent=2, ensure_ascii=False)

    # Save social graph
    social = result.get("social_graph")
    if social:
        if isinstance(social, dict):
            social = [social]
        with open(social_path, "w", encoding="utf-8") as f:
            json.dump(social, f, indent=2, ensure_ascii=False)
    else:
        # Create empty social graph
        with open(social_path, "w", encoding="utf-8") as f:
            json.dump([], f)

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--batch", type=int, nargs=2, help="Start and end indices")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not PERSONA_SPEC.exists():
        print(f"ERROR: {PERSONA_SPEC} not found. Run generate_100_personas.py first.")
        sys.exit(1)

    personas = json.loads(PERSONA_SPEC.read_text(encoding="utf-8"))

    if args.batch:
        start, end = args.batch
        personas = personas[start:end]

    if args.dry_run:
        print(f"Would build KGs for {len(personas)} personas")
        return

    print(f"Building KGs for {len(personas)} personas...")
    success = 0
    for i, persona in enumerate(personas):
        tid = persona["target_id"]
        print(f"[{i+1}/{len(personas)}] {tid}: {persona['full_name']}...", end=" ", flush=True)
        if build_kg_for_persona(persona):
            print("OK")
            success += 1
        else:
            print("FAILED")
        time.sleep(2)  # rate limit for Claude API

    print(f"\nBuilt {success}/{len(personas)} KGs")


if __name__ == "__main__":
    main()
