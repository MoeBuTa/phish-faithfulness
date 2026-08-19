"""Turn raw PhreshPhish shards into a frozen manifest.

Filters, in order: language, HTML size, exact duplicates, near duplicates.
Every filter reports how many rows it removed -- that table goes into
`dedup_report.md`, it is not a debug print.

    python -m phishfaith.preprocess data/raw/data/test-000.parquet --out data/manifests/dev.csv
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

import pandas as pd

from .config import MANIFEST_DIR, MAX_HTML_CHARS, MIN_HTML_CHARS, MIN_LANG_SCORE

COLUMNS = ["sha256", "url", "label", "target", "date", "lang", "lang_score", "html"]

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def near_dup_key(html: str) -> str:
    """Cheap near-duplicate key: hash of the visible-text shingle set.

    Not LSH. It catches templated kits that differ only in attributes, which is
    the dominant duplicate mode in phishing corpora. Replace with datasketch
    MinHash before the Dataset B freeze if the collision rate looks wrong.
    """
    text = _WS.sub(" ", _TAG.sub(" ", html)).strip().lower()
    words = text.split()
    shingles = {" ".join(words[i : i + 5]) for i in range(0, max(len(words) - 4, 0), 5)}
    digest = hashlib.sha1()
    for s in sorted(shingles)[:200]:
        digest.update(s.encode("utf-8", "ignore"))
    return digest.hexdigest()


def _tally(df: pd.DataFrame) -> tuple[int, int, int, float]:
    vc = df["label"].value_counts()
    b, p = int(vc.get("benign", 0)), int(vc.get("phish", 0))
    return len(df), b, p, (p / (b + p) if b + p else 0.0)


def build_manifest(shards: list[Path], out: Path) -> pd.DataFrame:
    frames = [pd.read_parquet(p, columns=COLUMNS) for p in shards]
    df = pd.concat(frames, ignore_index=True)
    steps = [("loaded", _tally(df))]

    df = df[df["lang"] == "en"]
    steps.append(("english", _tally(df)))

    df = df[df["lang_score"] >= MIN_LANG_SCORE]
    steps.append(("lang_score", _tally(df)))

    size = df["html"].str.len()
    df = df[(size >= MIN_HTML_CHARS) & (size <= MAX_HTML_CHARS)]
    steps.append(("size", _tally(df)))

    df = df.drop_duplicates(subset="sha256")
    steps.append(("exact_dedup", _tally(df)))

    df = df.assign(dup_key=df["html"].map(near_dup_key)).drop_duplicates(subset="dup_key")
    steps.append(("near_dedup", _tally(df)))

    out.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["html"]).to_csv(out, index=False)
    df.to_parquet(out.with_suffix(".parquet"), index=False)

    print(f"{'filter':<14}{'rows':>8}{'benign':>8}{'phish':>8}{'phish %':>9}")
    for name, (n, b, p, share) in steps:
        print(f"{name:<14}{n:>8}{b:>8}{p:>8}{share:>8.1%}")

    # The two classes differ in size by roughly an order of magnitude (benign median
    # ~271k chars, phish ~29k in test-000), and phishing pages are short enough that
    # language detection is less confident on them. So several of these filters cut
    # one class harder than the other and quietly rewrite the class balance. Every
    # such step is reported -- a filter that moves the balance is a sampling decision,
    # not a cleaning step, and it must not be made by accident.
    skewed = [
        (name, prev[3], cur[3])
        for (_, prev), (name, cur) in zip(steps, steps[1:])
        if abs(cur[3] - prev[3]) > 0.02
    ]
    if skewed:
        print("\nWARNING: these filters moved the class balance:")
        for name, before, after in skewed:
            print(f"         {name:<12} {before:>6.1%} -> {after:>6.1%}  ({after - before:+.1%})")
        print("         Do not let them set the balance of the RQ1 baseline set -- sample that\n"
              "         with explicit length matching. See docs/SPEC.md, 'What the raw HTML is'.")

    print(f"\nwrote {out} and {out.with_suffix('.parquet')}")
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("shards", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=MANIFEST_DIR / "dev.csv")
    args = ap.parse_args()
    build_manifest(args.shards, args.out)


if __name__ == "__main__":
    main()
