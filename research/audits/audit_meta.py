"""Day-1 shortcut audit on the Zenodo 8041387 metadata CSVs (all 10,395 sites).

The question this answers: how much of the phishing/legitimate decision is carried by
trivial channels that have nothing to do with the "structured evidence" we want to study?
If a char-ngram on the URL alone scores 0.95, then any LLM result on this corpus is
uninterpretable and the intervention design is measuring a URL classifier.

Splits are GROUPED BY REGISTRABLE DOMAIN. A random split leaks: the same host appears
many times (one crawl per page), so a random split lets the model memorise the host.
"""
import ast
import json
import re
import numpy as np
import pandas as pd
from collections import Counter
from urllib.parse import urlsplit

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 20260812


def reg(host):
    p = str(host).lower().split(".")
    return ".".join(p[-2:]) if len(p) >= 2 else str(host).lower()


def ntags(s):
    try:
        return len(ast.literal_eval(s)) if isinstance(s, str) else 0
    except Exception:
        return 0


def tagseq(s):
    try:
        return " ".join(ast.literal_eval(s)) if isinstance(s, str) else ""
    except Exception:
        return ""


def ncss(s):
    try:
        d = json.loads(s) if isinstance(s, str) else {}
        return len(d), sum(len(v) for v in d.values() if isinstance(v, list))
    except Exception:
        return 0, 0


def load():
    p = pd.read_csv("phishing.csv", low_memory=False)
    n = pd.read_csv("not-phishing.csv", low_memory=False)
    p["y"], n["y"] = 1, 0
    d = pd.concat([p, n.assign(brands=np.nan)], ignore_index=True)
    d["text"] = d["features.text"].fillna("").astype(str)
    d["tagseq"] = d["features.html"].map(tagseq)
    d["ntags"] = d["features.html"].map(ntags)
    d["url"] = d["url"].fillna("").astype(str)
    d["host"] = d["url"].map(lambda u: urlsplit(u).netloc)
    d["group"] = d["host"].map(reg)
    d["age"] = pd.to_numeric(d["whois_domain_age"], errors="coerce").fillna(-1)
    d["assets"] = pd.to_numeric(d["assets_downloaded"], errors="coerce").fillna(-1)
    css = d["features.css"].map(ncss)
    d["ncss_prop"] = [c[0] for c in css]
    d["ncss_val"] = [c[1] for c in css]
    return d


def handfeats(d):
    X = np.column_stack([
        d["text"].str.len(), d["ntags"], d["age"], d["assets"],
        d["ncss_prop"], d["ncss_val"], d["url"].str.len(),
        d["url"].str.count(r"[.]"), d["url"].str.count("-"),
        (d["security_state"].astype(str) == "secure").astype(int),
        (d["protocol"].astype(str) == "h2").astype(int),
    ]).astype(float)
    return np.nan_to_num(X)


def run(name, kind, data, y, tr, te):
    if kind == "num":
        X = np.nan_to_num(np.asarray(data, dtype=float))
        if X.ndim == 1:
            X = X[:, None]
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000))
        m.fit(X[tr], y[tr])
        pr, sc = m.predict(X[te]), m.predict_proba(X[te])[:, 1]
    else:
        v = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                            min_df=3, max_features=200000) if kind == "char" else \
            TfidfVectorizer(analyzer="word", ngram_range=(1, 3), min_df=3, max_features=200000)
        Xt = v.fit_transform([data[i] for i in tr])
        Xe = v.transform([data[i] for i in te])
        m = LogisticRegression(max_iter=4000)
        m.fit(Xt, y[tr])
        pr, sc = m.predict(Xe), m.predict_proba(Xe)[:, 1]
    print(f"  {name:36s} acc {accuracy_score(y[te], pr):.3f}   "
          f"F1(phish) {f1_score(y[te], pr):.3f}   AUC {roc_auc_score(y[te], sc):.3f}")


def main():
    d = load()
    y = d["y"].values
    print(f"rows {len(d)}   phish {y.sum()}   legit {(1-y).sum()}   "
          f"distinct registrable domains {d['group'].nunique()}")
    print(f"rows per group: median {d.groupby('group').size().median():.0f}  "
          f"max {d.groupby('group').size().max()}")

    gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
    tr, te = next(gss.split(d, y, groups=d["group"]))
    maj = max(Counter(y[te]).values()) / len(te)
    print(f"\nGROUPED SPLIT (by registrable domain): train {len(tr)} test {len(te)}, "
          f"majority = {maj:.3f}\n")

    print("SHORTCUT BASELINES")
    run("B1 text length only", "num", d["text"].str.len().values, y, tr, te)
    run("B2 tag count only", "num", d["ntags"].values, y, tr, te)
    run("B3 whois domain age only", "num", d["age"].values, y, tr, te)
    run("B4 hand features (11)", "num", handfeats(d), y, tr, te)
    run("B5 URL string char 3-5gram", "char", d["url"].tolist(), y, tr, te)
    run("B6 host only char 3-5gram", "char", d["host"].tolist(), y, tr, te)
    run("B7 page text char 3-5gram", "char", d["text"].tolist(), y, tr, te)
    run("B8 page text word 1-3gram", "word", d["text"].tolist(), y, tr, te)
    run("B9 HTML tag sequence word 1-3gram", "word", d["tagseq"].tolist(), y, tr, te)

    # random (leaky) split for contrast
    rng = np.random.RandomState(SEED)
    idx = rng.permutation(len(d))
    rtr, rte = idx[: int(0.7 * len(d))], idx[int(0.7 * len(d)):]
    print("\nSAME, RANDOM SPLIT (leaky - for contrast only)")
    run("B5r URL string char 3-5gram", "char", d["url"].tolist(), y, rtr, rte)
    run("B7r page text char 3-5gram", "char", d["text"].tolist(), y, rtr, rte)

    print("\nCLASS-CONDITIONAL DISTRIBUTIONS (median)")
    for c in ["text", "ntags", "age", "assets", "ncss_prop"]:
        v = d["text"].str.len() if c == "text" else d[c]
        print(f"  {c:12s} phish {np.median(v[y == 1]):10.1f}   legit {np.median(v[y == 0]):10.1f}")


if __name__ == "__main__":
    main()
