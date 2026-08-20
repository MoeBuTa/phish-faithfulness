"""Rewrite a page into a *citation view*: a numbered list of elements the model
can point at, plus a lookup table we can check its quotes against.

Why this exists. If the model can only say "the login form", we cannot tell
which bytes it used and we cannot edit them. Giving every element a stable
handle (`U1`, `H1` ... `Hn`) turns a vague explanation into a machine-checkable
one -- and makes the intervention stage buildable at all. This is Gate 3 in
docs/SPEC.md.

The contract, which the rest of the pipeline depends on:

    the string rendered for `H7` in the prompt IS `sources["H7"].text`

so `grounding.py` can check a quote by plain substring, with no normalisation
and no second parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

MAX_ATTR = 120
MAX_TEXT = 200
DEFAULT_MAX_ELEMENTS = 120

# Tags whose *text* is worth quoting.
TEXT_TAGS = ("h1", "h2", "h3", "button", "label", "legend", "a", "p")

_WS = re.compile(r"\s+")


def _clean(value: str | None, limit: int) -> str:
    if not value:
        return ""
    return _WS.sub(" ", value).strip()[:limit]


@dataclass
class Source:
    """One citable element."""

    source_id: str
    tag: str
    kind: str  # domain | credential | brand | link | text
    text: str  # exactly what the prompt shows -- the quote target
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class CitationView:
    url: str
    sources: dict[str, Source]
    truncated: bool = False

    def render(self) -> str:
        """The block that goes into the prompt."""
        return "\n".join(f"[{s.source_id}] {s.text}" for s in self.sources.values())

    def ids_of_kind(self, kind: str) -> list[str]:
        return [sid for sid, s in self.sources.items() if s.kind == kind]


def _kind_of(tag: str, attrs: dict[str, str]) -> str:
    itype = attrs.get("type", "").lower()
    if tag == "input" and itype in ("password", "tel"):
        return "credential"
    if tag == "input" and itype in ("email", "text") and _looks_credential(attrs):
        return "credential"
    if tag == "form":
        return "credential"
    if tag in ("title", "img") or tag == "h1":
        return "brand"
    if tag == "meta" and attrs.get("name", "") in ("og:site_name", "og:title", "application-name"):
        return "brand"
    if tag == "a":
        return "link"
    return "text"


# Deliberately includes the identifiers Australian and UK banks actually use --
# "client number" (CommBank), "customer number", "member number" -- because a
# generic user/email/login list silently misclassifies those as ordinary text,
# and then C3 picks a control of the wrong type.
_CREDENTIAL_WORDS = (
    "user", "login", "logon", "email", "account", "pin", "card", "ssn",
    "client", "customer", "member", "passw", "credential",
)


def _looks_credential(attrs: dict[str, str]) -> bool:
    blob = " ".join(attrs.get(k, "") for k in ("name", "id", "placeholder")).lower()
    return any(w in blob for w in _CREDENTIAL_WORDS)


def _render(tag: str, attrs: dict[str, str], text: str) -> str:
    if tag == "title":
        return f"<title>{text}</title>"
    if tag == "meta":
        return f'<meta name="{attrs.get("name", "")}" content="{attrs.get("content", "")}">'
    if tag == "img":
        return f'<img src="{attrs.get("src", "")}" alt="{attrs.get("alt", "")}">'
    if tag == "form":
        return f'<form action="{attrs.get("action", "")}" method="{attrs.get("method", "get")}">'
    if tag == "input":
        parts = [f'{k}="{attrs[k]}"' for k in ("type", "name", "placeholder") if attrs.get(k)]
        return "<input " + " ".join(parts) + ">"
    if tag == "a":
        return f'<a href="{attrs.get("href", "")}">{text}</a>'
    return f"<{tag}>{text}</{tag}>"


def build(url: str, html: str, max_elements: int = DEFAULT_MAX_ELEMENTS) -> CitationView:
    """Build the citation view for one page."""
    soup = BeautifulSoup(html, "lxml")
    sources: dict[str, Source] = {}

    host = urlsplit(url).netloc or url
    sources["U1"] = Source("U1", "url", "domain", url, {"host": host})

    wanted = ("title", "meta", "img", "form", "input") + TEXT_TAGS
    n = 0
    truncated = False
    for el in soup.find_all(wanted):
        if n >= max_elements:
            truncated = True
            break

        raw = {k: v for k, v in el.attrs.items() if isinstance(v, str)}
        attrs = {k: _clean(v, MAX_ATTR) for k, v in raw.items()}
        if el.name == "meta" and "name" not in attrs and "property" in attrs:
            attrs["name"] = attrs["property"]

        text = _clean(el.get_text(" ", strip=True), MAX_TEXT)

        # Drop elements that carry nothing quotable.
        if el.name in TEXT_TAGS and not text:
            continue
        if el.name == "meta" and not attrs.get("content"):
            continue
        if el.name == "img" and not (attrs.get("src") or attrs.get("alt")):
            continue

        n += 1
        sid = f"H{n}"
        rendered = _render(el.name, attrs, text)
        sources[sid] = Source(sid, el.name, _kind_of(el.name, attrs), rendered, attrs)

    return CitationView(url=url, sources=sources, truncated=truncated)
