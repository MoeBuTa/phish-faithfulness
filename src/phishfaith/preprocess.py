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
from collections import Counter
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


def build_manifest(shards: list[Path], out: Path) -> pd.DataFrame:
    frames = [pd.read_parquet(p, columns=COLUMNS) for p in shards]
    df = pd.concat(frames, ignore_index=True)
    counts = Counter({"loaded": len(df)})

    df = df[df["lang"] == "en"]
    counts["after_english"] = len(df)

    df = df[df["lang_score"] >= MIN_LANG_SCORE]
    counts["after_lang_score"] = len(df)

    size = df["html"].str.len()
    df = df[(size >= MIN_HTML_CHARS) & (size <= MAX_HTML_CHARS)]
    counts["after_size"] = len(df)

    df = df.drop_duplicates(subset="sha256")
    counts["after_exact_dedup"] = len(df)

    df = df.assign(dup_key=df["html"].map(near_dup_key)).drop_duplicates(subset="dup_key")
    counts["after_near_dedup"] = len(df)

    out.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["html"]).to_csv(out, index=False)
    df.to_parquet(out.with_suffix(".parquet"), index=False)

    print("filter                 rows")
    for k, v in counts.items():
        print(f"{k:<22} {v:>7}")
    print("\nlabel balance:", df["label"].value_counts().to_dict())
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
