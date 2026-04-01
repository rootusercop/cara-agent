"""
CARA agent backed by Ollama (OpenAI-compatible local LLM).

Mirrors CARAAgent but uses Ollama's OpenAI-compatible API so the eval
can run without any network dependency on api.anthropic.com.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from agent.prompts import SYSTEM_PROMPT
from agent.cara_agent import (
    TOOL_DEFINITIONS,
    AgentState,
    MigrationReport,
    _reconstruct_change,
)
from tools.schema_diff import parse_schema_diff
from tools.api_diff import diff_api_contracts
from tools.consumer_tracer import trace_consumers
from tools.change_classifier import classify_breaking_change
from tools.plan_generator import generate_migration_plan
from tools.code_generator import generate_adapter_code
from tools.plan_validator import validate_plan


# ---------------------------------------------------------------------------
# Convert Anthropic tool definitions -> OpenAI function definitions
# ---------------------------------------------------------------------------

def _to_openai_tools(anthropic_tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool definitions to OpenAI function-calling format."""
    result = []
    for t in anthropic_tools:
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })
    return result


OPENAI_TOOL_DEFINITIONS = _to_openai_tools(TOOL_DEFINITIONS)


# ---------------------------------------------------------------------------
# Ollama-backed CARA agent
# ---------------------------------------------------------------------------

class OllamaCARAAgent:
    """
    ReAct-style CARA agent that calls Ollama via the OpenAI-compatible API.
    Drop-in replacement for CARAAgent for local eval runs.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3.2",
        api_key: str = "ollama",  # Ollama ignores this but OpenAI client requires it
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
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
        state = AgentState()

        user_message = _build_user_message(
            task_description, old_schema, new_schema, schema_type,
            old_api_spec, new_api_spec, api_spec_type, codebase_path, language,
        )

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=OPENAI_TOOL_DEFINITIONS,
                tool_choice="auto",
            )

            msg = response.choices[0].message

            # Record any text reasoning
            if msg.content:
                state.reasoning_trace.append({
                    "type": "thought",
                    "content": msg.content,
                    "iteration": iteration,
                })

            finish_reason = response.choices[0].finish_reason

            # No tool calls: agent is done
            if not msg.tool_calls:
                messages.append({"role": "assistant", "content": msg.content or ""})
                break

            # Process tool calls
            tool_results_msgs: list[dict] = []
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                state.reasoning_trace.append({
                    "type": "action",
                    "tool": tool_name,
                    "input": tool_input,
                    "iteration": iteration,
                })

                result = _dispatch_tool(tool_name, tool_input, state, codebase_path, language)

                state.reasoning_trace.append({
                    "type": "observation",
                    "tool": tool_name,
                    "result_summary": str(result)[:500],
                    "iteration": iteration,
                })

                tool_results_msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })

            # Append assistant message (with tool_calls) and all tool results
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })
            messages.extend(tool_results_msgs)

        return _compile_report(state)


# ---------------------------------------------------------------------------
# Tool dispatch (identical logic to CARAAgent._dispatch_tool)
# ---------------------------------------------------------------------------

def _dispatch_tool(
    tool_name: str, tool_input: dict, state: AgentState,
    codebase_path: str, language: str,
) -> Any:
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
            seen = set()
            unique = []
            for c in state.consumers:
                key = (c.file_path, c.line_number)
                if key not in seen:
                    seen.add(key)
                    unique.append(c)
            state.consumers = unique
            return [c.to_dict() for c in consumers[:50]]

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
            change_obj = _reconstruct_change(change_dict)
            relevant_consumers = state.consumers[:consumer_count] if consumer_count else state.consumers
            classification = classify_breaking_change(change_obj, relevant_consumers)
            from tools.schema_diff import SchemaChange
            if isinstance(change_obj, SchemaChange):
                state.schema_classifications.append(classification)
            else:
                state.api_classifications.append(classification)
            return classification.to_dict()

        elif tool_name == "generate_migration_plan":
            schema_cls = state.schema_classifications
            api_cls = state.api_classifications
            while len(schema_cls) < len(state.schema_changes):
                from tools.change_classifier import ChangeClassification, Severity
                schema_cls.append(ChangeClassification(Severity.BACKWARD_COMPATIBLE, "Unclassified"))
            while len(api_cls) < len(state.api_changes):
                from tools.change_classifier import ChangeClassification, Severity
                api_cls.append(ChangeClassification(Severity.BACKWARD_COMPATIBLE, "Unclassified"))
            plan = generate_migration_plan(
                state.schema_changes, state.api_changes, schema_cls, api_cls, state.consumers
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


def _compile_report(state: AgentState) -> MigrationReport:
    from tools.change_classifier import Severity
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


def _build_user_message(
    task_description: str,
    old_schema: str, new_schema: str, schema_type: str,
    old_api_spec: str, new_api_spec: str, api_spec_type: str,
    codebase_path: str, language: str,
) -> str:
    parts = [f"## Refactoring Task\n{task_description}"]
    if old_schema and new_schema:
        parts.append(
            f"## Schema Change ({schema_type})\n"
            f"### Old Schema\n```\n{old_schema}\n```\n"
            f"### New Schema\n```\n{new_schema}\n```"
        )
    if old_api_spec and new_api_spec:
        parts.append(
            f"## API Contract Change ({api_spec_type})\n"
            f"### Old Spec\n```\n{old_api_spec}\n```\n"
            f"### New Spec\n```\n{new_api_spec}\n```"
        )
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
