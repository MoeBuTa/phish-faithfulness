# Phishing-webpage explanation-faithfulness — feasibility measurements

> **Provenance.** This is the pre-project audit, kept verbatim. It is a record,
> not a plan — the corrections at the bottom include mistakes that were made and
> then caught, and they are kept because the same mistakes are available to be
> made again. The scripts it refers to are in
> [`research/audits/`](../research/audits/); `verify_labelfn/` (Phishpedia and
> PhishVLM clones) is not committed — re-clone it from the repos in
> [`references.md`](references.md). Design decisions that followed from this
> audit are in [`SPEC.md`](SPEC.md), which supersedes anything here.

Everything here was measured first-hand. Numbers taken from a paper, a README or a survey
are marked as such. Reviews (a 10-agent artifact verification, a 7-agent adversarial
re-check, and a Codex source review) were run against these; corrections land at the bottom.

## The question

Do LLM/MLLM phishing-webpage detectors causally rely on the structured evidence they cite —
brand impersonation (E3), credential-taking form (E2), domain-brand mismatch (E1)?
The originally proposed method was: neutralise a **cited** piece of evidence, re-ask, and
compare against neutralising a comparable **uncited** piece.

## Finding 1 — that method is confounded, verified in source

E1/E2/E3 are not merely *correlated* with the label. They **are** the operational label
function in this literature:

- `Phishpedia/phishpedia/logo_matching.py` — comment verbatim: *"If the webpage domain
  exactly aligns with the target website's domain => Benign"*, then
  `if extracted_domain in matched_domain: matched_target, matched_domain = None, None`.
  `phishpedia.py:85` sets `phish_category = 1` otherwise.
- `PhishVLM/scripts/pipeline/phishvlm.py:610-653` —
  `domain_brand_inconsistent = (domain4pred != domain4url) or (suffix4pred != suffix4url)`;
  `phish_condition = domain_brand_inconsistent`; then gated on `crp_prediction_llm`.

So erasing the domain mismatch, or the credential form, flips the ground truth under the
field's own rule. **A model that flips is being correct, not unfaithful.** And the
cited-vs-uncited control is impossible as specified: anything genuinely uncited is by
construction not part of the label definition, so it has strictly lower predictive strength.

Open question the adversarial pass was asked to settle: the corpora's labels are
community/crawler-reported, not produced by running Phishpedia. If so this is a statement
about detector logic rather than about the dataset label, and the confound is weaker than
stated above. Do not write the strong version until that is resolved.

## Finding 2 — label-preserving substitution works, and is mechanical

Instead of erasure, substitute **within the class** so the label is provably unchanged:

| operator | what it does | clean rate (n=151 phishing pilot) |
|---|---|---|
| S1 brand swap | rewrite the impersonated brand in visible text, `<title>`, alt/title/placeholder/aria-label, image filenames | 91.4% arbitrary decoy / 87.4% within-category decoy |
| S2 host swap | replace the host with another host observed in the corpus, still != the official domain | 93.4% / 100% |
| S0 no-op | byte-identical but for an HTML comment | — (the noise floor the original design lacked) |

Both preserve the label: the page still impersonates a brand it is not hosted by. The
prediction is directional on two channels at once — a faithful explanation **must** update
the cited brand/host string, and the verdict **must not** move.

Supporting measurements on the same pilot:

- brand string locatable in the page: **90.7%** (visible text 78.1%, `<title>` 57.0%,
  `img src` 51.0%, alt/title attrs 47.0%)
- `<input type="password">`: **63.6%** of phishing vs **14.8%** of legitimate pages
- page domain == official brand domain: **0.0%** of phishing pages

Known defects in the S1 prototype, not yet fixed: `metamask [Finance] -> M&T Bank` yields
"M&T - A crypto wallet & gateway to blockchain apps" (brands.csv lumps crypto wallets with
banks) and `microsoft -> OneDrive` picks a same-parent brand. The **semantically coherent**
swap rate is therefore below 87.4% and is currently unmeasured.

## Finding 3 — Zenodo 8041387 cannot carry a detection benchmark

`audit_meta.py`, all 10,395 sites, `GroupShuffleSplit` on registrable domain, majority 0.585:

