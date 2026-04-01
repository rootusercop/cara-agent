"""
Breaking change classifier for CARA.

Classifies schema and API changes as SAFE, BACKWARD_COMPATIBLE, or BREAKING,
using a rule-based decision tree with LLM fallback for ambiguous cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.schema_diff import SchemaChange, ChangeType as SchemaChangeType
    from tools.api_diff import APIChange, ChangeType as APIChangeType
    from tools.consumer_tracer import Consumer


class Severity(Enum):
    SAFE = "SAFE"
    BACKWARD_COMPATIBLE = "BACKWARD_COMPATIBLE"
    BREAKING = "BREAKING"


@dataclass
class ChangeClassification:
    severity: Severity
    reason: str
    affected_consumers: list["Consumer"] = field(default_factory=list)
    requires_adapter: bool = False
    requires_migration_script: bool = False
    expand_contract_phases: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "reason": self.reason,
            "affected_consumer_count": len(self.affected_consumers),
            "requires_adapter": self.requires_adapter,
            "requires_migration_script": self.requires_migration_script,
            "expand_contract_phases": self.expand_contract_phases,
        }


def classify_breaking_change(
    change: "SchemaChange | APIChange",
    consumers: list["Consumer"] | None = None,
) -> ChangeClassification:
    """
    Classify a single schema or API change.

    Uses a rule-based decision tree first. Falls back to heuristics for
    ambiguous cases. Returns a ChangeClassification with severity and remediation guidance.
    """
    if consumers is None:
        consumers = []

    # Determine which classifier to use based on object type
    from tools.schema_diff import SchemaChange
    from tools.api_diff import APIChange

    if isinstance(change, SchemaChange):
        return _classify_schema_change(change, consumers)
    elif isinstance(change, APIChange):
        return _classify_api_change(change, consumers)
    else:
        return ChangeClassification(
            severity=Severity.SAFE,
            reason="Unknown change type — defaulting to SAFE. Manual review recommended.",
        )


# ---------------------------------------------------------------------------
# Schema change classification
# ---------------------------------------------------------------------------

def _classify_schema_change(
    change: "SchemaChange", consumers: list["Consumer"]
) -> ChangeClassification:
    from tools.schema_diff import ChangeType

    ct = change.change_type

    if ct == ChangeType.FIELD_ADDED:
        nullable = change.metadata.get("nullable", True)
        new_val_str = str(change.new_value or "").upper()
        has_default = "DEFAULT" in new_val_str
        if nullable or has_default:
            return ChangeClassification(
                severity=Severity.SAFE,
                reason="Adding a nullable column (or NOT NULL with a DEFAULT) is backward-compatible: existing rows are unaffected.",
                affected_consumers=[],
            )
        else:
            return ChangeClassification(
                severity=Severity.BREAKING,
                reason="Adding a NOT NULL column without a DEFAULT breaks existing INSERT statements that don't include this column.",
                affected_consumers=consumers,
                requires_migration_script=True,
                expand_contract_phases=[
                    "Phase 1 (Expand): Add column as nullable",
                    "Phase 2 (Backfill): Populate existing rows with default value",
                    "Phase 3 (Contract): Add NOT NULL constraint after backfill",
                ],
            )

    if ct == ChangeType.FIELD_REMOVED:
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason=f"Removing column '{change.element_name}' will break any query, ORM mapping, or serializer that references it.",
            affected_consumers=consumers,
            requires_adapter=len(consumers) > 0,
            requires_migration_script=True,
            expand_contract_phases=[
                "Phase 1: Mark field as deprecated in schema comments",
                "Phase 2: Remove all consumer references",
                "Phase 3 (Contract): Drop the column after all consumers are migrated",
            ],
        )

    if ct == ChangeType.FIELD_RENAMED:
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason=f"Renaming '{change.old_value}' to '{change.new_value}' breaks all existing consumers.",
            affected_consumers=consumers,
            requires_adapter=True,
            requires_migration_script=True,
            expand_contract_phases=[
                f"Phase 1 (Expand): Add new column '{change.new_value}', keep '{change.old_value}'",
                "Phase 2: Update all consumers to use new column name",
                f"Phase 3 (Contract): Drop old column '{change.old_value}'",
            ],
        )

    if ct == ChangeType.TYPE_CHANGED:
        old_type = (change.old_value or "").upper()
        new_type = (change.new_value or "").upper()
        # Widening is typically safe (INT -> BIGINT, VARCHAR(50) -> VARCHAR(100))
        if _is_type_widening(old_type, new_type):
            return ChangeClassification(
                severity=Severity.BACKWARD_COMPATIBLE,
                reason=f"Type change from {old_type} to {new_type} is a widening conversion and backward-compatible for reads, but may require ORM/serializer updates.",
                affected_consumers=consumers,
                requires_migration_script=True,
            )
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason=f"Type change from {old_type} to {new_type} is a narrowing or incompatible conversion that will break existing data and consumers.",
            affected_consumers=consumers,
            requires_adapter=True,
            requires_migration_script=True,
            expand_contract_phases=[
                f"Phase 1 (Expand): Add new column with type {new_type}",
                "Phase 2: Dual-write to both columns during migration",
                f"Phase 3: Backfill new column from old",
                f"Phase 4 (Contract): Remove old column",
            ],
        )

    if ct == ChangeType.NULLABLE_CHANGED:
        was_nullable = change.old_value == "True"
        is_nullable = change.new_value == "True"
        if not was_nullable and is_nullable:
            return ChangeClassification(
                severity=Severity.BACKWARD_COMPATIBLE,
                reason="Making a NOT NULL column nullable is backward-compatible for existing data.",
            )
        is_primary_key = change.metadata.get("primary_key", False)
        if is_primary_key:
            return ChangeClassification(
                severity=Severity.SAFE,
                reason="Explicitly adding NOT NULL to a PRIMARY KEY column is safe — primary keys are implicitly NOT NULL.",
            )
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason="Making a nullable column NOT NULL will fail if any existing rows have NULL values.",
            affected_consumers=consumers,
            requires_migration_script=True,
            expand_contract_phases=[
                "Phase 1: Backfill all NULL values with a sensible default",
                "Phase 2: Add NOT NULL constraint",
            ],
        )

    if ct in {ChangeType.TABLE_REMOVED, ChangeType.TABLE_RENAMED}:
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason=f"{ct.value}: All consumers of this table will break.",
            affected_consumers=consumers,
            requires_adapter=True,
            requires_migration_script=True,
        )

    if ct == ChangeType.TABLE_ADDED:
        return ChangeClassification(
            severity=Severity.SAFE,
            reason="Adding a new table has no impact on existing consumers.",
        )

    return ChangeClassification(
        severity=Severity.BACKWARD_COMPATIBLE,
        reason=f"Change type {ct.value} — assumed backward-compatible. Manual verification recommended.",
    )


# ---------------------------------------------------------------------------
# API change classification
# ---------------------------------------------------------------------------

def _classify_api_change(change: "APIChange", consumers: list["Consumer"]) -> ChangeClassification:
    from tools.api_diff import ChangeType

    ct = change.change_type

    if ct == ChangeType.ENDPOINT_ADDED:
        return ChangeClassification(severity=Severity.SAFE, reason="New endpoint does not affect existing consumers.")

    if ct == ChangeType.ENDPOINT_REMOVED:
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason=f"Removing endpoint '{change.endpoint_or_rpc}' breaks all consumers that call it.",
            affected_consumers=consumers,
            requires_adapter=True,
            expand_contract_phases=[
                "Phase 1: Add deprecation header/notice to endpoint",
                "Phase 2: Migrate all consumers to replacement endpoint",
                "Phase 3 (Contract): Remove endpoint after sunset date",
            ],
        )

    if ct == ChangeType.PATH_CHANGED:
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason="Changing an endpoint path breaks all hardcoded client URLs.",
            affected_consumers=consumers,
            requires_adapter=True,
            expand_contract_phases=[
                "Phase 1 (Expand): Register both old and new paths",
                "Phase 2: Migrate consumers to new path",
                "Phase 3 (Contract): Remove old path with deprecation notice",
            ],
        )

    if ct == ChangeType.REQUEST_FIELD_ADDED:
        return ChangeClassification(
            severity=Severity.BACKWARD_COMPATIBLE,
            reason="Adding an optional request field is backward-compatible. Existing clients simply don't send it.",
            affected_consumers=[],
            metadata={"note": "Ensure field has a default value or is marked optional in the schema."},
        )

    if ct == ChangeType.REQUEST_FIELD_REMOVED:
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason=f"Removing request field '{change.field_or_param}' breaks clients that send it.",
            affected_consumers=consumers,
            requires_adapter=True,
            expand_contract_phases=[
                "Phase 1: Accept both old and new request shapes (adapter layer)",
                "Phase 2: Migrate consumers to drop the field",
                "Phase 3 (Contract): Remove field from spec and adapter",
            ],
        )

    if ct == ChangeType.RESPONSE_FIELD_ADDED:
        return ChangeClassification(
            severity=Severity.SAFE,
            reason="Adding a response field is backward-compatible. Existing consumers ignore unknown fields (if properly written).",
            affected_consumers=[],
            metadata={"warning": "Consumers with strict deserialization (e.g., sealed classes) may break."},
        )

    if ct == ChangeType.RESPONSE_FIELD_REMOVED:
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason=f"Removing response field '{change.field_or_param}' breaks consumers that rely on it.",
            affected_consumers=consumers,
            requires_adapter=True,
            expand_contract_phases=[
                "Phase 1: Keep field in response (return null/empty)",
                "Phase 2: Migrate consumers off the field",
                "Phase 3 (Contract): Remove field from response",
            ],
        )

    if ct in {ChangeType.REQUEST_FIELD_TYPE_CHANGED, ChangeType.RESPONSE_FIELD_TYPE_CHANGED}:
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason=f"Changing the type of '{change.field_or_param}' will cause deserialization errors in consumers.",
            affected_consumers=consumers,
            requires_adapter=True,
        )

    if ct == ChangeType.RPC_REMOVED:
        return ChangeClassification(
            severity=Severity.BREAKING,
            reason=f"Removing RPC '{change.endpoint_or_rpc}' breaks all callers.",
            affected_consumers=consumers,
            requires_adapter=True,
        )

    if ct == ChangeType.RPC_ADDED:
        return ChangeClassification(severity=Severity.SAFE, reason="New RPC does not affect existing consumers.")

    return ChangeClassification(
        severity=Severity.BACKWARD_COMPATIBLE,
        reason=f"Change type {ct.value} — assumed backward-compatible.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TYPE_HIERARCHY = {
    "TINYINT": 1, "SMALLINT": 2, "INT": 3, "INTEGER": 3,
    "BIGINT": 4, "FLOAT": 5, "DOUBLE": 6, "DECIMAL": 7, "NUMERIC": 7,
    "CHAR": 10, "VARCHAR": 11, "TEXT": 12, "LONGTEXT": 13,
}


def _is_type_widening(old_type: str, new_type: str) -> bool:
    """Return True if changing from old_type to new_type is a widening conversion."""
    old_base = old_type.split("(")[0].strip()
    new_base = new_type.split("(")[0].strip()
    old_rank = _TYPE_HIERARCHY.get(old_base, 0)
    new_rank = _TYPE_HIERARCHY.get(new_base, 0)
    if old_rank > 0 and new_rank > 0:
        return new_rank >= old_rank
    # VARCHAR(n) -> VARCHAR(m) with m > n
    if old_base == new_base and "(" in old_type and "(" in new_type:
        try:
            old_len = int(old_type.split("(")[1].rstrip(")"))
            new_len = int(new_type.split("(")[1].rstrip(")"))
            return new_len >= old_len
        except (ValueError, IndexError):
            pass
    return False
