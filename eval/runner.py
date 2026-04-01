"""
Evaluation runner for CARA.

Loads test cases from eval/dataset/, runs the CARA agent on each,
and compares results against ground truth.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.cara_agent import CARAAgent, MigrationReport


DATASET_DIR = Path(__file__).parent / "dataset"


@dataclass
class CaseResult:
    case_id: str
    title: str
    category: str
    ground_truth: dict
    report: dict
    passed: bool
    score: float
    errors: list[str] = field(default_factory=list)
    latency_seconds: float = 0.0
    reasoning_trace_length: int = 0

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "category": self.category,
            "passed": self.passed,
            "score": round(self.score, 3),
            "errors": self.errors,
            "latency_seconds": round(self.latency_seconds, 2),
            "reasoning_trace_length": self.reasoning_trace_length,
            "ground_truth_breaking": self.ground_truth.get("expected", {}).get("breaking_change_count", 0),
            "detected_breaking": self.report.get("breaking_count", 0),
            "plan_steps": self.report.get("plan", {}).get("step_count", 0),
            "validation_score": self.report.get("validation", {}).get("completeness_score", 0),
        }


@dataclass
class EvalResult:
    total_cases: int
    passed_cases: int
    failed_cases: int
    mean_score: float
    case_results: list[CaseResult] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "pass_rate": round(self.passed_cases / self.total_cases, 3) if self.total_cases > 0 else 0,
            "mean_score": round(self.mean_score, 3),
            "metrics": self.metrics,
            "timestamp": self.timestamp,
            "case_results": [r.to_dict() for r in self.case_results],
        }


class EvalRunner:
    """
    Runs CARA against the evaluation dataset and scores each case
    against ground truth.
    """

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6"):
        self.agent = CARAAgent(api_key=api_key, model=model)

    def run_all(
        self,
        case_ids: list[str] | None = None,
        language: str = "python",
        verbose: bool = True,
    ) -> EvalResult:
        """
        Run CARA on all (or selected) evaluation cases.

        Args:
            case_ids: Specific case IDs to run (e.g. ['case_01', 'case_03']).
                      If None, runs all cases in DATASET_DIR.
            language: Target language for adapter code generation.
            verbose: Print progress to stdout.

        Returns:
            EvalResult with per-case scores and aggregate metrics.
        """
        case_dirs = sorted(DATASET_DIR.iterdir()) if DATASET_DIR.exists() else []
        if case_ids:
            case_dirs = [d for d in case_dirs if d.name in case_ids]

        case_results: list[CaseResult] = []

        for case_dir in case_dirs:
            if not case_dir.is_dir():
                continue
            gt_path = case_dir / "ground_truth.json"
            if not gt_path.exists():
                continue

            ground_truth = json.loads(gt_path.read_text())
            case_id = ground_truth.get("case_id", case_dir.name)
            title = ground_truth.get("title", case_id)

            if verbose:
                print(f"\n[CARA EVAL] Running {case_id}: {title}")

            start = time.time()
            try:
                report = self._run_case(case_dir, ground_truth, language)
                latency = time.time() - start
                result = self._score_case(case_id, title, ground_truth, report, latency)
            except Exception as e:
                latency = time.time() - start
                result = CaseResult(
                    case_id=case_id,
                    title=title,
                    category=ground_truth.get("category", "unknown"),
                    ground_truth=ground_truth,
                    report={},
                    passed=False,
                    score=0.0,
                    errors=[f"Agent exception: {str(e)}"],
                    latency_seconds=latency,
                )

            case_results.append(result)

            if verbose:
                status = "PASS" if result.passed else "FAIL"
                print(f"  [{status}] score={result.score:.2f} latency={result.latency_seconds:.1f}s errors={result.errors}")

        from eval.metrics import compute_metrics
        metrics = compute_metrics(case_results)
        mean_score = sum(r.score for r in case_results) / len(case_results) if case_results else 0.0
        passed = sum(1 for r in case_results if r.passed)

        import datetime
        return EvalResult(
            total_cases=len(case_results),
            passed_cases=passed,
            failed_cases=len(case_results) - passed,
            mean_score=mean_score,
            case_results=case_results,
            metrics=metrics,
            timestamp=datetime.datetime.utcnow().isoformat() + "Z",
        )

    def _run_case(self, case_dir: Path, ground_truth: dict, language: str) -> dict:
        """Load case files and run the CARA agent."""
        old_schema = _read_optional(case_dir / "old_schema.sql") or _read_optional(case_dir / "old_schema.proto") or ""
        new_schema = _read_optional(case_dir / "new_schema.sql") or _read_optional(case_dir / "new_schema.proto") or ""
        schema_type = "protobuf" if (case_dir / "old_schema.proto").exists() else "sql"

        old_api = _read_optional(case_dir / "old_api.yaml") or _read_optional(case_dir / "old_api.json") or ""
        new_api = _read_optional(case_dir / "new_api.yaml") or _read_optional(case_dir / "new_api.json") or ""
        api_type = "openapi"

        task_description = ground_truth.get("description", "Analyze this schema and API change.")

        report: MigrationReport = self.agent.analyze(
            task_description=task_description,
            old_schema=old_schema,
            new_schema=new_schema,
            schema_type=schema_type,
            old_api_spec=old_api,
            new_api_spec=new_api,
            api_spec_type=api_type,
            language=language,
        )
        return report.to_dict()

    def _score_case(
        self,
        case_id: str,
        title: str,
        ground_truth: dict,
        report: dict,
        latency: float,
    ) -> CaseResult:
        """Score agent output against ground truth on multiple dimensions."""
        expected = ground_truth.get("expected", {})
        errors: list[str] = []
        checks_passed = 0
        total_checks = 0

        # Check 1: Breaking change count accuracy (within ±1 tolerance)
        total_checks += 1
        expected_breaking = expected.get("breaking_change_count", 0)
        detected_breaking = report.get("breaking_count", 0)
        if abs(detected_breaking - expected_breaking) <= 1:
            checks_passed += 1
        else:
            errors.append(f"Breaking change count: expected {expected_breaking}, got {detected_breaking}")

        # Check 2: Expand steps present when required
        total_checks += 1
        must_expand = expected.get("plan_must_include_expand", False)
        plan_steps = report.get("plan", {}).get("steps", [])
        has_expand = any(s.get("title", "").startswith("[EXPAND]") for s in plan_steps)
        if must_expand and not has_expand:
            errors.append("Missing EXPAND steps in plan (required by ground truth)")
        else:
            checks_passed += 1

        # Check 3: Rollback checkpoint present
        total_checks += 1
        must_rollback = expected.get("plan_must_include_rollback", True)
        has_rollback = any(s.get("step_type") == "ROLLBACK_CHECKPOINT" for s in plan_steps)
        if must_rollback and not has_rollback:
            errors.append("Missing ROLLBACK_CHECKPOINT in plan")
        else:
            checks_passed += 1

        # Check 4: Minimum plan steps
        total_checks += 1
        min_steps = expected.get("minimum_plan_steps", 2)
        actual_steps = len(plan_steps)
        if actual_steps >= min_steps:
            checks_passed += 1
        else:
            errors.append(f"Plan has {actual_steps} steps, expected at least {min_steps}")

        # Check 5: Adapter code generated when required
        total_checks += 1
        requires_adapter = expected.get("requires_adapter", False)
        has_adapter = len(report.get("adapter_codes", [])) > 0
        if requires_adapter and not has_adapter:
            errors.append("Adapter code required but not generated")
        else:
            checks_passed += 1

        # Check 6: Plan validation score >= 0.6
        total_checks += 1
        val_score = report.get("validation", {}).get("completeness_score", 0)
        if val_score >= 0.6:
            checks_passed += 1
        else:
            errors.append(f"Plan validation score too low: {val_score:.2f} (need >= 0.6)")

        # Check 7: Schema change count within ±1 tolerance
        total_checks += 1
        expected_schema = expected.get("schema_change_count", 0)
        detected_schema = report.get("schema_change_count", 0)
        if abs(detected_schema - expected_schema) <= 1:
            checks_passed += 1
        else:
            errors.append(f"Schema change count: expected {expected_schema}, got {detected_schema}")

        score = checks_passed / total_checks if total_checks > 0 else 0.0
        passed = len(errors) == 0

        return CaseResult(
            case_id=case_id,
            title=title,
            category=ground_truth.get("category", "unknown"),
            ground_truth=ground_truth,
            report=report,
            passed=passed,
            score=score,
            errors=errors,
            latency_seconds=latency,
            reasoning_trace_length=report.get("reasoning_trace_length", 0),
        )


def _read_optional(path: Path) -> str | None:
    if path.exists():
        return path.read_text(encoding="utf-8")
    # Also check schema/ subdirectory (some cases nest schema files)
    alt = path.parent / "schema" / path.name
    if alt.exists():
        return alt.read_text(encoding="utf-8")
    return None
