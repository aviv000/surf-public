"""Generate blind email pairs with proper controls.
Fixes:
- Impersonal control: generic-but-relevant academic invitation, NOT self-promotional spam
- No label leakage in email bodies
- Length-matched by design
"""
import csv, json, random, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR, CACHE_DIR
from agents.llm_utils import llm_json

random.seed(42)

# Proper impersonal control: generic academic invitation, relevant to the target's field
# NOT self-promotional ("ALL about YOU"), NOT irrelevant
IMPERSONAL_TEMPLATES = [
    "We invite submissions to a workshop on {field}. The event will feature keynote speakers, panel discussions, and networking opportunities for researchers in the field.",
    "A special issue on advances in {field} is accepting submissions. We welcome original research, surveys, and position papers.",
    "The program committee for the upcoming {field} conference seeks reviewers. If interested, please indicate your availability.",
    "A new research collaboration network in {field} is forming. Members share preprints, discuss ideas, and coordinate grant proposals.",
    "A doctoral consortium in {field} is seeking mentors. Senior researchers are invited to provide feedback on student work.",
]

def generate_impersonal_email(field, target_words):
    """Generate a proper impersonal email: generic but field-relevant."""
    template = random.choice(IMPERSONAL_TEMPLATES).format(field=field)
    # Expand to target word count using LLM
    result = llm_json(
        "Generate a polite, professional academic email. It should be generic (no personalization to any specific recipient). Return JSON: {\"subject\": \"...\", \"body\": \"...\"}",
        f"Write a {target_words}-word academic email with this content: {template}\n\nMake it sound like a real academic cold email. Do NOT mention any specific person, paper, or institution.",
        model="gpt-4.1-mini", max_tokens=1024,
    )
    if result and "body" in result:
        return result
    # Fallback
    return {"subject": f"Invitation: {field} opportunity", "body": template}


def generate_tkg_email(persona, hooks, target_words=None):
    """Generate a personalized TKG email with given hooks."""
    hooks_text = "\n".join(f"  - {h['hook_text']}" for h in hooks)
    result = llm_json(
        "Generate a polite, professional academic cold email. Use the personalization hooks provided to make it feel targeted. Return JSON: {\"subject\": \"...\", \"body\": \"...\"}",
        f"Target: {persona['full_name']}, {persona['institution']}, {persona['sub_field']}\nHooks:\n{hooks_text}\n\nGenerate a professional academic email. Do NOT mention that you are using hooks or personalization. Write naturally.",
        model="gpt-4.1-mini", max_tokens=1024,
    )
    if result and "body" in result:
        return result
    return None


