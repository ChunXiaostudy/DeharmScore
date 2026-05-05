# Scientific Harmfulness Evaluation and Dataset Construction

The project is divided into two main sub-components, each contained within its own directory with detailed documentation.

## Repository Structure

### 1. [DeHarmScore](./DeHarmScore/)
**Agent-as-a-Judge Framework for Scientific Harmfulness Evaluation**

This directory contains the core evaluation framework. It implements an "Agent-as-a-Judge" methodology to assess the harmfulness of model responses to potentially dangerous scientific queries using a dual-grading scale:
- **E (Executability)**: Measures how actionable the response is.
- **N (Net-New Risk)**: Measures the novelty and risk of the provided information.

Please navigate to the `DeHarmScore` folder and read its `README.md` for installation, architecture, and usage details.

### 2. [SciHazardBench-pipeline](./SciHazardBench-pipeline/)
**Data Construction & Harmfulness Classification Pipeline**

This directory contains the pipeline used to construct a multi-disciplinary dataset of hazardous scientific questions. It covers 12 academic disciplines and handles:
- Hazardous substance extraction
- Dangerous and benign question generation
- Harmfulness evaluation and L1-L5 risk classification
- Question conversion (repackaging)

Please navigate to the `SciHazardBench-pipeline` folder and read its `README.md` for detailed instructions on running the data generation and classification scripts.

## Getting Started

To explore the code, please enter the respective subdirectories:

```bash
# For the evaluation framework
cd DeHarmScore

# For the data construction pipeline
cd SciHazardBench-pipeline
```

Each subdirectory contains its own `requirements.txt` or environment setup instructions.
