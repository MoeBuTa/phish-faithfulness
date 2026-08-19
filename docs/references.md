# References

All links verified 2026-08-19. **Check the licence before reusing anything** —
three of these repos ship no licence at all, which means their code and data
cannot be redistributed.

## Datasets

**PhreshPhish** — the project's main corpus · CC-BY-4.0
Dalton, Gowda, Rao, Pargi, Hadj Khodabakhshi, Rombs, Jou & Marwah · arXiv preprint (no venue)
666,315 pages: 498,255 train / 168,060 test. Fields: `sha256, url, label, target, date, lang, lang_score, html`. ~36.6 GB download, ~193 GB expanded. Ships base-rate benchmark subsets.
<https://huggingface.co/datasets/phreshphish/phreshphish> · <https://arxiv.org/abs/2507.10854>

**Phishing Website Dataset (Zenodo)** — fallback for any visual arm · CC-BY-4.0
Putra, I Kadek Agus Ariesta · 2023
10,395 sites — 5,244 legitimate, 5,151 phishing, 86 target brands. The only source shipping screenshots + HTML + CSS + WHOIS per site. **Not usable for cross-class claims** — see `feasibility.md`.
<https://zenodo.org/records/8041387> · <https://doi.org/10.5281/zenodo.8041387>

## Model

**WhiteRabbitNeo-V3-7B → DeepHat-V1-7B** · Apache-2.0 · base `Qwen/Qwen2.5-Coder-7B`
The old ID now 301-redirects. Cite the new one and note the former name.
<https://huggingface.co/DeepHat/DeepHat-V1-7B>

## Method — read before Week 1

**Walk the Talk? Measuring the Faithfulness of LLM Explanations**
Matton, Ness, Guttag & Kıcıman · ICLR 2025 (spotlight)
Defines faithfulness as causal concept influence and surfaces concepts that drive the decision but never appear in the explanation. The closest methodological ancestor.
<https://arxiv.org/abs/2504.14150>

**Explanation-Driven Counterfactual Testing (EDCT)**
Ding, Vasa & Ramadwar · NeurIPS 2025 Workshop on Regulatable ML
Treats the explanation as a falsifiable hypothesis: parse cited concepts, edit them, score whether answer and explanation move. Same procedure as ours, on vision-language tasks. **Cite as foundation, not related work.**
<https://arxiv.org/abs/2510.00047>

**On Measuring Faithfulness or Self-consistency of NL Explanations (CC-SHAP)**
Parcalabescu & Frank · ACL 2024 (Main, Long)
Compares which input tokens drive the prediction versus the explanation. Useful as a baseline; its authors are explicit that it tests output-level self-consistency, not internals.
<https://aclanthology.org/2024.acl-long.329>

**ERASER: A Benchmark to Evaluate Rationalized NLP Models**
DeYoung, Jain, Rajani, Lehman, Xiong, Socher & Wallace · ACL 2020
Origin of comprehensiveness / sufficiency. Extension A is essentially this pair applied to phishing.
<https://aclanthology.org/2020.acl-main.408>

## Closest work — read before writing any novelty claim

**Evaluating LLMs for Phishing Detection, Self-Consistency, Faithfulness, and Explainability**
Kuikel, Piplai & Aggarwal · arXiv preprint (no venue)
Despite the title it is **email-only** — HTML is stripped during preprocessing — and correlational (CC-SHAP), with no intervention. Cite with an explicit scoping sentence.
<https://arxiv.org/abs/2506.13746>

## Detectors — where E1/E2/E3 comes from

**Phishpedia** · repo CC0-1.0
Lin, Liu, Divakaran, Ng, Chan, Lu, Si, Zhang & Dong · USENIX Security '21
Visual brand identification against a reference list. Decision rule is essentially *brand matched + domain mismatched → phishing* — worth reading as the field's implicit definition of the label.
<https://www.usenix.org/conference/usenixsecurity21/presentation/lin> · <https://github.com/lindsey98/Phishpedia>

**PhishLLM / PhishVLM** · repo **NO LICENCE**
Liu, Lin, Teoh, Liu, Huang & Dong · USENIX Security '24, pp. 523–540
Reference-based detection without a predefined brand list. Its pipeline — brand recognition → credential-requiring-page check → domain consistency — is where E1/E2/E3 comes from. **Do not redistribute.**
<https://www.usenix.org/conference/usenixsecurity24/presentation/liu-ruofan> · <https://github.com/code-philia/PhishVLM>

**Multimodal LLMs for Phishing Webpage Detection** · repo **NO LICENCE**
Lee, Lim, Hooi & Divakaran · eCrime 2024 (IEEE), doi 10.1109/eCrime66200.2024.00007
Two-phase LLM system — brand identification then domain verification — explicitly marketed as interpretable. The clearest example of the systems this project audits. Re-author the prompt schema in your own words rather than copying.
<https://arxiv.org/abs/2408.05941> · <https://github.com/JehLeeKR/Multimodal_LLM_Phishing_Detection>

## Perturbation operators

**Are Adversarial Phishing Webpages a Threat in Reality?** · repo **MIT**
Yuan, Hao, Apruzzese, Conti & Wang · WWW 2024, pp. 1712–1723
Legitimate, unperturbed phishing, lab-adversarial and wild-adversarial webpages plus generation code. MIT-licensed — **the one set of perturbation operators we can legally borrow** for Student 4.
<https://arxiv.org/abs/2404.02832> · <https://github.com/hihey54/www24_threatAdvPhish>

## SLM baseline

**Small Language Models for Phishing Website Detection** · repo **NO LICENCE**
Goldenits, König, Raubitzek & Ekelhart · J. Cybersecurity and Privacy 6(2):48, 2026
The nearest SLM benchmark: cost, performance and privacy trade-offs on HTML-only pages. Checks label-vs-score coherence but does no intervention. Repo ships no data and no generations — their outputs cannot be reused.
<https://arxiv.org/abs/2511.15434> · <https://www.mdpi.com/2624-800X/6/2/48> · <https://github.com/sbaresearch/benchmarking-SLMs>
