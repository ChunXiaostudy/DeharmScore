#!/bin/bash
# Run evaluation pipeline for all judge models

source activate autodanturbo
proxy_on

echo "Starting evaluation pipeline..."
echo "=================================="

# Run Gemini 3.1 Pro Preview Thinking
echo ""
echo "[1/3] Running Gemini 3.1 Pro Preview Thinking..."
python run_agent_judge_eval.py \
    --config core_judge/config_gemini_3_1.yaml \
    --output-dir output/agent_judge_gemini_3_1

# Run Qwen 3.5 35B A3B
echo ""
echo "[2/3] Running Qwen 3.5 35B A3B..."
python run_agent_judge_eval.py \
    --config core_judge/config_qwen3_5.yaml \
    --output-dir output/agent_judge_qwen3_5

# Run GPT 4o Mini
echo ""
echo "[3/3] Running GPT 4o Mini..."
python run_agent_judge_eval.py \
    --config core_judge/config_gpt_4o_mini.yaml \
    --output-dir output/agent_judge_gpt_4o_mini

echo ""
echo "=================================="
echo "All evaluations completed!"
echo "Results are saved in output/ directory"
