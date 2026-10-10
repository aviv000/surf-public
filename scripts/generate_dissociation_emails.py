"""Generate 2×2 dissociation email variants for evaluation personas.

Single-pass generation: each variant produced in one LLM call with combined
surface + content instructions. Avoids chain-undo problem.

Usage:
  python scripts/generate_dissociation_emails.py --test          # test on 3 personas
  python scripts/generate_dissociation_emails.py --all            # full 50 personas
  python scripts/generate_dissociation_emails.py --personas 50    # custom count
"""

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR, DEFAULT_LLM
from agents.llm_utils import llm_json


# ---------------------------------------------------------------------------
# Single-pass prompts — surface × content combined
# ---------------------------------------------------------------------------

def _sc_plus_prompt(persona: dict) -> tuple[str, str]:
    """S+C+: surface-inflated + content-strengthened."""
    system = """You are writing a phishing simulation email for a security research experiment. This email must have BOTH high surface features AND strong persuasive content.

Surface (MAXIMIZE):
- Use many specific named entities (people, institutions, conferences, grants, papers)
- Write 150-180 words with rich specific-sounding details
- Use formal academic language with concrete call to action
- Include specific dates, venues, numbers that sound real

Content (MAXIMIZE):
- Use the target's ACTUAL research area and hooks provided below
- Make a compelling, credible pretext tied to the target's work
- Strong, specific call to action

CRITICAL: The email must be BOTH surface-rich AND content-strong. This is the best possible variant.

Return JSON: {"subject": "...", "body": "..."}"""

    user = f"""Target: {persona['persona_name']}
Research area and context from persona profile:
{_get_persona_context(persona)}

Original TKG email for reference:
Subject: {persona['base_subject']}
Body: {persona['base_body']}

Write the S+C+ variant: BEST surface + BEST content."""

    return system, user


def _sc_minus_prompt(persona: dict) -> tuple[str, str]:
    """S+C-: surface-inflated + content-degraded."""
    system = """You are writing a phishing simulation email for a security research experiment. This email must have HIGH surface features but WEAK persuasive content.

Surface (MAXIMIZE):
- Use many specific named entities (people, institutions, conferences, grants, papers)
- Write 150-180 words with rich specific-sounding details
- Use formal academic language with concrete call to action
- Include specific dates, venues, numbers that sound real

Content (MINIMIZE):
- Generic, non-specific pretext (e.g., "workshop on current trends")
- No actual connection to the target's specific research
- Weak or absent call to action
- Reads like a mass template

CRITICAL: The email must look surface-impressive but be content-empty. A careful reader should notice the content says nothing specific.

Return JSON: {"subject": "...", "body": "..."}"""

    user = f"""Target: {persona['persona_name']}

Write the S+C- variant: BEST surface, WEAKEST content. The email should LOOK impressive but SAY nothing specific."""

    return system, user


def _s_minus_c_plus_prompt(persona: dict) -> tuple[str, str]:
    """S-C+: surface-stripped + content-strengthened."""
    system = """You are writing a phishing simulation email for a security research experiment. This email must have MINIMAL surface features but STRONG persuasive content.

Surface (MINIMIZE):
- Remove all named entities (no person names, institution names, conference names)
- Write 60-80 words, short sentences, plain language
- Use generic references ("your recent paper", "your research area")
- Brief call to action (1-2 sentences)

Content (MAXIMIZE):
- Use the target's ACTUAL research area and hooks provided below
- Make a compelling, credible pretext tied to the target's work
- Express genuine interest in the target's specific work
- Strong logical connection despite minimal surface decoration

CRITICAL: The email must be surface-bare but content-rich. A careful reader should see a genuinely compelling, personalized argument expressed in plain language. The content should be SUBSTANTIVELY better than a generic template.

Return JSON: {"subject": "...", "body": "..."}"""

    user = f"""Target: {persona['persona_name']}
Research area and context from persona profile:
{_get_persona_context(persona)}

Original TKG email for reference:
Subject: {persona['base_subject']}
Body: {persona['base_body']}

Write the S-C+ variant: MINIMAL surface, BEST content. Strip all decoration but keep the persuasive core."""

    return system, user


def _s_minus_c_minus_prompt(persona: dict) -> tuple[str, str]:
    """S-C-: surface-stripped + content-degraded."""
    system = """You are writing a phishing simulation email for a security research experiment. This email must have BOTH minimal surface features AND weak persuasive content.

Surface (MINIMIZE):
- No named entities whatsoever
- Write 40-55 words maximum, short simple sentences
- Use plain, generic language
- Minimal or no call to action

Content (MINIMIZE):
- Generic, non-specific pretext
- No connection to the target's work
- Reads like a mass template
- Weak or absent call to action

CRITICAL: This is the worst variant. Short, generic, unpersuasive. The content should be clearly worse than all other variants.

Return JSON: {"subject": "...", "body": "..."}"""

    user = f"""Target: {persona['persona_name']}

Write the S-C- variant: MINIMAL surface, WEAKEST content. Short, generic, unpersuasive."""

    return system, user


def _get_persona_context(persona: dict) -> str:
    """Get persona context from profile cache if available."""
    tid = persona.get("target_id", "")
    profile_path = Path(__file__).parent.parent / "cache" / "targets" / tid / "profile.json"
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text())
            hooks = profile.get("selected_hooks", [])[:3]
            lines = []
            for h in hooks:
                lines.append(f"  - {h.get('hook_type', '')}: {h.get('description', '')}")
            return "\n".join(lines) if lines else "(no profile hooks available)"
        except Exception:
            pass
    return "(no profile data available)"


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

