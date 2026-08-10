"""FastAPI service for TalentRank matching."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import subprocess
import time
from typing import AsyncIterator
import uuid

import anyio
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import torch

from src.talentrank import pipeline as pipeline_module
from src.talentrank.config import BASE_DIR, CORS_ALLOWED_ORIGINS, get_settings
from src.talentrank.extract import (
    EmptyExtractionError,
    EncryptedPdfError,
    UnsupportedFileTypeError,
    extract_text_from_upload,
)
from src.talentrank.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from src.talentrank.models import ModelBundle, get_model_bundle, warmup
from src.talentrank.schemas import ExtractTextResponse, HealthResponse, JobFamilyCount, MatchRequest, MatchResponse

# Bounds each chunked read from the upload stream -- see `extract_text` below, which
# reads in chunks rather than `await file.read()`-ing an unbounded body into memory.
_UPLOAD_CHUNK_BYTES = 1_048_576

logger = logging.getLogger("talentrank.api")
if not logger.handlers:
    # A logger with no handler drops every record below WARNING regardless of what
    # uvicorn's own --log-level is set to -- that flag only governs uvicorn's loggers.
    # `logging.basicConfig()` would fix that too, but it configures the *root*
    # logger, which also raises every third-party logger's effective level (httpx,
    # huggingface_hub) to INFO, flooding startup with their request-level logs.
    # Attaching a handler directly here and disabling propagation keeps this scoped
    # to talentrank's own logger.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _git_sha() -> str:
    """Best-effort short git SHA, computed once at import time. "unknown" outside a
    git checkout (e.g. a container image that doesn't COPY .git/)."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


GIT_SHA: str = _git_sha()
START_TIME: float = time.monotonic()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure torch/thread limits, then load the model bundle once and warm it.

    `get_model_bundle()` loads models, the FAISS index, and the jobs frame in one
    seam (see enhancements/03). Its `FileNotFoundError` (missing `data/processed/`)
    is caught here rather than left to propagate, because `functools.lru_cache` does
    not cache an exception -- startup still succeeds instead of crashing, and the
    first request after the corpus exists retries the load and succeeds.
    """

    settings = get_settings()
    torch.set_num_threads(settings.torch_num_threads)
    torch.set_grad_enabled(False)
    anyio.to_thread.current_default_thread_limiter().total_tokens = settings.max_request_threads

    logger.info("Booting ML engine")
    try:
        bundle = get_model_bundle()
        warmup(bundle)
        logger.info("Model bundle warm on device=%s", bundle.device)
    except FileNotFoundError:
        logger.warning("Corpus artifacts not found at startup; run scripts/prep_data.py and build_index.py.")

    yield


app = FastAPI(title="TalentRank API", lifespan=lifespan)

# Registration order is significant: the *last*-added middleware becomes the
# *outermost* layer. CORS must wrap the rate limiter and the logger -- added last --
# so a 429 or an unhandled error still carries CORS headers, not just a 200.
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _format_validation_errors(exc: RequestValidationError) -> str:
    """Turn pydantic's structured error list into one human sentence, per enhancements/02."""

    parts: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(piece) for piece in error["loc"] if piece != "body")
        parts.append(f"{loc}: {error['msg']}" if loc else str(error["msg"]))
    return "; ".join(parts) or "Invalid request."


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": _format_validation_errors(exc)})


@app.exception_handler(FileNotFoundError)
def handle_missing_artifacts(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Corpus artifacts not built; run scripts/prep_data.py and scripts/build_index.py."},
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = uuid.uuid4().hex[:8]
    logger.exception("Unhandled error (request_id=%s)", request_id)
    return JSONResponse(status_code=500, content={"detail": f"Internal server error (request id: {request_id})."})


@app.get("/health", response_model=HealthResponse)
def health(bundle: ModelBundle = Depends(get_model_bundle)) -> HealthResponse:
    """Rich, cheap health check that feeds the frontend hero and warming state."""

    settings = get_settings()

    return HealthResponse(
        status="healthy",
        version=GIT_SHA,
        device=bundle.device,
        warm=bundle.warm,
        corpus_profile=settings.corpus_profile,
        corpus_size=len(bundle.jobs),
        index_size=bundle.index.index.ntotal,
        bi_encoder=settings.bi_encoder_model_name,
        cross_encoder=settings.cross_encoder_model_name,
        cache_backend=settings.cache_backend,
        uptime_seconds=time.monotonic() - START_TIME,
    )


@app.get("/job-families", response_model=list[JobFamilyCount])
def job_families(bundle: ModelBundle = Depends(get_model_bundle)) -> list[JobFamilyCount]:
    """The family facet, with measured counts, computed once at startup from the
    loaded frame. Never hardcode this list client-side -- see enhancements/05."""

    return bundle.families


@app.post("/extract-text", response_model=ExtractTextResponse)
async def extract_text(file: UploadFile = File(...)) -> ExtractTextResponse:
    """Extract resume text from an uploaded PDF or DOCX. Deliberately separate from
    `/match` -- see enhancements/06 -- so the user can see and edit the extracted
    text before anything is matched, and so `/match`'s cache key stays a hash of
    text rather than of file bytes.

    Reads the upload in bounded chunks (never `await file.read()` the whole body)
    so an oversized upload is rejected before it fully lands in memory.
    """

    settings = get_settings()
    filename = file.filename or "upload"

    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > settings.max_upload_bytes:
            raise HTTPException(413, detail=f"File exceeds the {settings.max_upload_bytes}-byte upload limit.")
        chunks.append(chunk)

    content = b"".join(chunks)

    try:
        result = extract_text_from_upload(filename, content)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(415, detail=str(exc)) from exc
    except (EncryptedPdfError, EmptyExtractionError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc

    return ExtractTextResponse(
        text=result.text,
        char_count=result.char_count,
        page_count=result.page_count,
        filename=filename,
        truncated=result.truncated,
    )


@app.post("/retrieve", response_model=MatchResponse)
def retrieve(request: MatchRequest, bundle: ModelBundle = Depends(get_model_bundle)) -> MatchResponse:
    """Stage 1 only: bi-encoder retrieval, no reranking, never cached. Fast -- the
    progressive-UI enabler."""

    return pipeline_module.retrieve_response(
        request.resume_text, top_k=request.top_k, top_n=request.top_n, bundle=bundle
    )


@app.post("/match", response_model=MatchResponse)
def match_resume(request: MatchRequest, bundle: ModelBundle = Depends(get_model_bundle)) -> MatchResponse:
    """Retrieve candidates and rerank them with the cross-encoder, fronted by the
    process result cache -- see enhancements/07."""

    return pipeline_module.cached_match(
        request.resume_text,
        top_k=request.top_k,
        top_n=request.top_n,
        filters=request.filters,
        bundle=bundle,
        explain=request.explain,
    )
