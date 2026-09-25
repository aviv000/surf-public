"""Blind, counterbalanced, properly-instrumented pairwise judge.
Fixes all bugs identified by 3 independent reviewers:
- No label leakage (just "Email 1" and "Email 2")
- Counterbalanced A/B assignment
- temperature=0.3 (non-zero for real repeats)
- Markdown-stripping for ALL models
- Explicit confidence request
- Proper fallback parsing (no substring ambiguity)
"""
import csv, json, random, sys, time, re
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR
from agents.llm_utils import llm_call

random.seed(42)

JUDGES = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6"]
REPEATS = 3
TEMPERATURE = 0.3  # Non-zero for genuine repeats

SYSTEM_PROMPT = """You are comparing two academic emails to determine which is more persuasive.
Your task is a careful reading task. Read both emails fully, then decide which one a recipient would find more persuasive.

IMPORTANT: Return ONLY a JSON object with exactly these fields:
- winner: "1" (if Email 1 is more persuasive) or "2" (if Email 2 is more persuasive)
- confidence: integer from 1 (pure guess) to 5 (completely certain)
- reasoning: one sentence explaining your choice

Do NOT include any other text. Do NOT wrap the JSON in markdown."""


def parse_response(resp_text):
    """Robust JSON parsing. Handles markdown wrapping, stray text, thinking blocks."""
    if not resp_text:
        return {"winner": "error", "confidence": 0, "reasoning": "no response"}

    text = resp_text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)

    # Find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        parsed = json.loads(text)
        w = parsed.get("winner", "?")
        # Normalize "1"/"2" to "A"/"B" for backwards compatibility
        if w == "1":
            w = "A"
        elif w == "2":
            w = "B"
        return {
            "winner": w,
            "confidence": int(parsed.get("confidence", 0)),
            "reasoning": parsed.get("reasoning", "")[:200],
        }
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: look for explicit "Email 1" or "Email 2" mentions
    text_lower = text.lower()
    mentions_1 = len(re.findall(r"\bemail\s*1\b|\bone\b.*more persuasive", text_lower))
    mentions_2 = len(re.findall(r"\bemail\s*2\b|\btwo\b.*more persuasive", text_lower))
    if mentions_1 > mentions_2:
        return {"winner": "A", "confidence": 1, "reasoning": "fallback: Email 1 mentioned more"}
    elif mentions_2 > mentions_1:
        return {"winner": "B", "confidence": 1, "reasoning": "fallback: Email 2 mentioned more"}

    return {"winner": "error", "confidence": 0, "reasoning": "could not parse: " + text[:80]}


def build_blind_prompt(email_a, email_b, swap=False):
    """Build a blind prompt. If swap=True, email order is reversed."""
    if swap:
        first, second = email_b, email_a
        first_label, second_label = "B", "A"  # original labels (used for winner mapping)
    else:
        first, second = email_a, email_b
        first_label, second_label = "A", "B"

    prompt = f"""Email 1:
Subject: {first['email_subject']}
Body: {first['email_body']}

Email 2:
Subject: {second['email_subject']}
Body: {second['email_body']}

Which email is more persuasive?"""

    return prompt, first_label, second_label


def judge_pair(email_a, email_b, n_repeats=REPEATS):
    """Judge one pair with counterbalanced A/B across repeats.
    Returns list of judgment dicts with original_labels mapped back.
    """
    judgments = []
    for r in range(n_repeats):
        swap = (r % 2 == 1)  # Alternate: even repeats = normal, odd = swapped
        prompt, first_label, second_label = build_blind_prompt(email_a, email_b, swap=swap)

        for model in JUDGES:
            resp = llm_call(SYSTEM_PROMPT, prompt, model=model, max_tokens=256,
                          json_mode=False, temperature=TEMPERATURE)
            result = parse_response(resp)

            # Map back: if swapped, "1"=B wins, "2"=A wins
            raw_winner = result["winner"]
            if swap and raw_winner == "A":  # A=Email1, which was originally B
                mapped_winner = "B"
            elif swap and raw_winner == "B":  # B=Email2, which was originally A
                mapped_winner = "A"
            else:
                mapped_winner = raw_winner

            judgments.append({
                "model": model,
                "repeat": r + 1,
                "swapped": swap,
                "winner": mapped_winner,
                "confidence": result["confidence"],
                "reasoning": result["reasoning"],
                "raw_response": resp[:200] if resp else "None",
            })

        time.sleep(0.5)  # Rate limit between repeats

    return judgments


def run_judge_on_pairs(email_pairs, output_path, label=""):
    """Run blind judge on a list of (email_a, email_b, metadata) tuples."""
    all_results = []
    total = len(email_pairs) * REPEATS * len(JUDGES)
    count = 0

    for email_a, email_b, meta in email_pairs:
        judgments = judge_pair(email_a, email_b)
        for j in judgments:
            j.update(meta)
        all_results.extend(judgments)
        count += len(judgments)
        if count % 30 == 0:
            print(f"  [{count}/{total}] {label}", flush=True)
        time.sleep(0.3)

    # Write CSV
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_results[0].keys()))
        writer.writeheader()
        writer.writerows(all_results)

    # Summary
    winners = [j["winner"] for j in all_results if j["winner"] in ("A", "B")]
    a_count = sum(1 for w in winners if w == "A")
    b_count = sum(1 for w in winners if w == "B")
    errors = sum(1 for j in all_results if j["winner"] == "error")
    confs = [j["confidence"] for j in all_results if j["confidence"] > 0]
    mean_conf = sum(confs) / max(len(confs), 1)

    print(f"\n{label}: {len(all_results)} judgments, A={a_count}, B={b_count}, errors={errors}, mean_confidence={mean_conf:.1f}")
    return all_results
