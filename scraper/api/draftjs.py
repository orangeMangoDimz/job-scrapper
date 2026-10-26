from __future__ import annotations

import json

_PREFIX_BY_TYPE = {
    "unordered-list-item": "- ",
    "ordered-list-item": "1. ",
    "header-one": "# ",
    "header-two": "## ",
    "header-three": "### ",
}


def draftjs_to_markdown(raw: str | None) -> str | None:
    """Glints stores descriptions as Draft.js JSON: {"blocks": [{"text", "type"}]}."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    blocks = payload.get("blocks") if isinstance(payload, dict) else None
    if not isinstance(blocks, list):
        return None
    lines = [
        _PREFIX_BY_TYPE.get(str(block.get("type")), "") + block["text"].strip()
        for block in blocks
        if isinstance(block, dict) and isinstance(block.get("text"), str) and block["text"].strip()
    ]
    return "\n".join(lines) or None
