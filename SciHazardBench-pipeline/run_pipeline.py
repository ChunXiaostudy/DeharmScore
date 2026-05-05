#!/usr/bin/env python3
"""
Hazardous Science Question Dataset Generation Pipeline

Usage:
    python run_pipeline.py --all                          # Run all 12 subjects
    python run_pipeline.py --track 1                      # Track 1 only (substance-driven)
    python run_pipeline.py --track 2                      # Track 2 only (scenario-driven)
    python run_pipeline.py --subject Chemistry             # Run a specific subject
    python run_pipeline.py --subject Chemistry Biology     # Run multiple subjects
    python run_pipeline.py --all --concurrency 20          # Set concurrency
    python run_pipeline.py --all --target 100              # Per-subject target (for testing)
    python run_pipeline.py --all --dry-run                 # Dry run (no API calls)
    python run_pipeline.py --stats                         # Show current generation stats
"""

import argparse
import asyncio
import logging
from collections import Counter

from tqdm import tqdm

from pipeline import api_client
from pipeline.config import (
    DATASET_PATH, SUBJECT_SUBSTANCE_MAP, SCENARIO_SUBJECTS,
    TARGET_PER_SUBJECT, DEFAULT_CONCURRENCY,
)
from pipeline.method1 import generate_questions_for_subject as m1_gen
from pipeline.method2 import generate_questions_for_subject as m2_gen
from pipeline.utils import read_jsonl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("pipeline")


def show_stats():
    items = read_jsonl(DATASET_PATH)
    if not items:
        print("No data yet.")
        return
    counter = Counter(item.get("subject", "unknown") for item in items)
    print(f"\n{'='*55}")
    print(f"Dataset: {DATASET_PATH}")
    print(f"Total:   {len(items)}")
    print(f"{'='*55}")
    print(f"{'Subject':<30} {'Count':>8}")
    print(f"{'-'*40}")
    for subj in sorted(counter, key=counter.get, reverse=True):
        print(f"{subj:<30} {counter[subj]:>8}")
    print(f"{'-'*40}")
    print(f"{'TOTAL':<30} {len(items):>8}")
    print()


async def run_subjects(plan: list[tuple[str, int]], target: int, dry_run: bool) -> int:
    """Run a list of (subject, track) pairs with an overall progress bar."""
    total_target = target * len(plan)
    pbar = tqdm(total=total_target, desc="Overall", unit="q", colour="green", position=0)
    total = 0
    for subj, track in plan:
        gen_fn = m1_gen if track == 1 else m2_gen
        count = await gen_fn(subj, target=target, dry_run=dry_run)
        total += count
        pbar.update(count)
    pbar.close()
    return total


async def main():
    parser = argparse.ArgumentParser(description="Hazardous Science Question Dataset Pipeline")
    parser.add_argument("--all", action="store_true", help="Run all 12 subjects")
    parser.add_argument("--track", type=int, choices=[1, 2], help="Run specific track (1=substance, 2=scenario)")
    parser.add_argument("--subject", nargs="+", help="Run specific subject(s)")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="API concurrency")
    parser.add_argument("--target", type=int, default=TARGET_PER_SUBJECT, help="Per-subject target count")
    parser.add_argument("--dry-run", action="store_true", help="Dry run, no actual API calls")
    parser.add_argument("--stats", action="store_true", help="Show current generation stats")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    if not (args.all or args.track or args.subject):
        parser.print_help()
        return

    api_client.init_client(args.concurrency)
    target = args.target

    plan: list[tuple[str, int]] = []  # (subject, track_number)

    if args.all:
        logger.info("=== Running all subjects (concurrency=%d, target=%d/subject) ===", args.concurrency, target)
        for s in SUBJECT_SUBSTANCE_MAP:
            plan.append((s, 1))
        for s in SCENARIO_SUBJECTS:
            plan.append((s, 2))

    elif args.track == 1:
        subjects = args.subject if args.subject else list(SUBJECT_SUBSTANCE_MAP.keys())
        plan = [(s, 1) for s in subjects if s in SUBJECT_SUBSTANCE_MAP]

    elif args.track == 2:
        subjects = args.subject if args.subject else list(SCENARIO_SUBJECTS.keys())
        plan = [(s, 2) for s in subjects if s in SCENARIO_SUBJECTS]

    elif args.subject:
        for s in args.subject:
            if s in SUBJECT_SUBSTANCE_MAP:
                plan.append((s, 1))
            elif s in SCENARIO_SUBJECTS:
                plan.append((s, 2))
            else:
                logger.warning("Unknown subject: %s", s)

    total = await run_subjects(plan, target, args.dry_run)
    logger.info("=== Pipeline finished, generated %d items this run ===", total)
    show_stats()


if __name__ == "__main__":
    asyncio.run(main())