| given only… | acc | AUC |
|---|---|---|
| whois domain age | 0.716 | 0.740 |
| hand features (11) | 0.786 | 0.874 |
| URL string char 3-5gram | 0.803 | 0.878 |
| **page text word 1-3gram** | **0.960** | **0.990** |

A random split gives 0.957 — essentially identical — so this is **not** split leakage, it is
a population difference: visible-text median 294 chars (phish) vs 2651 (legit), tags 89 vs 336.

Controlling for it, step by step:

| design level | pairs | page-text ngram |
|---|---|---|
| raw corpus | 5,151 / 5,244 | 0.960 |
| size-matched (`audit_matched.py`, controls at 0.495/0.483) | 2,374 | 0.899 — driven by brand tokens: dhl, metamask, paypal, citi, instagram, mygov |
| brand-controlled (`audit_brandmatched.py`) | 336 over 54 brands | 0.687 |
| brand-controlled **and** size-matched | **82 over 30 brands** | test fold 35 rows — too small to measure |

The residual signal after size-matching is a **brand-name lexical prior**: the legitimate half
almost never contains those brands' own pages, so "mentions PayPal" ≈ phishing. That is
precisely the E3 evidence we would intervene on, which is why the uncited control matters.

## Finding 4 — cost and validity are in direct conflict

`audit_render.py`, n=395, tokens approximated as chars/4 (tiktoken unavailable):

| rendering | med tok | p95 tok | fits 32k | fits 128k | **length-only AUC** | cost @300 pages x k=5 x 8 conditions |
|---|---|---|---|---|---|---|
| raw HTML | 22,275 | 256,098 | 59.7% | 87.6% | **0.413** | 267.3M / model |
| no scripts/styles/data-URIs | 6,040 | 60,180 | 88.1% | 98.7% | 0.806 | 72.5M |
| skeleton (whitelisted attrs) | 4,532 | 35,979 | 93.9% | 99.7% | 0.816 | 54.4M |
| visible text only | 600 | 4,864 | 99.7% | 99.7% | 0.779 | 7.2M |

Raw HTML is the **only** rendering where length carries no class signal — because phishing
pages are bloated with inline assets that mask the 9x visible-text gap. Every affordable
rendering brings the shortcut back.

This constrains but does not break the design, because the core arms (no-op, substitution,
injection) are **within-page paired** comparisons: the same page against its own perturbed
version. A class-level length shortcut cannot confound a within-page paired contrast. It
does still bear on any cross-class arm and on any claim that the model "reads the page", so
the shortcut table stays as a mandatory companion.

## Finding 5 — corpus trade-off

| | Zenodo 8041387 | PhreshPhish |
|---|---|---|
| licence | CC-BY-4.0 | CC-BY-4.0, ungated |
| size | 10,395 sites / 38.5 GB | 498,255 train + 168,060 test / 193 GB |
| per page | `original/index/clean.html`, 6 screenshots, CSS, localised assets | `url`, `html`, `target`, `date`, `lang` |
| brand label | `brands` column, phishing rows only | `target` column, phishing rows only |
| **brand label verifiable in page** | **90.7%** | **13/20 in a 20-row sample** |
| re-renderable offline | yes (assets localised) | no screenshots |
| dedup / temporal split / base rates | none | LSH pruning, temporal partition, base-rate benchmarks |

PhreshPhish `target` examples that do not check out: `coolfocus.info/google.php` labelled
`betwinner`; `jiu-jitsuinbridport.blogspot.pt` labelled `google`;
`github.com/darklegiongwin/canvaproaccess` labelled `canva`. The 20-row sample is small —
the adversarial pass was asked to measure this properly. Note the presence test is a lower
bound either way, since a brand can appear only as a logo image.

Verified via `curl https://datasets-server.huggingface.co/info?dataset=phreshphish%2Fphreshphish`
and the HF dataset API (`gated: false`, `license:cc-by-4.0`, lastModified 2026-02-09).

## Finding 6 — what the cited prior artifacts actually are

From the artifact-verification pass, each checked by cloning/executing rather than reading
the README:

- **eCrime 2024 repo** (`JehLeeKR/Multimodal_LLM_Phishing_Detection`) — 3,459 samples ship,
  but each is only `add_info.json` (two keys: `Url`, `html_brand_info` — a flattened 9-field
  text summary) plus a screenshot. **No raw HTML, no DOM, no CSS.** The domain-verification
  stage that produces the phishing verdict **is not in the repo**; `system_prompt_phase2.txt`
  is an LLM judge that requires the ground-truth brand as input, and `Url` is referenced zero
  times in `src/*.py`. The shipped code raises `AssertionError` in `load_prompt_text()` before
  any API call. **No licence file at all.** The reusable asset is the 7-field prompt schema,
  which should be re-authored rather than copied.
