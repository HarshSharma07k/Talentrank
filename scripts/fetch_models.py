"""Bake model weights into the Docker image's Hugging Face cache. See enhancements/14.

Run inside the `models` build stage with `HF_HOME` pointed at a cache directory that
gets copied forward into the runtime image. `runtime-base` then sets
`HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`, so at container boot `models.py`'s
`SentenceTransformer(...)`/`CrossEncoder(...)` calls must find these weights already
on disk rather than reaching out to huggingface.co.

Reads model identifiers from `get_settings()` rather than hardcoding them, so this
script structurally cannot bake a different model than the one `models.py` will
request at runtime -- see enhancements/14's risk note on `CROSS_ENCODER_MODEL_NAME`
needing the explicit `cross-encoder/` org prefix to resolve the same way in both
places.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentence_transformers import CrossEncoder, SentenceTransformer  # noqa: E402

from src.talentrank.config import get_settings  # noqa: E402


def fetch_models() -> None:
    """Download and cache the bi-encoder and cross-encoder weights."""

    settings = get_settings()

    print(f"Fetching bi-encoder: {settings.bi_encoder_model_name}")
    SentenceTransformer(settings.bi_encoder_model_name)

    print(f"Fetching cross-encoder: {settings.cross_encoder_model_name}")
    CrossEncoder(settings.cross_encoder_model_name, max_length=settings.cross_encoder_max_length)

    print("Model weights baked.")


if __name__ == "__main__":
    fetch_models()
