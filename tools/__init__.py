from tools.schema_diff import parse_schema_diff, SchemaChange, ChangeType as SchemaChangeType
from tools.api_diff import diff_api_contracts, APIChange, ChangeType as APIChangeType
from tools.consumer_tracer import trace_consumers, Consumer
from tools.change_classifier import classify_breaking_change, ChangeClassification, Severity
from tools.plan_generator import generate_migration_plan, MigrationPlan, MigrationStep
from tools.code_generator import generate_adapter_code, GeneratedCode
from tools.plan_validator import validate_plan, ValidationResult

__all__ = [
    "parse_schema_diff", "SchemaChange", "SchemaChangeType",
    "diff_api_contracts", "APIChange", "APIChangeType",
    "trace_consumers", "Consumer",
    "classify_breaking_change", "ChangeClassification", "Severity",
    "generate_migration_plan", "MigrationPlan", "MigrationStep",
    "generate_adapter_code", "GeneratedCode",
    "validate_plan", "ValidationResult",
]
