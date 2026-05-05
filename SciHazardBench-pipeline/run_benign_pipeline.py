#!/usr/bin/env python3
"""
Benign Science Question Dataset Generation Pipeline

Usage:
    python run_benign_pipeline.py --all                          # Run all 12 subjects
    python run_benign_pipeline.py --subject Chemistry Biology    # Specific subjects
    python run_benign_pipeline.py --all --target 10              # Override per-subject target
    python run_benign_pipeline.py --all --concurrency 20         # API concurrency
    python run_benign_pipeline.py --stats                        # Show current stats
"""

import argparse
import asyncio
import json
import logging
import math
import os
import random
from collections import Counter

from tqdm import tqdm

from pipeline import api_client
from pipeline.api_client import REFUSAL_SENTINEL
from pipeline.config import (
    SUBJECT_SUBSTANCE_MAP, DEFAULT_CONCURRENCY, SUBSTANCES_PATH,
)
from pipeline.benign_config import (
    BENIGN_DATASET_PATH, BENIGN_TARGETS, DEFENSE_ANGLES,
    TRACK1_SUBJECTS, TRACK2_SUBJECTS, BENIGN_SCENARIOS,
)
from pipeline.benign_prompts import (
    BENIGN_SUBSTANCE_SYSTEM, BENIGN_SUBSTANCE_USER,
    BENIGN_SCENARIO_SYSTEM, BENIGN_SCENARIO_USER,
)
from pipeline.utils import (
    JSONLWriter, load_substances, get_substances_for_subject,
    load_completed_keys, read_jsonl, count_jsonl,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("benign")

N_PER_CALL = 5
BENIGN_MODEL = "gpt-5"


def show_stats():
    items = read_jsonl(BENIGN_DATASET_PATH)
    if not items:
        print("No benign data yet.")
        return
    counter = Counter(item.get("subject", "unknown") for item in items)
    print(f"\n{'='*55}")
    print(f"Dataset: {BENIGN_DATASET_PATH}")
    print(f"Total:   {len(items)}")
    print(f"{'='*55}")
    print(f"{'Subject':<30} {'Count':>8}")
    print(f"{'-'*40}")
    for subj in sorted(counter, key=counter.get, reverse=True):
        print(f"{subj:<30} {counter[subj]:>8}")
    print(f"{'-'*40}")
    print(f"{'TOTAL':<30} {len(items):>8}")
    print()


# ── Track 1: Substance-defense generation ────────────────────────────
async def run_track1_subject(subject: str, target: int) -> int:
    cfg = SUBJECT_SUBSTANCE_MAP[subject]
    data = load_substances()
    substances = get_substances_for_subject(subject, cfg, data)

    if not substances:
        logger.warning("[%s] No substances found", subject)
        return 0

    sub_disciplines = cfg["sub_disciplines"]
    angles = list(DEFENSE_ANGLES.items())

    total_calls = math.ceil(target / N_PER_CALL)
    done_keys = load_completed_keys(BENIGN_DATASET_PATH, ("subject", "substance", "defense_angle"))

    writer = JSONLWriter(BENIGN_DATASET_PATH, flush_every=30)
    generated = 0
    idx_counter = count_jsonl(BENIGN_DATASET_PATH)

    async def _gen(substance: str, angle_name: str, angle_desc: str, sub_disc: str):
        nonlocal generated, idx_counter

        if (subject, substance, angle_name) in done_keys:
            return

        user_prompt = BENIGN_SUBSTANCE_USER.format(
            subject=subject,
            sub_discipline=sub_disc,
            substance=substance,
            defense_angle=angle_name,
            angle_description=angle_desc,
            n=N_PER_CALL,
        )

        questions = await api_client.chat_json(BENIGN_SUBSTANCE_SYSTEM, user_prompt, model=BENIGN_MODEL)

        if questions is REFUSAL_SENTINEL or not isinstance(questions, list):
            return

        for q in questions:
            if not isinstance(q, str) or len(q) < 10:
                continue
            idx_counter += 1
            writer.write({
                "idx": idx_counter,
                "subject": subject,
                "sub_discipline": sub_disc,
                "category": "Substance-defense",
                "substance": substance,
                "defense_angle": angle_name,
                "question": q,
            })
            generated += 1

    all_tasks = []
    for _ in range(total_calls):
        s = random.choice(substances)
        angle_name, angle_desc = random.choice(angles)
        sub_disc = random.choice(sub_disciplines)
        all_tasks.append((s, angle_name, angle_desc, sub_disc))

    logger.info("[%s] Track 1: %d substances, %d API calls, target %d",
                subject, len(substances), len(all_tasks), target)

    pbar = tqdm(total=target, desc=f"[{subject}] Benign", unit="q", leave=False)
    batch_size = 30
    for i in range(0, len(all_tasks), batch_size):
        prev = generated
        batch = all_tasks[i:i + batch_size]
        await asyncio.gather(*[_gen(s, an, ad, sd) for s, an, ad, sd in batch])
        pbar.update(generated - prev)
        if generated >= target:
            break
    pbar.close()
    writer.close()

    logger.info("[%s] Track 1 done, generated %d questions", subject, generated)
    return generated


# ── Track 2: Benign scenario generation ──────────────────────────────
async def run_track2_subject(subject: str, target: int) -> int:
    cfg = BENIGN_SCENARIOS[subject]
    scenarios = cfg["scenarios"]
    sub_disciplines = cfg["sub_disciplines"]
    context = cfg["context"]

    total_calls = math.ceil(target / N_PER_CALL)
    done_keys = load_completed_keys(BENIGN_DATASET_PATH, ("subject", "scenario"))

    writer = JSONLWriter(BENIGN_DATASET_PATH, flush_every=30)
    generated = 0
    idx_counter = count_jsonl(BENIGN_DATASET_PATH)

    async def _gen(scenario: str, sub_disc: str):
        nonlocal generated, idx_counter

        user_prompt = BENIGN_SCENARIO_USER.format(
            subject=subject,
            sub_discipline=sub_disc,
            scenario=scenario,
            context=context,
            n=N_PER_CALL,
        )

        questions = await api_client.chat_json(BENIGN_SCENARIO_SYSTEM, user_prompt, model=BENIGN_MODEL)

        if questions is REFUSAL_SENTINEL or not isinstance(questions, list):
            return

        for q in questions:
            if not isinstance(q, str) or len(q) < 10:
                continue
            idx_counter += 1
            writer.write({
                "idx": idx_counter,
                "subject": subject,
                "sub_discipline": sub_disc,
                "category": "Benign-scenario",
                "scenario": scenario,
                "question": q,
            })
            generated += 1

    all_tasks = []
    for _ in range(total_calls):
        scenario = random.choice(scenarios)
        sub_disc = random.choice(sub_disciplines)
        all_tasks.append((scenario, sub_disc))

    logger.info("[%s] Track 2: %d scenarios, %d API calls, target %d",
                subject, len(scenarios), len(all_tasks), target)

    pbar = tqdm(total=target, desc=f"[{subject}] Benign", unit="q", leave=False)
    batch_size = 30
    for i in range(0, len(all_tasks), batch_size):
        prev = generated
        batch = all_tasks[i:i + batch_size]
        await asyncio.gather(*[_gen(s, sd) for s, sd in batch])
        pbar.update(generated - prev)
        if generated >= target:
            break
    pbar.close()
    writer.close()

    logger.info("[%s] Track 2 done, generated %d questions", subject, generated)
    return generated


# ── Main ─────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Benign Science Question Generation Pipeline")
    parser.add_argument("--all", action="store_true", help="Run all 12 subjects")
    parser.add_argument("--subject", nargs="+", help="Run specific subject(s)")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--target", type=int, default=0,
                        help="Override per-subject target (0=use BENIGN_TARGETS)")
    parser.add_argument("--stats", action="store_true", help="Show current stats")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    if not (args.all or args.subject):
        parser.print_help()
        return

    api_client.init_client(args.concurrency)

    subjects = list(BENIGN_TARGETS.keys()) if args.all else args.subject

    plan = []
    for subj in subjects:
        if subj not in BENIGN_TARGETS:
            logger.warning("Unknown subject: %s", subj)
            continue
        t = args.target if args.target > 0 else BENIGN_TARGETS[subj]
        track = 1 if subj in TRACK1_SUBJECTS else 2
        plan.append((subj, track, t))

    total_target = sum(t for _, _, t in plan)
    pbar_overall = tqdm(total=total_target, desc="Overall", unit="q", colour="green", position=0)
    grand_total = 0

    for subj, track, t in plan:
        if track == 1:
            count = await run_track1_subject(subj, t)
        else:
            count = await run_track2_subject(subj, t)
        grand_total += count
        pbar_overall.update(count)

    pbar_overall.close()
    logger.info("=== Benign pipeline finished, generated %d items ===", grand_total)
    show_stats()


if __name__ == "__main__":
    asyncio.run(main())
