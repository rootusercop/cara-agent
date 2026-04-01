"""
DirectCARAAgent: runs the CARA 7-tool pipeline deterministically.

Used to generate reproducible eval results without requiring an LLM API.
The paper metrics (F1, plan completeness, pass rate) measure the rule-based
pipeline correctness, not LLM orchestration quality.
"""

from __future__ import annotations

from agent.cara_agent import AgentState, MigrationReport
from tools.schema_diff import parse_schema_diff
from tools.api_diff import diff_api_contracts
from tools.consumer_tracer import trace_consumers
from tools.change_classifier import classify_breaking_change, ChangeClassification, Severity
from tools.plan_generator import generate_migration_plan
from tools.code_generator import generate_adapter_code
from tools.plan_validator import validate_plan


class DirectCARAAgent:
    """
    Runs the full CARA pipeline deterministically without an LLM.

    Executes tools in the canonical ReAct order:
      1. parse_schema_diff
      2. diff_api_contracts
      3. trace_consumers (if codebase_path provided)
      4. classify_breaking_change (for each change)
      5. generate_migration_plan
      6. generate_adapter_code (for each BREAKING change)
      7. validate_plan
    """

    def __init__(self, *args, **kwargs):
        pass  # No API client needed

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
        state = AgentState()
        state.reasoning_trace.append({"type": "thought", "content": f"Analyzing: {task_description}", "iteration": 0})

        # Step 1: Parse schema diff
        if old_schema and new_schema:
            state.schema_changes = parse_schema_diff(old_schema, new_schema, schema_type)
            state.reasoning_trace.append({
                "type": "observation", "tool": "parse_schema_diff",
                "result_summary": f"{len(state.schema_changes)} schema changes", "iteration": 1,
            })

        # Step 2: Diff API contracts
        if old_api_spec and new_api_spec:
            state.api_changes = diff_api_contracts(old_api_spec, new_api_spec, api_spec_type)
            state.reasoning_trace.append({
                "type": "observation", "tool": "diff_api_contracts",
                "result_summary": f"{len(state.api_changes)} API changes", "iteration": 2,
            })

        # Step 3: Trace consumers (if codebase path provided)
        if codebase_path:
            all_elements = (
                [c.element_name for c in state.schema_changes]
                + [c.field_or_param for c in state.api_changes if c.field_or_param]
            )
            for element in set(all_elements):
                if element:
                    consumers = trace_consumers(element, codebase_path)
                    state.consumers.extend(consumers)
            # Deduplicate
            seen: set[tuple] = set()
            unique = []
            for c in state.consumers:
                key = (c.file_path, c.line_number)
                if key not in seen:
                    seen.add(key)
                    unique.append(c)
            state.consumers = unique

        # Step 4: Classify all changes
        for change in state.schema_changes:
            cls = classify_breaking_change(change, state.consumers)
            state.schema_classifications.append(cls)

        for change in state.api_changes:
            cls = classify_breaking_change(change, state.consumers)
            state.api_classifications.append(cls)

        # Step 5: Generate migration plan
        state.plan = generate_migration_plan(
            state.schema_changes,
            state.api_changes,
            state.schema_classifications,
            state.api_classifications,
            state.consumers,
        )

        # Step 6: Generate adapter code for BREAKING changes
        breaking_schema = [
            (sc, cls) for sc, cls in zip(state.schema_changes, state.schema_classifications)
            if cls.severity == Severity.BREAKING
        ]
        breaking_api = [
            (ac, cls) for ac, cls in zip(state.api_changes, state.api_classifications)
            if cls.severity == Severity.BREAKING
        ]

        for change, _ in breaking_schema + breaking_api:
            element = getattr(change, "element_name", None) or getattr(change, "field_or_param", None) or "field"
            table = getattr(change, "table_or_message", None) or getattr(change, "endpoint_or_rpc", None) or "Entity"
            old_val = change.old_value or element
            new_val = change.new_value or element

            code = generate_adapter_code(
                old_contract=f"{table}.{element} (old)",
                new_contract=f"{table}.{new_val} (new)",
                language=language,
                change_type="field_rename",
                old_field=str(old_val),
                new_field=str(new_val),
                entity_name=table,
            )
            state.adapter_codes.append(code)

        # Step 7: Validate plan
        state.validation = validate_plan(
            state.plan,
            state.schema_classifications,
            state.api_classifications,
            state.consumers,
        )

        return _compile_report(state)


def _compile_report(state: AgentState) -> MigrationReport:
    breaking = sum(
        1 for c in state.schema_classifications + state.api_classifications
        if c.severity == Severity.BREAKING
    )
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
