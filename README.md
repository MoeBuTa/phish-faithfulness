# Evaluating Evidence Grounding and Faithfulness in Small Language Models for Phishing Webpage Detection

**SLMs cite evidence. We test whether they use it.**

A 7B security model can label a webpage *phishing* and quote the exact HTML that
proves it. This project takes the harder step: **we change that quoted evidence
and see whether the decision changes with it.** If it does not, the citation was
a story told afterwards.

If the claim and the cause come apart, accuracy overstates trustworthiness. The
model is right for reasons it cannot correctly report. That gap is the project.

---

## Read in this order

1. **[docs/proposal.html](docs/proposal.html)** — the illustrated version. Open
   it in a browser. Fastest way in.
2. **[docs/SPEC.md](docs/SPEC.md)** — the authority. Where anything disagrees,
   this wins.
3. **[docs/work-plan.md](docs/work-plan.md)** — who does what, over eight weeks.
4. **[docs/feasibility.md](docs/feasibility.md)** — the audit that chose the
   corpus and killed the first design. Read before writing any claim.

[docs/slide.html](docs/slide.html) is the one-page overview;
[docs/references.md](docs/references.md) has every paper and repo, with licences.

## The four conditions, in one table

Every eligible page is run in all four. Each page is its own control, so
phishing-vs-benign differences cannot contaminate the result.

| | what we do | what it answers |
|---|---|---|
| **C1** Original | change nothing | what did it decide, and what did it cite? |
| **C2** Cited intervention | neutralise the element it cited | does it depend on the evidence it claims? |
| **C3** Matched uncited control | the same operator, on a comparable element it did *not* cite | is C2's movement just generic edit-sensitivity? |
| **C4** Placebo injection | add an element known to be irrelevant | will it invent a reason out of an inert cue? |

**C2 moves and C3 does not** → the citation was load-bearing.
**Both move** → the model is merely sensitive to any HTML edit — which is
exactly what C3 exists to catch.

These are *intervention* conditions. V1/V2/V3 — verdict only, + citations,
+ explanation — are *prompt* conditions, a separate axis. Do not mix them in one
results table.

**Only C1 is real data.** PhreshPhish ships original pages, not counterfactual
pairs. C2 and C3 are *model-conditioned*: which element to edit depends on what
the model cited in C1, so the pipeline must run the model before it can build
them.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# See the whole pipeline on one fictional page -- no network, no model, no GPU.
python scripts/demo_pipeline.py

pytest -q
```

Then, with real data:

```bash
# 1. one 55 MB shard is enough to build and test everything
python -m phishfaith.download --split test --shards 1

# 2. filter and freeze a manifest
python -m phishfaith.preprocess data/raw/data/test-000.parquet \
    --out data/manifests/dev.csv

# 3. run your model on the C1 prompts, writing one JSON object per line:
#    {"sha256": "...", "raw": "<result>...</result>"}

# 4. build the C1-C4 paired benchmark from what the model cited
python scripts/build_variants.py \
    --manifest data/manifests/dev.parquet \
    --c1-outputs data/interim/c1_outputs.jsonl \
    --out data/interim/variants.jsonl
```

The full corpus is ~36.6 GB compressed and ~193 GB expanded. Nothing here
downloads it by default; scale up only once the pipeline is frozen.

## What is in here

```
src/phishfaith/
  config.py          paths, dataset coordinates, frozen thresholds
  download.py        fetch PhreshPhish shards from the HF hub
  preprocess.py      language / size / exact / near-duplicate filters -> manifest
  citation_view.py   page -> [U1] [H1]...[Hn], the handles the model cites
  prompts.py         V1 / V2 / V3
  parse.py           lenient XML parsing that records how it recovered
  grounding.py       GROUNDED | INVALID_ID | NOT_LOCATABLE, and eligibility
  interventions.py   C2 / C3 / C4 builders, and the Gate-4 change check
scripts/
  demo_pipeline.py   the whole thing on one page, stubbed model
  build_variants.py  manifest + C1 outputs -> the paired benchmark
research/audits/     the pre-project feasibility audit (Zenodo corpus, rejected)
tests/               enough to prove the pipeline holds together
```

## Two things the starter code takes a position on

**Interventions are applied to the citation view, not to raw HTML.** The
citation view is exactly what the model sees, which makes "only the intended
element changed" (Gate 4) true by construction rather than by inspection —
`interventions.verify_single_change` is a set comparison, not a diff heuristic.
HTML-level intervention is a documented extension, and it is where 58.9% of
naive string edits were found to also mutate script, style or asset URLs.

**Every intervention is labelled `LABEL_PRESERVING` or `DECISION_EVIDENCE`.**
Rewriting a domain to a neutral one is a good sensitivity probe and is *not*
safe to call label-preserving. The generated variants are not new ground truth
and must never be described as such. See [SPEC.md §6](docs/SPEC.md).

## Corpus

[PhreshPhish](https://huggingface.co/datasets/phreshphish/phreshphish) —
CC-BY-4.0, ungated. 666,315 pages, **298,402 of them phishing**: 498,255 train
(276,729 benign / 221,526 phish) + 168,060 test (91,260 benign / 76,876 phish).
Fields `sha256, url, label, target, date, lang, lang_score, html`, with `target`
on phishing rows only.

We use nowhere near all of it. English-only, size bounds and dedup cut it first;
then a page enters the experiment only if the model's citations are all
`GROUNDED`. [SPEC.md §7](docs/SPEC.md) fixes the working set at **n = 300
eligible pages**, which is 1,200 runs across C1–C4 plus the no-op repeats for
the noise floor.

Zenodo 8041387 was rejected as the main corpus: it is separable at 0.960 by page
text alone, 0.880 after brand control, and **0.838 from English function words
alone** — the class signal there is document register, not phishing. It remains
the fallback for any arm that needs screenshots. The numbers are in
[docs/feasibility.md](docs/feasibility.md).
