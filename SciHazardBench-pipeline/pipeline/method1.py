"""Track 1: Substance-driven Pipeline — Entity Profiling → Combinatorial Generation → Deepening"""

import asyncio
import json
import logging
import math
import os
import random

from tqdm import tqdm

from pipeline import api_client
from pipeline.api_client import REFUSAL_SENTINEL
from pipeline.config import (
    ENTITY_PROFILES_PATH, DATASET_PATH, OUTPUT_DIR,
    LIFECYCLE_STAGES, SUBJECT_SUBSTANCE_MAP, TARGET_PER_SUBJECT,
)
from pipeline.prompts import (
    ENTITY_PROFILE_SYSTEM, ENTITY_PROFILE_USER,
    QUESTION_GEN_SYSTEM, QUESTION_GEN_USER,
    STAGE_DESCRIPTIONS,
)
from pipeline.utils import (
    JSONLWriter, load_substances, get_substances_for_subject,
    load_profile_cache, load_completed_keys,
)

logger = logging.getLogger(__name__)

REFUSED_PATH = os.path.join(OUTPUT_DIR, "refused.json")

_refused_lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None


def _load_refused() -> list[dict]:
    if os.path.exists(REFUSED_PATH):
        with open(REFUSED_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_refused(items: list[dict]):
    with open(REFUSED_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

PROFILE_BATCH_SIZE = 5

CATEGORY_EN = {
    "化学武器类": "Chemical Weapons",
    "易制毒化学品类": "Drug Precursor Chemicals",
    "生物毒素与病原体类": "Biological Toxins & Pathogens",
    "核辐射材料类": "Nuclear Radiation Materials",
    "毒品类": "Illicit Drugs",
    "麻醉药品和精神药品类": "Narcotic & Psychotropic Substances",
    "高关注度危险化学品(SVHC)": "SVHC Hazardous Chemicals",
}


async def profile_substances(subject: str, substances: list[str]) -> dict[str, list[str]]:
    cache = load_profile_cache(ENTITY_PROFILES_PATH)
    todo = [s for s in substances if s not in cache]
    if not todo:
        logger.info("[%s] All %d substance profiles cached", subject, len(substances))
        return {s: cache[s] for s in substances if s in cache}

    logger.info("[%s] Profiling %d substances (%d cached)",
                subject, len(todo), len(substances) - len(todo))

    writer = JSONLWriter(ENTITY_PROFILES_PATH, flush_every=10)
    batches = [todo[i:i + PROFILE_BATCH_SIZE] for i in range(0, len(todo), PROFILE_BATCH_SIZE)]

    async def _do_batch(batch: list[str]):
        substance_list = "\n".join(f"- {s}" for s in batch)
        user_prompt = ENTITY_PROFILE_USER.format(subject=subject, substance_list=substance_list)
        result = await api_client.chat_json(ENTITY_PROFILE_SYSTEM, user_prompt, temperature=0.7)
        if isinstance(result, list):
            for item in result:
                name = item.get("substance", "")
                bns = item.get("bottlenecks", [])
                if name and bns:
                    cache[name] = bns
                    writer.write({"substance": name, "bottlenecks": bns})

    tasks = [_do_batch(b) for b in batches]
    pbar = tqdm(total=len(tasks), desc=f"[{subject}] Profiling", unit="batch", leave=False)
    for i in range(0, len(tasks), 20):
        await asyncio.gather(*tasks[i:i + 20])
        pbar.update(min(20, len(tasks) - i))
    pbar.close()

    writer.close()
    return {s: cache.get(s, ["general safety risk", "synthesis difficulty", "detection evasion"]) for s in substances}


async def generate_questions_for_subject(
    subject: str,
    target: int | None = None,
    dry_run: bool = False,
) -> int:
    if target is None:
        target = TARGET_PER_SUBJECT
    cfg = SUBJECT_SUBSTANCE_MAP[subject]
    data = load_substances()
    substances = get_substances_for_subject(subject, cfg, data)

    if not substances:
        logger.warning("[%s] No substances found", subject)
        return 0

    logger.info("[%s] %d substances, target %d questions", subject, len(substances), target)

    profiles = await profile_substances(subject, substances)

    n_per_substance = max(1, math.ceil(target / len(substances)))
    n_per_call = min(n_per_substance, 5)
    calls_per_substance = max(1, math.ceil(n_per_substance / n_per_call))

    done_keys = load_completed_keys(DATASET_PATH, ("subject", "substance"))

    writer = JSONLWriter(DATASET_PATH, flush_every=30)
    generated = 0
    idx_counter = len(done_keys)
    refused_items: list[dict] = []

    sub_disciplines = cfg["sub_disciplines"]
    verbs = cfg["verbs"]
    categories = cfg["categories"]
    context = cfg["context"]

    async def _gen_one(substance: str, call_idx: int):
        nonlocal generated, idx_counter

        if (subject, substance) in done_keys and call_idx == 0:
            return

        bottlenecks = profiles.get(substance, ["general safety risk"])
        stage = LIFECYCLE_STAGES[call_idx % len(LIFECYCLE_STAGES)]
        sub_disc = random.choice(sub_disciplines)
        category_raw = random.choice(categories)
        category = CATEGORY_EN.get(category_raw, category_raw)

        user_prompt = QUESTION_GEN_USER.format(
            subject=subject,
            sub_discipline=sub_disc,
            substance=substance,
            category=category,
            context=context,
            bottlenecks=", ".join(bottlenecks),
            lifecycle_stage=stage,
            stage_description=STAGE_DESCRIPTIONS[stage],
            verbs=", ".join(verbs),
            n=n_per_call,
        )

        if dry_run:
            return

        questions = await api_client.chat_json(QUESTION_GEN_SYSTEM, user_prompt)

        if questions is REFUSAL_SENTINEL:
            refused_items.append({
                "subject": subject,
                "substance": substance,
                "category": category,
                "lifecycle_stage": stage,
                "sub_discipline": sub_disc,
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
                "category": category,
                "substance": substance,
                "lifecycle_stage": stage,
                "technical_bottleneck": ", ".join(bottlenecks),
                "question": q,
            })
            generated += 1

    all_tasks = []
    for substance in substances:
        for ci in range(calls_per_substance):
            all_tasks.append((substance, ci))

    max_tasks = math.ceil(target / n_per_call) + 10
    if len(all_tasks) > max_tasks:
        random.shuffle(all_tasks)
        all_tasks = all_tasks[:max_tasks]

    logger.info("[%s] %d API calls planned (%d questions/call)", subject, len(all_tasks), n_per_call)

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


async def run_track1(subjects: list[str] | None = None, target: int | None = None, dry_run: bool = False) -> int:
    if subjects is None:
        subjects = list(SUBJECT_SUBSTANCE_MAP.keys())

    total = 0
    for subj in subjects:
        if subj not in SUBJECT_SUBSTANCE_MAP:
            logger.warning("Subject '%s' not in Track 1, skipping", subj)
            continue
        count = await generate_questions_for_subject(subj, target=target, dry_run=dry_run)
        total += count
    return total
