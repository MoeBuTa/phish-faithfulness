"""Build the C1-C4 paired benchmark from a manifest plus the model's C1 outputs.

This is the step that makes the dataset model-conditioned: C2 and C3 depend on
what the model cited, so this cannot run until C1 inference is done.

    # 1. run the model on C1 prompts, one JSON object per line:
    #    {"sha256": "...", "raw": "<result>...</result>"}
    python scripts/build_variants.py \
        --manifest data/manifests/dev.parquet \
        --c1-outputs data/interim/c1_outputs.jsonl \
        --out data/interim/variants.jsonl

Every emitted row carries the prompt to run and the provenance of the edit, so
the pair-validation report is a query over this file rather than a rerun.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from phishfaith import citation_view, grounding, interventions, parse, prompts  # noqa: E402


def build(manifest: Path, c1_outputs: Path, out: Path, version: str = "V3") -> Counter:
    df = pd.read_parquet(manifest).set_index("sha256")
    stats = Counter()

    out.parent.mkdir(parents=True, exist_ok=True)
    with c1_outputs.open() as fin, out.open("w") as fout:
        for line in fin:
            rec = json.loads(line)
            sha = rec["sha256"]
            if sha not in df.index:
                stats["not_in_manifest"] += 1
                continue
            row = df.loc[sha]
            stats["pages"] += 1

            view = citation_view.build(row["url"], row["html"])
            parsed = parse.parse(rec["raw"])
            if parsed.verdict is None:
                stats["unparseable"] += 1
                continue

            g = grounding.check(view, parsed)
            if not g.eligible:
                stats["not_eligible"] += 1
                continue
            stats["eligible"] += 1

            cited = {c.source_id for c in parsed.citations}
            # Edit one cited element per pair, so the contrast stays single-factor.
            target = sorted(cited)[0]

            rows = [dict(sha256=sha, condition="C1", source_id=None, operator=None,
                         kind=None, operator_matched=None, prompt=prompts.render(view, version))]

            v2, iv2 = interventions.build_c2(view, target)
            interventions.verify_single_change(view, v2, {target})
            rows.append(dict(sha256=sha, condition="C2", source_id=iv2.source_id,
                             operator=iv2.operator, kind=iv2.kind, operator_matched=None,
                             prompt=prompts.render(v2, version)))

            matched = interventions.pick_matched_uncited(view, cited, target)
            if matched is None:
                stats["no_matched_control"] += 1
                continue  # a pair without its control is not usable
            v3, iv3 = interventions.build_c3(view, matched, iv2)
            interventions.verify_single_change(view, v3, {matched})
            rows.append(dict(sha256=sha, condition="C3", source_id=iv3.source_id,
                             operator=iv3.operator, kind=iv3.kind,
                             operator_matched=iv3.operator_matched,
                             prompt=prompts.render(v3, version)))
            stats["operator_matched" if iv3.operator_matched else "operator_mismatched"] += 1

            v4, iv4 = interventions.build_c4(view)
            interventions.verify_single_change(view, v4, {"P1", "P2"})
            rows.append(dict(sha256=sha, condition="C4", source_id=None,
                             operator=iv4.operator, kind=iv4.kind, operator_matched=None,
                             prompt=prompts.render(v4, version)))

            for r in rows:
                fout.write(json.dumps(r) + "\n")
            stats["complete_quads"] += 1

    for k, v in stats.most_common():
        print(f"{k:<22} {v:>7}")
    print(f"\nwrote {out}")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--c1-outputs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--prompt-version", default="V3", choices=["V1", "V2", "V3"])
    args = ap.parse_args()
    build(args.manifest, args.c1_outputs, args.out, args.prompt_version)


if __name__ == "__main__":
    main()
