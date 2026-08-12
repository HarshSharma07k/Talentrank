"""The `/me` APIRouter: history, saved lists, and feedback. See enhancements/21."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.auth.deps import get_current_user
from src.talentrank.config import get_settings
from src.talentrank.db.models import MatchRun, SavedList, SavedListItem, User
from src.talentrank.db.session import get_db
from src.talentrank.userdata import feedback as feedback_module
from src.talentrank.userdata import history as history_module
from src.talentrank.userdata import lists as lists_module
from src.talentrank.userdata.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    FeedbackStateOut,
    HistoryPatchRequest,
    ImportRequest,
    ImportResult,
    ListCreateRequest,
    ListItemRequest,
    ListRenameRequest,
    MatchRunDetail,
    MatchRunSummary,
    SavedListDetail,
    SavedListItemOut,
    SavedListSummary,
)

router = APIRouter(prefix="/me", tags=["me"])


def _parse_uuid(value: str) -> uuid.UUID | None:
    """A malformed id is exactly as "not found" as one that doesn't exist -- never
    a 422/500. Matches enhancements/21's own ownership-check philosophy: a row
    belonging to another user must be indistinguishable from a row that does not
    exist, and a garbage id is the same category of "not this caller's row."
    """

    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _run_summary(row: MatchRun) -> MatchRunSummary:
    return MatchRunSummary(
        id=str(row.id),
        label=row.label,
        created_at=row.created_at,
        top_k=row.top_k,
        top_n=row.top_n,
        filters=row.filters,
        corpus_profile=row.corpus_profile,
        result_count=len(row.results),
        top_job_titles=[str(r.get("job_title", "")) for r in row.results[:3]],
    )


def _run_detail(row: MatchRun) -> MatchRunDetail:
    return MatchRunDetail(
        id=str(row.id),
        label=row.label,
        resume_hash=row.resume_hash,
        resume_text=row.resume_text,
        top_k=row.top_k,
        top_n=row.top_n,
        filters=row.filters,
        corpus_profile=row.corpus_profile,
        took_ms=row.took_ms,
        created_at=row.created_at,
        results=row.results,
    )


def _list_summary(row: SavedList, item_count: int) -> SavedListSummary:
    return SavedListSummary(
        id=str(row.id), name=row.name, created_at=row.created_at, updated_at=row.updated_at, item_count=item_count
    )


def _item_out(item: SavedListItem) -> SavedListItemOut:
    return SavedListItemOut(
        job_id=item.job_id,
        job_title=item.job_title,
        job_family=item.job_family,
        note=item.note,
        created_at=item.created_at,
    )


def _list_detail(row: SavedList, items: list[SavedListItem]) -> SavedListDetail:
    return SavedListDetail(
        id=str(row.id),
        name=row.name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        items=[_item_out(item) for item in items],
    )


# --- History -------------------------------------------------------------------


@router.get("/history", response_model=list[MatchRunSummary])
async def get_history(
    page: int = Query(default=1, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MatchRunSummary]:
    """Paginated; **never returns `results`** -- a list view that eagerly
    serialises twenty runs x ten results is a slow endpoint and a large response
    for data this list does not render."""

    settings = get_settings()
    rows = await history_module.list_runs(db, user, page=page, page_size=settings.history_page_size)
    return [_run_summary(row) for row in rows]


@router.get("/history/{run_id}", response_model=MatchRunDetail)
async def get_history_detail(
    run_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MatchRunDetail:
    parsed = _parse_uuid(run_id)
    row = await history_module.get_run(db, user, parsed) if parsed is not None else None
    if row is None:
        raise HTTPException(status_code=404, detail="History entry not found.")
    return _run_detail(row)


@router.patch("/history/{run_id}", response_model=MatchRunDetail)
async def patch_history_entry(
    run_id: str,
    body: HistoryPatchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatchRunDetail:
    parsed = _parse_uuid(run_id)
    row = await history_module.rename_run(db, user, parsed, body.label) if parsed is not None else None
    if row is None:
        raise HTTPException(status_code=404, detail="History entry not found.")
    return _run_detail(row)


@router.delete("/history/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history_entry(
    run_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    parsed = _parse_uuid(run_id)
    deleted = await history_module.delete_run(db, user, parsed) if parsed is not None else False
    if not deleted:
        raise HTTPException(status_code=404, detail="History entry not found.")


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await history_module.clear_runs(db, user)


@router.post("/history/import", response_model=ImportResult)
async def import_history(
    body: ImportRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ImportResult:
    return await history_module.import_entries(db, user, body.entries)


# --- Saved lists -----------------------------------------------------------------


@router.get("/lists", response_model=list[SavedListSummary])
async def get_lists(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[SavedListSummary]:
    pairs = await lists_module.list_lists(db, user)
    return [_list_summary(row, count) for row, count in pairs]


@router.post("/lists", response_model=SavedListDetail, status_code=status.HTTP_201_CREATED)
async def create_saved_list(
    body: ListCreateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> SavedListDetail:
    try:
        saved_list = await lists_module.create_list(db, user, body.name)
    except lists_module.DuplicateListNameError as exc:
        raise HTTPException(status_code=409, detail="A list with this name already exists.") from exc
    except lists_module.ListQuotaExceededError as exc:
        raise HTTPException(status_code=409, detail="Saved list quota reached.") from exc
    return _list_detail(saved_list, [])


@router.get("/lists/{list_id}", response_model=SavedListDetail)
async def get_list_detail(
    list_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> SavedListDetail:
    parsed = _parse_uuid(list_id)
    saved_list = await lists_module.get_list(db, user, parsed) if parsed is not None else None
    if saved_list is None:
        raise HTTPException(status_code=404, detail="List not found.")
    items = await lists_module.list_items(db, saved_list)
    return _list_detail(saved_list, items)


@router.patch("/lists/{list_id}", response_model=SavedListDetail)
async def rename_saved_list(
    list_id: str,
    body: ListRenameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedListDetail:
    parsed = _parse_uuid(list_id)
    if parsed is None:
        raise HTTPException(status_code=404, detail="List not found.")
    try:
        saved_list = await lists_module.rename_list(db, user, parsed, body.name)
    except lists_module.DuplicateListNameError as exc:
        raise HTTPException(status_code=409, detail="A list with this name already exists.") from exc
    if saved_list is None:
        raise HTTPException(status_code=404, detail="List not found.")
    items = await lists_module.list_items(db, saved_list)
    return _list_detail(saved_list, items)


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_list(
    list_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    parsed = _parse_uuid(list_id)
    deleted = await lists_module.delete_list(db, user, parsed) if parsed is not None else False
    if not deleted:
        raise HTTPException(status_code=404, detail="List not found.")


@router.post("/lists/{list_id}/items", response_model=SavedListItemOut)
async def add_saved_list_item(
    list_id: str,
    body: ListItemRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedListItemOut:
    """201 when a new item was added, 200 when it was already present -- idempotent,
    per enhancements/21's own table. The status code is set dynamically rather than
    fixed, since the same request body can legitimately mean either outcome."""

    parsed = _parse_uuid(list_id)
    if parsed is None:
        raise HTTPException(status_code=404, detail="List not found.")

    try:
        item, created = await lists_module.add_item(
            db, user, parsed, body.job_id, body.job_title, body.job_family, body.note
        )
    except lists_module.ItemQuotaExceededError as exc:
        raise HTTPException(status_code=409, detail="Saved list item quota reached.") from exc

    if item is None:
        raise HTTPException(status_code=404, detail="List not found.")

    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _item_out(item)


@router.delete("/lists/{list_id}/items/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_saved_list_item(
    list_id: str, job_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    parsed = _parse_uuid(list_id)
    removed = await lists_module.remove_item(db, user, parsed, job_id) if parsed is not None else False
    if not removed:
        raise HTTPException(status_code=404, detail="List item not found.")


# --- Feedback --------------------------------------------------------------------


@router.get("/feedback", response_model=list[FeedbackStateOut])
async def get_feedback_state(
    run_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[FeedbackStateOut]:
    """Lets `FeedbackButtons` restore its toggled state after a reload -- see
    enhancements/23. Scoped to one run at a time (a query param, not a path
    segment, since it's a filter on the caller's own feedback rather than a
    resource in its own right)."""

    return await feedback_module.list_feedback_for_run(db, user, run_id)


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def post_feedback(
    body: FeedbackRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> FeedbackResponse:
    row, action = await feedback_module.submit_feedback(
        db,
        user,
        job_id=body.job_id,
        signal=body.signal,
        rank=body.rank,
        resume_hash=body.resume_hash,
        run_id=body.run_id,
    )
    return FeedbackResponse(id=str(row.id) if row is not None else None, action=action)
