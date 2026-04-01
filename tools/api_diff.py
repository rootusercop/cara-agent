"""
API contract diffing tool for CARA.

Diffs OpenAPI (REST), Protobuf (gRPC), and GraphQL schemas,
producing a normalized list of APIChange objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChangeType(Enum):
    ENDPOINT_ADDED = "ENDPOINT_ADDED"
    ENDPOINT_REMOVED = "ENDPOINT_REMOVED"
    PATH_CHANGED = "PATH_CHANGED"
    METHOD_CHANGED = "METHOD_CHANGED"
    REQUEST_FIELD_ADDED = "REQUEST_FIELD_ADDED"
    REQUEST_FIELD_REMOVED = "REQUEST_FIELD_REMOVED"
    REQUEST_FIELD_TYPE_CHANGED = "REQUEST_FIELD_TYPE_CHANGED"
    RESPONSE_FIELD_ADDED = "RESPONSE_FIELD_ADDED"
    RESPONSE_FIELD_REMOVED = "RESPONSE_FIELD_REMOVED"
    RESPONSE_FIELD_TYPE_CHANGED = "RESPONSE_FIELD_TYPE_CHANGED"
    STATUS_CODE_CHANGED = "STATUS_CODE_CHANGED"
    AUTH_CHANGED = "AUTH_CHANGED"
    RPC_ADDED = "RPC_ADDED"
    RPC_REMOVED = "RPC_REMOVED"


@dataclass
class APIChange:
    change_type: ChangeType
    endpoint_or_rpc: str
    field_or_param: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "change_type": self.change_type.value,
            "endpoint_or_rpc": self.endpoint_or_rpc,
            "field_or_param": self.field_or_param,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "metadata": self.metadata,
        }


def diff_api_contracts(
    old_spec: str,
    new_spec: str,
    spec_type: str = "openapi",
) -> list[APIChange]:
    """
    Diff two API specifications and return a normalized list of changes.

    Args:
        old_spec: The original API specification string.
        new_spec: The updated API specification string.
        spec_type: One of 'openapi', 'protobuf', 'graphql'.

    Returns:
        A list of APIChange objects.
    """
    differs = {
        "openapi": _diff_openapi,
        "protobuf": _diff_proto_services,
        "graphql": _diff_graphql,
    }
    differ = differs.get(spec_type)
    if differ is None:
        raise ValueError(f"Unsupported spec_type: {spec_type}. Use openapi, protobuf, or graphql.")
    return differ(old_spec, new_spec)


# ---------------------------------------------------------------------------
# OpenAPI diffing
# ---------------------------------------------------------------------------

def _load_yaml_or_json(text: str) -> dict:
    try:
        import yaml
        return yaml.safe_load(text)
    except Exception:
        import json
        return json.loads(text)


def _diff_openapi(old_text: str, new_text: str) -> list[APIChange]:
    old = _load_yaml_or_json(old_text)
    new = _load_yaml_or_json(new_text)
    changes: list[APIChange] = []

    old_paths: dict = old.get("paths", {})
    new_paths: dict = new.get("paths", {})

    for path in set(new_paths) - set(old_paths):
        for method in new_paths[path]:
            changes.append(APIChange(
                ChangeType.ENDPOINT_ADDED,
                f"{method.upper()} {path}",
            ))
    for path in set(old_paths) - set(new_paths):
        for method in old_paths[path]:
            changes.append(APIChange(
                ChangeType.ENDPOINT_REMOVED,
                f"{method.upper()} {path}",
            ))

    for path in set(old_paths) & set(new_paths):
        old_ops = old_paths[path]
        new_ops = new_paths[path]

        for method in set(new_ops) - set(old_ops):
            changes.append(APIChange(ChangeType.ENDPOINT_ADDED, f"{method.upper()} {path}"))
        for method in set(old_ops) - set(new_ops):
            changes.append(APIChange(ChangeType.ENDPOINT_REMOVED, f"{method.upper()} {path}"))

        for method in set(old_ops) & set(new_ops):
            endpoint = f"{method.upper()} {path}"
            old_op = old_ops[method] or {}
            new_op = new_ops[method] or {}

            # Diff request body fields
            old_req_props = _extract_request_properties(old_op, old)
            new_req_props = _extract_request_properties(new_op, new)
            for f in set(new_req_props) - set(old_req_props):
                changes.append(APIChange(ChangeType.REQUEST_FIELD_ADDED, endpoint, f, new_value=str(new_req_props[f])))
            for f in set(old_req_props) - set(new_req_props):
                changes.append(APIChange(ChangeType.REQUEST_FIELD_REMOVED, endpoint, f, old_value=str(old_req_props[f])))
            for f in set(old_req_props) & set(new_req_props):
                if old_req_props[f] != new_req_props[f]:
                    changes.append(APIChange(
                        ChangeType.REQUEST_FIELD_TYPE_CHANGED, endpoint, f,
                        old_value=str(old_req_props[f]), new_value=str(new_req_props[f]),
                    ))

            # Diff response fields (200 response)
            old_resp_props = _extract_response_properties(old_op, old, "200")
            new_resp_props = _extract_response_properties(new_op, new, "200")
            for f in set(new_resp_props) - set(old_resp_props):
                changes.append(APIChange(ChangeType.RESPONSE_FIELD_ADDED, endpoint, f, new_value=str(new_resp_props[f])))
            for f in set(old_resp_props) - set(new_resp_props):
                changes.append(APIChange(ChangeType.RESPONSE_FIELD_REMOVED, endpoint, f, old_value=str(old_resp_props[f])))
            for f in set(old_resp_props) & set(new_resp_props):
                if old_resp_props[f] != new_resp_props[f]:
                    changes.append(APIChange(
                        ChangeType.RESPONSE_FIELD_TYPE_CHANGED, endpoint, f,
                        old_value=str(old_resp_props[f]), new_value=str(new_resp_props[f]),
                    ))
    return changes


def _resolve_ref(ref_str: str, root: dict) -> dict:
    """Resolve a $ref string like '#/components/schemas/User' to the referenced object."""
    if not ref_str.startswith("#/"):
        return {}
    parts = ref_str.lstrip("#/").split("/")
    obj = root
    for p in parts:
        if isinstance(obj, dict):
            obj = obj.get(p, {})
        else:
            return {}
    return obj or {}


def _extract_request_properties(op: dict, root: dict) -> dict[str, Any]:
    props: dict[str, Any] = {}
    body = op.get("requestBody", {})
    content = body.get("content", {})
    for media_type in content.values():
        schema = media_type.get("schema", {})
        if "$ref" in schema:
            schema = _resolve_ref(schema["$ref"], root)
        props.update(schema.get("properties", {}))
    return props


def _extract_response_properties(op: dict, root: dict, status_code: str) -> dict[str, Any]:
    props: dict[str, Any] = {}
    responses = op.get("responses", {})
    resp = responses.get(status_code, responses.get(int(status_code), {}))
    content = resp.get("content", {})
    for media_type in content.values():
        schema = media_type.get("schema", {})
        if "$ref" in schema:
            schema = _resolve_ref(schema["$ref"], root)
        props.update(schema.get("properties", {}))
    return props


# ---------------------------------------------------------------------------
# Protobuf service diffing
# ---------------------------------------------------------------------------

def _parse_proto_services(proto: str) -> dict[str, set[str]]:
    """Parse proto3 into {service_name: {rpc_name}}."""
    services: dict[str, set[str]] = {}
    svc_pattern = re.compile(r"service\s+(\w+)\s*\{([^}]*)\}", re.DOTALL)
    rpc_pattern = re.compile(r"rpc\s+(\w+)\s*\(")
    for m in svc_pattern.finditer(proto):
        svc_name = m.group(1)
        body = m.group(2)
        rpcs = {rm.group(1) for rm in rpc_pattern.finditer(body)}
        services[svc_name] = rpcs
    return services


def _diff_proto_services(old_proto: str, new_proto: str) -> list[APIChange]:
    old_svcs = _parse_proto_services(old_proto)
    new_svcs = _parse_proto_services(new_proto)
    changes: list[APIChange] = []

    for svc in set(new_svcs) | set(old_svcs):
        old_rpcs = old_svcs.get(svc, set())
        new_rpcs = new_svcs.get(svc, set())
        for rpc in new_rpcs - old_rpcs:
            changes.append(APIChange(ChangeType.RPC_ADDED, f"{svc}.{rpc}"))
        for rpc in old_rpcs - new_rpcs:
            changes.append(APIChange(ChangeType.RPC_REMOVED, f"{svc}.{rpc}"))
    return changes


# ---------------------------------------------------------------------------
# GraphQL schema diffing
# ---------------------------------------------------------------------------

def _parse_graphql_types(schema: str) -> dict[str, dict[str, str]]:
    """Parse GraphQL SDL into {type_name: {field_name: field_type}}."""
    types: dict[str, dict[str, str]] = {}
    type_pattern = re.compile(r"type\s+(\w+)(?:\s+implements\s+\w+)?\s*\{([^}]*)\}", re.DOTALL)
    field_pattern = re.compile(r"(\w+)\s*(?:\([^)]*\))?\s*:\s*([\w!\[\]]+)")
    for m in type_pattern.finditer(schema):
        type_name = m.group(1)
        body = m.group(2)
        fields: dict[str, str] = {}
        for fm in field_pattern.finditer(body):
            fields[fm.group(1)] = fm.group(2)
        types[type_name] = fields
    return types


def _diff_graphql(old_schema: str, new_schema: str) -> list[APIChange]:
    old_types = _parse_graphql_types(old_schema)
    new_types = _parse_graphql_types(new_schema)
    changes: list[APIChange] = []

    for t in set(new_types) - set(old_types):
        changes.append(APIChange(ChangeType.ENDPOINT_ADDED, t))
    for t in set(old_types) - set(new_types):
        changes.append(APIChange(ChangeType.ENDPOINT_REMOVED, t))

    for t in set(old_types) & set(new_types):
        old_fields = old_types[t]
        new_fields = new_types[t]
        for f in set(new_fields) - set(old_fields):
            changes.append(APIChange(ChangeType.RESPONSE_FIELD_ADDED, t, f, new_value=new_fields[f]))
        for f in set(old_fields) - set(new_fields):
            changes.append(APIChange(ChangeType.RESPONSE_FIELD_REMOVED, t, f, old_value=old_fields[f]))
        for f in set(old_fields) & set(new_fields):
            if old_fields[f] != new_fields[f]:
                changes.append(APIChange(
                    ChangeType.RESPONSE_FIELD_TYPE_CHANGED, t, f,
                    old_value=old_fields[f], new_value=new_fields[f],
                ))
    return changes
