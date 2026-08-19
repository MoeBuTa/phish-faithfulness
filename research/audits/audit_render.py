"""Which HTML rendering can the study actually afford, WITHOUT reintroducing the shortcut?

Two constraints pull opposite ways.
  cost      raw original.html is a median ~22k tokens and a p95 of 236k-455k; only 59.7% of
            pages fit a 32k window, and the proposed condition grid comes to ~267M input
            tokens per model. Not affordable.
  validity  visible text is ~135 tokens (phish) vs ~1204 (legit) and that 9x length gap is
            exactly the shortcut: visible-text length alone gives AUC 0.779, and a
            bag-of-words on it gives 0.960 on the full corpus.

So the input must be an intermediate rendering. This script measures, for each candidate,
BOTH the token cost and whether the trivial length shortcut comes back, on the same pages.
A rendering is only usable if it is affordable AND its length-only AUC is near 0.5.

Token counts use tiktoken when available and chars/4 otherwise; the ratio between variants
is what matters here, not the absolute number.
"""
import re
import sys
import zipfile

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from urllib.parse import urlsplit

sys.path.insert(0, ".")
from audit_html import visible
from audit_meta import reg

SCRIPT = re.compile(r"<script\b.*?</script>", re.I | re.S)
STYLE = re.compile(r"<style\b.*?</style>", re.I | re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
DATAURI = re.compile(r"""(["'(])\s*data:[^"')]{80,}(["')])""", re.I)
SVGPATH = re.compile(r"""\bd\s*=\s*["'][^"']{120,}["']""", re.I)
KEEP = {"href", "src", "action", "method", "type", "name", "id", "alt", "title",
        "placeholder", "value", "aria-label", "content", "property", "rel", "class"}
TAGRE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^<>]*?)?)(/?)>", re.S)
ATTRRE = re.compile(r"""([a-zA-Z_:@\-\.]+)\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+))""")


def v_raw(h):
    return h


def v_noassets(h):
    """Strip executable/style payloads and embedded binaries. Structure and text intact."""
    h = SCRIPT.sub("<script></script>", h)
    h = STYLE.sub("<style></style>", h)
    h = COMMENT.sub("", h)
    h = DATAURI.sub(r"\1data:TRUNCATED\2", h)
    h = SVGPATH.sub('d="TRUNCATED"', h)
    return re.sub(r"[ \t]{2,}", " ", h)


def v_skeleton(h):
    """noassets + drop every attribute outside the whitelist, and cap class values."""
    h = v_noassets(h)

    def fix(m):
        close, tag, attrs, selfclose = m.groups()
        if close:
            return f"</{tag}>"
        kept = []
        for a in ATTRRE.finditer(attrs or ""):
            k = a.group(1).lower()
            if k not in KEEP:
                continue
            val = a.group(3) or a.group(4) or a.group(5) or ""
            if k == "class":
                val = " ".join(val.split()[:3])
            if len(val) > 160:
                val = val[:160] + "..."
            kept.append(f'{k}="{val}"')
        s = " ".join(kept)
        return f"<{tag}{' ' + s if s else ''}{'/' if selfclose else ''}>"

    return TAGRE.sub(fix, h)


def v_visible(h):
    return visible(h)


VARIANTS = [("raw HTML", v_raw), ("no scripts/styles/data-URIs", v_noassets),
            ("skeleton (whitelisted attrs)", v_skeleton), ("visible text only", v_visible)]


def main():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        tok = lambda s: len(enc.encode(s, disallowed_special=()))
        print("tokeniser: tiktoken cl100k_base")
    except Exception:
        tok = lambda s: len(s) // 4
        print("tokeniser: chars/4 approximation (tiktoken unavailable)")

    rows = []
    for zf, lab in [("phishing_5001-5151.zip", 1), ("not-phishing_5001-5244.zip", 0)]:
        z = zipfile.ZipFile(zf)
        for s in sorted({n.split("/")[0] for n in z.namelist() if "/" in n}):
            nm = f"{s}/original.html"
            if nm not in z.namelist():
                continue
            rows.append((s, lab, z.read(nm).decode("utf-8", "replace")))
    meta = pd.concat([pd.read_csv("phishing.csv", low_memory=False),
                      pd.read_csv("not-phishing.csv", low_memory=False)])
    umap = meta.set_index("_id")["url"].to_dict()
    y = np.array([r[1] for r in rows])
    groups = [reg(urlsplit(str(umap.get(r[0], ""))).netloc) for r in rows]
    print(f"n={len(rows)}  phish={y.sum()}  legit={(1-y).sum()}\n")

    gss = GroupShuffleSplit(n_splits=1, test_size=0.35, random_state=20260812)
    tr, te = next(gss.split(rows, y, groups=groups))
    maj = max(np.bincount(y[te])) / len(te)

    print(f"{'rendering':32s} {'med tok':>9s} {'p95 tok':>9s} {'fit32k':>7s} "
          f"{'fit128k':>8s} {'len AUC':>8s} {'len acc':>8s}")
    print("-" * 90)
    for name, fn in VARIANTS:
        txts = [fn(r[2]) for r in rows]
        t = np.array([tok(x) for x in txts], float)
        L = np.array([len(x) for x in txts], float)[:, None]
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000))
        m.fit(L[tr], y[tr])
        auc = roc_auc_score(y[te], m.predict_proba(L[te])[:, 1])
        acc = accuracy_score(y[te], m.predict(L[te]))
        print(f"{name:32s} {np.median(t):9.0f} {np.percentile(t,95):9.0f} "
              f"{np.mean(t<=30768):6.1%} {np.mean(t<=129072):7.1%} "
              f"{auc:8.3f} {acc:8.3f}")
    print(f"{'':32s} {'':9s} {'':9s} {'':7s} {'':8s} {'(0.500':>8s} {maj:8.3f}{'=majority)':>1s}")

    print("\nCOST at 300 pages x k=5 samples x 8 conditions, per model:")
    for name, fn in VARIANTS:
        t = np.array([tok(fn(r[2])) for r in rows], float)
        print(f"  {name:32s} {np.median(t)*300*5*8/1e6:8.1f}M input tokens "
              f"(mean-based {np.mean(t)*300*5*8/1e6:8.1f}M)")


if __name__ == "__main__":
    main()