- **arXiv:2506.13746** — phishing **email** only; HTML explicitly stripped with BeautifulSoup
  in Sec. II-A; CC-SHAP token-level masking; 40-email evaluation set. webpage / website / URL
  / screenshot / brand appear zero times. Its title says "Phishing Detection", so it must be
  cited with an explicit scoping sentence.
- **sbaresearch/benchmarking-SLMs** — 7 files, 26 KB, **zero data and zero generations across
  all git history**; the paper's claim that the dataset is on GitHub is false. Their
  "coherence" check is a label-vs-score crosstab plus keyword counting, run on n=40, not on
  the 500+500 set. They used this same Zenodo corpus, truncated to <=5% of HTML.
- **EDCT (arXiv:2510.00047, Sept 2025)** — already published the exact procedure (parse cited
  concepts from the explanation, apply targeted counterfactual edits, score the change in both
  answer and explanation) for VLMs on OK-VQA. **The novelty here is domain transfer plus a
  security evidence taxonomy plus a zero-effect control, not a new method.** Cite it as
  foundation.

## Files

| file | what it does |
|---|---|
| `audit_meta.py` | shortcut baselines on all 10,395 sites, grouped by registrable domain |
| `audit_matched.py` | size-matched subset; shows the residual signal is brand-name lexical prior |
| `audit_brandmatched.py` | brand-controlled pair yield (336 / 82 pairs) |
| `audit_html.py` | HTML-level features and E1/E2/E3 localisability on both classes |
| `audit_render.py` | cost vs length-shortcut for four input renderings |
| `intervene.py` | S1/S2 label-preserving substitution prototype |
| `verify_labelfn/` | Phishpedia + PhishVLM clones used for the source-level verification |
| `brand_pair_yield.csv` | per-brand phishing count, official domain, legit pages, pair yield |

Data not committed: `phishing.csv` (61 MB), `not-phishing.csv` (107 MB), `brands.csv`,
`phishing_5001-5151.zip` (215 MB), `not-phishing_5001-5244.zip` (1.64 GB). All re-fetchable
from `https://zenodo.org/api/records/8041387/files/<name>/content`.

## Corrections applied after review

A Codex source-level review broke seven claims. Each is corrected here, and the sections
above should be read against this list. The scripts that produced the wrong numbers are kept
so the correction is auditable; the corrected replacements are `intervene2.py`,
`audit_pairs2.py` and `audit_ablation.py`.

**C-1. `reg()` was not public-suffix aware.** `audit_meta.py:29` returned the last two
labels, so `rakuten.co.jp` → `co.jp` and eight brands acquired the generic alias `com`. It
fed official-brand domains, legitimate grouping and the brand alias set. Everything below
flows from this. Fixed with `tldextract`.

**C-2. The residual after size-matching is NOT a brand-name prior — the claim was wrong.**
It was read off logistic-regression coefficients and never tested. `audit_ablation.py`, with
a public-suffix-aware 219-string alias set and grouping on the corrected domain:

| ablation | acc | AUC |
|---|---|---|
| A0 full visible text | 0.931 | 0.973 |
| A1 minus every brand alias | 0.925 | 0.967 |
| A2 minus brand aliases and multilingual credential vocabulary | 0.929 | 0.968 |
| A3 **English function words only** | **0.838** | 0.909 |

Deleting all 86 brands costs 0.006. Function words alone reach 0.838. The signal is
**document register / page role** — legitimate pages are prose-rich content sites, phishing
pages are terse forms — and it survives length-matching and content-word removal. (A0 reads
0.931 rather than the 0.899 reported earlier because the corrected grouping no longer
lumps every `*.co.jp` into one group.)

**C-3. The brand-controlled pair numbers were wrong and unstable.** v1 took the first *k*
rows unshuffled, discarded pair identity, and split on page domain, so most test-fold brands
contributed only one label. `audit_pairs2.py` shuffles, keeps pairs together, splits **by
pair**, and repeats 20 times:

