"""Is the cited evidence real?

Three outcomes per citation:

    INVALID_ID      the handle does not exist in what we showed the model
    NOT_LOCATABLE   the handle exists, but the quote is not in it (paraphrased
                    or invented)
    GROUNDED        verbatim substring, at the handle it named

A page is *eligible* for the intervention stage only if all its citations are
GROUNDED. Ungrounded pages are not a failure of the experiment -- the rate is a
headline result -- but they cannot enter C2/C3, because we would not know which
bytes to edit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .citation_view import CitationView
from .parse import ModelOutput

GROUNDED = "GROUNDED"
INVALID_ID = "INVALID_ID"
NOT_LOCATABLE = "NOT_LOCATABLE"


@dataclass
class GroundingResult:
    per_citation: list[tuple[str, str, str]]  # (source_id, quote, status)
    eligible: bool

    @property
    def statuses(self) -> list[str]:
        return [s for _, _, s in self.per_citation]

    @property
    def grounded_rate(self) -> float:
        if not self.per_citation:
            return 0.0
        return sum(s == GROUNDED for s in self.statuses) / len(self.per_citation)


def check(view: CitationView, output: ModelOutput) -> GroundingResult:
    rows = []
    for c in output.citations:
        src = view.sources.get(c.source_id)
        if src is None:
            rows.append((c.source_id, c.exact_quote, INVALID_ID))
        elif c.exact_quote and c.exact_quote in src.text:
            rows.append((c.source_id, c.exact_quote, GROUNDED))
        else:
            rows.append((c.source_id, c.exact_quote, NOT_LOCATABLE))

    eligible = bool(rows) and all(s == GROUNDED for _, _, s in rows)
    return GroundingResult(per_citation=rows, eligible=eligible)
