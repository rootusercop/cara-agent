"""
CLI entry point to run CARA evaluation.

Usage:
    python run_eval.py                          # run all cases
    python run_eval.py --cases case_01 case_03  # run specific cases
    python run_eval.py --language kotlin        # generate Kotlin adapters
    python run_eval.py --output results.json    # save results to file
"""

import argparse
import json
import os
import sys

from eval.runner import EvalRunner
from eval.metrics import print_results_table


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CARA evaluation benchmark")
    parser.add_argument("--cases", nargs="+", help="Specific case IDs to run")
    parser.add_argument("--language", default="python", choices=["python", "java", "kotlin", "typescript"])
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Claude model to use")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-case output")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    runner = EvalRunner(api_key=api_key, model=args.model)
    result = runner.run_all(
        case_ids=args.cases,
        language=args.language,
        verbose=not args.quiet,
    )

    print_results_table(result)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
