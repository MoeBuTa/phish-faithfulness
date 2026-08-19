"""LABEL-PRESERVING interventions, prototyped on the shipped phishing pages.

Why not erasure. Both flagship reference-based detectors define the label as exactly the
evidence we wanted to erase:
  Phishpedia   logo_matching.py: "If the webpage domain exactly aligns with the target
               website's domain => Benign"  -> phish_category = 1 otherwise
  PhishVLM     phishvlm.py:618-653  domain_brand_inconsistent = (domain4pred != domain4url)
               ...  phish_condition = domain_brand_inconsistent ; then gated on CRP
So removing the domain mismatch, or removing the credential form, flips the ground truth
under the field's own labelling rule. A model that flips is being CORRECT, not unfaithful.

What works instead: substitute WITHIN the class, so the label is provably unchanged while
the evidence the model must cite does change.

  S1 BRAND SWAP     rewrite every occurrence of impersonated brand A to a different
                    brand B (visible text, <title>, alt/title/placeholder/aria-label,
                    image filenames). The page still impersonates a brand it is not
                    hosted by, so it is still phishing. A faithful explanation MUST now
                    cite B; the verdict MUST NOT move.
  S2 HOST SWAP      rewrite the host to a different non-official host. Still
                    domain-brand inconsistent, so still phishing. A faithful explanation
                    MUST cite the new host string; the verdict MUST NOT move.
  S0 NO-OP          re-render byte-identical except an invisible HTML comment. Gives the
                    test-retest noise floor that the proposed design lacked.

Each operator reports COVERAGE (how many pages it applies cleanly to) and is verified by
re-scanning the output: the old brand must be gone and the new one present.
"""
import json
import os
import re
import sys
import zipfile
from collections import Counter
from urllib.parse import urlsplit

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit_html import ALT, IMG, TITLE, PW, visible, brand_aliases
from audit_brandmatched import parse_brands
from audit_meta import reg

DECOYS = ["chase", "wellsfargo", "santander", "rakuten", "orange"]


def swap_brand(html, old_aliases, new_name):
    """Replace brand strings everywhere they can appear. Case-insensitive, word-ish."""
    out, n = html, 0
    for a in sorted(old_aliases, key=len, reverse=True):
        pat = re.compile(re.escape(a), re.I)
        out, k = pat.subn(new_name, out)
        n += k
    return out, n


def swap_host(url, new_host):
    u = urlsplit(url)
    return u._replace(netloc=new_host).geturl()


def noop(html):
    return html.replace("<body", "<!-- r -->\n<body", 1) if "<body" in html else html + "\n<!-- r -->"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    brands_df = pd.read_csv("brands.csv")
    brands_df["identifier"] = brands_df["identifier"].astype(str)
    p = pd.read_csv("phishing.csv", low_memory=False).set_index("_id")

    z = zipfile.ZipFile("phishing_5001-5151.zip")
    sites = sorted({n.split("/")[0] for n in z.namelist() if "/" in n})

    stats = Counter()
    examples = []
    for s in sites:
        name = f"{s}/original.html"
        if name not in z.namelist() or s not in p.index:
            continue
        html = z.read(name).decode("utf-8", "replace")
        m = p.loc[s]
        if isinstance(m, pd.DataFrame):
            m = m.iloc[0]
        bl = parse_brands(m.get("brands"))
        if not bl:
            continue
        brand = bl[0]
        alias = brand_aliases(brand, brands_df)
        if not alias:
            stats["no_alias"] += 1
            continue
        stats["total"] += 1

        # --- S1 brand swap
        decoy = next(d for d in DECOYS if d not in brand)
        new_html, nrep = swap_brand(html, alias, decoy.capitalize())
        pre = sum(len(re.findall(re.escape(a), html, re.I)) for a in alias)
        post = sum(len(re.findall(re.escape(a), new_html, re.I)) for a in alias)
        if pre > 0 and post == 0 and decoy in new_html.lower():
            stats["S1_clean"] += 1
            ok1 = True
        else:
            stats["S1_failed"] += 1
            ok1 = False

        # did it survive as a still-recognisable page? crude structural check
        if ok1 and len(new_html) > 0.8 * len(html):
            stats["S1_structure_ok"] += 1

        # --- S2 host swap (label preserved: new host is still not the official one)
        url = str(m["url"])
        host = urlsplit(url).netloc
        r = brands_df[brands_df["identifier"].str.lower() == brand]
        official = reg(urlsplit(str(r.iloc[0]["website"])).netloc) if len(r) else None
        new_host = "cdn-" + re.sub(r"[^a-z0-9]", "", host)[:18] + ".secure-update.top"
        if official and reg(new_host) != official and reg(host) != official:
            stats["S2_clean"] += 1

        # --- E2 applicability (for reference only, NOT used as an erasure arm)
        if PW.search(html):
            stats["has_credential_form"] += 1

        if len(examples) < 3 and ok1:
            v_old, v_new = visible(html), visible(new_html)
            examples.append({
                "site": s, "brand": brand, "decoy": decoy, "url": url,
                "replacements": nrep,
                "title_before": (TITLE.search(html).group(1).strip()[:70] if TITLE.search(html) else ""),
                "title_after": (TITLE.search(new_html).group(1).strip()[:70] if TITLE.search(new_html) else ""),
                "visible_before": v_old[:220],
                "visible_after": v_new[:220],
                "host_before": host, "host_after": new_host,
                "official_domain": official,
            })

    print("=== LABEL-PRESERVING INTERVENTION COVERAGE  (151-site pilot) ===")
    t = stats["total"]
    for k in ["total", "S1_clean", "S1_structure_ok", "S1_failed", "S2_clean",
              "has_credential_form", "no_alias"]:
        v = stats[k]
        print(f"  {k:24s} {v:5d}" + (f"   ({v/t:.1%})" if t and k != "total" else ""))

    print("\n=== WORKED EXAMPLES ===")
    for e in examples:
        print(f"\n--- {e['site']}  impersonates {e['brand']!r}  -> swapped to {e['decoy']!r} "
              f"({e['replacements']} replacements)")
        print(f"    url      : {e['url'][:100]}")
        print(f"    host     : {e['host_before']}  ->  {e['host_after']}")
        print(f"    official : {e['official_domain']}   (both hosts differ from it => still phishing)")
        print(f"    title    : {e['title_before']!r}\n            -> {e['title_after']!r}")
        print(f"    visible  : {e['visible_before']!r}")
        print(f"            -> {e['visible_after']!r}")

    json.dump(examples, open("intervention_examples.json", "w"), indent=2)


if __name__ == "__main__":
    main()
