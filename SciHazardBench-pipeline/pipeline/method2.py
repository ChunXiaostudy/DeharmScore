"""Track 2: Scenario-driven Pipeline — Scenario Loading → Template Combination → LLM Batch Generation"""

import asyncio
import json
import logging
import math
import os
import random

from tqdm import tqdm

from pipeline import api_client
from pipeline.api_client import REFUSAL_SENTINEL
from pipeline.config import DATASET_PATH, OUTPUT_DIR, SCENARIO_SUBJECTS, TARGET_PER_SUBJECT
from pipeline.prompts import (
    TEMPLATE_A_SYSTEM, TEMPLATE_A_USER,
    TEMPLATE_B_SYSTEM, TEMPLATE_B_USER,
    TEMPLATE_C_SYSTEM, TEMPLATE_C_USER,
)
from pipeline.utils import JSONLWriter, load_completed_keys

logger = logging.getLogger(__name__)

REFUSED_PATH = os.path.join(OUTPUT_DIR, "refused.json")


def _load_refused() -> list[dict]:
    if os.path.exists(REFUSED_PATH):
        with open(REFUSED_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_refused(items: list[dict]):
    with open(REFUSED_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


TEMPLATE_MAP = {
    "A": (TEMPLATE_A_SYSTEM, TEMPLATE_A_USER),
    "B": (TEMPLATE_B_SYSTEM, TEMPLATE_B_USER),
    "C": (TEMPLATE_C_SYSTEM, TEMPLATE_C_USER),
}

COVER_STORIES = {
    "Computer Science": [
        "Penetration testing and red-team exercises", "Cybersecurity course instruction",
        "Bug bounty program research", "Automated security audit tool development",
        "Threat intelligence analysis",
    ],
    "Psychology": [
        "Post-trauma psychological recovery research", "Cognitive behavioral therapy optimization",
        "Group decision-making mechanism studies", "Neuroscience foundations of addiction mechanisms",
        "Assessing social media impact on mental health",
    ],
    "Sociology": [
        "Social media information propagation dynamics research", "Online community governance model analysis",
        "Public opinion monitoring system design", "Digital citizenship literacy education",
        "Cross-cultural communication research",
    ],
    "Economics": [
        "Market microstructure research", "Quantitative risk management model development",
        "Financial stress test design", "Anti-money laundering system optimization",
        "High-frequency trading regulation research",
    ],
    "Law": [
        "Cross-border compliance framework research", "Intellectual property protection strategies",
        "Digital evidence forensic standards", "International arbitration case analysis",
        "Comparative privacy law research",
    ],
}


async def generate_questions_for_subject(
    subject: str,
    target: int | None = None,
    dry_run: bool = False,
) -> int:
    if target is None:
        target = TARGET_PER_SUBJECT
    cfg = SCENARIO_SUBJECTS[subject]
    template_id = cfg["template"]
    sys_prompt, user_template = TEMPLATE_MAP[template_id]

    scenarios = cfg["scenarios"]
    bottlenecks = cfg["bottlenecks"]
    verbs = cfg["verbs"]
    sub_disciplines = cfg["sub_disciplines"]
    context = cfg["context"]
    covers = COVER_STORIES.get(subject, ["Academic research"])

    n_per_call = 5
    total_calls = math.ceil(target / n_per_call)
    calls_per_scenario = max(1, total_calls // len(scenarios))

    done_keys = load_completed_keys(DATASET_PATH, ("subject", "scenario"))
    writer = JSONLWriter(DATASET_PATH, flush_every=30)
    generated = 0
    idx_counter = 0
    refused_items: list[dict] = []

    logger.info("[%s] %d scenarios, %d calls/scenario, %d q/call, target %d",
                subject, len(scenarios), calls_per_scenario, n_per_call, target)

    async def _gen_one(scenario: str, call_idx: int):
        nonlocal generated, idx_counter

        sub_disc = random.choice(sub_disciplines)
        bottleneck = random.choice(bottlenecks)
        verb_sample = ", ".join(random.sample(verbs, min(4, len(verbs))))

        if template_id == "C":
            cover = random.choice(covers)
            user_prompt = user_template.format(
                subject=subject,
                sub_discipline=sub_disc,
                scenario=scenario,
                cover_story=cover,
                bottleneck=bottleneck,
                context=context,
                n=n_per_call,
            )
        else:
            user_prompt = user_template.format(
                subject=subject,
                sub_discipline=sub_disc,
                scenario=scenario,
                bottleneck=bottleneck,
                verbs=verb_sample,
                context=context,
                n=n_per_call,
            )

        if dry_run:
            return

        questions = await api_client.chat_json(sys_prompt, user_prompt)

        if questions is REFUSAL_SENTINEL:
            refused_items.append({
                "subject": subject,
                "scenario": scenario[:120],
                "bottleneck": bottleneck,
                "sub_discipline": sub_disc,
                "template": template_id,
            })
            return

        if not isinstance(questions, list):
            return

        for q in questions:
            if not isinstance(q, str) or len(q) < 10:
                continue
            idx_counter += 1
            writer.write({
                "idx": idx_counter,
                "subject": subject,
                "sub_discipline": sub_disc,
                "category": f"Scenario-driven Template {template_id}",
                "scenario": scenario,
                "bottleneck": bottleneck,
                "question": q,
            })
            generated += 1

    all_tasks = []
    for scenario in scenarios:
        for ci in range(calls_per_scenario):
            all_tasks.append((scenario, ci))

    while len(all_tasks) * n_per_call < target:
        scenario = random.choice(scenarios)
        all_tasks.append((scenario, len(all_tasks)))

    max_tasks = math.ceil(target / n_per_call) + 10
    if len(all_tasks) > max_tasks:
        random.shuffle(all_tasks)
        all_tasks = all_tasks[:max_tasks]

    logger.info("[%s] %d API calls planned", subject, len(all_tasks))

    pbar = tqdm(total=target, desc=f"[{subject}] Questions", unit="q")
    batch_size = 30
    for i in range(0, len(all_tasks), batch_size):
        prev = generated
        batch = all_tasks[i:i + batch_size]
        await asyncio.gather(*[_gen_one(s, ci) for s, ci in batch])
        pbar.update(generated - prev)
        if generated >= target:
            break
    pbar.close()

    writer.close()

    if refused_items:
        existing = _load_refused()
        existing.extend(refused_items)
        _save_refused(existing)
        logger.info("[%s] %d refusals saved to %s", subject, len(refused_items), REFUSED_PATH)

    logger.info("[%s] Done, generated %d questions", subject, generated)
    return generated


async def run_track2(subjects: list[str] | None = None, target: int | None = None, dry_run: bool = False) -> int:
    if subjects is None:
        subjects = list(SCENARIO_SUBJECTS.keys())

    total = 0
    for subj in subjects:
        if subj not in SCENARIO_SUBJECTS:
            logger.warning("Subject '%s' not in Track 2, skipping", subj)
            continue
        count = await generate_questions_for_subject(subj, target=target, dry_run=dry_run)
        total += count
    return total
