"""Corrected brand-controlled pair construction. Replaces audit_brandmatched.py's headline.

An adversarial review broke three things in v1:
  1. reg() returned the last two labels, so rakuten.co.jp and smbc.co.jp both became
     'co.jp'. Official-brand domains and legitimate grouping were built on that.
  2. Pairs were formed by taking the first k rows of each side unshuffled, then pair
     identity was discarded and the split was made on page domain. In the resulting test
     fold most brands contributed only ONE label, so the classifier could win by learning
     which brands are in the fold rather than anything about the pages.
  3. The reported 0.687 was one draw. Reshuffling moved it between 0.536 and 0.885.

This version uses tldextract, shuffles, keeps pairs together, splits BY PAIR so both members
of a pair land on the same side, and reports the distribution over repeats rather than a
single number.
"""
import ast
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import tldextract
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from urllib.parse import urlsplit

sys.path.insert(0, ".")
from audit_meta import load
from audit_brandmatched import parse_brands

SEED = 20260812
N_REPEATS = 20


def psl(host):
    e = tldextract.extract(str(host))
    return f"{e.domain}.{e.suffix}".strip(".").lower()


def build(d, bd, rng, size_match=False, calliper=0.35):
    off = {str(r["identifier"]).lower(): psl(urlsplit(str(r["website"])).netloc)
           for _, r in bd.iterrows()}
    d = d.copy()
    d["psl"] = d["host"].map(psl)
    pairs = []
    if size_match:
        f = np.column_stack([np.log1p(d["text"].str.len()), np.log1p(d["ntags"])])
        mu, sd = f.mean(0), f.std(0) + 1e-9
    for brand, dom in off.items():
        ph = d[(d.y == 1) & (d["blist"].map(lambda v, b=brand: b in v))]
        lg = d[(d.y == 0) & (d["psl"] == dom)]
        if len(ph) == 0 or len(lg) == 0:
            continue
        pi = rng.permutation(len(ph))
        li = rng.permutation(len(lg))
        if not size_match:
            for a, b in zip(pi[:len(li)], li[:len(pi)]):
                pairs.append((ph.index[a], lg.index[b], brand))
        else:
            A = (f[d.index.get_indexer(ph.index)] - mu) / sd
            B = (f[d.index.get_indexer(lg.index)] - mu) / sd
            used = np.zeros(len(B), bool)
            for a in pi:
                dist = np.linalg.norm(B - A[a], axis=1)
                dist[used] = np.inf
                b = int(np.argmin(dist))
                if dist[b] <= calliper:
                    used[b] = True
                    pairs.append((ph.index[a], lg.index[b], brand))
    return pairs


def evaluate(d, pairs, rng):
    """Split BY PAIR so both members stay on the same side; report acc and AUC."""
    n = len(pairs)
    perm = rng.permutation(n)
    cut = int(0.7 * n)
    tr_p, te_p = perm[:cut], perm[cut:]
    def rows(sel):
        idx, lab = [], []
        for i in sel:
            a, b, _ = pairs[i]
            idx += [a, b]
            lab += [1, 0]
        return idx, np.array(lab)
    itr, ytr = rows(tr_p)
    ite, yte = rows(te_p)
    Xtr = d.loc[itr, "text"].tolist()
    Xte = d.loc[ite, "text"].tolist()
    v = TfidfVectorizer(analyzer="word", ngram_range=(1, 3), min_df=3, max_features=200000)
    A = v.fit_transform(Xtr)
    B = v.transform(Xte)
    lr = LogisticRegression(max_iter=4000).fit(A, ytr)
    return (accuracy_score(yte, lr.predict(B)),
            roc_auc_score(yte, lr.predict_proba(B)[:, 1]))


def main():
    d = load()
    d["blist"] = d["brands"].map(parse_brands)
    bd = pd.read_csv("brands.csv")

    for label, sm in [("BRAND-CONTROLLED", False), ("BRAND-CONTROLLED + SIZE-MATCHED", True)]:
        accs, aucs, ns, bs = [], [], [], []
        for rep in range(N_REPEATS):
            rng = np.random.RandomState(SEED + rep)
            pairs = build(d, bd, rng, size_match=sm)
            if len(pairs) < 30:
                continue
            ns.append(len(pairs))
            bs.append(len({p[2] for p in pairs}))
            a, u = evaluate(d, pairs, rng)
            accs.append(a)
            aucs.append(u)
        accs, aucs = np.array(accs), np.array(aucs)
        print(f"\n=== {label} (public-suffix aware, pair-preserving split, "
              f"{len(accs)} repeats) ===")
        print(f"  pairs   : median {np.median(ns):.0f}  range {min(ns)}-{max(ns)}")
        print(f"  brands  : median {np.median(bs):.0f}")
        print(f"  accuracy: median {np.median(accs):.3f}  "
              f"IQR {np.percentile(accs,25):.3f}-{np.percentile(accs,75):.3f}  "
              f"range {accs.min():.3f}-{accs.max():.3f}")
        print(f"  AUC     : median {np.median(aucs):.3f}  "
              f"range {aucs.min():.3f}-{aucs.max():.3f}")
        print(f"  (chance = 0.500 by construction: every pair contributes one of each class)")


if __name__ == "__main__":
    main()
