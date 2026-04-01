"""
Consumer tracing tool for CARA.

Traces all references to a schema element or API endpoint
across a codebase, returning file, line, and context.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class Consumer:
    file_path: str
    line_number: int
    service_name: str
    usage_context: str
    match_snippet: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "service_name": self.service_name,
            "usage_context": self.usage_context,
            "match_snippet": self.match_snippet,
        }


def trace_consumers(
    changed_element: str,
    codebase_path: str,
    extensions: list[str] | None = None,
) -> list[Consumer]:
    """
    Find all consumers of a schema element or endpoint across a codebase.

    Args:
        changed_element: The element to search for (e.g., 'user_id', '/api/v1/users').
        codebase_path: Root directory to search.
        extensions: File extensions to scan. Defaults to common source files.

    Returns:
        A list of Consumer objects with file, line, and context.
    """
    if extensions is None:
        extensions = [".py", ".kt", ".java", ".ts", ".tsx", ".js", ".go", ".rb"]

    root = Path(codebase_path)
    consumers: list[Consumer] = []

    if not root.exists():
        return consumers

    for file_path in _walk_source_files(root, extensions):
        try:
            file_consumers = _search_file(file_path, changed_element, root)
            consumers.extend(file_consumers)
        except (OSError, UnicodeDecodeError):
            continue

    return consumers


def _walk_source_files(root: Path, extensions: list[str]) -> Iterator[Path]:
    skip_dirs = {".git", "node_modules", "__pycache__", ".gradle", "build", "dist", "target", ".idea"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for filename in filenames:
            if any(filename.endswith(ext) for ext in extensions):
                yield Path(dirpath) / filename


def _search_file(file_path: Path, element: str, root: Path) -> list[Consumer]:
    consumers: list[Consumer] = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return consumers

    lines = text.splitlines()
    service_name = _infer_service_name(file_path, root)

    # Build search patterns: exact word boundary match + quoted string match
    patterns = [
        re.compile(r"\b" + re.escape(element) + r"\b"),
        re.compile(r'["\']' + re.escape(element) + r'["\']'),
        # snake_case / camelCase variants
        re.compile(re.escape(element.replace("_", "")), re.IGNORECASE),
    ]

    for line_idx, line in enumerate(lines, start=1):
        for pattern in patterns:
            if pattern.search(line):
                context = _classify_usage_context(line, file_path)
                consumers.append(Consumer(
                    file_path=str(file_path),
                    line_number=line_idx,
                    service_name=service_name,
                    usage_context=context,
                    match_snippet=line.strip()[:200],
                ))
                break  # One Consumer per line

    # Try AST-level search for Python files
    if file_path.suffix == ".py":
        ast_consumers = _python_ast_search(text, element, file_path, service_name, lines)
        # Merge: add AST-found consumers not already found by regex
        existing_lines = {c.line_number for c in consumers}
        for c in ast_consumers:
            if c.line_number not in existing_lines:
                consumers.append(c)

    return consumers


def _python_ast_search(
    source: str, element: str, file_path: Path, service_name: str, lines: list[str]
) -> list[Consumer]:
    consumers: list[Consumer] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return consumers

    for node in ast.walk(tree):
        # Attribute access: obj.element
        if isinstance(node, ast.Attribute) and node.attr == element:
            ln = node.lineno
            consumers.append(Consumer(
                file_path=str(file_path),
                line_number=ln,
                service_name=service_name,
                usage_context="attribute_access",
                match_snippet=lines[ln - 1].strip()[:200] if ln <= len(lines) else "",
            ))
        # Dict key: {"element": ...}
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == element:
            ln = node.lineno
            consumers.append(Consumer(
                file_path=str(file_path),
                line_number=ln,
                service_name=service_name,
                usage_context="dict_key_or_string_literal",
                match_snippet=lines[ln - 1].strip()[:200] if ln <= len(lines) else "",
            ))
    return consumers


def _infer_service_name(file_path: Path, root: Path) -> str:
    """Infer service name from directory structure."""
    try:
        rel = file_path.relative_to(root)
        parts = rel.parts
        # Typically: services/<service_name>/... or <service_name>/src/...
        if len(parts) >= 2:
            for i, part in enumerate(parts):
                if part in {"services", "src", "apps", "packages"}:
                    return parts[i + 1] if i + 1 < len(parts) else parts[0]
            return parts[0]
    except ValueError:
        pass
    return file_path.parent.name


def _classify_usage_context(line: str, file_path: Path) -> str:
    """Classify how the element is being used based on line content."""
    line_lower = line.lower().strip()
    if any(kw in line_lower for kw in ["class ", "struct ", "interface ", "data class"]):
        return "model_definition"
    if any(kw in line_lower for kw in ["def ", "fun ", "function ", "public ", "private "]):
        return "function_definition"
    if any(kw in line_lower for kw in ["import ", "from ", "require("]):
        return "import"
    if any(kw in line_lower for kw in ["select ", "insert ", "update ", "delete ", "from ", "where "]):
        return "sql_query"
    if any(kw in line_lower for kw in ["json", "serialize", "deserialize", "marshal", "unmarshal"]):
        return "serialization"
    if any(kw in line_lower for kw in ["test", "assert", "expect", "should"]):
        return "test"
    if "=" in line:
        return "assignment"
    return "general_reference"
