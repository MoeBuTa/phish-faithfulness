"""Corrected intervention prototype. Replaces intervene.py, which an adversarial review broke.

What was wrong in v1, and what this does instead:

  1. reg() returned the last two labels, so rakuten.co.jp -> 'co.jp' and eight brands picked
     up the alias 'com'. Four pages had 6-70 unrelated 'com' occurrences rewritten.
     -> public-suffix-aware via tldextract; generic tokens excluded from the alias set.
  2. swap_host() was defined and never called; the reported S2 synthesised
     'cdn-<oldhost>.secure-update.top' instead of drawing from the observed distribution,
     and only checked the ORIGINAL brand's official domain, not the decoy's.
     -> the swap is performed, the host is drawn from the corpus, and the result is checked
        against BOTH brands' official domains.
  3. "clean" meant only that the enumerated aliases disappeared. It did not check that the
     replacement landed in rendered content rather than in scripts, styles or asset URLs,
     and logo IMAGES are never edited at all.
     -> mutations are counted separately for rendered text, script/style bodies and asset
        URLs, and the logo problem is reported as an explicit uncovered surface.
  4. "fully offline re-renderable" was asserted from the zip listing. original.html still
     references external hosts.
     -> external references are counted for original.html vs index.html vs clean.html.

Nothing here claims a verdict SHOULD stay fixed. Label preservation only makes the paired
comparison well posed; the endpoint has to be a calibrated score, not a verdict flip.
"""
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
import tldextract

sys.path.insert(0, ".")
from audit_html import ALT, IMG, TITLE, PW, SCRIPT, STYLE, visible
from audit_brandmatched import parse_brands

SEED = 20260812
GENERIC = {"com", "net", "org", "www", "the", "inc", "ltd", "group", "online", "web",
           "mail", "cloud", "app", "one", "co", "bank", "id"}
EXTREF = re.compile(r"""\b(?:src|href|action|data-src|poster)\s*=\s*["'](https?:)?//""", re.I)


def psl(host):
    e = tldextract.extract(str(host))
    return f"{e.domain}.{e.suffix}".strip(".").lower()


def stem(url):
    return tldextract.extract(str(url)).domain.lower()


def aliases_for(ident, bd):
    r = bd[bd["identifier"].str.lower() == str(ident).lower()]
    if not len(r):
        return set()
    r = r.iloc[0]
    name = str(r["name"]).lower()
    c = {str(ident).lower(), name, re.sub(r"[^a-z0-9]", "", name), stem(r["website"])}
    c |= {w for w in re.split(r"[^a-z0-9]+", name) if w}
    return {x for x in c if len(x) >= 4 and x not in GENERIC}


def parent_of(ident, bd):
    """Crude same-owner guard so microsoft -> onedrive is not offered as a decoy."""
    r = bd[bd["identifier"].str.lower() == str(ident).lower()]
    return stem(r.iloc[0]["website"]) if len(r) else str(ident).lower()


def where_changed(before, after, aliases):
    """Which surfaces did the substitution actually touch?"""
    def bodies(rx, s):
        return "".join(rx.findall(s)) if rx.findall(s) else ""
    sb, sa = bodies(SCRIPT, before), bodies(SCRIPT, after)
    yb, ya = bodies(STYLE, before), bodies(STYLE, after)
    ib, ia = " ".join(IMG.findall(before)), " ".join(IMG.findall(after))
    vb, va = visible(before), visible(after)
    return {
        "rendered_text": vb != va,
        "script_bodies": sb != sa,
        "style_bodies": yb != ya,
        "image_urls": ib != ia,
    }


