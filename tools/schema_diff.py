"""
Schema diffing tool for CARA.

Parses and diffs SQL DDL, Protobuf, and JSON Schema definitions,
producing a normalized list of SchemaChange objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChangeType(Enum):
    FIELD_ADDED = "FIELD_ADDED"
    FIELD_REMOVED = "FIELD_REMOVED"
    FIELD_RENAMED = "FIELD_RENAMED"
    TYPE_CHANGED = "TYPE_CHANGED"
    NULLABLE_CHANGED = "NULLABLE_CHANGED"
    TABLE_ADDED = "TABLE_ADDED"
    TABLE_REMOVED = "TABLE_REMOVED"
    TABLE_RENAMED = "TABLE_RENAMED"
    INDEX_CHANGED = "INDEX_CHANGED"
    DEFAULT_CHANGED = "DEFAULT_CHANGED"
    CONSTRAINT_CHANGED = "CONSTRAINT_CHANGED"


@dataclass
class SchemaChange:
    change_type: ChangeType
    table_or_message: str
    element_name: str
    old_value: str | None = None
    new_value: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "change_type": self.change_type.value,
            "table_or_message": self.table_or_message,
            "element_name": self.element_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "metadata": self.metadata,
        }


def parse_schema_diff(
    old_schema: str,
    new_schema: str,
    schema_type: str = "sql",
) -> list[SchemaChange]:
    """
    Diff two schema definitions and return a list of changes.

    Args:
        old_schema: The original schema string.
        new_schema: The updated schema string.
        schema_type: One of 'sql', 'protobuf', 'json_schema'.

    Returns:
        A list of SchemaChange objects describing every detected change.
    """
    parsers = {
        "sql": _diff_sql,
        "protobuf": _diff_protobuf,
        "json_schema": _diff_json_schema,
    }
    parser = parsers.get(schema_type)
    if parser is None:
        raise ValueError(f"Unsupported schema_type: {schema_type}. Use sql, protobuf, or json_schema.")
    return parser(old_schema, new_schema)


# ---------------------------------------------------------------------------
# SQL DDL diffing
# ---------------------------------------------------------------------------

def _parse_sql_tables(ddl: str) -> dict[str, dict[str, str]]:
    """Parse CREATE TABLE statements into {table_name: {col_name: col_def}}."""
    tables: dict[str, dict[str, str]] = {}
    # Match CREATE TABLE blocks (handles multi-line, case-insensitive)
    table_pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?(\w+)[`\"']?\s*\((.*?)\);",
        re.IGNORECASE | re.DOTALL,
    )
    col_pattern = re.compile(r"^\s*[`\"']?(\w+)[`\"']?\s+(.+?)(?:,\s*$|$)", re.MULTILINE)

    for m in table_pattern.finditer(ddl):
        table_name = m.group(1).lower()
        body = m.group(2)
        cols: dict[str, str] = {}
        for cm in col_pattern.finditer(body):
            col_name = cm.group(1).lower()
            # Skip constraint keywords
            if col_name.upper() in {"PRIMARY", "UNIQUE", "INDEX", "KEY", "CONSTRAINT", "FOREIGN", "CHECK"}:
                continue
            cols[col_name] = cm.group(2).strip().rstrip(",").strip()
        tables[table_name] = cols
    return tables


def _diff_sql(old_ddl: str, new_ddl: str) -> list[SchemaChange]:
    old_tables = _parse_sql_tables(old_ddl)
    new_tables = _parse_sql_tables(new_ddl)
    changes: list[SchemaChange] = []

    # Detect added/removed tables
    for t in set(new_tables) - set(old_tables):
        changes.append(SchemaChange(ChangeType.TABLE_ADDED, t, t))
    for t in set(old_tables) - set(new_tables):
        changes.append(SchemaChange(ChangeType.TABLE_REMOVED, t, t))

    # Diff columns within shared tables
    for table in set(old_tables) & set(new_tables):
        old_cols = old_tables[table]
        new_cols = new_tables[table]

        for col in set(new_cols) - set(old_cols):
            nullable = "NOT NULL" not in new_cols[col].upper()
            changes.append(SchemaChange(
                ChangeType.FIELD_ADDED, table, col,
                new_value=new_cols[col],
                metadata={"nullable": nullable},
            ))
        for col in set(old_cols) - set(new_cols):
            changes.append(SchemaChange(
                ChangeType.FIELD_REMOVED, table, col, old_value=old_cols[col],
            ))
        for col in set(old_cols) & set(new_cols):
            old_def = old_cols[col]
            new_def = new_cols[col]
            if old_def == new_def:
                continue
            old_type = _extract_sql_type(old_def)
            new_type = _extract_sql_type(new_def)
            old_nullable = "NOT NULL" not in old_def.upper()
            new_nullable = "NOT NULL" not in new_def.upper()

            if old_type != new_type:
                changes.append(SchemaChange(
                    ChangeType.TYPE_CHANGED, table, col,
                    old_value=old_type, new_value=new_type,
                ))
            if old_nullable != new_nullable:
                is_pk = "PRIMARY KEY" in old_def.upper() or "PRIMARY KEY" in new_def.upper()
                changes.append(SchemaChange(
                    ChangeType.NULLABLE_CHANGED, table, col,
                    old_value=str(old_nullable), new_value=str(new_nullable),
                    metadata={"primary_key": is_pk},
                ))
    return changes


def _extract_sql_type(col_def: str) -> str:
    """Extract the data type token from a column definition string."""
    return col_def.split()[0].upper() if col_def.split() else col_def.upper()


# ---------------------------------------------------------------------------
# Protobuf diffing
# ---------------------------------------------------------------------------

def _parse_proto_messages(proto: str) -> dict[str, dict[str, tuple[str, int]]]:
    """Parse proto3 into {message: {field_name: (type, field_number)}}."""
    messages: dict[str, dict[str, tuple[str, int]]] = {}
    msg_pattern = re.compile(r"message\s+(\w+)\s*\{([^}]*)\}", re.DOTALL)
    field_pattern = re.compile(r"(?:optional|repeated|required)?\s*(\w+)\s+(\w+)\s*=\s*(\d+)\s*;")

    for m in msg_pattern.finditer(proto):
        msg_name = m.group(1)
        body = m.group(2)
        fields: dict[str, tuple[str, int]] = {}
        for fm in field_pattern.finditer(body):
            ftype, fname, fnum = fm.group(1), fm.group(2), int(fm.group(3))
            fields[fname] = (ftype, fnum)
        messages[msg_name] = fields
    return messages


def _diff_protobuf(old_proto: str, new_proto: str) -> list[SchemaChange]:
    old_msgs = _parse_proto_messages(old_proto)
    new_msgs = _parse_proto_messages(new_proto)
    changes: list[SchemaChange] = []

    for msg in set(new_msgs) - set(old_msgs):
        changes.append(SchemaChange(ChangeType.TABLE_ADDED, msg, msg))
    for msg in set(old_msgs) - set(new_msgs):
        changes.append(SchemaChange(ChangeType.TABLE_REMOVED, msg, msg))

    for msg in set(old_msgs) & set(new_msgs):
        old_fields = old_msgs[msg]
        new_fields = new_msgs[msg]

        for f in set(new_fields) - set(old_fields):
            ftype, fnum = new_fields[f]
            changes.append(SchemaChange(
                ChangeType.FIELD_ADDED, msg, f, new_value=ftype,
                metadata={"field_number": fnum},
            ))
        for f in set(old_fields) - set(new_fields):
            ftype, fnum = old_fields[f]
            changes.append(SchemaChange(
                ChangeType.FIELD_REMOVED, msg, f, old_value=ftype,
                metadata={"field_number": fnum},
            ))
        for f in set(old_fields) & set(new_fields):
            old_type, old_num = old_fields[f]
            new_type, new_num = new_fields[f]
            if old_type != new_type:
                changes.append(SchemaChange(
                    ChangeType.TYPE_CHANGED, msg, f,
                    old_value=old_type, new_value=new_type,
                ))
    return changes


# ---------------------------------------------------------------------------
# JSON Schema diffing
# ---------------------------------------------------------------------------

def _diff_json_schema(old_schema_str: str, new_schema_str: str) -> list[SchemaChange]:
    import json
    old = json.loads(old_schema_str)
    new = json.loads(new_schema_str)
    changes: list[SchemaChange] = []

    root_title = new.get("title", old.get("title", "root"))

    def diff_properties(
        old_props: dict, new_props: dict,
        old_required: list, new_required: list,
        parent: str,
    ) -> None:
        for prop in set(new_props) - set(old_props):
            changes.append(SchemaChange(
                ChangeType.FIELD_ADDED, parent, prop,
                new_value=str(new_props[prop].get("type", "any")),
            ))
        for prop in set(old_props) - set(new_props):
            changes.append(SchemaChange(
                ChangeType.FIELD_REMOVED, parent, prop,
                old_value=str(old_props[prop].get("type", "any")),
            ))
        for prop in set(old_props) & set(new_props):
            old_type = old_props[prop].get("type")
            new_type = new_props[prop].get("type")
            if old_type != new_type:
                changes.append(SchemaChange(
                    ChangeType.TYPE_CHANGED, parent, prop,
                    old_value=str(old_type), new_value=str(new_type),
                ))
            was_required = prop in old_required
            is_required = prop in new_required
            if was_required != is_required:
                changes.append(SchemaChange(
                    ChangeType.NULLABLE_CHANGED, parent, prop,
                    old_value=str(not was_required), new_value=str(not is_required),
                ))

    diff_properties(
        old.get("properties", {}),
        new.get("properties", {}),
        old.get("required", []),
        new.get("required", []),
        root_title,
    )
    return changes
