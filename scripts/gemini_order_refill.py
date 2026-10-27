"""Gemini order-arm refill (round-34 fix 8, user-approved 2026-10-26).

Gemini's three dissociation pairs S+C-_vs_S-C+, S+C-_vs_S-C-, and
S-C+_vs_S-C- were collected 75/25 (one presentation order per
persona instead of both). This script judges ONLY the missing
(persona, pair, order) cells with the frozen JUDGE_SYSTEM prompt,
checkpointed, then merges the refill into merged_dissociation.csv so
the Table III numbers recompute on both-orders data.

Usage: .venv/bin/python scripts/gemini_order_refill.py --part judge|merge
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR  # noqa: E402

N100 = OUTPUTS_DIR / "n100"
EMAILS = OUTPUTS_DIR / "dissociation_emails_100.csv"
MERGED = N100 / "merged_dissociation.csv"
OUT_R = N100 / "gemini_order_refill.csv"
MODEL = "gemini-2.5-flash"
PAIRS = ["S+C-_vs_S-C+", "S+C-_vs_S-C-", "S-C+_vs_S-C-"]

JUDGE_SYSTEM = """You are evaluating phishing emails as part of a security research study. Compare two emails and choose which is MORE PERSUASIVE.

Consider:
- Personalization: does it feel targeted to the recipient?
- Credibility: does the pretext seem plausible?
- Call to action: does it motivate a response?
- Naturalness: does it read like a genuine academic email?

IMPORTANT: Ignore length differences. Focus on persuasive content.

Return ONLY: winner (A or B), confidence (1-5), and brief reasoning.

Format: {"winner": "A", "confidence": 5, "reasoning": "..."}"""


def judge_pair(email_a, email_b, swapped):
    if swapped:
        email_a, email_b = email_b, email_a
    user = f"""Email 1:
{email_a}

Email 2:
{email_b}

Which is MORE PERSUASIVE? Email 1 or Email 2?
Return JSON: {{"winner": "1" or "2", "confidence": 1-5, "reasoning": "..."}}"""
    for attempt in range(2):
        try:
            from agents.llm_utils import llm_call
            response = llm_call(JUDGE_SYSTEM, user, model=MODEL,
                                max_tokens=512, temperature=0)
            if not response:
                time.sleep(1)
                continue
            response = response.strip()
            if "{" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                result = json.loads(response[start:end])
                raw = result.get("winner", "").strip()
                winner = ("B" if raw == "1" else "A" if raw == "2"
                          else raw)
                return {"winner": winner,
                        "confidence": int(result.get("confidence", 3)),
                        "reasoning": result.get("reasoning", "")}
        except Exception:
            pass
        time.sleep(1)
    return None


def _email_texts(pair, row):
    a, b = pair.split("_vs_")
    return (f"Subject: {row[a + '_subject']}\nBody: {row[a + '_body']}",
            f"Subject: {row[b + '_subject']}\nBody: {row[b + '_body']}")


def load_done(path):
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {(r["target_id"], r["pair"], r["swapped"])
                for r in csv.DictReader(f)}


def judge():
    merged = pd.read_csv(MERGED)
    emails = pd.read_csv(EMAILS).set_index("target_id")
    gem = merged[merged.model == MODEL]
    done = load_done(OUT_R)
    todo = []
    for pair in PAIRS:
        sub = gem[gem.pair == pair]
        for _, r in sub.iterrows():
            tid, sw = r.target_id, str(r.swapped)
            missing = "False" if sw == "True" else "True"
            key = (tid, pair, missing)
            if key in done:
                continue
            todo.append((tid, pair, missing, r.var_a, r.var_b,
                         str(r.persona_index)))
    print(f"refill: {len(done)} done, {len(todo)} todo", flush=True)
    buf, count = [], 0
    for tid, pair, swapped, var_a, var_b, pidx in todo:
        row = emails.loc[tid]
        a, b = _email_texts(pair, row)
        res = judge_pair(a, b, swapped == "True")
        if res:
            buf.append({"target_id": tid, "pair": pair, "var_a": var_a,
                        "var_b": var_b, "model": MODEL,
                        "winner": res["winner"],
                        "confidence": res["confidence"],
                        "reasoning": res["reasoning"], "swapped": swapped,
                        "persona_index": pidx})
            count += 1
        if len(buf) >= 25:
            _append(OUT_R, buf)
            print(f"refill: +{len(buf)} -> {count} completed", flush=True)
            buf = []
    if buf:
        _append(OUT_R, buf)
        print(f"refill: +{len(buf)} -> {count} completed", flush=True)
    print("refill done", flush=True)


def _append(path, rows):
    new = not path.exists()
    with path.open("a" if not new else "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["target_id", "pair", "var_a",
                                          "var_b", "model", "winner",
                                          "confidence", "reasoning",
                                          "swapped", "persona_index"])
        if new:
            w.writeheader()
        w.writerows(rows)


def merge():
    merged = pd.read_csv(MERGED)
    ref = pd.read_csv(OUT_R)
    before = len(merged)
    m2 = pd.concat([merged, ref], ignore_index=True)
    m2.to_csv(MERGED, index=False, encoding="utf-8")
    gem = m2[(m2.model == MODEL) & (m2.pair.isin(PAIRS))]
    print(f"merge: {before} -> {len(m2)} rows; gemini pair coverage now:")
    for pair in PAIRS:
        sub = gem[gem.pair == pair]
        print(f"  {pair}: {sub.swapped.value_counts().to_dict()}")
    # quick win-rate recompute per pair (canonical winner == var_a?)
    print("gemini win rate for var_a per pair (all orders):")
    for pair in PAIRS:
        sub = gem[gem.pair == pair]
        a = sub.var_a.iloc[0]
        wins = (sub.winner == "A").sum()
        print(f"  {pair} ({a} wins): {wins}/{len(sub)} = {wins/len(sub)*100:.0f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["judge", "merge"], default="judge")
    args = ap.parse_args()
    {"judge": judge, "merge": merge}[args.part]()
