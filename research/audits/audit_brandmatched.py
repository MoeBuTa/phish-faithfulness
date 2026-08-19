"""Can we build a BRAND-CONTROLLED evaluation set?

The size-matched audit showed the residual 0.90 signal is carried by brand names:
"page mentions PayPal" => phishing, because the legitimate half of the corpus almost
never contains PayPal's own pages. Any intervention on brand cues would therefore move
the verdict for a reason that has nothing to do with the model's reasoning.

The fix, if the data supports it: pair each phishing page impersonating brand X with a
legitimate page that IS brand X. Then brand mention is constant within the pair and only
the domain / page role can decide the label.

This script measures whether that set can be built, and how big it is.
"""
import ast
import numpy as np
import pandas as pd
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from audit_meta import reg, load, run
from sklearn.model_selection import GroupShuffleSplit

SEED = 20260812


def parse_brands(s):
    try:
        v = ast.literal_eval(s) if isinstance(s, str) else []
        return [str(x).strip().lower() for x in v] if isinstance(v, list) else []
    except Exception:
        return []


def main():
    p = pd.read_csv("phishing.csv", low_memory=False)
    n = pd.read_csv("not-phishing.csv", low_memory=False)
    b = pd.read_csv("brands.csv")

    p["blist"] = p["brands"].map(parse_brands)
    print(f"phishing rows with >=1 brand label: {(p['blist'].str.len() > 0).sum()} / {len(p)}")
    print(f"brand-count per phishing page: {dict(Counter(p['blist'].str.len()).most_common(5))}")

    cnt = Counter(x for v in p["blist"] for x in v)
    print(f"distinct brands actually used as labels: {len(cnt)}  "
          f"(brands.csv lists {len(b)})")
    print(f"unknown labels not in brands.csv: "
          f"{sorted(set(cnt) - set(b['identifier'].str.lower()))[:20]}")

    # official registrable domain per brand
    off = {str(r["identifier"]).lower(): reg(urlsplit(str(r["website"])).netloc)
           for _, r in b.iterrows()}

    n["rdom"] = n["domain"].astype(str).map(reg)
    legit_by_dom = defaultdict(list)
    for i, r in n.iterrows():
        legit_by_dom[r["rdom"]].append(i)

    rows = []
    for brand, k in cnt.most_common():
        d = off.get(brand)
        nl = len(legit_by_dom.get(d, [])) if d else 0
        rows.append((brand, k, d, nl, min(k, nl)))
    t = pd.DataFrame(rows, columns=["brand", "n_phish", "official_domain",
                                    "n_legit_on_that_domain", "pairs"])
    print(f"\nBRAND-CONTROLLED PAIR YIELD")
    print(f"  brands with >=1 legit page on their official domain: "
          f"{(t['n_legit_on_that_domain'] > 0).sum()} / {len(t)}")
    print(f"  total pairs formable (1:1 within brand): {t['pairs'].sum()}")
    print(f"  distinct brands contributing >=1 pair: {(t['pairs'] > 0).sum()}")
    print("\n  top 25 brands by phishing volume:")
    print(t.head(25).to_string(index=False))
    t.to_csv("brand_pair_yield.csv", index=False)

    # how lopsided is it? one legit page per brand vs hundreds of phishing pages
    print(f"\n  legit pages available per brand (for brands with any): "
          f"{t[t.n_legit_on_that_domain>0]['n_legit_on_that_domain'].describe().round(2).to_dict()}")

    # Decisive: inside a brand-controlled set, does the text baseline collapse?
    # Build it with replacement on the legit side (few legit pages per brand), and
    # report both the naive number and the number under a strict 1:1 cap.
    d = load()
    d["blist"] = d["brands"].map(parse_brands)
    sel_p, sel_l = [], []
    for _, r in t[t.pairs > 0].iterrows():
        ph = d[(d.y == 1) & (d["blist"].map(lambda v, br=r.brand: br in v))]
        lg = d[(d.y == 0) & (d["group"] == r.official_domain)]
        k = min(len(ph), len(lg))
        sel_p += list(ph.index[:k])
        sel_l += list(lg.index[:k])
    m = d.loc[sel_p + sel_l].copy().reset_index(drop=True)
    y = m["y"].values
    print(f"\nSTRICT 1:1 BRAND-CONTROLLED SET: {len(m)} rows "
          f"({y.sum()} phish / {(1-y).sum()} legit)")
    if 30 <= len(m) and y.sum() > 5 and (1 - y).sum() > 5:
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
        tr, te = next(gss.split(m, y, groups=m["group"]))
        print(f"  grouped split: train {len(tr)} test {len(te)}, "
              f"majority {max(Counter(y[te]).values())/len(te):.3f}\n")
        try:
            run("  text length only", "num", m["text"].str.len().values, y, tr, te)
            run("  page text word 1-3gram", "word", m["text"].tolist(), y, tr, te)
            run("  URL char 3-5gram", "char", m["url"].tolist(), y, tr, te)
        except Exception as e:
            print("   baseline failed:", e)


if __name__ == "__main__":
    main()
