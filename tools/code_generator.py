"""
Adapter code generator for CARA.

Generates backward-compatible adapter/shim code that bridges old and new
API contracts during the migration window, in Python, Java, Kotlin, and TypeScript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.api_diff import APIChange
    from tools.schema_diff import SchemaChange


@dataclass
class GeneratedCode:
    language: str
    adapter_code: str
    test_code: str
    migration_script: str | None = None
    description: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "description": self.description,
            "adapter_code_lines": len(self.adapter_code.splitlines()),
            "test_code_lines": len(self.test_code.splitlines()),
            "has_migration_script": self.migration_script is not None,
            "warnings": self.warnings,
        }


def generate_adapter_code(
    old_contract: str,
    new_contract: str,
    language: str = "python",
    change_type: str = "field_rename",
    old_field: str = "",
    new_field: str = "",
    entity_name: str = "Entity",
) -> GeneratedCode:
    """
    Generate adapter/shim code bridging an old and new contract.

    Args:
        old_contract: Description or snippet of the old contract.
        new_contract: Description or snippet of the new contract.
        language: Target language: python, java, kotlin, typescript.
        change_type: Type of change: field_rename, field_removal, type_change, endpoint_versioning.
        old_field: Old field or endpoint name.
        new_field: New field or endpoint name.
        entity_name: The data class / model name.

    Returns:
        A GeneratedCode object with adapter, tests, and optional migration script.
    """
    generators = {
        "python": _generate_python_adapter,
        "java": _generate_java_adapter,
        "kotlin": _generate_kotlin_adapter,
        "typescript": _generate_typescript_adapter,
    }
    gen = generators.get(language)
    if gen is None:
        raise ValueError(f"Unsupported language: {language}. Use python, java, kotlin, or typescript.")

    return gen(old_contract, new_contract, change_type, old_field, new_field, entity_name)


# ---------------------------------------------------------------------------
# Python adapter
# ---------------------------------------------------------------------------

def _generate_python_adapter(
    old_contract: str, new_contract: str, change_type: str,
    old_field: str, new_field: str, entity_name: str,
) -> GeneratedCode:
    if change_type == "field_rename":
        adapter = f'''\
from dataclasses import dataclass
from typing import Any


@dataclass
class {entity_name}V2:
    """New contract with '{new_field}' field."""
    {new_field}: Any
    # ... other fields


@dataclass
class {entity_name}Adapter:
    """
    Backward-compatible adapter that accepts both the old ('{old_field}')
    and new ('{new_field}') field names.

    Deploy during the migration window. Remove after all consumers use the new contract.
    """

    @staticmethod
    def from_request(data: dict) -> "{entity_name}V2":
        """Accept both old and new field names transparently."""
        normalized = dict(data)
        if "{old_field}" in normalized and "{new_field}" not in normalized:
            normalized["{new_field}"] = normalized.pop("{old_field}")
        return {entity_name}V2({new_field}=normalized.get("{new_field}"))

    @staticmethod
    def to_legacy_response(entity: "{entity_name}V2") -> dict:
        """Return response with both old and new field names during migration."""
        return {{
            "{new_field}": entity.{new_field},
            "{old_field}": entity.{new_field},  # backward-compat alias — remove after migration
        }}
'''
        tests = f'''\
import pytest
from adapter import {entity_name}Adapter, {entity_name}V2


class Test{entity_name}Adapter:
    def test_accepts_old_field_name(self):
        result = {entity_name}Adapter.from_request({{"{old_field}": "value123"}})
        assert result.{new_field} == "value123"

    def test_accepts_new_field_name(self):
        result = {entity_name}Adapter.from_request({{"{new_field}": "value123"}})
        assert result.{new_field} == "value123"

    def test_response_includes_both_field_names(self):
        entity = {entity_name}V2({new_field}="value123")
        resp = {entity_name}Adapter.to_legacy_response(entity)
        assert resp["{new_field}"] == "value123"
        assert resp["{old_field}"] == "value123"  # backward compat

    def test_new_field_takes_precedence_when_both_present(self):
        result = {entity_name}Adapter.from_request({{
            "{old_field}": "old_value",
            "{new_field}": "new_value",
        }})
        assert result.{new_field} == "new_value"
'''
        return GeneratedCode(
            language="python",
            adapter_code=adapter,
            test_code=tests,
            description=f"Python adapter bridging '{old_field}' (old) to '{new_field}' (new) for {entity_name}.",
        )

    return _generate_generic_adapter("python", old_contract, new_contract, old_field, new_field, entity_name)


# ---------------------------------------------------------------------------
# Kotlin adapter
# ---------------------------------------------------------------------------

def _generate_kotlin_adapter(
    old_contract: str, new_contract: str, change_type: str,
    old_field: str, new_field: str, entity_name: str,
) -> GeneratedCode:
    if change_type == "field_rename":
        adapter = f'''\
import com.fasterxml.jackson.annotation.JsonAlias
import com.fasterxml.jackson.annotation.JsonProperty

/**
 * New contract DTO using '{new_field}'.
 *
 * Uses @JsonAlias to also accept the old field name '{old_field}' during migration.
 * Remove the @JsonAlias after all consumers send the new field name.
 */
data class {entity_name}Request(
    @JsonProperty("{new_field}")
    @JsonAlias("{old_field}")  // backward-compat alias — remove after migration
    val {new_field}: String,
    // ... other fields
)

/**
 * Response DTO that includes both old and new field names during migration window.
 * Remove '{old_field}' after all consumers are updated.
 */
data class {entity_name}Response(
    @JsonProperty("{new_field}")
    val {new_field}: String,
    @Deprecated("Use {new_field}. Will be removed after migration.")
    @JsonProperty("{old_field}")
    val {old_field}: String = {new_field},  // duplicate for backward compat
    // ... other fields
)

/**
 * Extension function to convert legacy requests to the new contract.
 */
object {entity_name}Adapter {{
    fun toNewContract(legacyData: Map<String, Any?>): {entity_name}Request {{
        val fieldValue = legacyData["{new_field}"] ?: legacyData["{old_field}"]
            ?: throw IllegalArgumentException("Neither '{new_field}' nor '{old_field}' found in request")
        return {entity_name}Request({new_field} = fieldValue.toString())
    }}
}}
'''
        tests = f'''\
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper

class {entity_name}AdapterTest {{
    private val mapper = jacksonObjectMapper()

    @Test
    fun `should deserialize old field name`() {{
        val json = """{{"{old_field}": "value123"}}"""
        val result = mapper.readValue(json, {entity_name}Request::class.java)
        assertEquals("value123", result.{new_field})
    }}

    @Test
    fun `should deserialize new field name`() {{
        val json = """{{"{new_field}": "value123"}}"""
        val result = mapper.readValue(json, {entity_name}Request::class.java)
        assertEquals("value123", result.{new_field})
    }}

    @Test
    fun `response should include both field names`() {{
        val response = {entity_name}Response({new_field} = "value123")
        val json = mapper.writeValueAsString(response)
        assertTrue(json.contains("{new_field}"))
        assertTrue(json.contains("{old_field}"))
    }}

    @Test
    fun `adapter should convert legacy map to new contract`() {{
        val legacy = mapOf("{old_field}" to "value123")
        val result = {entity_name}Adapter.toNewContract(legacy)
        assertEquals("value123", result.{new_field})
    }}
}}
'''
        return GeneratedCode(
            language="kotlin",
            adapter_code=adapter,
            test_code=tests,
            description=f"Kotlin adapter using @JsonAlias to bridge '{old_field}' to '{new_field}' for {entity_name}.",
        )

    return _generate_generic_adapter("kotlin", old_contract, new_contract, old_field, new_field, entity_name)


# ---------------------------------------------------------------------------
# Java adapter
# ---------------------------------------------------------------------------

def _generate_java_adapter(
    old_contract: str, new_contract: str, change_type: str,
    old_field: str, new_field: str, entity_name: str,
) -> GeneratedCode:
    if change_type == "field_rename":
        camel_new = _to_camel_case(new_field)
        camel_old = _to_camel_case(old_field)
        adapter = f'''\
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * New contract using '{new_field}'. Accepts old field name '{old_field}' via @JsonAlias.
 * Remove @JsonAlias after all consumers are migrated.
 */
public class {entity_name}Request {{
    @JsonProperty("{new_field}")
    @JsonAlias("{old_field}")
    private String {camel_new};

    public String get{camel_new.capitalize()}() {{ return {camel_new}; }}
    public void set{camel_new.capitalize()}(String value) {{ this.{camel_new} = value; }}
}}

public class {entity_name}Adapter {{
    /**
     * Convert a legacy map (using old field names) to the new contract.
     */
    public static {entity_name}Request fromLegacy(java.util.Map<String, Object> data) {{
        {entity_name}Request req = new {entity_name}Request();
        Object value = data.containsKey("{new_field}") ? data.get("{new_field}") : data.get("{old_field}");
        if (value == null) throw new IllegalArgumentException("Missing field: {new_field} or {old_field}");
        req.set{camel_new.capitalize()}(value.toString());
        return req;
    }}
}}
'''
        tests = f'''\
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;

class {entity_name}AdapterTest {{
    ObjectMapper mapper = new ObjectMapper();

    @Test
    void shouldAcceptOldFieldName() throws Exception {{
        String json = "{{\\""{old_field}\\"": \\"value123\\"}}";
        {entity_name}Request result = mapper.readValue(json, {entity_name}Request.class);
        assertEquals("value123", result.get{camel_new.capitalize()}());
    }}

    @Test
    void shouldAcceptNewFieldName() throws Exception {{
        String json = "{{\\""{new_field}\\"": \\"value123\\"}}";
        {entity_name}Request result = mapper.readValue(json, {entity_name}Request.class);
        assertEquals("value123", result.get{camel_new.capitalize()}());
    }}

    @Test
    void adapterShouldConvertLegacyMap() {{
        Map<String, Object> legacy = Map.of("{old_field}", "value123");
        {entity_name}Request result = {entity_name}Adapter.fromLegacy(legacy);
        assertEquals("value123", result.get{camel_new.capitalize()}());
    }}
}}
'''
        return GeneratedCode(
            language="java",
            adapter_code=adapter,
            test_code=tests,
            description=f"Java adapter using @JsonAlias to bridge '{old_field}' to '{new_field}' for {entity_name}.",
        )

    return _generate_generic_adapter("java", old_contract, new_contract, old_field, new_field, entity_name)


# ---------------------------------------------------------------------------
# TypeScript adapter
# ---------------------------------------------------------------------------

def _generate_typescript_adapter(
    old_contract: str, new_contract: str, change_type: str,
    old_field: str, new_field: str, entity_name: str,
) -> GeneratedCode:
    if change_type == "field_rename":
        adapter = f'''\
// New contract interface
export interface {entity_name}V2 {{
  {new_field}: string;
  // ... other fields
}}

// Legacy contract (kept for backward compat during migration)
export interface {entity_name}Legacy {{
  {old_field}: string;
  // ... other fields
}}

/**
 * Normalizes both old and new field names to the new contract shape.
 * Use during the migration window. Remove after all consumers use the new contract.
 */
export function normalize{entity_name}(
  input: {entity_name}V2 | {entity_name}Legacy | Record<string, unknown>
): {entity_name}V2 {{
  const data = input as Record<string, unknown>;
  const value = data["{new_field}"] ?? data["{old_field}"];
  if (value === undefined) {{
    throw new Error(`Missing required field: '{new_field}' or '{old_field}'`);
  }}
  return {{
    ...data,
    {new_field}: value as string,
  }} as {entity_name}V2;
}}

/**
 * Adds the legacy field name to a response for backward compatibility.
 * Use in API responses during migration. Remove after sunset date.
 */
export function addLegacyField(entity: {entity_name}V2): {entity_name}V2 & {entity_name}Legacy {{
  return {{
    ...entity,
    {old_field}: entity.{new_field},  // backward-compat alias
  }};
}}
'''
        tests = f'''\
import {{ normalize{entity_name}, addLegacyField }} from "./adapter";

describe("{entity_name}Adapter", () => {{
  it("accepts old field name", () => {{
    const result = normalize{entity_name}({{ {old_field}: "value123" }});
    expect(result.{new_field}).toBe("value123");
  }});

  it("accepts new field name", () => {{
    const result = normalize{entity_name}({{ {new_field}: "value123" }});
    expect(result.{new_field}).toBe("value123");
  }});

  it("new field takes precedence when both present", () => {{
    const result = normalize{entity_name}({{ {old_field}: "old", {new_field}: "new" }});
    expect(result.{new_field}).toBe("new");
  }});

  it("throws when neither field present", () => {{
    expect(() => normalize{entity_name}({{}})).toThrow();
  }});

  it("addLegacyField includes both field names", () => {{
    const result = addLegacyField({{ {new_field}: "value123" }});
    expect(result.{new_field}).toBe("value123");
    expect(result.{old_field}).toBe("value123");
  }});
}});
'''
        return GeneratedCode(
            language="typescript",
            adapter_code=adapter,
            test_code=tests,
            description=f"TypeScript adapter bridging '{old_field}' to '{new_field}' for {entity_name}.",
        )

    return _generate_generic_adapter("typescript", old_contract, new_contract, old_field, new_field, entity_name)


# ---------------------------------------------------------------------------
# Generic fallback
# ---------------------------------------------------------------------------

def _generate_generic_adapter(
    language: str, old_contract: str, new_contract: str,
    old_field: str, new_field: str, entity_name: str,
) -> GeneratedCode:
    return GeneratedCode(
        language=language,
        adapter_code=f"// Adapter for {entity_name}: {old_field} -> {new_field}\n// Old contract:\n// {old_contract}\n// New contract:\n// {new_contract}\n",
        test_code=f"// Tests for {entity_name} adapter\n",
        description=f"Generic adapter template for {entity_name} ({language}).",
        warnings=["Generic template — review and customize before use."],
    )


def _to_camel_case(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])
