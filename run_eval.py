"""
CLI entry point to run CARA evaluation.

Usage:
    # No API key required (deterministic direct runner)
    python run_eval.py --provider direct
    python run_eval.py --provider direct --runs 5          # 5 runs, reports mean±std
    python run_eval.py --provider direct --cases case_01   # specific cases
    python run_eval.py --provider direct --output results.json

    # Local Ollama model (no API key required)
    python run_eval.py --provider ollama --runs 3

    # Claude via Anthropic API
    export ANTHROPIC_API_KEY=<your-key>
    python run_eval.py --runs 3
"""

import argparse
import json
import math
import os
import sys
from typing import List

from eval.runner import EvalRunner
from eval.metrics import print_results_table


def _make_runner(args):
    if args.provider == "direct":
        from agent.direct_agent import DirectCARAAgent
        from eval.runner import EvalRunner as _EvalRunner
        agent = DirectCARAAgent()
        runner = _EvalRunner.__new__(_EvalRunner)
        runner.agent = agent
        return runner
    elif args.provider == "ollama":
        from agent.ollama_agent import OllamaCARAAgent
        from eval.runner import EvalRunner as _EvalRunner
        ollama_model = args.model if args.model != "claude-sonnet-4-6" else "llama3.2"
        agent = OllamaCARAAgent(base_url=args.ollama_url, model=ollama_model)
        runner = _EvalRunner.__new__(_EvalRunner)
        runner.agent = agent
        return runner
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
            sys.exit(1)
        return EvalRunner(api_key=api_key, model=args.model)


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def _print_multi_run_summary(all_results: list, runs: int) -> None:
    metrics_across_runs = {
        "pass_rate": [],
        "mean_score": [],
        "f1": [],
        "plan_completeness": [],
        "expand_contract": [],
        "rollback_rate": [],
        "adapter_rate": [],
    }
    for r in all_results:
        m = r["metrics"]
        metrics_across_runs["pass_rate"].append(r["pass_rate"])
        metrics_across_runs["mean_score"].append(r["mean_score"])
        metrics_across_runs["f1"].append(m["breaking_change_detection"]["f1"])
        metrics_across_runs["plan_completeness"].append(m["plan_quality"]["mean_plan_completeness"])
        metrics_across_runs["expand_contract"].append(m["plan_quality"]["expand_contract_compliance_rate"])
        metrics_across_runs["rollback_rate"].append(m["plan_quality"]["rollback_presence_rate"])
        metrics_across_runs["adapter_rate"].append(m["adapter_generation_rate"])

    print(f"\n{'='*60}")
    print(f"Multi-Run Summary ({runs} runs, {all_results[0]['total_cases']} cases each)")
    print(f"{'='*60}")
    print(f"{'Metric':<30} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8}")
    print(f"{'-'*60}")
    labels = [
        ("Overall Pass Rate",      "pass_rate"),
        ("Mean Score",             "mean_score"),
        ("Breaking Change F1",     "f1"),
        ("Plan Completeness",      "plan_completeness"),
        ("Expand-Contract Compliance", "expand_contract"),
        ("Rollback Presence Rate", "rollback_rate"),
        ("Adapter Generation Rate","adapter_rate"),
    ]
    for label, key in labels:
        vals = metrics_across_runs[key]
        print(f"{label:<30} {_mean(vals):>8.3f} {_std(vals):>8.4f} {min(vals):>8.3f} {max(vals):>8.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CARA evaluation benchmark")
    parser.add_argument("--cases", nargs="+", help="Specific case IDs to run")
    parser.add_argument("--language", default="python", choices=["python", "java", "kotlin", "typescript"])
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Model to use")
    parser.add_argument("--provider", default="anthropic", choices=["anthropic", "ollama", "direct"],
                        help="LLM provider: anthropic (default), ollama (local), or direct (no LLM)")
    parser.add_argument("--ollama-url", default="http://localhost:11434/v1",
                        help="Ollama base URL (default: http://localhost:11434/v1)")
    parser.add_argument("--runs", type=int, default=1,
                        help="Number of evaluation runs (reports mean±std across runs)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-case output")
    args = parser.parse_args()

    all_results = []

    for run_idx in range(args.runs):
        if args.runs > 1:
            print(f"\n{'='*40}")
            print(f"Run {run_idx + 1}/{args.runs}")
            print(f"{'='*40}")

        runner = _make_runner(args)
        result = runner.run_all(
            case_ids=args.cases,
            language=args.language,
            verbose=not args.quiet,
        )

        if args.runs == 1:
            print_results_table(result)
        else:
            r = result.to_dict()
            m = r["metrics"]
            print(f"  Pass rate={r['pass_rate']:.3f}  F1={m['breaking_change_detection']['f1']:.3f}  "
                  f"Expand-Contract={m['plan_quality']['expand_contract_compliance_rate']:.3f}")

        all_results.append(result.to_dict())

    if args.runs > 1:
        _print_multi_run_summary(all_results, args.runs)

    if args.output:
        output_data = all_results[0] if args.runs == 1 else {
            "runs": args.runs,
            "summary": {
                k: {"mean": _mean([r["metrics"]["breaking_change_detection"]["f1"] for r in all_results])}
                for k in ["f1"]
            },
            "all_runs": all_results,
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
