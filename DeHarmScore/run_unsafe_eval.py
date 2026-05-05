import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from tqdm import tqdm

from core_judge.pipeline import JudgePipeline
from core_judge.schemas import EvalInput
from core_judge.utils import load_config

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "core_judge" / "config_unsafe_eval.yaml"


def run_one(pipeline: JudgePipeline, row: dict, lock: Lock) -> dict:
    eval_input = EvalInput(
        question=str(row["question"]).strip(),
        model_response=str(row["_response_text"]).strip(),
        subject=str(row.get("subject", "")),
    )
    
    # Run the pipeline
    out = pipeline.run(
        eval_input,
        progress_prefix=f"[{row.get('idx', '?')}]",
        output_lock=lock,
    )
    
    # Update the row with the results
    row["judge_E"] = out.overall_executability
    row["judge_N"] = out.overall_net_new_risk
    row["judge_E_reason"] = out.overall_reason
    row["judge_N_reason"] = out.overall_net_new_reason
    row["rule_E"] = out.rule_executability
    row["judge_model"] = getattr(pipeline.llm, "model", "")
    coverage_status_counts = {str(score): 0 for score in range(1, 6)}
    matcher_missing_count = 0
    for coverage in out.checklist_coverage:
        coverage_status_counts[str(coverage.status)] = coverage_status_counts.get(str(coverage.status), 0) + 1
        if coverage.reason == "Matcher did not return a judgement for this item.":
            matcher_missing_count += 1
    row["matcher_missing_count"] = matcher_missing_count
    row["coverage_status_counts"] = coverage_status_counts
    row.pop("judge_error", None)
    
    # Calculate final score (simplified version, adjust as needed based on your logic)
    # E1-E4 mapping to some score, N1-N4 mapping to some score
    # For now, we just mark it as evaluated
    row["final_score"] = f"{out.overall_executability}_{out.overall_net_new_risk}"
    
    return row


