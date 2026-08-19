"""Parse the model's XML back into a record -- leniently, and without repairing
anything silently.

A 7B model will not emit well-formed XML every time. Malformed output is a
reported result (Gate 2), so every parse records *how* it was recovered, and
`raw` is always kept.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

_RESULT = re.compile(r"<result\b.*?</result>", re.S | re.I)
_VERDICT = re.compile(r"<verdict>\s*(phishing|benign)\s*</verdict>", re.I)
_EXPLANATION = re.compile(r"<explanation>(.*?)</explanation>", re.S | re.I)
# Attribute form: <item source_id="H3" exact_quote="..."/>
_ITEM_ATTR = re.compile(
    r'<item\b[^>]*\bsource_id\s*=\s*"([^"]+)"[^>]*\bexact_quote\s*=\s*"([^"]*)"[^>]*/?>', re.I
)
# Child-element form, with or without CDATA.
_ITEM_EL = re.compile(
    r"<item\b[^>]*>\s*<source_id>\s*(.*?)\s*</source_id>\s*"
    r"<exact_quote>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</exact_quote>",
    re.S | re.I,
)


@dataclass
class Citation:
    source_id: str
    exact_quote: str


@dataclass
class ModelOutput:
    verdict: str | None
    citations: list[Citation] = field(default_factory=list)
    explanation: str | None = None
    raw: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def well_formed(self) -> bool:
        return self.verdict is not None and not self.notes


def parse(raw: str) -> ModelOutput:
    out = ModelOutput(verdict=None, raw=raw)

    block = _RESULT.search(raw)
    if block:
        body = block.group(0)
    else:
        body = raw
        out.notes.append("no <result> wrapper")

    m = _VERDICT.search(body)
    if m:
        out.verdict = m.group(1).lower()
    else:
        out.notes.append("no parseable <verdict>")

    seen: set[tuple[str, str]] = set()
    for rx in (_ITEM_ATTR, _ITEM_EL):
        for sid, quote in rx.findall(body):
            key = (sid.strip(), html.unescape(quote).strip())
            if key in seen:
                continue
            seen.add(key)
            out.citations.append(Citation(*key))

    e = _EXPLANATION.search(body)
    if e:
        out.explanation = html.unescape(e.group(1)).strip()

    return out
