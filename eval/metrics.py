"""
Evaluation metrics for CARA.

Computes precision, recall, F1, and aggregate scores
across all evaluation cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eval.runner import CaseResult


@dataclass
class EvalMetrics:
    # Breaking change detection
    breaking_precision: float
    breaking_recall: float
    breaking_f1: float

    # Plan quality
    mean_plan_completeness: float
    expand_contract_compliance_rate: float
    rollback_presence_rate: float

    # Adapter generation
    adapter_generation_rate: float

    # Overall
    overall_pass_rate: float
    mean_score: float

    # Per-category breakdown
    by_category: dict[str, dict]

    def to_dict(self) -> dict:
        return {
            "breaking_change_detection": {
                "precision": round(self.breaking_precision, 3),
                "recall": round(self.breaking_recall, 3),
                "f1": round(self.breaking_f1, 3),
            },
            "plan_quality": {
                "mean_plan_completeness": round(self.mean_plan_completeness, 3),
                "expand_contract_compliance_rate": round(self.expand_contract_compliance_rate, 3),
                "rollback_presence_rate": round(self.rollback_presence_rate, 3),
            },
            "adapter_generation_rate": round(self.adapter_generation_rate, 3),
            "overall": {
                "pass_rate": round(self.overall_pass_rate, 3),
                "mean_score": round(self.mean_score, 3),
            },
            "by_category": self.by_category,
        }

    def to_latex_table(self) -> str:
        """Render key metrics as a LaTeX table for the paper."""
        return r"""
\begin{table}[h]
\centering
\caption{CARA Evaluation Results on 15-Case Benchmark}
\label{tab:results}
\begin{tabular}{lcc}
\hline
\textbf{Metric} & \textbf{Value} & \textbf{Threshold} \\
\hline
Breaking Change Precision & """ + f"{self.breaking_precision:.2f}" + r""" & $\geq$0.80 \\
Breaking Change Recall    & """ + f"{self.breaking_recall:.2f}" + r""" & $\geq$0.80 \\
Breaking Change F1        & """ + f"{self.breaking_f1:.2f}" + r""" & $\geq$0.80 \\
\hline
Plan Completeness (mean)  & """ + f"{self.mean_plan_completeness:.2f}" + r""" & $\geq$0.70 \\
Expand-Contract Compliance & """ + f"{self.expand_contract_compliance_rate:.2f}" + r""" & $\geq$0.90 \\
Rollback Presence Rate    & """ + f"{self.rollback_presence_rate:.2f}" + r""" & $\geq$0.95 \\
\hline
Adapter Generation Rate   & """ + f"{self.adapter_generation_rate:.2f}" + r""" & $\geq$0.80 \\
Overall Pass Rate         & """ + f"{self.overall_pass_rate:.2f}" + r""" & $\geq$0.70 \\
\hline
\end{tabular}
\end{table}
"""


def compute_metrics(case_results: list["CaseResult"]) -> dict:
    """
    Compute aggregate metrics across all case results.

    Returns:
        A dict (also available as EvalMetrics) with precision, recall, F1,
        plan quality, and per-category breakdown.
    """
    if not case_results:
        return {}

    # Breaking change detection: compare predicted vs. expected counts
    true_positives = 0
    false_positives = 0
    false_negatives = 0

    for r in case_results:
        expected_breaking = r.ground_truth.get("expected", {}).get("breaking_change_count", 0)
        detected_breaking = r.report.get("breaking_count", 0)
        tp = min(detected_breaking, expected_breaking)
        fp = max(0, detected_breaking - expected_breaking)
        fn = max(0, expected_breaking - detected_breaking)
        true_positives += tp
        false_positives += fp
        false_negatives += fn

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # Plan quality
    plan_scores = [
        r.report.get("validation", {}).get("completeness_score", 0.0)
        for r in case_results
    ]
    mean_plan_completeness = sum(plan_scores) / len(plan_scores) if plan_scores else 0.0

    cases_needing_expand = [r for r in case_results if r.ground_truth.get("expected", {}).get("plan_must_include_expand", False)]
    expand_compliance = sum(
        1 for r in cases_needing_expand
        if any(s.get("title", "").startswith("[EXPAND]") for s in r.report.get("plan", {}).get("steps", []))
    ) / len(cases_needing_expand) if cases_needing_expand else 1.0

    rollback_cases = [r for r in case_results if r.ground_truth.get("expected", {}).get("plan_must_include_rollback", True)]
    rollback_rate = sum(
        1 for r in rollback_cases
        if any(s.get("step_type") == "ROLLBACK_CHECKPOINT" for s in r.report.get("plan", {}).get("steps", []))
    ) / len(rollback_cases) if rollback_cases else 1.0

    # Adapter generation
    adapter_cases = [r for r in case_results if r.ground_truth.get("expected", {}).get("requires_adapter", False)]
    adapter_rate = sum(
        1 for r in adapter_cases
        if len(r.report.get("adapter_codes", [])) > 0
    ) / len(adapter_cases) if adapter_cases else 1.0

    # Per-category breakdown
    categories: dict[str, list] = {}
    for r in case_results:
        cat = r.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)

    by_category = {
        cat: {
            "count": len(cases),
            "passed": sum(1 for r in cases if r.passed),
            "mean_score": round(sum(r.score for r in cases) / len(cases), 3),
        }
        for cat, cases in categories.items()
    }

    overall_pass_rate = sum(1 for r in case_results if r.passed) / len(case_results)
    mean_score = sum(r.score for r in case_results) / len(case_results)

    metrics = EvalMetrics(
        breaking_precision=precision,
        breaking_recall=recall,
        breaking_f1=f1,
        mean_plan_completeness=mean_plan_completeness,
        expand_contract_compliance_rate=expand_compliance,
        rollback_presence_rate=rollback_rate,
        adapter_generation_rate=adapter_rate,
        overall_pass_rate=overall_pass_rate,
        mean_score=mean_score,
        by_category=by_category,
    )
    return metrics.to_dict()


def print_results_table(eval_result: "EvalResult") -> None:
    """Print a human-readable summary table of eval results."""
    from rich.table import Table
    from rich.console import Console

    console = Console()
    table = Table(title="CARA Evaluation Results", show_lines=True)
    table.add_column("Case ID", style="bold")
    table.add_column("Title", max_width=40)
    table.add_column("Category")
    table.add_column("Score", justify="right")
    table.add_column("Breaking (exp/got)", justify="center")
    table.add_column("Steps", justify="right")
    table.add_column("Status", justify="center")

    for r in eval_result.case_results:
        status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        exp_b = r.ground_truth.get("expected", {}).get("breaking_change_count", "?")
        got_b = r.report.get("breaking_count", "?")
        table.add_row(
            r.case_id,
            r.title[:40],
            r.category,
            f"{r.score:.2f}",
            f"{exp_b}/{got_b}",
            str(r.report.get("plan", {}).get("step_count", "-")),
            status,
        )

    console.print(table)
    console.print(f"\nOverall: {eval_result.passed_cases}/{eval_result.total_cases} passed | "
                  f"Mean score: {eval_result.mean_score:.2f} | "
                  f"Pass rate: {eval_result.passed_cases/eval_result.total_cases:.0%}\n")