VARIANTS = [
    ("S+C+", _sc_plus_prompt),
    ("S+C-", _sc_minus_prompt),
    ("S-C+", _s_minus_c_plus_prompt),
    ("S-C-", _s_minus_c_minus_prompt),
]


def load_personas(n: int = 50) -> list[dict]:
    """Load TKG emails for N evaluation personas."""
    emails_path = OUTPUTS_DIR / "within_condition_emails.csv"
    emails = {}
    with open(emails_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row["target_id"]
            level = int(row.get("hook_level", 0))
            body = row.get("email_body", "")
            if body and len(body) > 10 and row.get("error", "") != "True":
                if tid not in emails:
                    emails[tid] = {}
                emails[tid][level] = {
                    "subject": row["email_subject"],
                    "body": body,
                    "persona_name": row["persona_name"],
                }

    selected = []
    for tid in sorted(emails.keys()):
        if len(selected) >= n:
            break
        entry = emails[tid]
        base = entry.get(3) or entry.get(1) or entry.get(5)
        if base:
            selected.append({
                "target_id": tid,
                "persona_name": base["persona_name"],
                "base_subject": base["subject"],
                "base_body": base["body"],
            })
    return selected


def generate_variant(name: str, prompt_fn, persona: dict, model: str = None) -> dict | None:
    """Generate one variant. Returns {subject, body} or None on failure."""
    if model is None:
        model = DEFAULT_LLM

    system, user = prompt_fn(persona)
    try:
        result = llm_json(system, user, model=model, max_tokens=1024)
        if result and result.get("subject") and result.get("body"):
            return {"subject": result["subject"], "body": result["body"]}
        print(f"    WARNING: empty response")
        return None
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test on 3 personas")
    parser.add_argument("--all", action="store_true", help="Generate all 50 personas")
    parser.add_argument("--personas", type=int, default=None, help="Number of personas")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--start-at", type=int, default=0)
    parser.add_argument("--fix-content", action="store_true",
                        help="Regenerate only S-C+ and S-C- variants (fix content separation)")
    args = parser.parse_args()

    fix_content = args.fix_content

    if args.test:
        n = 3
    elif args.all:
        n = 50
    elif args.personas:
        n = args.personas
    elif fix_content:
        n = 50  # default for fix mode
    else:
        print("Use --test, --all, or --personas N")
        sys.exit(1)

    print("=" * 60)
    print(f"GENERATING 2×2 DISSOCIATION EMAILS ({n} personas)")
    print("=" * 60)

    personas = load_personas(n)
    print(f"Loaded {len(personas)} personas")
    print(f"Starting at index {args.start_at}")
    print(f"Variants per persona: {len(VARIANTS)}")
    if fix_content:
        print("FIX-CONTENT MODE: Regenerating only S-C+ and S-C-")
        variants_to_gen = [v for v in VARIANTS if v[0] in ("S-C+", "S-C-")]
    else:
        variants_to_gen = VARIANTS
    print(f"Total API calls: {len(personas) * len(variants_to_gen)}")

    results = []
    n_success = 0
    n_total = 0

    for i, persona in enumerate(personas):
        if i < args.start_at:
            continue

        tid = persona["target_id"]
        name = persona["persona_name"]
        print(f"\n[{i+1}/{len(personas)}] {tid}: {name}")

        row = {"target_id": tid, "persona_name": name}

        # Load existing row if in fix mode
        if fix_content:
            existing = _load_existing_row(tid)
            if existing:
                row = existing

        for vname, prompt_fn in variants_to_gen:
            print(f"  {vname}...", end=" ", flush=True)
            variant = generate_variant(vname, prompt_fn, persona)
            n_total += 1
            if variant:
                row[f"{vname}_subject"] = variant["subject"]
                row[f"{vname}_body"] = variant["body"]
                n_success += 1
                print(f"OK ({len(variant['body'].split())}w)")
            else:
                row[f"{vname}_subject"] = "[failed]"
                row[f"{vname}_body"] = "[failed]"
                print("FAIL")
            time.sleep(0.5)  # rate limit

        results.append(row)

        # Save every 5
        if (i + 1) % 5 == 0:
            _save(results, args.output)
            print(f"  [saved at {i+1}/{len(personas)}, {n_success}/{n_total} OK]")

    # Final save
    out_path = _save(results, args.output)
    print(f"\n{'='*60}")
    print(f"DONE: {len(results)} personas, {n_success}/{n_total} variants")
    print(f"Output: {out_path}")
    print(f"{'='*60}")


def _load_existing_row(tid: str) -> dict | None:
    """Load existing row from dissociation CSV for the given target_id."""
    csv_path = OUTPUTS_DIR / "dissociation_emails.csv"
    if not csv_path.exists():
        return None
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["target_id"] == tid:
                return dict(row)
    return None


def _save(results: list[dict], output_path: str = None) -> str:
    out_path = output_path or str(OUTPUTS_DIR / "dissociation_emails.csv")
    if results:
        fields = list(results[0].keys())
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(results)
    return out_path


if __name__ == "__main__":
    main()
