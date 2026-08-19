"""Fetch PhreshPhish shards from the Hugging Face hub.

The full corpus is ~36.6 GB compressed / ~193 GB expanded, so nothing here
downloads everything by default. One shard is enough to build and test the
whole pipeline; scale up only once the pipeline is frozen.

    python -m phishfaith.download --shards 1 --split test
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import HF_DATASET, HF_REVISION, RAW_DIR, TEST_SHARDS, TRAIN_SHARDS


def shard_name(split: str, index: int) -> str:
    return f"data/{split}-{index:03d}.parquet"


def download_shards(split: str = "test", n: int = 1, dest: Path = RAW_DIR) -> list[Path]:
    """Download the first `n` shards of `split` into `dest`. Returns local paths."""
    from huggingface_hub import hf_hub_download

    total = TRAIN_SHARDS if split == "train" else TEST_SHARDS
    if not 1 <= n <= total:
        raise ValueError(f"{split} has {total} shards; asked for {n}")

    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        local = hf_hub_download(
            repo_id=HF_DATASET,
            filename=shard_name(split, i),
            repo_type="dataset",
            revision=HF_REVISION,
            local_dir=dest,
        )
        paths.append(Path(local))
        print(f"[download] {shard_name(split, i)} -> {local}")
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["train", "test"], default="test")
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--dest", type=Path, default=RAW_DIR)
    args = ap.parse_args()
    download_shards(args.split, args.shards, args.dest)


if __name__ == "__main__":
    main()
