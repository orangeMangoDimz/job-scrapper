from __future__ import annotations

import json

from scraper.api.draftjs import draftjs_to_markdown


def _raw(*blocks: tuple[str, str]) -> str:
    return json.dumps({"blocks": [{"text": text, "type": kind} for text, kind in blocks]})


def test_paragraphs_and_lists():
    raw = _raw(
        ("Requirements", "header-three"),
        ("AWS experience", "unordered-list-item"),
        ("Terraform", "unordered-list-item"),
        ("Step one", "ordered-list-item"),
        ("Nice to have.", "unstyled"),
    )
    assert draftjs_to_markdown(raw) == (
        "### Requirements\n- AWS experience\n- Terraform\n1. Step one\nNice to have."
    )


def test_blank_blocks_are_skipped():
    assert draftjs_to_markdown(_raw(("", "unstyled"), ("Only", "unstyled"))) == "Only"


def test_invalid_input_returns_none():
    assert draftjs_to_markdown(None) is None
    assert draftjs_to_markdown("not json") is None
    assert draftjs_to_markdown(json.dumps({"blocks": []})) is None
