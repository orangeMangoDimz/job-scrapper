from __future__ import annotations

import re

from bs4 import BeautifulSoup
from markdownify import ATX, MarkdownConverter

_DROPPED_TAGS = ("img", "script", "style", "noscript", "iframe", "svg")
_HTML_TAG_RE = re.compile(
    r"</?(?:p|div|br|hr|ul|ol|li|h[1-6]|b|strong|i|em|u|a|span|font|small|sub|sup"
    r"|table|thead|tbody|tr|td|th|section|article|blockquote|pre|code)(?=[\s/>])[^>]*>",
    re.IGNORECASE,
)
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SETEXT_UNDERLINE_RE = re.compile(r"(?<=[^\n]\n)([-=]+)$", re.MULTILINE)
_LINE_MARKER_RE = re.compile(r"(\s|^)(#{1,6}|[-=+>]+)(?=\s|$)")
_ORDERED_MARKER_RE = re.compile(r"(\s|^)(\d{1,9})([.)])(?=\s|$)")
_EDGE_UNDERSCORE_RE = re.compile(r"(?<!\w)_|_(?!\w)")


class _JobMarkdownConverter(MarkdownConverter):
    def escape(self, text: str, parent_tags: set[str]) -> str:
        if not text:
            return ""
        text = text.replace("*", r"\*")
        text = _EDGE_UNDERSCORE_RE.sub(r"\\_", text)
        text = _LINE_MARKER_RE.sub(r"\1\\\2", text)
        return _ORDERED_MARKER_RE.sub(r"\1\2\\\3", text)


_CONVERTER = _JobMarkdownConverter(heading_style=ATX, bullets="-")


def _tidy(markdown: str) -> str | None:
    markdown = _TRAILING_WS_RE.sub("\n", markdown)
    markdown = _BLANK_LINES_RE.sub("\n\n", markdown).strip()
    return markdown or None


def _plain_text_to_markdown(text: str) -> str | None:
    text = text.replace("\r\n", "\n").replace("\r", "\n") + "\n"
    tidied = _tidy(text)
    return _SETEXT_UNDERLINE_RE.sub(r"\\\1", tidied) if tidied else None


def html_to_markdown(html: str | None) -> str | None:
    """Convert a job description HTML fragment to Markdown; plain text keeps its layout."""
    if not html or not html.strip():
        return None
    if not _HTML_TAG_RE.search(html):
        return _plain_text_to_markdown(html)
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_DROPPED_TAGS):
        tag.decompose()
    return _tidy(_CONVERTER.convert_soup(soup))
