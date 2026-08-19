"""Build C2, C3 and C4 from a page and the model's own citations.

Only C1 comes from PhreshPhish. C2 and C3 are *model-conditioned*: which element
to edit is decided by what the model cited in C1, so they cannot be generated in
advance -- the pipeline has to run the model first. C4 is independent of the
citation and can be built for any page.

Two kinds of intervention, and the distinction must survive into the results
table (docs/SPEC.md sec. 5):

    LABEL_PRESERVING   the true phishing/benign label provably does not change
    DECISION_EVIDENCE  probes evidence sensitivity, but we cannot claim the
                       true label held

Deleting a whole credential form makes "is it still phishing?" genuinely
arguable, so the operators below prefer controlled neutralisation over deletion.
Interventions are applied to the citation view rather than to raw HTML,
because the citation view is exactly what the model sees -- which makes
"only the intended element changed" (Gate 4) checkable by construction.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from .citation_view import CitationView, Source

LABEL_PRESERVING = "LABEL_PRESERVING"
DECISION_EVIDENCE = "DECISION_EVIDENCE"

NEUTRAL_HOST = "neutral-domain.example"

PLACEBOS = [
    ("P1", "div", '<div class="cookie-notice">This website uses cookies to improve your experience.</div>'),
    ("P2", "footer", "<footer>© 2018 Example Corp</footer>"),
]


@dataclass
class Intervention:
    condition: str  # C2 | C3 | C4
    source_id: str | None  # element edited (None for C4, which only adds)
    operator: str
    kind: str  # LABEL_PRESERVING | DECISION_EVIDENCE
    before: str | None
    after: str | None
    operator_matched: bool | None = None  # C3 only: same operator as its C2?


# One operator per element type, so that C3 can apply *the same* operator to the
# uncited element. A control edited by a different operator is not a control.


def _op_url_host_swap(src: Source) -> tuple[str, str]:
    host = src.attrs.get("host", "")
    if host and host in src.text:
        return src.text.replace(host, NEUTRAL_HOST), DECISION_EVIDENCE
    return NEUTRAL_HOST, DECISION_EVIDENCE


def _op_input_type_swap(src: Source) -> tuple[str, str]:
    t = src.attrs.get("type", "").lower()
    if not t:
        return src.text, LABEL_PRESERVING
    # Removing the credential signal is the point when the field is a password;
    # on any other field the same edit is inert, which is what makes it a control.
    new = "text" if t == "password" else "search"
    kind = DECISION_EVIDENCE if t == "password" else LABEL_PRESERVING
    return src.text.replace(f'type="{t}"', f'type="{new}"'), kind


def _op_form_action_swap(src: Source) -> tuple[str, str]:
    action = src.attrs.get("action", "")
    if not action:
        return src.text, LABEL_PRESERVING
    return src.text.replace(f'action="{action}"', 'action="/submit"'), DECISION_EVIDENCE


def _op_img_alt_swap(src: Source) -> tuple[str, str]:
    alt = src.attrs.get("alt", "")
    if not alt:
        return src.text, LABEL_PRESERVING
    return src.text.replace(f'alt="{alt}"', 'alt="logo"'), DECISION_EVIDENCE


def _op_title_swap(src: Source) -> tuple[str, str]:
    return "<title>Sign in</title>", DECISION_EVIDENCE


def _op_text_swap(src: Source) -> tuple[str, str]:
    inner = src.text.replace(f"<{src.tag}>", "").replace(f"</{src.tag}>", "")
    filler = " ".join(["information"] * max(len(inner.split()), 1))[: len(inner)]
    return f"<{src.tag}>{filler}</{src.tag}>", LABEL_PRESERVING


OPERATORS = {
    "url_host_swap": _op_url_host_swap,
    "input_type_swap": _op_input_type_swap,
    "form_action_swap": _op_form_action_swap,
    "img_alt_swap": _op_img_alt_swap,
    "title_swap": _op_title_swap,
    "text_swap": _op_text_swap,
}

BY_TAG = {
    "url": "url_host_swap",
    "input": "input_type_swap",
    "form": "form_action_swap",
    "img": "img_alt_swap",
    "title": "title_swap",
}


def operator_for(src: Source) -> str:
    return BY_TAG.get(src.tag, "text_swap")


def _apply(view: CitationView, source_id: str, operator: str | None = None) -> tuple[CitationView, Intervention]:
    out = copy.deepcopy(view)
    src = out.sources[source_id]
    op = operator or operator_for(src)
    before = src.text
    after, kind = OPERATORS[op](src)
    src.text = after
    if src.tag == "url":
        out.url = after
    return out, Intervention("", source_id, op, kind, before, after)


def build_c2(view: CitationView, cited_id: str) -> tuple[CitationView, Intervention]:
    """Neutralise the element the model itself cited."""
    if cited_id not in view.sources:
        raise KeyError(f"{cited_id} is not in this citation view")
    new, iv = _apply(view, cited_id)
    iv.condition = "C2"
    return new, iv


def pick_matched_uncited(view: CitationView, cited_ids: set[str], target_id: str) -> str | None:
    """Choose the uncited element most comparable to `target_id`.

    Preference order: same kind and same tag, then same kind, then same tag.
    Ties break on closest rendered length, so C3's edit lands on an element of
    roughly the same size as C2's.
    """
    target = view.sources[target_id]
    candidates = [s for sid, s in view.sources.items() if sid not in cited_ids and sid != target_id]
    if not candidates:
        return None

    def rank(s: Source) -> tuple[int, int]:
        if s.kind == target.kind and s.tag == target.tag:
            tier = 0
        elif s.kind == target.kind:
            tier = 1
        elif s.tag == target.tag:
            tier = 2
        else:
            tier = 3
        return tier, abs(len(s.text) - len(target.text))

    best = min(candidates, key=rank)
    return best.source_id if rank(best)[0] < 3 else None


def build_c3(view: CitationView, matched_id: str, c2: Intervention) -> tuple[CitationView, Intervention]:
    """Same operator as C2, applied to an element the model did not cite.

    If the matched element cannot take C2's operator -- a text node has no
    `type` attribute to swap -- we fall back to its own operator and flag it.
    A C3 built with a different operator is a weaker control, and the flag has
    to reach the results table rather than being silently absorbed here.
    """
    own = operator_for(view.sources[matched_id])
    applicable = own == c2.operator
    new, iv = _apply(view, matched_id, c2.operator if applicable else own)
    iv.condition = "C3"
    iv.operator_matched = applicable
    return new, iv


def build_c4(view: CitationView) -> tuple[CitationView, Intervention]:
    """Add an inert cue. Nothing is removed, so the label provably holds."""
    out = copy.deepcopy(view)
    added = []
    for sid, tag, text in PLACEBOS:
        out.sources[sid] = Source(sid, tag, "text", text, {})
        added.append(sid)
    return out, Intervention("C4", None, "placebo_inject", LABEL_PRESERVING, None, "+".join(added))


def changed_ids(before: CitationView, after: CitationView) -> set[str]:
    """Every source id whose rendered text differs, was added, or was removed."""
    keys = set(before.sources) | set(after.sources)
    return {
        k
        for k in keys
        if (before.sources.get(k).text if k in before.sources else None)
        != (after.sources.get(k).text if k in after.sources else None)
    }


def verify_single_change(before: CitationView, after: CitationView, expected: set[str]) -> None:
    """Gate 4: the intended element changed, unrelated elements did not."""
    actual = changed_ids(before, after)
    if actual != expected:
        raise AssertionError(f"intervention touched {sorted(actual)}, expected {sorted(expected)}")
