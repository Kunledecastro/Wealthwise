import hashlib
import re
import uuid
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth import ratelimit
from app.auth.sessions import CurrentAuth, client_ip, require_auth
from app.core.config import get_settings
from app.core.security import hash_identifier
from app.db.models import Account, ImportBatch, ImportRow, Transaction, utcnow
from app.db.session import get_db
from app.finance.service import balances_for, get_account, today_for
from app.ingestion import service
from app.ingestion.readers import ReadError, read_any
from app.ingestion.schemas import (
    CommitIn,
    CommitOut,
    ImportBatchOut,
    ImportDetailOut,
    ImportRowOut,
    MappingIn,
    RowUpdatesIn,
    SimulateIn,
)
from app.ingestion.simulate import simulate_grid

router = APIRouter(prefix="/api/imports", tags=["imports"])

STAGED_TTL = timedelta(hours=24)
MAX_STAGED = 10


def _clean_filename(name: str | None) -> str:
    base = re.split(r"[\\/]", name or "statement")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip() or "statement"
    return base[:200]


def _get_batch(
    db: Session, user_id: int, batch_id: uuid.UUID, *, lock: bool = False
) -> ImportBatch:
    stmt = select(ImportBatch).where(
        ImportBatch.user_id == user_id, ImportBatch.public_id == batch_id
    )
    if lock:
        stmt = stmt.with_for_update()
    b = db.scalar(stmt)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found.")
    return b


def _account_of(db: Session, b: ImportBatch, *, lock: bool = False) -> Account:
    stmt = select(Account).where(Account.id == b.account_id, Account.user_id == b.user_id)
    if lock:
        stmt = stmt.with_for_update()
    a = db.scalar(stmt)
    if a is None:  # pragma: no cover - FK guarantees this
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found.")
    return a


def _batch_out(db: Session, b: ImportBatch, a: Account) -> ImportBatchOut:
    can_open = False
    if b.status == "staged" and b.statement_opening_balance_minor is not None:
        can_open = not db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == a.id, Transaction.deleted_at.is_(None))
        )
    same = db.scalar(
        select(func.max(ImportBatch.committed_at)).where(
            ImportBatch.user_id == b.user_id,
            ImportBatch.account_id == b.account_id,
            ImportBatch.file_sha256 == b.file_sha256,
            ImportBatch.status == "committed",
            ImportBatch.id != b.id,
        )
    )
    return ImportBatchOut(
        id=b.public_id,
        account_id=a.public_id,
        account_name=a.display_name,
        adapter=b.adapter,
        filename=b.filename,
        sheet_name=b.sheet_name,
        status=b.status,
        counts=b.counts or {},
        warnings=b.warnings or [],
        statement_first_date=b.statement_first_date,
        statement_last_date=b.statement_last_date,
        statement_opening_balance_minor=b.statement_opening_balance_minor,
        statement_closing_balance_minor=b.statement_closing_balance_minor,
        can_set_opening=can_open,
        created_at=b.created_at,
        committed_at=b.committed_at,
        finished_at=b.finished_at,
        same_file_imported_at=same,
    )


def _row_out(r: ImportRow, txn_pub: dict[int, uuid.UUID]) -> ImportRowOut:
    return ImportRowOut(
        id=r.public_id,
        row_number=r.row_number,
        outcome=r.outcome,
        include=r.include,
        error=r.error,
        note=r.note,
        transaction_date=r.transaction_date,
        posting_date=r.posting_date,
        direction=r.direction,
        amount_minor=r.amount_minor,
        narration=r.narration,
        external_ref=r.external_ref,
        balance_after_minor=r.balance_after_minor,
        suggested_kind=r.suggested_kind,
        kind=r.kind,
        allowed_kinds=sorted(service.allowed_kinds(r)) if r.outcome != "error" else [],
        transaction_id=txn_pub.get(r.transaction_id) if r.transaction_id else None,
    )


Outcome = Literal["new", "duplicate", "possible_duplicate", "error", "included"]


def _detail(
    db: Session,
    b: ImportBatch,
    a: Account,
    outcome: Outcome | None = None,
    page: int = 1,
    page_size: int = 200,
) -> ImportDetailOut:
    stmt = select(ImportRow).where(ImportRow.batch_id == b.id)
    if outcome == "included":
        stmt = stmt.where(ImportRow.include.is_(True))
    elif outcome:
        stmt = stmt.where(ImportRow.outcome == outcome)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(ImportRow.row_number).offset((page - 1) * page_size).limit(page_size)
    ).all()
    tids = {r.transaction_id for r in rows if r.transaction_id}
    pub: dict[int, uuid.UUID] = {}
    if tids:
        pub = {
            k: v
            for k, v in db.execute(
                select(Transaction.id, Transaction.public_id).where(Transaction.id.in_(tids))
            ).all()
        }
    grid = b.grid or []
    m = b.mapping or {}
    hr = m.get("header_row")
    headers = grid[hr] if isinstance(hr, int) and 0 <= hr < len(grid) else []
    return ImportDetailOut(
        **_batch_out(db, b, a).model_dump(),
        mapping=b.mapping,
        headers=headers,
        preview=[r[:30] for r in grid[:15]],
        rows=[_row_out(r, pub) for r in rows],
        rows_total=total,
        page=page,
        page_size=page_size,
    )


