"""Measure rules, the full system, or a plain single-LLM baseline on held-out rows."""
import argparse
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "data"


def _rules_only(text: str) -> str:
    from src.policy import calculate_decision
    from src.red_flags import detect_red_flags

    decision = calculate_decision(detect_red_flags(text))
    return {"High Risk": "fraudulent", "Low Risk": "legitimate"}.get(decision.category, "uncertain")


def _run(mode: str, text: str) -> tuple[str, float, dict[str, int]]:
    started = time.perf_counter()
    if mode == "rules":
        label = _rules_only(text)
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
    elif mode == "system":
        from src.pipeline import analyze_posting
        result = analyze_posting(text)
        label = {"High Risk": "fraudulent", "Low Risk": "legitimate"}.get(result.decision.category, "uncertain")
        usage = result.token_usage
    else:
        from dotenv import load_dotenv
        load_dotenv()
        from src.agent_team import classify_single_llm_baseline
        from src.observability import set_current_run_id, usage_summary
        set_current_run_id(str(uuid4()))
        result = classify_single_llm_baseline(text)
        label = result.label
        usage = usage_summary()
    return label, time.perf_counter() - started, usage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("rules", "system", "single-llm"), default="rules")
    parser.add_argument("--limit", type=int, default=0, help="Random sample size; 0 means use all held-out rows")
    args = parser.parse_args()

    source = DATA_DIR / "test_postings.csv"
    if not source.exists():
        raise SystemExit("Missing data/test_postings.csv. Build the train-only index/splits first.")
    frame = pd.read_csv(source).fillna("")
    if args.limit > 0 and args.limit < len(frame):
        frame = frame.sample(n=args.limit, random_state=42).reset_index(drop=True)

    truth: list[str] = []
    predicted: list[str] = []
    durations: list[float] = []
    token_totals = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
    for index, row in frame.iterrows():
        text = str(row.get("_text", "")).strip()
        if len(text) < 30:
            continue
        actual = "fraudulent" if str(row.get("_label", "0")).strip().lower() in {"1", "true", "fraudulent"} else "legitimate"
        try:
            guess, elapsed, usage = _run(args.mode, text)
        except Exception as error:
            raise SystemExit(f"Row {index} failed ({type(error).__name__}). No partial metrics were saved.") from error
        truth.append(actual)
        predicted.append(guess)
        durations.append(elapsed)
        for key in token_totals:
            token_totals[key] += int(usage.get(key, 0))
        if (index + 1) % 25 == 0:
            print(f"Processed {index + 1}/{len(frame)} rows")

    if not truth:
        raise SystemExit("No usable held-out postings were found.")

    labels = ["legitimate", "fraudulent"]
    binary_predictions = ["fraudulent" if label == "fraudulent" else "legitimate" for label in predicted]
    tn, fp, fn, tp = confusion_matrix(truth, binary_predictions, labels=labels).ravel()
    report = {
        "mode": args.mode,
        "rows": len(truth),
        "uncertain_or_abstained": sum(label == "uncertain" for label in predicted),
        "positive_class": "fraudulent",
        "precision": precision_score(truth, binary_predictions, pos_label="fraudulent", zero_division=0),
        "recall": recall_score(truth, binary_predictions, pos_label="fraudulent", zero_division=0),
        "f1": f1_score(truth, binary_predictions, pos_label="fraudulent", zero_division=0),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_positives": int(tp),
        "true_negatives": int(tn),
        "mean_seconds_per_posting": sum(durations) / len(durations),
        "total_seconds": sum(durations),
        "recorded_token_usage": token_totals,
        "interpretation": "High Risk is counted as a fraud prediction; Needs Verification is treated as not declaring fraud. Review this conservative metric choice when reporting results.",
    }
    output = DATA_DIR / f"evaluation_{args.mode}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame({"actual": truth, "predicted": predicted}).to_csv(
        DATA_DIR / f"evaluation_{args.mode}_rows.csv", index=False
    )
    print(json.dumps(report, indent=2))
    print(f"Saved report: {output}")


if __name__ == "__main__":
    main()