| design | v1 reported | corrected |
|---|---|---|
| brand-controlled | 336 pairs / 54 brands, acc 0.687 | **178 pairs / 47 brands, acc median 0.880** (IQR 0.852–0.889, AUC 0.960) |
| brand-controlled + size-matched | 82 pairs / 30 brands | **41 pairs / 24 brands**, acc median 0.599 (range 0.500–0.750) |

So brand-controlling barely suppresses the signal, and the fully controlled set is 41 pairs.
**This corpus cannot support a controlled cross-class classification set at all.**

**C-4. The S1 brand-swap coverage was badly overstated.** v1 called a swap "clean" when the
enumerated aliases disappeared, which says nothing about *where* the replacement landed.
`intervene2.py`, n=151:

| | v1 | corrected |
|---|---|---|
| aliases removed | 91.4% | 96.0% (meaningless on its own) |
| **changed rendered text only** | not measured | **19.2%** |
| also mutated script/style bodies or asset URLs | not measured | **58.9%** |
| has an `<img>` whose URL names the brand (pixels never edited) | not measured | **37.7%** |

The `microsoft → OneDrive` same-owner collision still passes the domain-stem guard. So the
E3 brand arm is **not** cheaply mechanical: it needs image editing, OCR verification and a
coherence check, or it must be restricted to the ~19% of text-only pages.

**C-5. S2 was not implemented as described.** `intervene.py:57` defined `swap_host()` and
never called it; the reported figure came from a synthesised `cdn-<old>.secure-update.top`
and only checked the *original* brand's official domain. `intervene2.py` draws from the
observed phishing-host distribution, rewrites the URL, and checks against **both** the
original and the decoy brand's official domain: **96.0%**. This arm survives.

**C-6. "Fully offline re-renderable" was overstated.** Measured on the 151-site zip:

| variant | pages with ≥1 external reference | median refs |
|---|---|---|
| `original.html` | **95.4%** | 10 |
| `index.html` | 55.0% | 1 |
| `clean.html` | 50.7% | 1 |

The localised assets belong to `index.html`, and the intervention prototype was editing
`original.html`. No page was ever actually re-rendered.

**C-7. "The three evidence types are the field's ground-truth label function" is too strong.**
Two implementations' decision branches were verified and do behave as described, but neither
defines the corpus label — Zenodo and PhreshPhish labels are crawler/community-reported.
The correct statement: *erasure changes the decision path of the two cited reference-based
detectors, so it confounds evaluation of them; it does not by itself redefine the
counterfactual's factual label.*

**C-8. A control was quoted by accuracy alone.** The size-matched length control was reported
as "0.495, chance". Its full output is `acc 0.495  F1(phish) 0.000  AUC 0.589` — it predicts
no phishing rows at the default threshold while retaining above-chance ranking. This is the
same failure mode as the previous project's degenerate-model metric. Report acc, F1 and AUC
together for every control.

**What survived the review unchanged:** the 0.960 headline shortcut table and its class
medians (reproduced exactly, and an independent extraction from `clean.html` gave 0.806 vs
0.814 with median token-set overlap 1.0, so it is not an extraction artifact); the ≈0.90
size-matched result across matching order, calliper and maximum-cardinality assignment;
the narrow behaviour of the Phishpedia and PhishVLM decision branches; and the 63.6%
password-input / 0.0% official-domain pilot counts.

### Second review round — the redesign's own metrics do not survive

An adversarial pass re-measured the redesign itself. Six of its seven agents died on API
errors, so **the literature side (novelty, the unread ResearchGate item) is still
unverified**; the findings below are the surviving agent's own measurements, re-verified
here from its artifacts in `adv/`.

**C-9. "PhreshPhish's brand labels are noisy" was a misreading — withdrawn.** Scanning all
30,041 brand-labelled phishing rows (`adv/brand_scan.jsonl`, 47 MB, re-aggregated
independently) against decoy brands drawn from the empirical distribution:

| | attested in page (any channel) | decoy-brand null | lift |
|---|---|---|---|
| PhreshPhish, n=30,041 | 0.642 | 0.111 (300,410 draws) | **5.77×** |
| Zenodo, same code, n=151 | 0.868 | 0.159 | **5.46×** |

