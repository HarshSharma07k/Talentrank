"""FastAPI service for TalentRank matching."""

from __future__ import annotations

import torch
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import faiss
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import CrossEncoder, SentenceTransformer

from src.talentrank import embeddings as embeddings_module
from src.talentrank import pipeline as pipeline_module
from src.talentrank import rerank as rerank_module
from src.talentrank.config import (
    BI_ENCODER_MODEL_NAME,
    CORS_ALLOWED_ORIGINS,
    CROSS_ENCODER_MODEL_NAME,
    JOB_INDEX_PATH,
)
from src.talentrank.pipeline import match


class MatchRequest(BaseModel):
    """Request payload for resume-to-job matching."""

    resume_text: str


FAISS_INDEX: faiss.Index | None = None
BI_ENCODER_MODEL: SentenceTransformer | None = None
CROSS_ENCODER_MODEL: CrossEncoder | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load shared models and the FAISS index once at application startup."""

    global FAISS_INDEX, BI_ENCODER_MODEL, CROSS_ENCODER_MODEL

    # 1. Detect the RTX 3050 GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("\n" + "=" * 40)
    print(f"BOOTING ML ENGINE ON: {device.upper()}")
    print("=" * 40 + "\n")

    index_path = Path(JOB_INDEX_PATH)
    FAISS_INDEX = faiss.read_index(str(index_path))

    # 2. Route the models directly to the GPU VRAM
    BI_ENCODER_MODEL = SentenceTransformer(BI_ENCODER_MODEL_NAME, device=device)
    CROSS_ENCODER_MODEL = CrossEncoder(CROSS_ENCODER_MODEL_NAME, device=device)

    embeddings_module.DEFAULT_SENTENCE_TRANSFORMER_MODEL = BI_ENCODER_MODEL
    rerank_module.DEFAULT_CROSS_ENCODER_MODEL = CROSS_ENCODER_MODEL

    pipeline_module._load_index_manager()
    yield


app = FastAPI(title="TalentRank API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Return a minimal health check response."""
    return {"status": "healthy"}


@app.post("/match")
def match_resume(request: MatchRequest) -> list[dict[str, Any]]:
    """Match a resume against the job corpus and return ranked results."""
    return match(request.resume_text)
