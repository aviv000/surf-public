"""Master pipeline runner for 100-persona within-condition evaluation.

Runs: profile → generate → judge → analyze → features
Can run individual stages or --all.

Usage:
  python scripts/run_100_pipeline.py --all
  python scripts/run_100_pipeline.py --generate
  python scripts/run_100_pipeline.py --judge
  python scripts/run_100_pipeline.py --status
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

STAGES = {
    "profile": ["python", "scripts/profile_100_personas.py"],
    "generate": ["python", "scripts/within_condition_eval.py", "--generate"],
    "judge": ["python", "scripts/within_condition_eval.py", "--judge"],
    "analyze": ["python", "scripts/within_condition_eval.py", "--analyze"],
    "features": ["python", "scripts/linguistic_persuasion_features.py"],
}


def run_stage(name: str) -> bool:
    """Run one pipeline stage. Returns True on success."""
    if name not in STAGES:
        print(f"Unknown stage: {name}")
        return False

    print(f"\n{'='*60}")
    print(f"STAGE: {name}")
    print(f"{'='*60}")

    start = time.time()
    result = subprocess.run(STAGES[name], cwd=Path(__file__).parent.parent)
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"STAGE {name}: OK ({elapsed:.0f}s)")
        return True
    else:
        print(f"STAGE {name}: FAILED (exit {result.returncode})")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--features", action="store_true")
    parser.add_argument("--from", dest="from_stage", type=str, help="Start from this stage")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    stage_order = ["profile", "generate", "judge", "analyze", "features"]

    if args.status:
        print("Pipeline status:")
        for s in stage_order:
            check = _check_stage(s)
            print(f"  {s}: {'DONE' if check else 'PENDING'}")
        return

    if args.from_stage:
        start_idx = stage_order.index(args.from_stage)
        stages_to_run = stage_order[start_idx:]
    elif args.all:
        stages_to_run = stage_order
    else:
        stages_to_run = [s for s in stage_order
                        if getattr(args, s, False)]

    if not stages_to_run:
        print("Specify --all or individual stages")
        return

    for stage in stages_to_run:
        if not run_stage(stage):
            print(f"Pipeline stopped at {stage}")
            break


def _check_stage(name: str) -> bool:
    """Check if stage output exists."""
    outputs_dir = Path(__file__).parent.parent / "outputs"
    persona_spec = Path(__file__).parent.parent / "publish" / "llmnet-2026" / "supplementary" / "persona_specifications_100.json"
    cache_dir = Path(__file__).parent.parent / "cache" / "targets"

    checks = {
        "profile": cache_dir / "per-001" / "profile.json",
        "generate": outputs_dir / "within_condition_emails.csv",
        "judge": outputs_dir / "within_condition_judgments.csv",
        "features": outputs_dir / "linguistic_features.csv",
    }
    return persona_spec.exists() and checks.get(name, Path("/nonexistent")).exists()


if __name__ == "__main__":
    main()
