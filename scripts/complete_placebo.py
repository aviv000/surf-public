#!/usr/bin/env python
"""Complete the placebo pair to 100 personas.

The placebo (S+C- vs. matched paraphrase) currently covers 83 of 100
personas; the paraphrases for 17 personas were never generated. This
script (1) generates the 17 missing paraphrases with the exact prompt
and model from ablation_placebo.py, (2) judges the 17 new pairs with all
four judges using the same seeded swap logic, appending to the existing
checkpointed CSVs.

Usage: .venv/bin/python scripts/complete_placebo.py
"""
import csv
import random
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR  # noqa: E402
from agents.llm_utils import llm_json  # noqa: E402
from scripts.ablation_placebo import (PARA_SYSTEM, JUDGE_SYSTEM, PARAPHRASE_MODEL,
                                      _gemini)  # noqa: E402

EMAILS = OUTPUTS_DIR / "dissociation_emails_100.csv"
PLACEBO_EMAILS = OUTPUTS_DIR / "n100" / "placebo_emails.csv"
PLACEBO_JUDGMENTS = OUTPUTS_DIR / "n100" / "placebo_judgments.csv"
JUDGE_MODELS = ["gpt-4.1-mini", "deepseek-chat", "claude-sonnet-4-6",
                "gemini-2.5-flash"]


def stage1_generate():
    emails = pd.read_csv(EMAILS)
    pe = pd.read_csv(PLACEBO_EMAILS)
    have = set(pe.target_id)
    todo = emails[~emails.target_id.isin(have)]
    print(f"missing paraphrases: {len(todo)}", flush=True)
    for _, row in todo.iterrows():
        body = str(row["S+C-_body"])
        res = None
        for attempt in range(3):
            try:
                res = llm_json(PARA_SYSTEM, f"Email body:\n{body}",
                               model=PARAPHRASE_MODEL, max_tokens=1500)
            except Exception:
                res = None
            if res and res.get("body"):
                break
            time.sleep(1)
        if res and res.get("body"):
            pe = pd.concat([pe, pd.DataFrame([{"target_id": row["target_id"],
                                               "para_body": res["body"]}])],
                           ignore_index=True)
            pe.to_csv(PLACEBO_EMAILS, index=False)
            print(f"{row['target_id']}: paraphrased", flush=True)
        else:
            print(f"{row['target_id']}: FAILED", flush=True)
    print("generation done", flush=True)


def stage2_judge():
    emails = pd.read_csv(EMAILS)
    para = pd.read_csv(PLACEBO_EMAILS)
    m = emails.merge(para, on="target_id")
    done = set()
    if PLACEBO_JUDGMENTS.exists():
        with PLACEBO_JUDGMENTS.open(encoding="utf-8") as f:
            done = {(r["target_id"], r["model"]) for r in csv.DictReader(f)}
    out = []
    for _, row in m.iterrows():
        for model in JUDGE_MODELS:
            if (row["target_id"], model) in done:
                continue
            a = f"EMAIL A:\nSubject: {row['S+C-_subject']}\nBody: {row['S+C-_body']}"
            b = f"EMAIL B:\nSubject: {row['S+C-_subject']}\nBody: {row['para_body']}"
            swapped = random.Random(hash((row["target_id"], model, 7)) % 2**32).random() < 0.5
            user_msg = f"{b}\n\n{a}" if swapped else f"{a}\n\n{b}"
            for attempt in range(2):
                try:
                    res = (_gemini(user_msg) if model == "gemini-2.5-flash"
                           else llm_json(JUDGE_SYSTEM, user_msg, model=model, max_tokens=512))
                except Exception:
                    res = None
                if res and res.get("winner") in ("A", "B"):
                    out.append({"target_id": row["target_id"], "model": model,
                                "winner": res["winner"],
                                "chose_original": int(
                                    (res["winner"] == "B") if swapped else (res["winner"] == "A")),
                                "swapped": swapped})
                    break
                time.sleep(1)
        if len(out) >= 20:
            new_file = not PLACEBO_JUDGMENTS.exists()
            with PLACEBO_JUDGMENTS.open("a" if not new_file else "w",
                                        encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["target_id", "model", "winner",
                                                  "chose_original", "swapped"])
                if new_file:
                    w.writeheader()
                w.writerows(out)
            print(f"judged +{len(out)}", flush=True)
            out = []
    if out:
        new_file = not PLACEBO_JUDGMENTS.exists()
        with PLACEBO_JUDGMENTS.open("a" if not new_file else "w",
                                    encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["target_id", "model", "winner",
                                              "chose_original", "swapped"])
            if new_file:
                w.writeheader()
            w.writerows(out)
        print(f"judged +{len(out)}", flush=True)
    print("judging done", flush=True)


if __name__ == "__main__":
    stage1_generate()
    stage2_judge()