def _purge_stale(db: Session, user_id: int) -> None:
    cutoff = utcnow() - STAGED_TTL
    for b in db.scalars(
        select(ImportBatch).where(
            ImportBatch.user_id == user_id,
            ImportBatch.status == "staged",
            ImportBatch.created_at < cutoff,
        )
    ):
        _discard(db, b)


def _discard(db: Session, b: ImportBatch) -> None:
    db.query(ImportRow).filter(ImportRow.batch_id == b.id).delete()
    b.status, b.grid, b.finished_at = "discarded", None, utcnow()


# ---------------------------------------------------------------- endpoints


@router.get("", response_model=list[ImportBatchOut])
def list_imports(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(require_auth)
) -> list[ImportBatchOut]:
    batches = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.user_id == auth.user.id, ImportBatch.status != "discarded")
        .order_by(ImportBatch.created_at.desc())
        .limit(100)
    ).all()
    accts = {a.id: a for a in db.scalars(select(Account).where(Account.user_id == auth.user.id))}
    return [_batch_out(db, b, accts[b.account_id]) for b in batches]


@router.post("", response_model=ImportDetailOut, status_code=status.HTTP_201_CREATED)
async def upload(
    request: Request,
    account_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> ImportDetailOut:
    s = get_settings()
    ident = hash_identifier(f"upload:{auth.user.id}")
    ratelimit.check_generic(
        db, "upload", window=timedelta(hours=1), limit=60, identifier_hash=ident
    )
    acct = get_account(db, auth.user.id, account_id)
    if acct.is_archived:
        raise service.unprocessable("This account is archived. Unarchive it first.")
    limit = s.upload_max_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"The file is larger than {s.upload_max_mb} MB."
        )
    if not data:
        raise service.unprocessable("The file is empty.")
    ratelimit.record_attempt(
        db, "upload", identifier_hash=ident, ip=client_ip(request), success=True
    )
    _purge_stale(db, auth.user.id)
    staged = (
        db.scalar(
            select(func.count())
            .select_from(ImportBatch)
            .where(ImportBatch.user_id == auth.user.id, ImportBatch.status == "staged")
        )
        or 0
    )
    if staged >= MAX_STAGED:
        raise service.unprocessable(
            "You have too many imports waiting for review. Finish or cancel some first."
        )
    try:
        grid = read_any(data, file.filename or "")
    except ReadError as exc:
        db.commit()  # keep the rate-limit record
        raise service.unprocessable(str(exc)) from exc
    b = ImportBatch(
        user_id=auth.user.id,
        account_id=acct.id,
        adapter=grid.adapter,
        filename=_clean_filename(file.filename),
        sheet_name=grid.sheet_name,
        file_sha256=hashlib.sha256(data).hexdigest(),
        grid=grid.rows,
    )
    b.mapping = service.initial_mapping(db, acct, grid.rows)
    db.add(b)
    db.flush()
    service.stage(db, b, acct)
    audit(
        db,
        "import.uploaded",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="import",
        target_id=str(b.public_id),
        details={"adapter": grid.adapter, "rows": len(grid.rows)},
    )
    db.commit()
    db.refresh(b)
    return _detail(db, b, acct)


