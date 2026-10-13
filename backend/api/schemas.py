"""
The JSON Schemas (Draft 2020-12) of the two deliverables, in backend/schemas:
served as files, and folded into the public API's OpenAPI document so its
docs describe exactly what the tests validate responses against.
"""
from __future__ import annotations

import json
import os

from fastapi import HTTPException
from fastapi.responses import FileResponse

from . import settings

SUFFIX = ".schema.json"


def names() -> list[str]:
    return sorted(f[:-len(SUFFIX)] for f in os.listdir(settings.SCHEMAS_DIR) if f.endswith(SUFFIX))


def response(name: str) -> FileResponse:
    """The schema file `name` (also accepted as name.json / name.schema.json)."""
    name = name.removesuffix(SUFFIX).removesuffix(".json")
    if name not in names():
        raise HTTPException(404, f"Schemas: {names()}")
    return FileResponse(os.path.join(settings.SCHEMAS_DIR, name + SUFFIX), media_type="application/schema+json")


def load(name: str) -> dict:
    with open(os.path.join(settings.SCHEMAS_DIR, name + SUFFIX), encoding="utf-8") as fh:
        return json.load(fh)


def openapi_components(name: str, component: str) -> dict[str, dict]:
    """Schema `name` as OpenAPI components: the root as `component`, each of
    its $defs as `component.def`. The files' own "#/$defs/x" references point
    inside the file, so they are rewritten to the hoisted components --
    Swagger UI does not resolve $defs relative to an embedded $id."""
    root = load(name)
    defs = root.pop("$defs", {})
    for key in ("$schema", "$id"):
        root.pop(key, None)

    def rewrite(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            out = {k: rewrite(v) for k, v in node.items()}
            if ref == "#":
                out["$ref"] = f"#/components/schemas/{component}"
            elif isinstance(ref, str) and ref.startswith("#/$defs/"):
                out["$ref"] = f"#/components/schemas/{component}.{ref[len('#/$defs/'):]}"
            return out
        if isinstance(node, list):
            return [rewrite(v) for v in node]
        return node

    return {component: rewrite(root), **{f"{component}.{k}": rewrite(v) for k, v in defs.items()}}
