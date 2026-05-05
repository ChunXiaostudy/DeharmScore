# Data Construction & Harmfulness Classification Pipeline

## Overview

This project constructs a multi-disciplinary dataset of hazardous scientific questions and performs harmfulness evaluation and risk-level classification. The pipeline covers **12 academic disciplines**, producing ~30,000 dangerous questions, ~6,000 benign questions, and includes harmfulness evaluation, L1-L5 risk classification, question conversion (repackaging), and cross-dataset comparison.

---

## 1. Hazardous Substance Extraction

**Script**: `extract_hazardous_substances.py`  
**Input**: Raw `.txt` / `.csv` files in `item_source/`  
**Output**: `hazardous_substances.json` (1,548 substances across 7 categories)

Categories:
- Chemical Weapons (CWC-listed)
- Precursor Chemicals (Category 1-3)
- Nuclear/Radiological Materials
- Narcotics
- Narcotic Drugs & Psychotropic Substances
- Biological Toxins & Pathogens (CDC/APHIS Select Agents, Australia Group)
- Substances of Very High Concern (SVHC)

---

## 2. Dangerous Question Generation

**Entry point**: `run_pipeline.py`  
**Model**: `gpt-4o`  
**Output**: `output/hazardous_science_dataset.jsonl` (29,319 questions)

Two generation tracks:

### Track 1 — Substance-Driven (Method 1)
**Config**: `pipeline/config.py` → `SUBJECT_SUBSTANCE_MAP`  
**Logic**: `pipeline/method1.py`  
**Applicable subjects** (7): Chemistry, Biology, Physics, Pharmacology, Medicine, Environmental Science, Agriculture & Food Science

Pipeline:
1. **Entity Profiling** — LLM characterizes each substance's properties, lifecycle stages, and technical bottlenecks
2. **Combinatorial Generation** — Substance × lifecycle stage × technical bottleneck × sub-discipline → question prompts
3. **Question Refinement** — LLM generates detailed, contextual questions

### Track 2 — Scenario-Driven (Method 2)
**Config**: `pipeline/config.py` → `SCENARIO_SUBJECTS`  
**Logic**: `pipeline/method2.py`  
**Applicable subjects** (5): Computer Science, Psychology, Sociology, Economics, Law

Three prompt templates:
- **Template A** (CS, Economics, Law): Scenario → bottleneck → technical question
- **Template B** (Psychology, Sociology): Scenario → cover story → manipulation question
- **Template C**: General scenario-based question

Each template generates questions by combining scenarios × sub-disciplines × verbs × bottlenecks.

### Shared Components
- `pipeline/api_client.py` — Async OpenAI client with semaphore concurrency control, retry, JSON parsing
- `pipeline/prompts.py` — All prompt templates (English)
- `pipeline/config.py` — Subject mappings, API config, lifecycle stages, verb matrices
- `output/refused.json` — Substances/scenarios where LLM refused to generate (687 entries)
- `output/entity_profiles.jsonl` — LLM-generated substance profiles for Track 1

---

## 3. Harmfulness Evaluation

**Script**: `run_evaluate.py`  
**Model**: `gpt-5`  
**Input**: `output/hazardous_science_dataset.jsonl` (29,319)  
**Outputs**:
- `output/evaluated_all.jsonl` (26,386) — all questions with `is_harmful` boolean + `reasoning`
- `output/harmful_questions.jsonl` (25,378) — subset where `is_harmful = true`
- `output/eval_refused.jsonl` (2,928) — questions GPT-5 refused to evaluate due to safety policies

Evaluation prompt criteria:
1. **Evasion & Concealment** — bypassing security/detection mechanisms
2. **Weaponization & Enhancement** — increasing destructive power, persistence, transmission
3. **Malicious Optimization** — optimizing processes with destructive consequences

---


## 4. Benign Question Generation

**Script**: `run_benign_pipeline.py`  
**Model**: `gpt-5`  
**Config**: `pipeline/benign_config.py`, `pipeline/benign_prompts.py`  
**Output**: `output/benign_science_dataset.jsonl` (6,030 questions)

For substance-related subjects: defense/mitigation perspective (e.g., cyanide antidote, anthrax prevention)  
For scenario-driven subjects: constructive scientific perspective  
Proportionally distributed across 12 subjects (~500 each).

---

### Pipeline module (`pipeline/`)
| File | Purpose |
|------|---------|
| `config.py` | Subject mappings, API settings, lifecycle stages |
| `api_client.py` | Async OpenAI client with retry + concurrency |
| `prompts.py` | Dangerous question generation prompts |
| `method1.py` | Track 1: substance-driven generation |
| `method2.py` | Track 2: scenario-driven generation |
| `benign_config.py` | Benign question distribution & scenarios |
| `benign_prompts.py` | Benign question prompt templates |
| `utils.py` | Shared utilities |


## 5. How to Run


### Full pipeline sequence:
```bash
# 1. Extract hazardous substances
python extract_hazardous_substances.py

# 2. Generate dangerous questions (~30k, gpt-4o)
python run_pipeline.py

# 3. Harmfulness evaluation (gpt-5)
python run_evaluate.py

# 4. Generate benign questions (~6k, gpt-5)
python run_benign_pipeline.py

All scripts support `--limit N` for small-scale testing and checkpoint-based resumption.