The two labels carry the same information; PhreshPhish's is simply attested less often
(35.8% of rows have no in-page attestation at all). The earlier 13/20 point estimate was
right and the inference from it was wrong. The specific example cited as mislabelled —
`coolfocus.info/google.php` → `betwinner` — actually checks out; `betwinner` is present in
the page text and `google.php` is a leftover filename.
Correspondingly, **the Zenodo 90.7% figure is also wrong as stated**: 0.868 under the same
matcher, and it was never scored against a null. Zenodo's null is *higher* (0.159 vs 0.111)
because its pool is 86 brands rather than 1,691 — part of that raw rate is brand-pool
concentration, the same lexical prior as C-2.

**C-10. Arm B's "true causal effect is exactly zero by construction" is half false.**
Marginal base rates on real pages (`adv/armB_baserates.csv`) are lopsided for all four
candidates, but the conditional test (a model of the rest of the page with the carrier
stripped) separates them:

| injection | conditional effect | verdict |
|---|---|---|
| B1 cookie banner | +0.02 bits, p = 0.91 | inert — keep |
| B2 stale copyright | +0.11 bits, p = 0.71 | inert — keep |
| B3 analytics script | −0.53 bits, p = 0.003 | **not inert — drop** |
| B4 SSL badge | +0.48 bits, p = 0.038 | **not inert — drop** |

**C-11. The headline cell `CE > 3σ ∧ EE = 0` is vacuous.** Every injected feature is absent
from the unperturbed page, so it can never appear in the unperturbed explanation: EE ≡ 0 with
probability 1 for B1–B5. The cell collapses to "CE > 3σ". A perfectly faithful model that
says "the injected banner reassured me" still scores EE = 0, because EE is read from the
unperturbed explanation only. That is Matton Def 2.2 with the counterfactual term deleted.
**Fix: EE must be read from the perturbed explanation, or the quadrant must be deleted.**

**C-12. `CE = mean|ΔP| − σ` is not a usable estimator.** On simulated null data (true effect
0, σ = 0.06, 4,000 runs): `abs_then_mean` gives CE = **+0.0069**, `mean_then_abs` gives
**−0.0301** — same data, same null, opposite sign, and the design never says which. It is
also k-dependent (k=1 → +0.008, k=5 → −0.030, k=20 → −0.045), so more data moves it further
from zero. And |ΔP| erases the sign that Arm B's whole question turns on.
**Fix: signed paired ΔP with pre-specified k and aggregation order, reported as a
distribution with a CI. No −σ subtraction, no 3σ threshold.**

**C-13. Per-page PCC(CE, EE) is uninterpretable.** With 9 concepts a true PCC of 0 lands in
[−0.67, +0.67] 95% of the time (5 concepts: [−0.88, +0.88]). Worse, if Arm A yields high EE
and Arm B yields EE = 0, then EE is just an arm label and the correlation's sign is fixed by
which arm the designer gave the larger CE — simulated faithful −0.976, unfaithful +0.533,
inverted +0.995. **Fix: pool across pages, or use ≥20 concepts with a hierarchical estimator.
Never report a per-page PCC.**

**C-14. The power claim fails in context.** Bare, n=150 at d=0.26 gives power 0.886. But
9 perturbations × 3 conditions = 27 primary tests, so Bonferroni α = 0.00185 and power falls
to **0.508** at n=150 (0.912 at n=300). The headline is also an *acceptance* of a null, which
needs TOST: at n=150 with an equivalence bound of d = ±0.20, TOST power is **0.572**, and no
bound was ever specified. **Fix: n = 300, pre-registered 27-test family, explicit equivalence
bound.**

**C-15. Brand-arm yield, refined.** Requiring the brand to be editable in text/title AND
absent from every asset URL and the host: Zenodo **25.8%** (39 of 151), PhreshPhish **10.2%**
(3,059 of 30,041). The percentage is worse for PhreshPhish but the absolute yield is
3,059 pages against 39.

### Third round — the literature side, finally verified

**C-16. The unread ResearchGate item is not a threat.** RG 405481392, *"Counterfactual XAI for
Phishing Detection…"*, is a self-posted preprint by a sole author (Muhammad Abdullah,
NUCES-FAST), DOI 10.13140/RG.2.2.12966.08004, issued 2026-05-30, DataCite publisher
"Unpublished", no venue, no peer review, zero citations. **The full text remains
unobtainable** — RG returns 403 to every route, there is no Wayback or archive.today capture,
and it is absent from Semantic Scholar, CORE, BASE and Unpaywall (OpenAlex
`has_fulltext=false`). The assessment below rests on the abstract recovered verbatim from the
author's Google Scholar record, so it is PLAUSIBLE at body level, not CONFIRMED.

