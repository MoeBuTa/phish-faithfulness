"""Is the 0.96 a page-POPULATION artefact or real phishing content signal?

The corpus separates because phishing pages are small single-purpose login forms
(median 294 chars of text) and legitimate pages are large content sites (median 2651).
That difference is about what was crawled, not about impersonation.

This script builds size-matched subsets and re-runs the same baselines inside them.
If accuracy collapses toward chance, the headline signal is population, not content.

Matching: 1:1 nearest neighbour on (log text length, log tag count), greedy, with a
hard calliper. Reports how many pairs survive and the resulting balance.
"""
import ast
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

from audit_meta import load, run, reg

SEED = 20260812
CALLIPER = 0.25   # max distance in standardised (log-len, log-tags) space


def match(d):
    a = d[d.y == 1].copy()
    b = d[d.y == 0].copy()

    def feat(x):
        return np.column_stack([np.log1p(x["text"].str.len()), np.log1p(x["ntags"])])

    A, B = feat(a), feat(b)
    mu, sd = np.vstack([A, B]).mean(0), np.vstack([A, B]).std(0) + 1e-9
    A, B = (A - mu) / sd, (B - mu) / sd

    used = np.zeros(len(B), bool)
    pairs = []
    order = np.argsort(A[:, 0])                       # deterministic order
    for i in order:
        dist = np.linalg.norm(B - A[i], axis=1)
        dist[used] = np.inf
        j = int(np.argmin(dist))
        if dist[j] <= CALLIPER:
            used[j] = True
            pairs.append((a.index[i], b.index[j]))
    return pairs


def main():
    d = load()
    pairs = match(d)
    print(f"size-matched pairs formed: {len(pairs)}  "
          f"(calliper {CALLIPER} on standardised log-length / log-tagcount)")

    idx = [i for p in pairs for i in p]
    m = d.loc[idx].copy().reset_index(drop=True)
    y = m["y"].values
    print(f"matched set: {len(m)} rows, {y.sum()} phish / {(1-y).sum()} legit")
    print("  balance check (median):")
    for c, v in [("text len", m["text"].str.len()), ("n tags", m["ntags"])]:
        print(f"    {c:10s} phish {np.median(v[y==1]):8.1f}   legit {np.median(v[y==0]):8.1f}")

    gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
    tr, te = next(gss.split(m, y, groups=m["group"]))
    maj = max(Counter(y[te]).values()) / len(te)
    print(f"\nGROUPED SPLIT inside matched set: train {len(tr)} test {len(te)}, "
          f"majority = {maj:.3f}\n")
    run("M1 text length only [control]", "num", m["text"].str.len().values, y, tr, te)
    run("M2 tag count only [control]", "num", m["ntags"].values, y, tr, te)
    run("M3 whois domain age only", "num", m["age"].values, y, tr, te)
    run("M4 URL string char 3-5gram", "char", m["url"].tolist(), y, tr, te)
    run("M5 page text char 3-5gram", "char", m["text"].tolist(), y, tr, te)
    run("M6 page text word 1-3gram", "word", m["text"].tolist(), y, tr, te)
    run("M7 HTML tag sequence word 1-3gram", "word", m["tagseq"].tolist(), y, tr, te)

    # what words drive it, so we can see whether it is impersonation or crawl artefact
    v = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=5, max_features=100000)
    X = v.fit_transform(m["text"].tolist())
    lr = LogisticRegression(max_iter=4000).fit(X, y)
    names = np.array(v.get_feature_names_out())
    co = lr.coef_[0]
    print("\n  top 25 tokens PUSHING TOWARD PHISHING:")
    print("   ", ", ".join(names[np.argsort(co)[-25:]][::-1]))
    print("  top 25 tokens PUSHING TOWARD LEGITIMATE:")
    print("   ", ", ".join(names[np.argsort(co)[:25]]))


if __name__ == "__main__":
    main()
