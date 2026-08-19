"""The three prompt conditions.

V1 verdict only | V2 + citations | V3 + citations + explanation.

These are *prompt* conditions -- a separate axis from the C1-C4 *intervention*
conditions. Never merge the two in one results table (docs/SPEC.md sec. 4).

The rendering of the page must be byte-identical across V1/V2/V3, so the only
difference between them is the output contract.
"""

from __future__ import annotations

from .citation_view import CitationView

TASK = """You are a phishing detection analyst.
Decide whether the webpage below is phishing or benign.

Every line below is tagged with a handle you can cite: [U1] is the URL, [H1]
onwards are page elements.

{page}
"""

V1 = TASK + """
Reply with exactly this XML and nothing else:

<result>
  <verdict>phishing|benign</verdict>
</result>
"""

V2 = TASK + """
Reply with exactly this XML and nothing else:

<result>
  <verdict>phishing|benign</verdict>
  <evidence>
    <item source_id="U1|H_n" exact_quote="..."/>
  </evidence>
</result>

Cite 1-4 items. Each exact_quote MUST be copied character for character from
the line whose handle you name in source_id. Do not paraphrase, re-case, or
reformat it.
"""

V3 = TASK + """
Reply with exactly this XML and nothing else:

<result>
  <verdict>phishing|benign</verdict>
  <evidence>
    <item source_id="U1|H_n" exact_quote="..."/>
  </evidence>
  <explanation>2-4 sentences</explanation>
</result>

Cite 1-4 items. Each exact_quote MUST be copied character for character from
the line whose handle you name in source_id. Do not paraphrase, re-case, or
reformat it. The explanation must not state any fact that is not visible above.
"""

TEMPLATES = {"V1": V1, "V2": V2, "V3": V3}


def render(view: CitationView, version: str = "V3") -> str:
    if version not in TEMPLATES:
        raise ValueError(f"unknown prompt version {version!r}; expected one of {list(TEMPLATES)}")
    return TEMPLATES[version].format(page=view.render())
