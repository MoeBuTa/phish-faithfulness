# Work plan — five students, eight weeks

Roles, the order things must exist in, the timeline, and what everyone does
regardless of role. The science is in [SPEC.md](SPEC.md); this file is who and
when.

## The chain

Nobody downstream can start until the box to their left produces something real.

```
S1 data          S2 model          S3 grounding        S4 intervention     S5 statistics
citation_view.py  raw XML out       eligible pages      paired manifest     final numbers
```

Student 5 sits across all of it — freezing the hypotheses before any run,
choosing the tests, and independently reproducing whatever the other four report.

## Student 1 — dataset and preprocessing

Create the final reproducible benchmark: download and freeze PhreshPhish,
document every field, build train/test manifests, filter invalid samples,
English-only filtering, exact and near-duplicate removal, the HTML parser,
citation-ready HTML with deterministic `H1…Hn` IDs, token-budget filtering,
dataset statistics, frozen Datasets A/B/C.

Starting points: `phishfaith/download.py`, `phishfaith/preprocess.py`,
`phishfaith/citation_view.py`.

Deliverables: `data_manifest.csv` · `preprocessing.py` · `citation_view.py` ·
`dedup_report.md` · `dataset_report.md`

## Student 2 — LLM and XML pipeline

The model is already deployed and served behind an OpenAI-compatible endpoint,
so this role starts at **configuration, not deployment**: point the client at the
endpoint, verify and pin which checkpoint it is actually serving, fix and record
the generation settings (temperature, max tokens, seed / determinism), and smoke
it. Then implement the V1/V2/V3 prompts, design the XML schema and parser, handle
malformed output, record raw outputs unmodified, run baseline classification,
calculate XML compliance, capture logprobs where technically reliable, and log
runtime and cost.

One risk that comes *with* not owning the deployment: we do not control when the
endpoint changes. Record the served model ID with every run and re-check it
before each experiment. A silent checkpoint swap mid-project invalidates every
paired comparison in C1–C4, and it will not announce itself.

Starting points: `phishfaith/prompts.py`, `phishfaith/parse.py`.

Note for Week 1: `WhiteRabbitNeo/WhiteRabbitNeo-V3-7B` now 301-redirects to
`DeepHat/DeepHat-V1-7B` (base model `Qwen/Qwen2.5-Coder-7B`, Apache-2.0). Cite
the new ID and note the former name — and confirm which of the two the endpoint
reports, rather than assuming.

Deliverables: `model_config.md` · `prompts/` · `xml_schema/` ·
`inference_runner.py` · `baseline_predictions.csv` · `raw_outputs/`

## Student 3 — citation grounding

Determine whether the evidence is real and supported: validate `source_id`,
validate exact quotes, map citations back to DOM nodes, categorise evidence
types, implement automatic grounding metrics, design the semantic-support
rubric, coordinate human annotation, measure unsupported claims, analyse
correct-verdict/wrong-evidence cases.

Starting point: `phishfaith/grounding.py`.

Deliverables: `citation_validator.py` · `evidence_taxonomy.md` ·
`annotation_guideline.md` · `grounding_results.csv` · `failure_cases.md`

## Student 4 — intervention and placebo

Build the causal experiments: cited-evidence neutralisation, matched uncited
controls, domain interventions, form/credential interventions, restricted brand
interventions if feasible, cookie and copyright placebos, verification that only
the intended element changed, paired manifests, placebo-adoption analysis.

Starting points: `phishfaith/interventions.py`, `scripts/build_variants.py`.
The MIT-licensed perturbation operators in `hihey54/www24_threatAdvPhish` are
the one set that can legally be borrowed.

Deliverables: `intervention_engine/` · `placebo_engine/` ·
`intervention_manifest.csv` · `pair_validation_report.md` ·
`intervention_results.csv`

## Student 5 — design, statistics, integration

Maintain the related-work review, define novelty boundaries, freeze RQs and
hypotheses **before** runs, define sample sizes and power, choose the paired
tests and the multiple-comparison policy, compute CIs and effect sizes,
independently reproduce major results, integrate everything, produce figures.

Starting point: [SPEC.md](SPEC.md) §7 and §9, and `feasibility.md`.

Deliverables: `literature_review.md` · `hypotheses.md` · `statistics_plan.md` ·
`reproducibility_report.md` · `tables/` · `figures/` · `final_report/`

## Everyone

Dataset inspection · prompt review · annotation calibration · code review ·
weekly experiment review · failure-case analysis · proposal writing · final
presentation.

**At least two students must be able to independently reproduce every major
reported result.** If only one person can regenerate a number, that number is
not yet a result.

## Eight weeks

| week | focus | what happens |
|---|---|---|
| **W1** | build | All five in parallel: S1 dataset audit and preprocessing · S2 endpoint configuration and validation · S3 citation schema · S4 intervention design · S5 literature and statistics plan. **Milestone: 20 pages pass raw HTML → citation view → model → valid XML.** |
| **W2** | pilot | 100–150 development pages. Validate classification, XML compliance, citation exact-match, context length, preprocessing, inference stability. **The real go/no-go: can the model reliably produce machine-locatable evidence?** |
| **W3** | baseline | Freeze Dataset B. 300 phishing + 300 benign for the RQ1 results. Pilot the V1/V2/V3 ladder. |
| **W4** | citations | Full XML prompt. Evaluate grounding, semantic support, unsupported claims, reasoning↔verdict consistency. Freeze the eligible set. |
| **W5** | intervene | C1 · C2 · C3 on eligible pages. Analyse paired changes. |
| **W6** | placebo | C1 + cookie placebo + copyright placebo. Adoption rate, verdict flips, explanation changes. |
| **W7** | extend | Human annotation, inter-annotator agreement, correct-answer/wrong-evidence analysis. If time: evidence competition, necessity/sufficiency, a second LLM. |
| **W8** | write | Statistics, tables, figures, failure examples, limitations, report, paper draft, presentation. |

Weeks 1 and 2 carry hard milestones. If they are not met the plan changes,
rather than continuing on hope.

## Optional extensions

Add these only once the core has landed. Each is self-contained.

- **A — necessity and sufficiency.** Removal tests one direction. Also keep only
  the cited evidence plus minimal context and ask whether the verdict survives.
- **B — evidence competition.** Show genuine evidence and a superficially
  suspicious placebo at once; study which one it chooses to cite.
- **C — explanation burden.** Compare accuracy across V1/V2/V3: does asking for
  more reasoning make it worse at security?
- **D — cross-LLM.** One or two more 7B/8B models — not a leaderboard, but
  whether grounding failures are model-specific or common to LLMs.
- **E — right answer, wrong evidence.** Quantify how far accuracy overestimates
  trustworthy reasoning.
