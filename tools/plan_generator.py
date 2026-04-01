"""
Migration plan generator for CARA.

Produces a coordinated, ordered migration plan given schema changes,
API changes, and their classifications. Implements the expand-contract pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.schema_diff import SchemaChange
    from tools.api_diff import APIChange
    from tools.change_classifier import ChangeClassification, Severity
    from tools.consumer_tracer import Consumer


class StepType(Enum):
    SCHEMA_MIGRATION = "SCHEMA_MIGRATION"
    CODE_CHANGE = "CODE_CHANGE"
    API_VERSIONING = "API_VERSIONING"
    ADAPTER_DEPLOYMENT = "ADAPTER_DEPLOYMENT"
    CONSUMER_MIGRATION = "CONSUMER_MIGRATION"
    VALIDATION = "VALIDATION"
    DEPRECATION_NOTICE = "DEPRECATION_NOTICE"
    CLEANUP = "CLEANUP"
    ROLLBACK_CHECKPOINT = "ROLLBACK_CHECKPOINT"


@dataclass
class MigrationStep:
    step_number: int
    step_type: StepType
    title: str
    description: str
    affected_services: list[str] = field(default_factory=list)
    sql_or_code: str | None = None
    can_rollback: bool = True
    estimated_risk: str = "LOW"  # LOW | MEDIUM | HIGH
    dependencies: list[int] = field(default_factory=list)  # step numbers this depends on

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "step_type": self.step_type.value,
            "title": self.title,
            "description": self.description,
            "affected_services": self.affected_services,
            "sql_or_code": self.sql_or_code,
            "can_rollback": self.can_rollback,
            "estimated_risk": self.estimated_risk,
            "dependencies": self.dependencies,
        }


@dataclass
class MigrationPlan:
    title: str
    summary: str
    total_breaking_changes: int
    total_safe_changes: int
    steps: list[MigrationStep] = field(default_factory=list)
    rollback_strategy: str = ""
    estimated_downtime: str = "Zero (if expand-contract followed)"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "total_breaking_changes": self.total_breaking_changes,
            "total_safe_changes": self.total_safe_changes,
            "step_count": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
            "rollback_strategy": self.rollback_strategy,
            "estimated_downtime": self.estimated_downtime,
            "warnings": self.warnings,
        }


def generate_migration_plan(
    schema_changes: list["SchemaChange"],
    api_changes: list["APIChange"],
    schema_classifications: list["ChangeClassification"],
    api_classifications: list["ChangeClassification"],
    consumers: list["Consumer"] | None = None,
) -> MigrationPlan:
    """
    Generate a coordinated migration plan for all schema and API changes.

    Always follows the expand-contract pattern:
    1. Expand: add new structures, keep old ones
    2. Migrate: update consumers incrementally
    3. Contract: remove old structures after all consumers migrated

    Args:
        schema_changes: List of detected schema changes.
        api_changes: List of detected API changes.
        schema_classifications: Classifications for each schema change.
        api_classifications: Classifications for each API change.
        consumers: All discovered consumers (used for affected_services).

    Returns:
        A MigrationPlan with ordered steps.
    """
    from tools.change_classifier import Severity

    consumers = consumers or []
    affected_services = list({c.service_name for c in consumers})

    breaking_schema = [
        (ch, cl) for ch, cl in zip(schema_changes, schema_classifications)
        if cl.severity == Severity.BREAKING
    ]
    breaking_api = [
        (ch, cl) for ch, cl in zip(api_changes, api_classifications)
        if cl.severity == Severity.BREAKING
    ]
    safe_count = (
        len(schema_classifications) + len(api_classifications)
        - len(breaking_schema) - len(breaking_api)
    )

    steps: list[MigrationStep] = []
    step_num = 1
    warnings: list[str] = []

    # Step 0: Always add a rollback checkpoint first
    steps.append(MigrationStep(
        step_number=step_num,
        step_type=StepType.ROLLBACK_CHECKPOINT,
        title="Create rollback checkpoint",
        description="Take a database snapshot and tag the current deployment. All subsequent steps must be reversible from this point.",
        can_rollback=True,
        estimated_risk="LOW",
    ))
    step_num += 1

    # Phase 1: EXPAND — add new structures without removing old ones
    expand_steps = _build_expand_steps(breaking_schema, breaking_api, step_num, affected_services)
    for s in expand_steps:
        s.step_number = step_num
        steps.append(s)
        step_num += 1

    # Phase 2: Consumer migration — update all consumers to use new structures
    if breaking_schema or breaking_api:
        consumer_step = _build_consumer_migration_step(
            step_num, breaking_schema, breaking_api, affected_services
        )
        consumer_step.dependencies = list(range(2, step_num))
        steps.append(consumer_step)
        step_num += 1

    # Phase 3: Validation — verify all consumers are migrated
    steps.append(MigrationStep(
        step_number=step_num,
        step_type=StepType.VALIDATION,
        title="Validate consumer migration completeness",
        description=(
            "Run integration tests across all affected services. "
            "Check that no service still references old field/endpoint names. "
            "Monitor error rates for 24 hours before proceeding to cleanup."
        ),
        affected_services=affected_services,
        estimated_risk="LOW",
        dependencies=[step_num - 1],
    ))
    step_num += 1

    # Phase 4: CONTRACT — remove old structures
    contract_steps = _build_contract_steps(breaking_schema, breaking_api, step_num, affected_services)
    for s in contract_steps:
        s.step_number = step_num
        s.dependencies = [step_num - 1]
        steps.append(s)
        step_num += 1

    # Warnings
    if len(breaking_schema) > 3:
        warnings.append("High number of breaking schema changes. Consider splitting into multiple PRs.")
    if not consumers and (breaking_schema or breaking_api):
        warnings.append("No consumers found — consumer tracer may have missed references. Manual audit recommended.")

    return MigrationPlan(
        title=f"Coordinated Migration Plan ({len(breaking_schema)} breaking schema + {len(breaking_api)} breaking API changes)",
        summary=(
            f"This plan coordinates {len(schema_changes)} schema change(s) and "
            f"{len(api_changes)} API change(s) across {len(affected_services)} service(s). "
            f"Breaking changes: {len(breaking_schema) + len(breaking_api)}. "
            f"Safe changes: {safe_count}. "
            "Follows expand-contract to maintain zero downtime."
        ),
        total_breaking_changes=len(breaking_schema) + len(breaking_api),
        total_safe_changes=safe_count,
        steps=steps,
        rollback_strategy=(
            "Restore database snapshot from step 1. Redeploy previous service versions. "
            "All expand steps (adding columns/endpoints) are safe to rollback as they do not remove data."
        ),
        warnings=warnings,
    )


def _build_expand_steps(
    breaking_schema: list,
    breaking_api: list,
    start_num: int,
    affected_services: list[str],
) -> list[MigrationStep]:
    from tools.schema_diff import ChangeType as SCT
    from tools.api_diff import ChangeType as ACT

    steps: list[MigrationStep] = []

    for change, classification in breaking_schema:
        ct = change.change_type
        if ct == SCT.FIELD_RENAMED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.SCHEMA_MIGRATION,
                title=f"[EXPAND] Add new column '{change.new_value}' to '{change.table_or_message}'",
                description=f"Add the new column alongside the old '{change.element_name}'. Both columns exist simultaneously.",
                affected_services=affected_services,
                sql_or_code=f"ALTER TABLE {change.table_or_message} ADD COLUMN {change.new_value} /* same type as {change.element_name} */;",
                estimated_risk="LOW",
            ))
        elif ct == SCT.FIELD_REMOVED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.SCHEMA_MIGRATION,
                title=f"[EXPAND] Add deprecation comment to column '{change.element_name}'",
                description="Mark the column as deprecated in schema documentation. Do not remove yet.",
                affected_services=[],
                estimated_risk="LOW",
            ))
        elif ct == SCT.TYPE_CHANGED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.SCHEMA_MIGRATION,
                title=f"[EXPAND] Add new column '{change.element_name}_v2' with type {change.new_value}",
                description=f"Add a shadow column to hold the new type while the old column still serves existing consumers.",
                sql_or_code=f"ALTER TABLE {change.table_or_message} ADD COLUMN {change.element_name}_v2 {change.new_value};",
                estimated_risk="LOW",
            ))

    for change, classification in breaking_api:
        ct = change.change_type
        if ct == ACT.ENDPOINT_REMOVED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.DEPRECATION_NOTICE,
                title=f"[EXPAND] Add deprecation notice to '{change.endpoint_or_rpc}'",
                description="Add Deprecation and Sunset HTTP headers. Notify consumers of sunset date.",
                estimated_risk="LOW",
            ))
        elif ct == ACT.REQUEST_FIELD_REMOVED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.ADAPTER_DEPLOYMENT,
                title=f"[EXPAND] Deploy adapter accepting both old and new request shapes for '{change.endpoint_or_rpc}'",
                description=f"The adapter accepts requests with and without '{change.field_or_param}'. Routes to the same handler.",
                estimated_risk="MEDIUM",
            ))
        elif ct == ACT.RESPONSE_FIELD_REMOVED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.API_VERSIONING,
                title=f"[EXPAND] Keep '{change.field_or_param}' in response (return null/empty)",
                description="Maintain the field in the response payload — return null or empty string until consumers are migrated off it.",
                estimated_risk="LOW",
            ))
        elif ct == ACT.RESPONSE_FIELD_TYPE_CHANGED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.API_VERSIONING,
                title=f"[EXPAND] Version the response to support both old and new type for '{change.field_or_param}'",
                description=(
                    f"Add a versioned response variant that returns '{change.field_or_param}' in both "
                    f"the old type ({change.old_value}) and the new type ({change.new_value}). "
                    "Consumers can migrate to the new type before the old representation is removed."
                ),
                estimated_risk="MEDIUM",
            ))

    # Handle schema TABLE_REMOVED as an expand step
    for change, classification in breaking_schema:
        from tools.schema_diff import ChangeType as SCT
        ct = change.change_type
        if ct == SCT.TABLE_REMOVED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.DEPRECATION_NOTICE,
                title=f"[EXPAND] Mark table '{change.table_or_message}' as deprecated and restrict new writes",
                description=(
                    f"Do not remove table '{change.table_or_message}' yet. "
                    "Redirect all writes to the replacement table(s) and add an audit trigger. "
                    "Keep old table readable until all consumers have migrated."
                ),
                estimated_risk="LOW",
            ))

    return steps


def _build_consumer_migration_step(
    step_num: int,
    breaking_schema: list,
    breaking_api: list,
    affected_services: list[str],
) -> MigrationStep:
    schema_items = [f"'{ch.element_name}' in '{ch.table_or_message}'" for ch, _ in breaking_schema]
    api_items = [f"'{ch.field_or_param or ch.endpoint_or_rpc}'" for ch, _ in breaking_api]
    all_items = schema_items + api_items

    return MigrationStep(
        step_number=step_num,
        step_type=StepType.CONSUMER_MIGRATION,
        title="[MIGRATE] Update all consumers to use new field/endpoint names",
        description=(
            f"Update references to: {', '.join(all_items)}. "
            "Each service must be updated and deployed independently. "
            "Verify each service in staging before production deployment."
        ),
        affected_services=affected_services,
        estimated_risk="MEDIUM",
    )


def _build_contract_steps(
    breaking_schema: list,
    breaking_api: list,
    start_num: int,
    affected_services: list[str],
) -> list[MigrationStep]:
    from tools.schema_diff import ChangeType as SCT
    from tools.api_diff import ChangeType as ACT

    steps: list[MigrationStep] = []

    for change, _ in breaking_schema:
        ct = change.change_type
        if ct in {SCT.FIELD_RENAMED, SCT.FIELD_REMOVED}:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.CLEANUP,
                title=f"[CONTRACT] Drop old column '{change.element_name}' from '{change.table_or_message}'",
                description="All consumers migrated. Safe to drop the old column now.",
                sql_or_code=f"ALTER TABLE {change.table_or_message} DROP COLUMN {change.element_name};",
                can_rollback=False,
                estimated_risk="HIGH",
            ))
        elif ct == SCT.TYPE_CHANGED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.CLEANUP,
                title=f"[CONTRACT] Drop old column '{change.element_name}', rename shadow column",
                description=f"Drop the old column and rename '{change.element_name}_v2' to '{change.element_name}'.",
                sql_or_code=(
                    f"ALTER TABLE {change.table_or_message} DROP COLUMN {change.element_name};\n"
                    f"ALTER TABLE {change.table_or_message} RENAME COLUMN {change.element_name}_v2 TO {change.element_name};"
                ),
                can_rollback=False,
                estimated_risk="HIGH",
            ))

    for change, _ in breaking_api:
        ct = change.change_type
        if ct == ACT.ENDPOINT_REMOVED:
            steps.append(MigrationStep(
                step_number=start_num,
                step_type=StepType.CLEANUP,
                title=f"[CONTRACT] Remove deprecated endpoint '{change.endpoint_or_rpc}'",
                description="All consumers migrated. Remove the endpoint and its adapter.",
                can_rollback=False,
                estimated_risk="MEDIUM",
            ))

    return steps
