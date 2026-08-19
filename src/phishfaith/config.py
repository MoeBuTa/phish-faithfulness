"""Paths and dataset coordinates. Everything else imports from here."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
MANIFEST_DIR = DATA_DIR / "manifests"

# PhreshPhish, verified 2026-08-19 against the HF dataset API:
# ungated, CC-BY-4.0, 498,255 train + 168,060 test rows in 56 + 21 parquet shards.
# Columns: sha256, url, label, target, date, lang, lang_score, html.
HF_DATASET = "phreshphish/phreshphish"
HF_REVISION = "main"
TRAIN_SHARDS = 56
TEST_SHARDS = 21

# The smallest shard (~55 MB). Use this one for development.
STARTER_SHARD = "data/test-000.parquet"

# Preprocessing thresholds. Frozen once Dataset A/B/C are frozen -- do not
# tune these after Week 2.
MIN_LANG_SCORE = 0.80
MIN_HTML_CHARS = 500
MAX_HTML_CHARS = 400_000
