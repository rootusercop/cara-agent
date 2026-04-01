"""
CARA: Contract-Aware Refactoring Agent

Main ReAct agent that orchestrates the tool registry to produce
a unified schema + API migration plan for distributed systems.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

import anthropic

from agent.prompts import SYSTEM_PROMPT
from tools.schema_diff import parse_schema_diff, SchemaChange
from tools.api_diff import diff_api_contracts, APIChange
from tools.consumer_tracer import trace_consumers, Consumer
from tools.change_classifier import classify_breaking_change, ChangeClassification
from tools.plan_generator import generate_migration_plan, MigrationPlan
from tools.code_generator import generate_adapter_code, GeneratedCode
from tools.plan_validator import validate_plan, ValidationResult


# ---------------------------------------------------------------------------
# Tool definitions for Claude's tool use API
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "parse_schema_diff",
        "description": "Parse and diff two schema definitions (SQL DDL, Protobuf, or JSON Schema). Returns a list of structural changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "old_schema": {"type": "string", "description": "The original schema string."},
                "new_schema": {"type": "string", "description": "The updated schema string."},
                "schema_type": {"type": "string", "enum": ["sql", "protobuf", "json_schema"], "description": "The schema format."},
            },
            "required": ["old_schema", "new_schema", "schema_type"],
        },
    },
    {
        "name": "trace_consumers",
        "description": "Find all code files that reference a schema element or endpoint across a codebase.",
        "input_schema": {
            "type": "object",
            "properties": {
                "changed_element": {"type": "string", "description": "The field, table, or endpoint name to search for."},
                "codebase_path": {"type": "string", "description": "Root directory to search."},
            },
            "required": ["changed_element", "codebase_path"],
        },
    },
    {
        "name": "diff_api_contracts",
        "description": "Diff two API specifications (OpenAPI, Protobuf service, or GraphQL). Returns a list of API-level changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "old_spec": {"type": "string", "description": "The original API specification string."},
                "new_spec": {"type": "string", "description": "The updated API specification string."},
                "spec_type": {"type": "string", "enum": ["openapi", "protobuf", "graphql"], "description": "The specification format."},
            },
            "required": ["old_spec", "new_spec", "spec_type"],
        },
    },
    {
        "name": "classify_breaking_change",
        "description": "Classify a schema or API change as SAFE, BACKWARD_COMPATIBLE, or BREAKING. Returns expand-contract phases for breaking changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "change": {"type": "object", "description": "A SchemaChange or APIChange dict (from parse_schema_diff or diff_api_contracts)."},
                "consumer_count": {"type": "integer", "description": "Number of consumers affected (from trace_consumers)."},
            },
            "required": ["change"],
        },
    },
    {
        "name": "generate_migration_plan",
        "description": "Generate a coordinated, ordered expand-contract migration plan for all detected changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "schema_changes": {"type": "array", "items": {"type": "object"}, "description": "List of schema change dicts."},
                "api_changes": {"type": "array", "items": {"type": "object"}, "description": "List of API change dicts."},
                "schema_classifications": {"type": "array", "items": {"type": "object"}, "description": "Classifications for each schema change."},
                "api_classifications": {"type": "array", "items": {"type": "object"}, "description": "Classifications for each API change."},
                "affected_services": {"type": "array", "items": {"type": "string"}, "description": "List of affected service names."},
            },
            "required": ["schema_changes", "api_changes", "schema_classifications", "api_classifications"],
        },
    },
    {
        "name": "generate_adapter_code",
        "description": "Generate backward-compatible adapter/shim code for a breaking change.",
        "input_schema": {
            "type": "object",
            "properties": {
                "old_contract": {"type": "string", "description": "Description of the old contract."},
                "new_contract": {"type": "string", "description": "Description of the new contract."},
                "language": {"type": "string", "enum": ["python", "java", "kotlin", "typescript"], "description": "Target language."},
                "change_type": {"type": "string", "description": "Type of change: field_rename, field_removal, type_change, endpoint_versioning."},
                "old_field": {"type": "string", "description": "Old field or endpoint name."},
                "new_field": {"type": "string", "description": "New field or endpoint name."},
                "entity_name": {"type": "string", "description": "The data class or model name."},
            },
            "required": ["old_contract", "new_contract", "language", "old_field", "new_field"],
        },
    },
    {
        "name": "validate_plan",
        "description": "Validate a migration plan for completeness and correctness. Returns a 0-1 score and list of issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan": {"type": "object", "description": "A MigrationPlan dict (from generate_migration_plan)."},
                "consumer_count": {"type": "integer", "description": "Total number of consumers found."},
            },
            "required": ["plan"],
        },
    },
]


# ---------------------------------------------------------------------------
# State container for the agent's accumulated findings
# ---------------------------------------------------------------------------

@dataclass
class AgentState:
    schema_changes: list[SchemaChange] = field(default_factory=list)
    api_changes: list[APIChange] = field(default_factory=list)
    consumers: list[Consumer] = field(default_factory=list)
    schema_classifications: list[ChangeClassification] = field(default_factory=list)
    api_classifications: list[ChangeClassification] = field(default_factory=list)
    plan: MigrationPlan | None = None
    adapter_codes: list[GeneratedCode] = field(default_factory=list)
    validation: ValidationResult | None = None
    reasoning_trace: list[dict] = field(default_factory=list)


@dataclass
class MigrationReport:
    executive_summary: str
    schema_change_count: int
    api_change_count: int
    breaking_count: int
    safe_count: int
    plan: dict
    adapter_codes: list[dict]
    validation: dict
    warnings: list[str]
    reasoning_trace: list[dict]

    def to_dict(self) -> dict:
        return {
            "executive_summary": self.executive_summary,
            "schema_change_count": self.schema_change_count,
            "api_change_count": self.api_change_count,
            "breaking_count": self.breaking_count,
            "safe_count": self.safe_count,
            "plan": self.plan,
            "adapter_codes": self.adapter_codes,
            "validation": self.validation,
            "warnings": self.warnings,
            "reasoning_trace_length": len(self.reasoning_trace),
        }


# ---------------------------------------------------------------------------
# Main CARA agent
# ---------------------------------------------------------------------------

class CARAAgent:
    """
    ReAct-style agent that orchestrates schema diff, API diff, consumer tracing,
    change classification, plan generation, adapter code generation, and validation
    to produce a unified migration report.
    """

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.max_iterations = 20

    def analyze(
        self,
        task_description: str,
        old_schema: str = "",
        new_schema: str = "",
        schema_type: str = "sql",
        old_api_spec: str = "",
        new_api_spec: str = "",
        api_spec_type: str = "openapi",
        codebase_path: str = "",
        language: str = "python",
    ) -> MigrationReport:
        """
        Analyze a refactoring task and produce a migration report.

        Args:
            task_description: Natural language description of the change being made.
            old_schema: Original schema DDL / Protobuf / JSON Schema.
            new_schema: Updated schema.
            schema_type: sql | protobuf | json_schema.
            old_api_spec: Original OpenAPI / Proto / GraphQL spec.
            new_api_spec: Updated API spec.
            api_spec_type: openapi | protobuf | graphql.
            codebase_path: Root directory to search for consumers.
            language: Primary language for adapter code generation.

        Returns:
            A MigrationReport with plan, adapter code, and validation results.
        """
        state = AgentState()

        # Build initial user message with all context
        user_message = self._build_user_message(
            task_description, old_schema, new_schema, schema_type,
            old_api_spec, new_api_spec, api_spec_type, codebase_path, language,
        )

        messages: list[dict] = [{"role": "user", "content": user_message}]
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1

            response = self.client.messages.create(
                model=self.model,
                max_tokens=8096,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            # Record reasoning trace
            for block in response.content:
                if hasattr(block, "text"):
                    state.reasoning_trace.append({"type": "thought", "content": block.text, "iteration": iteration})

            # Check stop condition
            if response.stop_reason == "end_turn":
                break

            if response.stop_reason != "tool_use":
                break

            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                state.reasoning_trace.append({"type": "action", "tool": tool_name, "input": tool_input, "iteration": iteration})

                result = self._dispatch_tool(tool_name, tool_input, state, codebase_path, language)
                state.reasoning_trace.append({"type": "observation", "tool": tool_name, "result_summary": str(result)[:500], "iteration": iteration})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

            # Add assistant response and tool results to message history
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return self._compile_report(state)

    def _dispatch_tool(
        self, tool_name: str, tool_input: dict, state: AgentState,
        codebase_path: str, language: str,
    ) -> Any:
        """Dispatch a tool call and update agent state."""
        try:
            if tool_name == "parse_schema_diff":
                changes = parse_schema_diff(
                    tool_input["old_schema"],
                    tool_input["new_schema"],
                    tool_input.get("schema_type", "sql"),
                )
                state.schema_changes = changes
                return [c.to_dict() for c in changes]

            elif tool_name == "trace_consumers":
                path = tool_input.get("codebase_path") or codebase_path
                consumers = trace_consumers(tool_input["changed_element"], path)
                state.consumers.extend(consumers)
                # Deduplicate by file+line
                seen = set()
                unique = []
                for c in state.consumers:
                    key = (c.file_path, c.line_number)
                    if key not in seen:
                        seen.add(key)
                        unique.append(c)
                state.consumers = unique
                return [c.to_dict() for c in consumers[:50]]  # cap output size

            elif tool_name == "diff_api_contracts":
                changes = diff_api_contracts(
                    tool_input["old_spec"],
                    tool_input["new_spec"],
                    tool_input.get("spec_type", "openapi"),
                )
                state.api_changes = changes
                return [c.to_dict() for c in changes]

            elif tool_name == "classify_breaking_change":
                change_dict = tool_input["change"]
                consumer_count = tool_input.get("consumer_count", len(state.consumers))

                # Reconstruct the change object from dict
                change_obj = _reconstruct_change(change_dict)
                relevant_consumers = state.consumers[:consumer_count] if consumer_count else state.consumers

                classification = classify_breaking_change(change_obj, relevant_consumers)

                # Store classification in the right list based on change type
                from tools.schema_diff import SchemaChange
                from tools.api_diff import APIChange
                if isinstance(change_obj, SchemaChange):
                    state.schema_classifications.append(classification)
                else:
                    state.api_classifications.append(classification)

                return classification.to_dict()

            elif tool_name == "generate_migration_plan":
                schema_changes = state.schema_changes
                api_changes = state.api_changes
                schema_cls = state.schema_classifications
                api_cls = state.api_classifications

                # Pad classifications if needed
                while len(schema_cls) < len(schema_changes):
                    from tools.change_classifier import ChangeClassification, Severity
                    schema_cls.append(ChangeClassification(Severity.BACKWARD_COMPATIBLE, "Unclassified — defaulting to BACKWARD_COMPATIBLE"))
                while len(api_cls) < len(api_changes):
                    from tools.change_classifier import ChangeClassification, Severity
                    api_cls.append(ChangeClassification(Severity.BACKWARD_COMPATIBLE, "Unclassified — defaulting to BACKWARD_COMPATIBLE"))

                plan = generate_migration_plan(
                    schema_changes, api_changes, schema_cls, api_cls, state.consumers
                )
                state.plan = plan
                return plan.to_dict()

            elif tool_name == "generate_adapter_code":
                code = generate_adapter_code(
                    old_contract=tool_input.get("old_contract", ""),
                    new_contract=tool_input.get("new_contract", ""),
                    language=tool_input.get("language", language),
                    change_type=tool_input.get("change_type", "field_rename"),
                    old_field=tool_input.get("old_field", ""),
                    new_field=tool_input.get("new_field", ""),
                    entity_name=tool_input.get("entity_name", "Entity"),
                )
                state.adapter_codes.append(code)
                return code.to_dict()

            elif tool_name == "validate_plan":
                if state.plan is None:
                    return {"error": "No plan generated yet. Call generate_migration_plan first."}
                validation = validate_plan(
                    state.plan,
                    state.schema_classifications,
                    state.api_classifications,
                    state.consumers,
                )
                state.validation = validation
                return validation.to_dict()

            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            return {"error": f"Tool {tool_name} failed: {str(e)}"}

    def _compile_report(self, state: AgentState) -> MigrationReport:
        from tools.change_classifier import Severity

        breaking = sum(1 for c in state.schema_classifications + state.api_classifications if c.severity == Severity.BREAKING)
        safe = len(state.schema_classifications) + len(state.api_classifications) - breaking
        warnings = state.plan.warnings if state.plan else []
        if state.validation and not state.validation.passed:
            for issue in state.validation.issues:
                if issue.severity == "ERROR":
                    warnings.append(f"[Plan ERROR] {issue.message}")

        summary = (
            f"CARA analyzed {len(state.schema_changes)} schema change(s) and "
            f"{len(state.api_changes)} API change(s) across "
            f"{len({c.service_name for c in state.consumers})} service(s). "
            f"Found {breaking} breaking change(s) requiring migration. "
            f"Generated a {len(state.plan.steps) if state.plan else 0}-step expand-contract migration plan."
        )

        return MigrationReport(
            executive_summary=summary,
            schema_change_count=len(state.schema_changes),
            api_change_count=len(state.api_changes),
            breaking_count=breaking,
            safe_count=safe,
            plan=state.plan.to_dict() if state.plan else {},
            adapter_codes=[c.to_dict() for c in state.adapter_codes],
            validation=state.validation.to_dict() if state.validation else {},
            warnings=warnings,
            reasoning_trace=state.reasoning_trace,
        )

    @staticmethod
    def _build_user_message(
        task_description: str,
        old_schema: str, new_schema: str, schema_type: str,
        old_api_spec: str, new_api_spec: str, api_spec_type: str,
        codebase_path: str, language: str,
    ) -> str:
        parts = [f"## Refactoring Task\n{task_description}"]
        if old_schema and new_schema:
            parts.append(f"## Schema Change ({schema_type})\n### Old Schema\n```\n{old_schema}\n```\n### New Schema\n```\n{new_schema}\n```")
        if old_api_spec and new_api_spec:
            parts.append(f"## API Contract Change ({api_spec_type})\n### Old Spec\n```\n{old_api_spec}\n```\n### New Spec\n```\n{new_api_spec}\n```")
        if codebase_path:
            parts.append(f"## Codebase Path\n{codebase_path}")
        parts.append(f"## Target Language for Adapter Code\n{language}")
        parts.append(
            "Please analyze this refactoring task using your tools. "
            "Start by diffing the schemas, then trace consumers, "
            "classify all changes, generate the migration plan, "
            "generate adapter code for breaking changes, and validate the plan."
        )
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Helper: reconstruct typed change objects from dicts
# ---------------------------------------------------------------------------

def _reconstruct_change(change_dict: dict):
    """Reconstruct a SchemaChange or APIChange from a serialized dict."""
    from tools.schema_diff import SchemaChange, ChangeType as SCT
    from tools.api_diff import APIChange, ChangeType as ACT

    change_type_str = change_dict.get("change_type", "")

    # Try schema change types
    try:
        ct = SCT(change_type_str)
        return SchemaChange(
            change_type=ct,
            table_or_message=change_dict.get("table_or_message", ""),
            element_name=change_dict.get("element_name", ""),
            old_value=change_dict.get("old_value"),
            new_value=change_dict.get("new_value"),
            metadata=change_dict.get("metadata", {}),
        )
    except ValueError:
        pass

    # Try API change types
    try:
        ct = ACT(change_type_str)
        return APIChange(
            change_type=ct,
            endpoint_or_rpc=change_dict.get("endpoint_or_rpc", ""),
            field_or_param=change_dict.get("field_or_param"),
            old_value=change_dict.get("old_value"),
            new_value=change_dict.get("new_value"),
            metadata=change_dict.get("metadata", {}),
        )
    except ValueError:
        pass

    # Fallback: return a minimal SchemaChange
    from tools.schema_diff import ChangeType as SCT
    return SchemaChange(SCT.FIELD_ADDED, "unknown", "unknown")