def length_match(body_a, body_b):
    """Truncate both to min length."""
    words_a = body_a.split()
    words_b = body_b.split()
    t = min(len(words_a), len(words_b))
    return " ".join(words_a[:t]), " ".join(words_b[:t])


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--hookcat", action="store_true", help="Hook-category perturbation")
    parser.add_argument("--profiler", action="store_true", help="Profiler ablation")
    parser.add_argument("--entity", action="store_true", help="Entity-relevance perturbation")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if not (args.hookcat or args.profiler or args.entity or args.all):
        print("Specify --hookcat, --profiler, --entity, or --all")
        return

    with open("publish/llmnet-2026/supplementary/persona_specifications_100.json") as f:
        personas = {p["target_id"]: p for p in json.load(f)}

    TEMPORAL = {"recent_paper", "recent_coauthor", "recent_venue", "public_appearance", "affiliation_change"}
    STATIC = {"teaching", "funding", "career_history", "education", "geographic", "personal_interest", "social_identity", "organization"}

    all_pairs = []

    if args.hookcat or args.all:
        print("=== Hook-category pairs ===")
        for i in range(1, 31):
            tid = f"per-{i:03d}"
            pp = CACHE_DIR / tid / "profile.json"
            if not pp.exists(): continue
            with open(pp) as f: profile = json.load(f)
            temporal = [h for h in profile["top_hooks"] if h.get("hook_type") in TEMPORAL][:3]
            static = [h for h in profile["top_hooks"] if h.get("hook_type") in STATIC][:3]
            if len(temporal) < 2 or len(static) < 2: continue
            persona = personas[tid]

            for cat, hooks in [("temporal", temporal), ("static", static)]:
                tkg = generate_tkg_email(persona, hooks)
                if not tkg: continue
                imp = generate_impersonal_email(persona["sub_field"], len(tkg["body"].split()))
                if not imp: continue
                body_a, body_b = length_match(tkg["body"], imp["body"])
                tkg["body"] = body_a
                imp["body"] = body_b
                all_pairs.append((
                    {"email_subject": tkg["subject"], "email_body": tkg["body"]},
                    {"email_subject": imp["subject"], "email_body": imp["body"]},
                    {"experiment": "hookcat", "tid": tid, "condition": cat, "tkg_len": len(tkg["body"].split()), "imp_len": len(imp["body"].split())},
                ))
                print(f"  {tid} {cat}: TKG={len(tkg['body'].split())}w, IMP={len(imp['body'].split())}w")

    if args.profiler or args.all:
        print("\n=== Profiler ablation pairs ===")
        for i in range(1, 31):
            tid = f"per-{i:03d}"
            pp = CACHE_DIR / tid / "profile.json"
            if not pp.exists(): continue
            with open(pp) as f: profile = json.load(f)
            all_hooks = profile["top_hooks"][:5]
            if len(all_hooks) < 5: continue
            top3 = all_hooks[:3]
            shuffled = list(all_hooks); random.shuffle(shuffled); rand3 = shuffled[:3]
            bottom3 = all_hooks[-3:]
            persona = personas[tid]

            for cond, hooks in [("top", top3), ("random", rand3), ("bottom", bottom3)]:
                tkg = generate_tkg_email(persona, hooks)
                if not tkg: continue
                imp = generate_impersonal_email(persona["sub_field"], len(tkg["body"].split()))
                if not imp: continue
                body_a, body_b = length_match(tkg["body"], imp["body"])
                tkg["body"] = body_a
                imp["body"] = body_b
                all_pairs.append((
                    {"email_subject": tkg["subject"], "email_body": tkg["body"]},
                    {"email_subject": imp["subject"], "email_body": imp["body"]},
                    {"experiment": "profiler", "tid": tid, "condition": cond, "tkg_len": len(tkg["body"].split()), "imp_len": len(imp["body"].split())},
                ))
                print(f"  {tid} {cond}: TKG={len(tkg['body'].split())}w, IMP={len(imp['body'].split())}w")

    if args.entity or args.all:
        print("\n=== Entity-relevance pairs ===")
        for i in range(1, 31):
            tid = f"per-{i:03d}"
            pp = CACHE_DIR / tid / "profile.json"
            if not pp.exists(): continue
            with open(pp) as f: profile = json.load(f)
            hooks = profile["top_hooks"][:3]
            if len(hooks) < 2: continue
            persona = personas[tid]

            tkg = generate_tkg_email(persona, hooks)
            if not tkg: continue
            imp = generate_impersonal_email(persona["sub_field"], len(tkg["body"].split()))
            if not imp: continue
            body_a, body_b = length_match(tkg["body"], imp["body"])
            tkg["body"] = body_a
            imp["body"] = body_b
            all_pairs.append((
                {"email_subject": tkg["subject"], "email_body": tkg["body"]},
                {"email_subject": imp["subject"], "email_body": imp["body"]},
                {"experiment": "entity", "tid": tid, "condition": "personalized", "tkg_len": len(tkg["body"].split()), "imp_len": len(imp["body"].split())},
            ))
            print(f"  {tid}: TKG={len(tkg['body'].split())}w, IMP={len(imp['body'].split())}w")

    # Save pairs
    out_path = OUTPUTS_DIR / "blind_pairs.json"
    # Convert to serializable format
    serializable = []
    for a, b, meta in all_pairs:
        serializable.append({"email_a": a, "email_b": b, "meta": meta})
    with open(out_path, "w") as f:
        json.dump(serializable, f)
    print(f"\nSaved {len(all_pairs)} blind pairs to {out_path}")


if __name__ == "__main__":
    main()
