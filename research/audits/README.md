# Feasibility audit scripts

The code behind [`docs/feasibility.md`](../../docs/feasibility.md). Kept for
auditability, not because the project runs them — they operate on Zenodo
8041387, which the project **rejected** as its corpus.

Keep them. When someone asks "why not the Zenodo corpus, it has screenshots?",
the answer is a number these scripts produced.

| script | what it establishes |
|---|---|
| `audit_meta.py` | shortcut baselines on all 10,395 sites, grouped by registrable domain — page text alone separates the classes at 0.960 |
| `audit_matched.py` | 1:1 size-matched subset; the residual signal survives size matching |
| `audit_ablation.py` | **the corrected ablation ladder** — 0.931 → 0.925 (minus brand aliases) → 0.929 (minus credential vocab) → **0.838 from English function words alone**. The residual is document register, not brand names |
| `audit_brandmatched.py` | brand-controlled pair yield |
| `audit_pairs2.py` | **corrected** pair construction — shuffles, keeps pairs together, splits *by pair*, 20 repeats |
| `audit_html.py` | HTML-level features and E1/E2/E3 localisability on both classes |
| `audit_render.py` | cost vs length-shortcut for four input renderings |
| `intervene.py` | first substitution prototype — superseded, kept because its bugs are documented |
| `intervene2.py` | **corrected** prototype: public-suffix-aware via `tldextract`, checks against *both* brands' official domains |
| `prompts_phish.py` | FORCED/FREE prompt contract; endpoint is `p_phish`, not the verdict |
| `smoke.py` | day-2 gate, with a balanced-brace JSON extractor |
| `brand_pair_yield.csv` | per-brand phishing count, official domain, legit pages, pair yield |

Two of these files exist in corrected and uncorrected form on purpose.
`intervene.py` defined `swap_host()` and never called it, and only checked the
original brand's domain rather than the decoy's; `intervene2.py` fixes both.
`audit_meta.py`'s `reg()` splits on the last two labels, so `rakuten.co.jp`
becomes `co.jp` — the fix is in `audit_ablation.py`. Read the corrections list
in `feasibility.md` before trusting any number printed by the earlier version.

Data is not committed. It is re-fetchable from
`https://zenodo.org/api/records/8041387/files/<name>/content`.

One deliberate edit to the archive: `smoke.py` originally defaulted
`OPENAI_BASE_URL` to a private gateway host. That default is removed — the
variable is now required from the environment. Nothing else was changed.