@router.post("/simulate", response_model=ImportDetailOut, status_code=status.HTTP_201_CREATED)
def simulate(
    body: SimulateIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> ImportDetailOut:
    if not get_settings().demo_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    today = today_for(auth.user)
    acct = db.scalar(
        select(Account)
        .where(Account.user_id == auth.user.id, Account.source == "simulated")
        .order_by(Account.id)
        .limit(1)
    )
    end = today - timedelta(days=1)
    if acct is None:
        start = end - timedelta(days=body.days - 1)
        acct = Account(
            user_id=auth.user.id,
            type="bank",
            display_name="Demo bank (simulated)",
            institution_name="Simulated — not real",
            currency="NGN",
            opening_balance_minor=25_000_000,
            opening_balance_date=start,
            source="simulated",
        )
        db.add(acct)
        db.flush()
        opening = acct.opening_balance_minor
    else:
        last = db.scalar(
            select(func.max(Transaction.transaction_date)).where(
                Transaction.account_id == acct.id, Transaction.deleted_at.is_(None)
            )
        )
        start = (last + timedelta(days=1)) if last else acct.opening_balance_date
        start = max(start, end - timedelta(days=body.days - 1))
        if start > end:
            raise service.unprocessable("The demo bank is up to date. Try again tomorrow.")
        bal = balances_for(db, auth.user.id, [acct], as_of=start - timedelta(days=1))[acct.id][0]
        opening = bal.posted_minor
    seed = (
        db.scalar(
            select(func.count()).select_from(ImportBatch).where(ImportBatch.user_id == auth.user.id)
        )
        or 0
    ) + auth.user.id * 1000
    grid = simulate_grid(start, end, opening, seed)
    b = ImportBatch(
        user_id=auth.user.id,
        account_id=acct.id,
        adapter="simulated",
        filename=f"Simulated bank events {start:%d %b} to {end:%d %b %Y}",
        sheet_name=None,
        file_sha256=hashlib.sha256(repr(grid).encode()).hexdigest(),
        grid=grid,
    )
    b.mapping = service.initial_mapping(db, acct, grid)
    db.add(b)
    db.flush()
    service.stage(db, b, acct)
    audit(
        db,
        "import.simulated",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="import",
        target_id=str(b.public_id),
    )
    db.commit()
    db.refresh(b)
    return _detail(db, b, acct)


@router.get("/{batch_id}", response_model=ImportDetailOut)
def get_import(
    batch_id: uuid.UUID,
    outcome: Outcome | None = None,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 200,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> ImportDetailOut:
    b = _get_batch(db, auth.user.id, batch_id)
    return _detail(db, b, _account_of(db, b), outcome, page, page_size)


def _require_staged(b: ImportBatch) -> None:
    if b.status != "staged":
        raise service.conflict(f"This import is already {b.status}.")


@router.post("/{batch_id}/mapping", response_model=ImportDetailOut)
def remap(
    batch_id: uuid.UUID,
    body: MappingIn,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> ImportDetailOut:
    b = _get_batch(db, auth.user.id, batch_id, lock=True)
    _require_staged(b)
    a = _account_of(db, b)
    if body.header_row >= len(b.grid or []):
        raise service.unprocessable("That header row doesn't exist.")
    b.mapping = body.model_dump()
    service.stage(db, b, a)
    db.commit()
    db.refresh(b)
    return _detail(db, b, a)


@router.post("/{batch_id}/rows", response_model=ImportBatchOut)
def update_rows(
    batch_id: uuid.UUID,
    body: RowUpdatesIn,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> ImportBatchOut:
    b = _get_batch(db, auth.user.id, batch_id, lock=True)
    _require_staged(b)
    ids = [u.id for u in body.updates]
    rows = {
        r.public_id: r
        for r in db.scalars(
            select(ImportRow).where(ImportRow.batch_id == b.id, ImportRow.public_id.in_(ids))
        )
    }
    for u in body.updates:
        r = rows.get(u.id)
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Row not found.")
        if u.kind is not None:
            if u.kind not in service.allowed_kinds(r):
                raise service.unprocessable(f"Row {r.row_number}: '{u.kind}' isn't allowed here.")
            r.kind = u.kind
        if u.include is not None:
            if u.include and r.outcome in ("error", "duplicate"):
                why = "it has an error" if r.outcome == "error" else "it is already imported"
                raise service.unprocessable(f"Row {r.row_number} can't be imported ({why}).")
            r.include = u.include
    db.flush()
    service.recount(db, b)
    db.commit()
    return _batch_out(db, b, _account_of(db, b))


@router.post("/{batch_id}/commit", response_model=CommitOut)
def commit_import(
    batch_id: uuid.UUID,
    body: CommitIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> CommitOut:
    b = _get_batch(db, auth.user.id, batch_id, lock=True)
    _require_staged(b)
    a = _account_of(db, b, lock=True)
    if a.is_archived:
        raise service.unprocessable("This account is archived. Unarchive it first.")
    res = service.commit(
        db,
        b,
        a,
        set_opening_from_statement=body.set_opening_from_statement,
        save_mapping=body.save_mapping,
    )
    db.query(ImportRow).filter(ImportRow.batch_id == b.id, ImportRow.include.is_(False)).delete()
    audit(
        db,
        "import.committed",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="import",
        target_id=str(b.public_id),
        details={
            "created": res.created,
            "transfers": res.transfers_linked,
            "reversals": res.reversals_linked,
            "reconciled": bool(res.reconciliation and res.reconciliation["matches"]),
        },
    )
    db.commit()
    return CommitOut(
        created=res.created,
        transfers_linked=res.transfers_linked,
        reversals_linked=res.reversals_linked,
        opening_balance_set=res.opening_balance_set,
        reconciliation=res.reconciliation,
        batch=_batch_out(db, b, a),
    )


@router.post("/{batch_id}/discard", response_model=ImportBatchOut)
def discard(
    batch_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> ImportBatchOut:
    b = _get_batch(db, auth.user.id, batch_id, lock=True)
    _require_staged(b)
    _discard(db, b)
    audit(
        db,
        "import.discarded",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="import",
        target_id=str(b.public_id),
    )
    db.commit()
    return _batch_out(db, b, _account_of(db, b))


@router.post("/{batch_id}/undo", response_model=ImportBatchOut)
def undo_import(
    batch_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> ImportBatchOut:
    b = _get_batch(db, auth.user.id, batch_id, lock=True)
    if b.status != "committed":
        raise service.conflict("Only completed imports can be undone.")
    a = _account_of(db, b, lock=True)
    removed = service.undo(db, b)
    audit(
        db,
        "import.undone",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="import",
        target_id=str(b.public_id),
        details={"removed": removed},
    )
    db.commit()
    return _batch_out(db, b, a)
