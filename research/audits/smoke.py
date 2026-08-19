"""Day-2 gate, run early: can the available models produce the contract at all?

Three things decide whether the study can run, and none of them need the full sample:
  1. does the model return parseable JSON on a real page of this size
  2. is every `quote` a verbatim substring of the input  (if not, the cited/uncited
     partition is invalid and the whole design collapses)
  3. does p_phish vary, or is it pinned at 0/1 (a constant predictor cannot show an effect)

Two pages only, both conditions, all reachable models. Output is one jsonl row per call
with the raw response stored so parsing can be redone without re-billing.
"""
import json
import os
import re
import sys
import zipfile

import pandas as pd
from openai import OpenAI

sys.path.insert(0, ".")
import prompts_phish as P
from audit_render import v_skeleton

TEMPERATURE = 0.0
MAXTOK = 900
BASE_7B = "WhiteRabbitNeo-V3-7B"


def make_client(model):
    if model == BASE_7B:
        return OpenAI(base_url=os.environ["OPENAI_BASE_URL"],
                      api_key=os.environ["OPENAI_API_KEY"], max_retries=0, timeout=180.0)
    key = os.environ["GATEWAY_KEYS"].split(",")[0].strip()
    return OpenAI(api_key=key, base_url=os.environ["GATEWAY_BASE_URL"],
                  max_retries=0, timeout=180.0,
                  default_headers={"User-Agent": "curl/8.4.0"})


def extract_json(text, key="verdict"):
    """First balanced JSON object containing `key` - models nest error-shaped objects."""
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        o = json.loads(text[i:j + 1])
                        if isinstance(o, dict) and key in o:
                            return o
                    except Exception:
                        pass
                    break
    return None


def main():
    from dotenv import load_dotenv
    load_dotenv("/Users/wenxiao/Projects/PentestAgent/.env")

    z = zipfile.ZipFile("phishing_5001-5151.zip")
    zl = zipfile.ZipFile("not-phishing_5001-5244.zip")
    p = pd.read_csv("phishing.csv", low_memory=False).set_index("_id")
    n = pd.read_csv("not-phishing.csv", low_memory=False).set_index("_id")

    cases = []
    for zf, meta, lab in ((z, p, "phish"), (zl, n, "legit")):
        for s in sorted({x.split("/")[0] for x in zf.namelist() if "/" in x}):
            k = f"{s}/original.html"
            if k not in zf.namelist() or s not in meta.index:
                continue
            h = v_skeleton(zf.read(k).decode("utf-8", "replace"))
            if not (3000 < len(h) < 40000):
                continue
            m = meta.loc[s]
            m = m.iloc[0] if isinstance(m, pd.DataFrame) else m
            cases.append(dict(site=s, label=lab, url=str(m["url"]), html=h))
            break

    models = [x for x in (sys.argv[1:] or ["qwen-flash", "qwen-plus", BASE_7B])]
    out = open("smoke.jsonl", "w")
    print(f"{len(cases)} pages x {len(models)} models x 2 conditions\n")
    for model in models:
        cli = make_client(model)
        for c in cases:
            for cond in ("forced", "free"):
                sysm, user = P.render(c["url"], c["html"], cond)
                rec = dict(model=model, site=c["site"], label=c["label"], cond=cond,
                           approx_tokens=len(user) // 4)
                try:
                    r = cli.chat.completions.create(
                        model=model, temperature=TEMPERATURE, max_tokens=MAXTOK,
                        messages=[{"role": "system", "content": sysm},
                                  {"role": "user", "content": user}])
                    raw = r.choices[0].message.content or ""
                    rec["raw"] = raw
                    o = extract_json(raw)
                    rec["parsed"] = o is not None
                    if o:
                        rec["verdict"] = o.get("verdict")
                        rec["p_phish"] = o.get("p_phish")
                        rec["brand"] = o.get("brand")
                        quotes = [e.get("quote", "") for e in (o.get("evidence") or [])
                                  if isinstance(e, dict)]
                        hay = c["url"] + "\n" + c["html"]
                        rec["n_quotes"] = len(quotes)
                        rec["verbatim"] = sum(1 for q in quotes if q and q in hay)
                except Exception as e:
                    rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                status = (rec.get("error") or
                          f"parsed={rec.get('parsed')} verdict={rec.get('verdict')} "
                          f"p={rec.get('p_phish')} quotes={rec.get('verbatim')}/{rec.get('n_quotes')}")
                print(f"  {model:24s} {c['label']:6s} {cond:6s} "
                      f"~{rec['approx_tokens']:6d}tok  {status}")
    out.close()


if __name__ == "__main__":
    main()