def evaluate_jsonl(
    config_path: Path,
    jsonl_path: Path,
    workers: int = 1,
    progress_file: Path = None,
    preview_file: Path = None,
    preview_limit: int = 3,
) -> None:
    def log_progress(msg: str):
        print(msg)
        if progress_file:
            with open(progress_file, "a", encoding="utf-8") as f:
                f.write(f"{msg}\n")

    log_progress(f"Loading config from {config_path}")
    config = load_config(config_path)
    # Turn off verbose progress/timing for individual items to keep the progress bar clean
    config.runtime.show_progress = False
    config.runtime.show_timing = False
    
    pipeline = JudgePipeline.from_app_config(config)
    
    log_progress(f"Reading {jsonl_path}")
    
    # Read all lines
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    
    # Parse and filter
    all_rows = []
    pending_indices = []
    
    for i, line in enumerate(lines):
        if not line.strip():
            all_rows.append(None)
            continue
            
        try:
            row = json.loads(line)
            all_rows.append(row)
            
            # Check if it needs judging (not yet judged: no final_score AND no judge_E)
            already_judged = row.get("judge_E") is not None or row.get("judge_N") is not None
            if row.get("need_judge") is True and row.get("final_score") is None and not already_judged:
                # Also ensure it has a response text
                if row.get("_response_text", "").strip():
                    pending_indices.append(i)
        except Exception as e:
            log_progress(f"Error parsing line {i}: {e}")
            all_rows.append(None)
            
    total_pending = len(pending_indices)
    log_progress(f"Found {total_pending} items needing evaluation out of {len(all_rows)} total items.")
    
    if total_pending == 0:
        log_progress("Nothing to do!")
        return
        
    lock = Lock()
    preview_written = 0
    if preview_file and preview_file.exists():
        preview_written = sum(1 for line in preview_file.read_text(encoding="utf-8").splitlines() if line.strip())

    def save_preview(row: dict, line_index: int):
        nonlocal preview_written
        if not preview_file or preview_written >= preview_limit:
            return
        with lock:
            if preview_written >= preview_limit:
                return
            preview_file.parent.mkdir(parents=True, exist_ok=True)
            preview_record = {
                "preview_no": preview_written + 1,
                "source_file": str(jsonl_path),
                "source_line_index": line_index,
                "idx": row.get("idx"),
                "model_under_eval": row.get("_model") or jsonl_path.parent.name,
                "judge_model": row.get("judge_model"),
                "question": row.get("question"),
                "model_response": row.get("_response_text"),
                "vllm_judge_output": {
                    "judge_E": row.get("judge_E"),
                    "judge_N": row.get("judge_N"),
                    "rule_E": row.get("rule_E"),
                    "matcher_missing_count": row.get("matcher_missing_count"),
                    "coverage_status_counts": row.get("coverage_status_counts"),
                    "judge_E_reason": row.get("judge_E_reason"),
                    "judge_N_reason": row.get("judge_N_reason"),
                    "final_score": row.get("final_score"),
                },
            }
            with open(preview_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(preview_record, ensure_ascii=False) + "\n")
            preview_written += 1
            log_progress(f"  Saved vLLM preview {preview_written}/{preview_limit}: {preview_file}")
    
    # Function to save the current state to the file
    def save_all():
        with lock:
            # Write to a temporary file first, then rename to avoid corruption
            temp_path = jsonl_path.with_suffix('.jsonl.tmp')
            with open(temp_path, "w", encoding="utf-8") as f:
                for row in all_rows:
                    if row is not None:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    else:
                        f.write("\n")
            temp_path.replace(jsonl_path)
    
    completed_count = 0
    start_time = time.time()
    
    # Process items
    with tqdm(total=total_pending, desc=f"Evaluating {jsonl_path.parent.name}") as pbar:
        if workers <= 1:
            for idx in pending_indices:
                row = all_rows[idx]
                try:
                    all_rows[idx] = run_one(pipeline, row, lock)
                except Exception as exc:
                    log_progress(f"\nError on idx {row.get('idx')}: {exc}")
                    row["judge_error"] = str(exc)
                
                # Save after each item
                save_all()
                if row.get("final_score") is not None:
                    save_preview(row, idx)
                pbar.update(1)
                completed_count += 1
                if completed_count % 10 == 0 or completed_count == total_pending:
                    elapsed = time.time() - start_time
                    rate = completed_count / elapsed if elapsed > 0 else 0
                    log_progress(f"  Progress: {completed_count}/{total_pending} ({completed_count/total_pending*100:.1f}%) - {rate:.2f} items/sec")
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                # Map future to index in all_rows
                futures = {pool.submit(run_one, pipeline, all_rows[idx], lock): idx for idx in pending_indices}
                
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        all_rows[idx] = future.result()
                    except Exception as exc:
                        row = all_rows[idx]
                        log_progress(f"\nError on idx {row.get('idx')}: {exc}")
                        row["judge_error"] = str(exc)
                        
                    # Save after each item completes
                    save_all()
                    row = all_rows[idx]
                    if row.get("final_score") is not None:
                        save_preview(row, idx)
                    pbar.update(1)
                    completed_count += 1
                    if completed_count % 10 == 0 or completed_count == total_pending:
                        elapsed = time.time() - start_time
                        rate = completed_count / elapsed if elapsed > 0 else 0
                        log_progress(f"  Progress: {completed_count}/{total_pending} ({completed_count/total_pending*100:.1f}%) - {rate:.2f} items/sec")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent-as-a-Judge on unsafe model outputs")
    parser.add_argument("jsonl_file", help="Path to the JSONL file to evaluate")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config.yaml")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--progress-file", type=str, default=None, help="File to append progress logs to")
    parser.add_argument("--preview-file", type=str, default=None, help="JSONL file to save the first few vLLM judge outputs")
    parser.add_argument("--preview-limit", type=int, default=3, help="Number of vLLM judge preview records to save")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl_file)
    if not jsonl_path.exists():
        print(f"Error: File not found: {jsonl_path}", file=sys.stderr)
        return 1

    evaluate_jsonl(
        config_path=Path(args.config),
        jsonl_path=jsonl_path,
        workers=args.workers,
        progress_file=Path(args.progress_file) if args.progress_file else None,
        preview_file=Path(args.preview_file) if args.preview_file else None,
        preview_limit=args.preview_limit,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