It replicates EXPLICATE's TF-IDF + logistic-regression pipeline and adds three modules:
zero-shot CLIP ViT-B/32 brand verification (60.7% brand accuracy, n=341); a 17-feature
structural classifier (Zenodo F1 0.9644→0.9735, McNemar p=0.008); and DiCE-style
minimum-change counterfactuals **over those tabular features**. So its counterfactuals are
recourse-style edits to a classical classifier's features, not interventions on evidence a
model cited; it measures F1 under shift/evasion plus attribution stability, not faithfulness;
there is no LLM/MLLM detector or explainer (LLMs only generated its PhishFuzzer test set);
and there is no placebo and no label-invariant substitution. Overlap ≈10%, confined to shared
vocabulary. Cite it as independent motivation for brand-impersonation being the hard case.
Residual risk: an unannounced LLM-explanation section cannot be formally excluded, though the
abstract enumerates exactly three modules and none is one.

**C-17. The novelty is narrower than claimed — one of the three deltas is already taken.**
The narrow gap survives: nothing intervenes on cited evidence of a phishing-*webpage*
LLM/MLLM detector while scoring verdict *and* explanation movement. But:

- **Walk the Talk (Matton et al., ICLR 2025 spotlight, arXiv:2504.14150)** intervenes on
  **all** input concepts, not just cited ones, and defines faithfulness as the correlation
  between causal concept effect and explanation-implied effect — explicitly surfacing
  high-CE / EE=0 concepts the explanation omits. **That is functionally the uncited-concept
  control**, published a year before EDCT and more rigorous (Bayesian hierarchical,
  do-operator). The "we add a control" delta is therefore largely spent.
- **EDCT (arXiv:2510.00047)** verified at artifact level: 8 pages, NeurIPS 2025 Regulatable
  ML workshop, 120 curated OK-VQA pairs, four stages ending in PCS × NCC = CCS. It confirms
  it has **no** control — zero occurrences of control/placebo/uncited/distractor, and it
  states outright that "the subsequent stages only intervene on concepts that the model
  itself claims to use."
- The security-transfer delta is partly taken by arXiv:2506.13746, which already brands
  itself as LLM phishing detection + self-consistency + faithfulness (email, correlational,
  no intervention).
- A "security evidence taxonomy" is weak novelty on its own: TraceScope already adjudicates
  phishing URLs against a MITRE ATT&CK evidence checklist.

**What is genuinely unoccupied**, and what the contribution must be reframed to:
 1. the phishing-**webpage multimodal** setting (screenshot + HTML/URL/brand/favicon evidence)
    with intervention on cited evidence scored for verdict AND explanation movement; and
 2. the **inert-injection placebo** — adding evidence whose causal effect on the label is
    null, to see whether the detector spuriously *cites* it. Walk the Talk only manipulates
    concepts genuinely present in the input; EDCT does neither.
Write it as *domain + injection-control*, never as "first with a control".

**C-18. C-11 and C-17 resolve each other.** C-11 showed the cell `CE>3σ ∧ EE=0` is vacuous
because an injected feature is absent from the unperturbed page, so it can never be cited
there. C-17 shows the injection arm is the surviving novelty. Both hold once the measure is
restated: the injection arm's endpoint is the **spurious-citation rate of an inert feature in
the PERTURBED explanation** — did the model, after the injection, cite a feature that has no
causal bearing on the label? That is well defined, is not what Walk the Talk or EDCT measure,
and needs no EE reading of the unperturbed explanation at all.

### Consequence for the design

The corrections do not reverse the direction of the verdict — they harden it. Every
cross-class construction on this corpus fails (0.960 raw, 0.880 brand-controlled, 41 pairs
when fully controlled, and 0.838 from function words alone). The only design the corpus
supports is **within-page paired intervention**, where each page is compared with its own
perturbed version and class-level shortcuts cannot enter. Within that design, order the arms
by how cheaply they are implementable and verifiable: the domain arm and a credential-form
field-renaming arm first, additive zero-effect injection alongside them, and the brand arm
last and scoped.
