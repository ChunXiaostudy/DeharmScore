"""Run the Agent-as-a-Judge (v2) pipeline on the PhD-annotated samples.

Inputs:  final/*.en_with_labels_annotated.jsonl (fields: question_en, response_en, final_E, final_N)
Outputs: output/agent_judge_v2/<subject>.jsonl (one line per sample)
Reports: Exact% / ±1% / MAE / signed-bias / QWK per dimension, plus a
         side-by-side comparison against direct-LLM baseline jsonl files
         (if present under output/direct_judge/).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from core_judge.pipeline import JudgePipeline
from core_judge.schemas import EvalInput
from core_judge.utils import load_config

BASE_DIR = Path(__file__).resolve().parent
FINAL_DIR = BASE_DIR / "final_corrected"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output" / "agent_judge_v2"
DEFAULT_CONFIG = BASE_DIR / "core_judge" / "config.yaml"

SUBJECT_FILES = {
    "biology": "biology.en_with_labels_annotated.jsonl",
    "chemistry": "chemistry.en_with_labels_annotated.jsonl",
    "computer": "computer.en_with_labels_annotated.jsonl",
    "other": "other.en_with_labels_annotated.jsonl",
}

E_ORDER = ("E1", "E2", "E3", "E4")
N_ORDER = ("N1", "N2", "N3", "N4")


# ----------------------------------------------------------------- metrics


def compute_metrics(pairs: list[tuple[str, str]], order: tuple[str, ...]) -> dict:
    if not pairs:
        return {"n": 0, "exact": 0.0, "off_by_one": 0.0, "mae": 0.0, "bias": 0.0, "qwk": 0.0}
    index = {label: idx for idx, label in enumerate(order)}
    exact = 0
    off1 = 0
    diffs: list[int] = []
    signed: list[int] = []
    for ref, pred in pairs:
        if ref not in index or pred not in index:
            continue
        d = index[pred] - index[ref]
        diffs.append(abs(d))
        signed.append(d)
        if d == 0:
            exact += 1
        if abs(d) <= 1:
            off1 += 1
    n = len(diffs)
    if n == 0:
        return {"n": 0, "exact": 0.0, "off_by_one": 0.0, "mae": 0.0, "bias": 0.0, "qwk": 0.0}
    return {
        "n": n,
        "exact": exact / n,
        "off_by_one": off1 / n,
        "mae": sum(diffs) / n,
        "bias": sum(signed) / n,
        "qwk": _quadratic_weighted_kappa(pairs, order),
    }


def _quadratic_weighted_kappa(pairs: list[tuple[str, str]], order: tuple[str, ...]) -> float:
    index = {label: idx for idx, label in enumerate(order)}
    k = len(order)
    obs = [[0] * k for _ in range(k)]
    row = [0] * k
    col = [0] * k
    n = 0
    for ref, pred in pairs:
        if ref not in index or pred not in index:
            continue
        r = index[ref]
        c = index[pred]
        obs[r][c] += 1
        row[r] += 1
        col[c] += 1
        n += 1
    if n == 0:
        return 0.0
    num = 0.0
    den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2 if k > 1 else 1)
            exp = row[i] * col[j] / n
            num += w * obs[i][j]
            den += w * exp
    if den == 0:
        return 1.0
    return 1.0 - num / den


def fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def fmt_num(x: float) -> str:
    return f"{x:+.3f}"


# ----------------------------------------------------------------- IO


def load_samples(subjects: list[str]) -> list[dict]:
    rows: list[dict] = []
    for subject in subjects:
        fname = SUBJECT_FILES[subject]
        path = FINAL_DIR / fname
        if not path.exists():
            print(f"[warn] missing {path}", file=sys.stderr)
            continue
        for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            d = json.loads(line)
            question = d.get("question_en") or d.get("question") or ""
            response = d.get("response_en") or d.get("response") or ""
            if not question or not response:
                continue
            rows.append(
                {
                    "subject": subject,
                    "idx": d.get("idx", idx),
                    "question": question,
                    "response": response,
                    "final_E": d.get("final_E"),
                    "final_N": d.get("final_N"),
                }
            )
    return rows


def load_done_keys(output_dir: Path) -> dict[str, set]:
    done: dict[str, set] = {}
    if not output_dir.exists():
        return done
    for path in output_dir.glob("*.jsonl"):
        keys: set = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    d = json.loads(line)
                    keys.add(d.get("idx"))
                except Exception:
                    continue
        done[path.stem] = keys
    return done


def run_one(pipeline: JudgePipeline, row: dict, lock: Lock) -> dict:
    eval_input = EvalInput(
        question=str(row["question"]).strip(),
        model_response=str(row["response"]).strip(),
        subject=str(row["subject"]),
    )
    out = pipeline.run(
        eval_input,
        progress_prefix=f"[{row['subject']}/{row['idx']}]",
        output_lock=lock,
    )
    return {
        "subject": row["subject"],
        "idx": row["idx"],
        "question": row["question"][:120],
        "human_E": row["final_E"],
        "human_N": row["final_N"],
        "rule_E": out.rule_executability,
        "judge_E": out.overall_executability,
        "judge_N": out.overall_net_new_risk,
        "judge_E_reason": out.overall_reason,
        "judge_N_reason": out.overall_net_new_reason,
        "checklist_cache_hit": out.checklist_cache_hit,
        "net_new_hard_ratio": out.net_new_stats.hard_ratio,
        "total_claims": out.net_new_stats.total_claims,
        "dimension_breakdown": [t.to_dict() for t in out.coverage_stats.dimension_breakdown],
        "timings": out.timings,
    }


def run_eval(
    config_path: Path,
    output_dir: Path,
    subjects: list[str],
    *,
    limit: int = 0,
    workers: int = 1,
    resume: bool = True,
) -> None:
    config = load_config(config_path)
    pipeline = JudgePipeline.from_app_config(config, show_progress=True, show_timing=True)
    rows = load_samples(subjects)
    if limit > 0:
        rows = rows[:limit]
    if not rows:
        print("[eval] no samples to run", file=sys.stderr)
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    done_keys = load_done_keys(output_dir) if resume else {}

    by_subject: dict[str, list[dict]] = {}
    for row in rows:
        by_subject.setdefault(row["subject"], []).append(row)

    lock = Lock()
    total_done = 0
    total = sum(len(v) for v in by_subject.values())
    t0 = time.perf_counter()
    for subject, samples in by_subject.items():
        out_path = output_dir / f"{subject}.jsonl"
        existing = done_keys.get(subject, set())
        pending = [row for row in samples if row["idx"] not in existing]
        skipped = len(samples) - len(pending)
        if skipped:
            print(f"[{subject}] skipping {skipped} already-done samples", file=sys.stderr)
        if not pending:
            continue
        with out_path.open("a", encoding="utf-8") as fh:
            if workers <= 1:
                for row in pending:
                    _exec_and_write(pipeline, row, fh, lock)
                    total_done += 1
                    _log_progress(total_done, total, t0)
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(run_one, pipeline, row, lock): row for row in pending}
                    for future in as_completed(futures):
                        row = futures[future]
                        try:
                            record = future.result()
                        except Exception as exc:
                            record = {
                                "subject": row["subject"],
                                "idx": row["idx"],
                                "error": f"{type(exc).__name__}: {exc}",
                                "traceback": traceback.format_exc(limit=5),
                            }
                        with lock:
                            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                            fh.flush()
                        total_done += 1
                        _log_progress(total_done, total, t0)
    report_results(output_dir, subjects)


def _exec_and_write(pipeline: JudgePipeline, row: dict, fh, lock: Lock) -> None:
    try:
        record = run_one(pipeline, row, lock)
    except Exception as exc:
        record = {
            "subject": row["subject"],
            "idx": row["idx"],
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=5),
        }
    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    fh.flush()
    tag = "OK" if "error" not in record else "ERR"
    if tag == "OK":
        print(
            f"  [{row['subject']}/{row['idx']}] {tag}  "
            f"human E={row['final_E']} N={row['final_N']}  "
            f"judge E={record.get('judge_E')} N={record.get('judge_N')}  "
            f"rule_E={record.get('rule_E')}  claims={record.get('total_claims')} "
            f"hard_ratio={record.get('net_new_hard_ratio')}",
            file=sys.stderr, flush=True,
        )
    else:
        print(f"  [{row['subject']}/{row['idx']}] {tag}: {record.get('error')}",
              file=sys.stderr, flush=True)


def _log_progress(done: int, total: int, t0: float) -> None:
    elapsed = time.perf_counter() - t0
    rate = done / elapsed if elapsed > 0 else 0.0
    eta = (total - done) / rate if rate > 0 else float("inf")
    bar_len = 20
    filled = int(bar_len * done / total) if total > 0 else bar_len
    bar = "█" * filled + "░" * (bar_len - filled)
    eta_str = f"{eta:.0f}s" if eta < 999 else ">999s"
    print(f"  [progress] {bar} {done}/{total}  elapsed={elapsed:.0f}s  eta={eta_str}",
          file=sys.stderr, flush=True)


# ----------------------------------------------------------------- reporting


def report_results(output_dir: Path, subjects: list[str]) -> None:
    print("\n" + "=" * 78)
    print(" Agent-as-a-Judge v2 (checklist + claim-check) vs human annotations")
    print("=" * 78)
    all_e: list[tuple[str, str]] = []
    all_n: list[tuple[str, str]] = []
    rule_e: list[tuple[str, str]] = []
    by_subject_pairs: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for subject in subjects:
        path = output_dir / f"{subject}.jsonl"
        if not path.exists():
            continue
        subj_e: list[tuple[str, str]] = []
        subj_n: list[tuple[str, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if "error" in d:
                continue
            he = d.get("human_E")
            hn = d.get("human_N")
            je = d.get("judge_E")
            jn = d.get("judge_N")
            re_ = d.get("rule_E")
            if he and je:
                subj_e.append((he, je))
                all_e.append((he, je))
            if hn and jn:
                subj_n.append((hn, jn))
                all_n.append((hn, jn))
            if he and re_:
                rule_e.append((he, re_))
        by_subject_pairs[subject] = {"E": subj_e, "N": subj_n}

    header = f"{'split':<12} {'dim':>3} {'n':>4} {'Exact':>7} {'±1':>7} {'MAE':>6} {'Bias':>7} {'QWK':>6}"
    print(header)
    print("-" * len(header))
    for subject, d in by_subject_pairs.items():
        for dim, pairs, order in (("E", d["E"], E_ORDER), ("N", d["N"], N_ORDER)):
            m = compute_metrics(pairs, order)
            print(f"{subject:<12} {dim:>3} {m['n']:>4} "
                  f"{fmt_pct(m['exact']):>7} {fmt_pct(m['off_by_one']):>7} "
                  f"{m['mae']:>6.3f} {fmt_num(m['bias']):>7} {m['qwk']:>6.3f}")
    # Overall
    print("-" * len(header))
    for dim, pairs, order, label in (
        ("E", all_e, E_ORDER, "ALL (reviewed)"),
        ("E", rule_e, E_ORDER, "ALL (rule only)"),
        ("N", all_n, N_ORDER, "ALL"),
    ):
        m = compute_metrics(pairs, order)
        print(f"{label:<12} {dim:>3} {m['n']:>4} "
              f"{fmt_pct(m['exact']):>7} {fmt_pct(m['off_by_one']):>7} "
              f"{m['mae']:>6.3f} {fmt_num(m['bias']):>7} {m['qwk']:>6.3f}")

    # Direct-LLM baseline comparison (if present)
    baseline_dir = BASE_DIR / "output" / "direct_judge"
    if baseline_dir.exists():
        print("\n--- Direct-LLM baselines (for reference) ---")
        for path in sorted(baseline_dir.glob("*.jsonl")):
            recs = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    recs.append(json.loads(line))
            for dim, hk, jk, order in (
                ("E", "human_executability", "judge_executability", E_ORDER),
                ("N", "human_net_new_risk", "judge_net_new_risk", N_ORDER),
            ):
                pairs = [(r[hk], r[jk]) for r in recs if r.get(hk) and r.get(jk)]
                m = compute_metrics(pairs, order)
                label = f"direct_{path.stem}"[:12]
                print(f"{label:<12} {dim:>3} {m['n']:>4} "
                      f"{fmt_pct(m['exact']):>7} {fmt_pct(m['off_by_one']):>7} "
                      f"{m['mae']:>6.3f} {fmt_num(m['bias']):>7} {m['qwk']:>6.3f}")
    print("=" * 78)


# ----------------------------------------------------------------- confusion matrix


def print_confusion(output_dir: Path, subjects: list[str]) -> None:
    for dim, order in (("E", E_ORDER), ("N", N_ORDER)):
        mat = {(r, c): 0 for r in order for c in order}
        for subject in subjects:
            path = output_dir / f"{subject}.jsonl"
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                if "error" in d:
                    continue
                h = d.get(f"human_{dim}")
                j = d.get(f"judge_{dim}")
                if h in order and j in order:
                    mat[(h, j)] += 1
        print(f"\n=== Confusion matrix for {dim} (rows=human, cols=judge) ===")
        print("       " + " ".join(f"{c:>5}" for c in order))
        for r in order:
            row_vals = [mat[(r, c)] for c in order]
            print(f"  {r:<4} " + " ".join(f"{v:>5}" for v in row_vals))


# ----------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent-as-a-Judge v2 on final/*.jsonl")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to core_judge config.yaml")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--subject", default="all",
                        choices=["all", "biology", "chemistry", "computer", "other"])
    parser.add_argument("--limit", type=int, default=0, help="Limit number of samples (0 = all)")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--compare-only", action="store_true",
                        help="Skip running; just report metrics from existing jsonl files.")
    parser.add_argument("--confusion", action="store_true",
                        help="Also print confusion matrices.")
    args = parser.parse_args()

    subjects = list(SUBJECT_FILES.keys()) if args.subject == "all" else [args.subject]
    output_dir = Path(args.output_dir)

    if args.compare_only:
        report_results(output_dir, subjects)
    else:
        run_eval(
            config_path=Path(args.config),
            output_dir=output_dir,
            subjects=subjects,
            limit=args.limit,
            workers=args.workers,
            resume=not args.no_resume,
        )

    if args.confusion:
        print_confusion(output_dir, subjects)

    return 0


if __name__ == "__main__":
    sys.exit(main())
