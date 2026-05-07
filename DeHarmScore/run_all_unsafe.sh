#!/bin/bash
# Run evaluation pipeline for all 22 unsafe models

# Use conda activate instead of source activate
eval "$(conda shell.bash hook)"
conda activate autodanturbo
proxy_on

BASE_DIR="final_output/unsafe/by_model"
PROGRESS_FILE="eval_progress.log"
PREVIEW_FILE="vllm_judge_preview.jsonl"
MATCHER_RAW_PREVIEW_FILE="vllm_matcher_raw_preview.jsonl"
export MATCHER_RAW_PREVIEW_FILE
export MATCHER_RAW_PREVIEW_LIMIT=3

echo "Starting evaluation pipeline for all models in $BASE_DIR..." > "$PROGRESS_FILE"
echo "==================================================================" >> "$PROGRESS_FILE"
rm -f "$PREVIEW_FILE"
rm -f "$MATCHER_RAW_PREVIEW_FILE"

# Count total models
TOTAL_MODELS=$(find "$BASE_DIR" -name "responses.jsonl" | wc -l)
CURRENT_MODEL=0

echo "Found $TOTAL_MODELS models to evaluate." | tee -a "$PROGRESS_FILE"

# Find all responses.jsonl files in the subdirectories
find "$BASE_DIR" -name "responses.jsonl" | while read -r jsonl_file; do
    ((CURRENT_MODEL++))
    model_name=$(basename $(dirname "$jsonl_file"))
    
    echo "" | tee -a "$PROGRESS_FILE"
    echo "==================================================================" | tee -a "$PROGRESS_FILE"
    echo "[$CURRENT_MODEL/$TOTAL_MODELS] Evaluating model: $model_name" | tee -a "$PROGRESS_FILE"
    echo "File: $jsonl_file" | tee -a "$PROGRESS_FILE"
    
    # Run the evaluation script
    python run_unsafe_eval.py "$jsonl_file" --workers 24 --progress-file "$PROGRESS_FILE" --preview-file "$PREVIEW_FILE" --preview-limit 3
    
    # Check if the command was successful
    if [ $? -eq 0 ]; then
        echo "Successfully evaluated $model_name" | tee -a "$PROGRESS_FILE"
    else
        echo "Error evaluating $model_name" | tee -a "$PROGRESS_FILE"
    fi
done

echo "" | tee -a "$PROGRESS_FILE"
echo "==================================================================" | tee -a "$PROGRESS_FILE"
echo "All evaluations completed!" | tee -a "$PROGRESS_FILE"