def main():
    bd = pd.read_csv("brands.csv")
    bd["identifier"] = bd["identifier"].astype(str)
    p = pd.read_csv("phishing.csv", low_memory=False)
    obs_hosts = [urlsplit(str(u)).netloc for u in p["url"] if isinstance(u, str) and urlsplit(str(u)).netloc]
    pset = p.set_index("_id")
    rng = np.random.RandomState(SEED)

    z = zipfile.ZipFile("phishing_5001-5151.zip")
    names = set(z.namelist())
    sites = sorted({n.split("/")[0] for n in names if "/" in n})

    st = Counter()
    surf = Counter()
    ext = defaultdict(list)
    ex = []
    for s in sites:
        # external-reference audit across the three shipped variants
        for var in ("original.html", "index.html", "clean.html"):
            k = f"{s}/{var}"
            if k in names:
                h = z.read(k).decode("utf-8", "replace")
                ext[var].append(len(EXTREF.findall(h)))

        k = f"{s}/original.html"
        if k not in names or s not in pset.index:
            continue
        html = z.read(k).decode("utf-8", "replace")
        m = pset.loc[s]
        m = m.iloc[0] if isinstance(m, pd.DataFrame) else m
        bl = parse_brands(m.get("brands"))
        if not bl:
            continue
        brand = bl[0]
        row = bd[bd["identifier"].str.lower() == brand]
        if not len(row):
            st["brand_not_in_taxonomy"] += 1
            continue
        st["total"] += 1
        cat = row.iloc[0]["category"]
        off_old = psl(urlsplit(str(row.iloc[0]["website"])).netloc)

        # --- decoy: same category, different owner
        pool = bd[(bd["category"] == cat)
                  & (bd["identifier"].str.lower() != brand)
                  & (bd["identifier"].map(lambda i: parent_of(i, bd)) != parent_of(brand, bd))]
        if not len(pool):
            st["no_decoy"] += 1
            continue
        dec = pool.iloc[rng.randint(len(pool))]
        dec_name = str(dec["name"]).split()[0]
        off_new = psl(urlsplit(str(dec["website"])).netloc)

        # --- S1 brand swap
        al = aliases_for(brand, bd)
        if not al:
            st["no_alias"] += 1
            continue
        out = html
        for a in sorted(al, key=len, reverse=True):
            out = re.sub(re.escape(a), dec_name, out, flags=re.I)
        residual = sum(len(re.findall(re.escape(a), out, re.I)) for a in al)
        s1_ok = residual == 0 and dec_name.lower() in out.lower()
        st["S1_alias_removed"] += s1_ok
        if s1_ok:
            w = where_changed(html, out, al)
            for kk, v in w.items():
                surf[kk] += v
            # the swap is only meaningful if it changed what a reader sees
            st["S1_changed_rendered_text"] += w["rendered_text"]
            st["S1_ALSO_mutated_code_or_assets"] += (w["script_bodies"] or w["style_bodies"]
                                                     or w["image_urls"])
            st["S1_rendered_only"] += (w["rendered_text"] and not (w["script_bodies"]
                                       or w["style_bodies"] or w["image_urls"]))

        # --- S2 host swap, drawn from the OBSERVED distribution, checked against BOTH brands
        old_host = urlsplit(str(m["url"])).netloc
        new_host = None
        for _ in range(60):
            c = obs_hosts[rng.randint(len(obs_hosts))]
            if c and c != old_host and psl(c) not in (off_old, off_new):
                new_host = c
                break
        if new_host:
            st["S2_drawn_ok"] += 1
            u = urlsplit(str(m["url"]))
            new_url = u._replace(netloc=new_host).geturl()
            st["S2_url_rewritten"] += (new_url != str(m["url"]))

        # --- the logo surface, which no string edit can reach
        imgs = IMG.findall(html)
        st["has_img_referencing_old_brand"] += any(
            any(a in i.lower() for a in al) for i in imgs)

        if len(ex) < 4 and s1_ok and new_host:
            ex.append(dict(site=s, brand=brand, cat=cat, decoy=dec_name,
                           t0=(TITLE.search(html).group(1).strip()[:60] if TITLE.search(html) else ""),
                           t1=(TITLE.search(out).group(1).strip()[:60] if TITLE.search(out) else ""),
                           old_host=old_host, new_host=new_host,
                           off_old=off_old, off_new=off_new,
                           surfaces=where_changed(html, out, al)))

    t = st["total"]
    print(f"=== CORRECTED INTERVENTION PROTOTYPE  (n={t} phishing pages) ===\n")
    print("S1 brand swap (within-category, different owner, public-suffix-aware aliases)")
    for k in ["S1_alias_removed", "S1_changed_rendered_text", "S1_rendered_only",
              "S1_ALSO_mutated_code_or_assets"]:
        print(f"   {k:34s} {st[k]:4d}  ({st[k]/t:.1%})")
    print(f"   {'has <img> whose URL names the brand':34s} {st['has_img_referencing_old_brand']:4d}  "
          f"({st['has_img_referencing_old_brand']/t:.1%})  <- pixels never edited")
    print("\nS2 host swap (drawn from the observed phishing-host distribution)")
    for k in ["S2_drawn_ok", "S2_url_rewritten"]:
        print(f"   {k:34s} {st[k]:4d}  ({st[k]/t:.1%})")
    print(f"\n   skipped: no_decoy {st['no_decoy']}, no_alias {st['no_alias']}, "
          f"brand_not_in_taxonomy {st['brand_not_in_taxonomy']}")

    print("\n=== OFFLINE RE-RENDERABILITY: external references per page ===")
    for var, v in ext.items():
        v = np.array(v)
        print(f"   {var:14s} n={len(v):3d}  pages with >=1 external ref: {np.mean(v>0):6.1%}  "
              f"median refs {np.median(v):5.0f}")

    print("\n=== EXAMPLES ===")
    for e in ex:
        print(f"\n  {e['brand']} [{e['cat']}] -> {e['decoy']}")
        print(f"    title  : {e['t0']!r} -> {e['t1']!r}")
        print(f"    host   : {e['old_host']} -> {e['new_host']}")
        print(f"    checked against official domains: {e['off_old']} and {e['off_new']}")
        print(f"    surfaces touched: {e['surfaces']}")
    json.dump(ex, open("intervention2_examples.json", "w"), indent=2)


if __name__ == "__main__":
    main()
