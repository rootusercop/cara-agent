"""
Plan validator for CARA.

Checks a migration plan for completeness, correctness, and potential conflicts.
Returns a ValidationResult with a score and a list of issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.plan_generator import MigrationPlan, StepType
    from tools.change_classifier import Severity


@dataclass
class ValidationIssue:
    severity: str  # ERROR | WARNING | INFO
    message: str
    step_number: int | None = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "message": self.message,
            "step_number": self.step_number,
        }


@dataclass
class ValidationResult:
    completeness_score: float  # 0.0 to 1.0
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    uncovered_consumers: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "completeness_score": round(self.completeness_score, 2),
            "passed": self.passed,
            "issue_count": len(self.issues),
            "error_count": sum(1 for i in self.issues if i.severity == "ERROR"),
            "warning_count": sum(1 for i in self.issues if i.severity == "WARNING"),
            "issues": [i.to_dict() for i in self.issues],
            "uncovered_consumers": self.uncovered_consumers,
            "summary": self.summary,
        }


def validate_plan(
    plan: "MigrationPlan",
    schema_classifications: list | None = None,
    api_classifications: list | None = None,
    consumers: list | None = None,
) -> ValidationResult:
    """
    Validate a migration plan for completeness and correctness.

    Checks:
    1. Rollback checkpoint exists
    2. Every breaking change has at least one expand step
    3. Consumer migration step exists if breaking changes present
    4. Validation step exists before contract steps
    5. Contract cleanup steps exist for every expand step
    6. No irreversible steps come before reversible ones without a checkpoint
    7. All known consumers are covered

    Returns:
        ValidationResult with a 0-1 completeness score.
    """
    from tools.plan_generator import StepType
    from tools.change_classifier import Severity

    issues: list[ValidationIssue] = []
    checks_passed = 0
    total_checks = 0

    step_types = [s.step_type for s in plan.steps]

    # Check 1: Rollback checkpoint at start
    total_checks += 1
    if StepType.ROLLBACK_CHECKPOINT in step_types:
        checks_passed += 1
        if plan.steps[0].step_type != StepType.ROLLBACK_CHECKPOINT:
            issues.append(ValidationIssue("WARNING", "Rollback checkpoint should be the first step.", plan.steps[0].step_number))
    else:
        issues.append(ValidationIssue("ERROR", "No rollback checkpoint found. Add a rollback checkpoint as the first step."))

    # Check 2: Expand steps exist when breaking changes present
    total_checks += 1
    has_breaking = plan.total_breaking_changes > 0
    has_expand = any(s.title.startswith("[EXPAND]") for s in plan.steps)
    if has_breaking and has_expand:
        checks_passed += 1
    elif has_breaking:
        issues.append(ValidationIssue("ERROR", "Breaking changes detected but no EXPAND steps found. Add expand steps before removing old structures."))
    else:
        checks_passed += 1  # No breaking changes = no expand needed

    # Check 3: Consumer migration step when breaking changes present
    total_checks += 1
    has_consumer_migration = StepType.CONSUMER_MIGRATION in step_types
    if has_breaking and has_consumer_migration:
        checks_passed += 1
    elif has_breaking:
        issues.append(ValidationIssue("ERROR", "Breaking changes present but no CONSUMER_MIGRATION step found."))
    else:
        checks_passed += 1

    # Check 4: Validation step before any contract/cleanup steps
    total_checks += 1
    validation_indices = [i for i, s in enumerate(plan.steps) if s.step_type == StepType.VALIDATION]
    cleanup_indices = [i for i, s in enumerate(plan.steps) if s.step_type == StepType.CLEANUP]
    if cleanup_indices and not validation_indices:
        issues.append(ValidationIssue("ERROR", "CLEANUP steps present but no VALIDATION step found. Always validate before cleanup."))
    elif cleanup_indices and validation_indices:
        if min(cleanup_indices) < max(validation_indices):
            issues.append(ValidationIssue("WARNING", "Some CLEANUP steps appear before VALIDATION steps. Reorder to validate before cleanup.", plan.steps[min(cleanup_indices)].step_number))
        checks_passed += 1
    else:
        checks_passed += 1

    # Check 5: Contract cleanup for every expand step
    total_checks += 1
    expand_count = sum(1 for s in plan.steps if s.title.startswith("[EXPAND]"))
    cleanup_count = len(cleanup_indices)
    if expand_count > 0 and cleanup_count == 0:
        issues.append(ValidationIssue("WARNING", f"Found {expand_count} EXPAND step(s) but no CONTRACT/CLEANUP steps. The plan is incomplete — old structures will never be removed."))
    else:
        checks_passed += 1

    # Check 6: Irreversible steps must come after validation
    total_checks += 1
    irreversible_steps = [s for s in plan.steps if not s.can_rollback]
    early_irreversible = [s for s in irreversible_steps if not validation_indices or s.step_number < plan.steps[max(validation_indices)].step_number]
    if early_irreversible:
        for s in early_irreversible:
            issues.append(ValidationIssue("WARNING", f"Irreversible step '{s.title}' appears before the validation step.", s.step_number))
    else:
        checks_passed += 1

    # Check 7: Consumer coverage
    total_checks += 1
    uncovered: list[str] = []
    if consumers:
        covered_services = set()
        for step in plan.steps:
            covered_services.update(step.affected_services)
        all_services = {c.service_name for c in consumers}
        uncovered_services = all_services - covered_services
        if uncovered_services:
            uncovered = list(uncovered_services)
            issues.append(ValidationIssue(
                "WARNING",
                f"These consumer services are not explicitly addressed in the plan: {', '.join(sorted(uncovered_services))}",
            ))
        else:
            checks_passed += 1
    else:
        checks_passed += 1  # No consumers provided — skip check

    # Check 8: Dependencies are well-formed
    total_checks += 1
    step_nums = {s.step_number for s in plan.steps}
    bad_deps = []
    for s in plan.steps:
        for dep in s.dependencies:
            if dep not in step_nums:
                bad_deps.append((s.step_number, dep))
    if bad_deps:
        for sn, dep in bad_deps:
            issues.append(ValidationIssue("ERROR", f"Step {sn} depends on step {dep} which doesn't exist.", sn))
    else:
        checks_passed += 1

    score = checks_passed / total_checks if total_checks > 0 else 0.0
    has_errors = any(i.severity == "ERROR" for i in issues)

    summary = (
        f"Plan validation: {checks_passed}/{total_checks} checks passed. "
        f"Score: {score:.0%}. "
        f"{'FAILED' if has_errors else 'PASSED'}. "
        f"{len([i for i in issues if i.severity == 'ERROR'])} error(s), "
        f"{len([i for i in issues if i.severity == 'WARNING'])} warning(s)."
    )

    return ValidationResult(
        completeness_score=score,
        passed=not has_errors,
        issues=issues,
        uncovered_consumers=uncovered,
        summary=summary,
    )
