"""Are the three intervention operators (E1 domain, E2 credential form, E3 brand cues)
actually implementable as MECHANICAL edits on the shipped HTML?

That is the difference between this study and the one the supervisor rejected: if the
"neutralisation" needs a human to decide what counts as a brand cue, we are back to
hand-building an oracle. Run over whatever site zips are present.

For each site, measured on original.html:
  E2  presence of <input type=password>, count of forms, count of inputs
  E3  occurrences of the labelled target brand string in visible text, in alt/title
      attributes, in image filenames, and in the page <title>
  E1  is the labelled brand's official registrable domain equal to the page's host
"""
import ast
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict
from urllib.parse import urlsplit

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit_meta import reg
from audit_brandmatched import parse_brands

PW = re.compile(r"""<input\b[^>]*\btype\s*=\s*["']?password["']?""", re.I)
INPUT = re.compile(r"<input\b", re.I)
FORM = re.compile(r"<form\b", re.I)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
ALT = re.compile(r"""\b(?:alt|title|placeholder|aria-label)\s*=\s*["']([^"']*)["']""", re.I)
IMG = re.compile(r"""<img\b[^>]*\bsrc\s*=\s*["']([^"']*)["']""", re.I)
SCRIPT = re.compile(r"<script\b.*?</script>", re.I | re.S)
STYLE = re.compile(r"<style\b.*?</style>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")


def visible(html):
    h = SCRIPT.sub(" ", html)
    h = STYLE.sub(" ", h)
    return re.sub(r"\s+", " ", TAG.sub(" ", h))


def analyse(html, brand_names):
    v = visible(html)
    lo, vlo = html.lower(), v.lower()
    alts = " ".join(ALT.findall(html)).lower()
    imgs = " ".join(IMG.findall(html)).lower()
    ttl = (TITLE.search(html).group(1) if TITLE.search(html) else "")
    hits = {}
    for b in brand_names:
        if not b:
            continue
        hits[b] = {
            "text": vlo.count(b), "attrs": alts.count(b),
            "img_src": imgs.count(b), "title": ttl.lower().count(b),
        }
    return {
        "has_password": bool(PW.search(html)),
        "n_inputs": len(INPUT.findall(html)),
        "n_forms": len(FORM.findall(html)),
        "n_imgs": len(IMG.findall(html)),
        "len_html": len(html),
        "len_visible": len(v),
        "title": ttl.strip()[:80],
        "brand_hits": hits,
    }


def brand_aliases(identifier, brands_df):
    r = brands_df[brands_df["identifier"].str.lower() == identifier]
    out = {identifier}
    if len(r):
        name = str(r.iloc[0]["name"]).lower()
        out |= {name, re.sub(r"[^a-z0-9]", "", name)}
        out |= {reg(urlsplit(str(r.iloc[0]["website"])).netloc).split(".")[0]}
    return {x for x in out if len(x) >= 3}


def run_zip(path, meta, brands_df, label):
    z = zipfile.ZipFile(path)
    sites = sorted({n.split("/")[0] for n in z.namelist() if "/" in n})
    by_id = meta.set_index("_id")
    rows = []
    for s in sites:
        name = f"{s}/original.html"
        if name not in z.namelist():
            continue
        try:
            html = z.read(name).decode("utf-8", "replace")
        except Exception:
            continue
        if s not in by_id.index:
            continue
        m = by_id.loc[s]
        if isinstance(m, pd.DataFrame):
            m = m.iloc[0]
        bl = parse_brands(m.get("brands")) if label == "phish" else []
        alias = set()
        for b in bl:
            alias |= brand_aliases(b, brands_df)
        a = analyse(html, alias)
        host = urlsplit(str(m["url"])).netloc
        offdom = None
        if bl:
            r = brands_df[brands_df["identifier"].str.lower() == bl[0]]
            if len(r):
                offdom = reg(urlsplit(str(r.iloc[0]["website"])).netloc)
        a.update(site=s, label=label, brand=bl[0] if bl else None,
                 host=host, rdom=reg(host), official=offdom,
                 domain_matches_brand=(offdom is not None and reg(host) == offdom))
        rows.append(a)
    return rows


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    brands_df = pd.read_csv("brands.csv")
    brands_df["identifier"] = brands_df["identifier"].astype(str)
    p = pd.read_csv("phishing.csv", low_memory=False)
    n = pd.read_csv("not-phishing.csv", low_memory=False)

    rows = []
    for f in sorted(os.listdir(".")):
        if not f.endswith(".zip"):
            continue
        lab = "legit" if f.startswith("not-phishing") else "phish"
        try:
            r = run_zip(f, n if lab == "legit" else p, brands_df, lab)
        except zipfile.BadZipFile:
            print(f"  {f}: still downloading / not a complete zip, skipped")
            continue
        print(f"  {f}: {len(r)} sites parsed ({lab})")
        rows += r
    if not rows:
        print("no zips available yet")
        return
    d = pd.DataFrame(rows)
    d.to_json("html_features.jsonl", orient="records", lines=True)

    print(f"\n=== HTML-LEVEL FEATURES  ({len(d)} sites) ===")
    for lab, g in d.groupby("label"):
        pw = g["has_password"].mean()
        print(f"\n{lab.upper()}  n={len(g)}")
        print(f"  has <input type=password>      {pw:.1%}")
        print(f"  has >=1 <form>                 {(g['n_forms']>0).mean():.1%}")
        print(f"  median inputs / forms / imgs   {g['n_inputs'].median():.0f} / "
              f"{g['n_forms'].median():.0f} / {g['n_imgs'].median():.0f}")
        print(f"  median html len / visible len  {g['len_html'].median():.0f} / "
              f"{g['len_visible'].median():.0f}")
    ph = d[d.label == "phish"]
    if len(ph):
        anyhit = ph["brand_hits"].map(
            lambda h: any(sum(v.values()) > 0 for v in h.values()) if h else False)
        texthit = ph["brand_hits"].map(
            lambda h: any(v["text"] > 0 for v in h.values()) if h else False)
        print(f"\nE3 BRAND-CUE LOCALISABILITY (phishing pages, using the shipped brand label)")
        print(f"  brand string found ANYWHERE in the page   {anyhit.mean():.1%}")
        print(f"  brand string found in VISIBLE TEXT        {texthit.mean():.1%}")
        for k in ("text", "attrs", "img_src", "title"):
            hit = ph["brand_hits"].map(
                lambda h, kk=k: any(v[kk] > 0 for v in h.values()) if h else False)
            print(f"    in {k:8s} {hit.mean():6.1%}")
        print(f"\nE1 DOMAIN CHECK  domain==official brand domain: "
              f"{ph['domain_matches_brand'].mean():.1%} of phishing pages")
        print(f"\n  sample titles: {ph['title'].head(8).tolist()}")


if __name__ == "__main__":
    main()
