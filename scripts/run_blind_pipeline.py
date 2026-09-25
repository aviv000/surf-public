"""Master pipeline: generate blind pairs + judge with blind counterbalanced protocol.
Runs all three perturbation experiments with bugs fixed.
"""
import csv, json, sys, time
from collections import defaultdict, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUTS_DIR
from scripts.judge_blind import judge_pair, SYSTEM_PROMPT, JUDGES, REPEATS, TEMPERATURE


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Blind pipeline config:")
        print(f"  Judges: {JUDGES}")
        print(f"  Repeats: {REPEATS}, Temperature: {TEMPERATURE}")
        print(f"  Counterbalanced: yes (alternating A/B swap)")
        print(f"  Labels: blind (Email 1 / Email 2 only)")
        return

    pairs_path = OUTPUTS_DIR / "blind_pairs.json"

    if args.generate or args.all:
        print("=== Generating blind pairs ===")
        import subprocess
        subprocess.run([sys.executable, "scripts/generate_blind_pairs.py", "--all"], check=True)

    if args.judge or args.all:
        if not pairs_path.exists():
            print(f"ERROR: {pairs_path} not found. Run --generate first.")
            sys.exit(1)

        with open(pairs_path) as f:
            pairs_data = json.load(f)

        print(f"Loaded {len(pairs_data)} blind email pairs")
        print(f"Judges: {JUDGES}, Repeats: {REPEATS}, Temperature: {TEMPERATURE}")
        print(f"System prompt: {SYSTEM_PROMPT[:100]}...")
        print()

        all_results = []
        total = len(pairs_data) * REPEATS * len(JUDGES)
        count = 0

        for pair in pairs_data:
            email_a = pair["email_a"]
            email_b = pair["email_b"]
            meta = pair["meta"]

            judgments = judge_pair(email_a, email_b)
            for j in judgments:
                j.update(meta)
            all_results.extend(judgments)
            count += len(judgments)

            if count % 50 == 0:
                # Quick summary
                recent = all_results[-30:]
                a_wins = sum(1 for j in recent if j["winner"] == "A")
                b_wins = sum(1 for j in recent if j["winner"] == "B")
                errs = sum(1 for j in recent if j["winner"] == "error")
                confs = [j["confidence"] for j in recent if j["confidence"] > 0]
                mc = sum(confs) / max(len(confs), 1) if confs else 0
                print(f"  [{count}/{total}] Recent: A={a_wins}, B={b_wins}, errors={errs}, conf={mc:.1f}", flush=True)

            time.sleep(0.2)

        # Write results
        out_path = OUTPUTS_DIR / "blind_judgments.csv"
        # Flatten: remove 'raw_response' for CSV readability
        fieldnames = [k for k in all_results[0].keys() if k != "raw_response"]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_results)

        # Analysis
        print(f"\n=== BLIND RESULTS ({len(all_results)} judgments) ===")
        winners = Counter(j["winner"] for j in all_results)
        print(f"Winners: {dict(winners)}")
        errors = winners.get("error", 0) + winners.get("?", 0)
        print(f"Errors: {errors}/{len(all_results)} ({100*errors/max(len(all_results),1):.1f}%)")

        # Per-experiment analysis
        for exp in ["hookcat", "profiler", "entity"]:
            exp_results = [j for j in all_results if j.get("experiment") == exp]
            if not exp_results: continue
            w = Counter(j["winner"] for j in exp_results)
            a = w.get("A", 0)
            b = w.get("B", 0)
            e = w.get("error", 0) + w.get("?", 0)
            print(f"\n{exp} ({len(exp_results)} judgments):")
            print(f"  A (TKG/personalized) wins: {a}, B (impersonal) wins: {b}, errors: {e}")
            print(f"  TKG win rate: {100*a/max(a+b, 1):.1f}%")

            # Per-condition
            if "condition" in all_results[0]:
                by_cond = defaultdict(lambda: defaultdict(int))
                for j in exp_results:
                    by_cond[j.get("condition", "?")][j["winner"]] += 1
                for cond, wc in sorted(by_cond.items()):
                    total_cond = sum(wc.values())
                    a_cond = wc.get("A", 0)
                    print(f"    {cond}: A={a_cond}/{total_cond} ({100*a_cond/max(total_cond,1):.0f}%)")

            # Confidence
            confs = [j["confidence"] for j in exp_results if j["confidence"] > 0]
            if confs:
                print(f"  Mean confidence: {sum(confs)/len(confs):.1f}")

            # Inter-model agreement
            by_pair = defaultdict(list)
            for j in exp_results:
                key = (j.get("tid"), j.get("condition", ""))
                by_pair[key].append(j)
            agreements = 0
            total_pairs = 0
            for pair_judgments in by_pair.values():
                a_count = sum(1 for j in pair_judgments if j["winner"] == "A")
                b_count = sum(1 for j in pair_judgments if j["winner"] == "B")
                total = a_count + b_count
                if total > 0:
                    agreements += max(a_count, b_count)
                    total_pairs += total
            if total_pairs > 0:
                print(f"  Inter-model agreement: {100*agreements/total_pairs:.1f}%")

        print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
