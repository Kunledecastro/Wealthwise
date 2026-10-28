"""Statement import: stage → review → commit (→ undo).

Every adapter produces a grid; every grid goes through the same normalise → dedupe →
match → stage path, and commit is a single database transaction.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.categorise import service as cats
from app.db.models import (
    Account,
    ImportBatch,
    ImportProfile,
    ImportRow,
    ReconciliationPoint,
    Transaction,
    utcnow,
)
from app.finance.service import add_revision, live_entries, snapshot
from app.ingestion.detect import guess_mapping, header_signature, validate_mapping
from app.ingestion.normalise import NormRow, ParseResult, normalise
from app.ledger.engine import reconcile

MATCH_WINDOW_DAYS = 2
REVERSAL_LOOKBACK_DAYS = 30
NATURAL_KIND = {"credit": "income", "debit": "expense"}
ALLOWED_KINDS = {
    "credit": {"income", "refund", "adjustment"},
    "debit": {"expense", "fee", "adjustment"},
}


def conflict(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, msg)


def unprocessable(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, msg)


# ---------------------------------------------------------------- mapping


def initial_mapping(db: Session, account: Account, grid: list[list[str]]) -> dict[str, Any]:
    """Use the remembered mapping for this account when a header row matches one saved
    before (even if we couldn't recognise the headers ourselves); otherwise guess."""
    sigs = {header_signature(row): i for i, row in reversed(list(enumerate(grid[:40]))) if any(row)}
    if sigs:
        prof = db.scalar(
            select(ImportProfile)
            .where(
                ImportProfile.account_id == account.id,
                ImportProfile.header_signature.in_(sigs),
            )
            .order_by(ImportProfile.updated_at.desc())
            .limit(1)
        )
        if prof is not None:
            saved = dict(prof.mapping)
            # Preamble length can vary between downloads; use where the headers are now.
            saved["header_row"] = sigs[prof.header_signature]
            saved["from_profile"] = True
            return saved
    return guess_mapping(grid)


# ---------------------------------------------------------------- staging


@dataclass
class _Claim:
    """Existing transactions already matched to a row in this batch (one-to-one matching)."""

    used: set[int]


def _drop_repeated_refs(rows: list[NormRow]) -> None:
    """Banks sometimes reuse one reference for a transfer and its fee. A reference that
    repeats inside a file can't identify a transaction, so it isn't used for that file."""
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.external_ref:
            counts[r.external_ref] += 1
    for r in rows:
        if r.external_ref and counts[r.external_ref] > 1:
            r.external_ref = None


def stage(db: Session, batch: ImportBatch, account: Account) -> None:
    """(Re)build the review rows for a batch from its grid and mapping."""
    db.execute(delete(ImportRow).where(ImportRow.batch_id == batch.id))
    batch.warnings = []
    batch.statement_closing_balance_minor = batch.statement_opening_balance_minor = None
    batch.statement_first_date = batch.statement_last_date = None
    grid = batch.grid or []
    m = batch.mapping or {}
    problems = validate_mapping(m, max((len(r) for r in grid), default=0))
    if problems:
        batch.warnings = problems
        batch.counts = {
            "new": 0,
            "duplicate": 0,
            "possible_duplicate": 0,
            "error": 0,
            "skipped": 0,
            "included": 0,
        }
        return
    batch.header_signature = header_signature(grid[m["header_row"]])
    res: ParseResult = normalise(grid, m, account.id)
    _drop_repeated_refs(res.rows)
    batch.warnings = list(res.warnings)
    batch.statement_first_date, batch.statement_last_date = res.first_date, res.last_date
    batch.statement_opening_balance_minor = res.opening_balance_minor
    batch.statement_closing_balance_minor = res.closing_balance_minor
    if res.last_date and res.last_date < account.opening_balance_date:
        batch.warnings.append(
            "Everything in this file is dated before the account's starting balance date, so "
            "it won't change the balance (it still shows in reports)."
        )

    good = [r for r in res.rows if r.error is None]
    fps = {r.fingerprint for r in good if r.fingerprint}
    refs = {r.external_ref for r in good if r.external_ref}
    known_fp: dict[str, Transaction] = {}
    known_ref: dict[str, Transaction] = {}
    if fps:
        for t in db.scalars(
            select(Transaction).where(
                Transaction.account_id == account.id, Transaction.fingerprint.in_(fps)
            )
        ):
            known_fp[t.fingerprint] = t  # type: ignore[index]
    if refs:
        for t in db.scalars(
            select(Transaction).where(
                Transaction.account_id == account.id, Transaction.external_ref.in_(refs)
            )
        ):
            known_ref[t.external_ref] = t  # type: ignore[index]

    lo = (res.first_date or date.today()) - timedelta(days=REVERSAL_LOOKBACK_DAYS)
    hi = (res.last_date or date.today()) + timedelta(days=MATCH_WINDOW_DAYS)
    same_acct = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == account.user_id,
                Transaction.account_id == account.id,
                Transaction.deleted_at.is_(None),
                Transaction.transaction_date.between(lo, hi),
            )
        )
    )
    other_accts = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == account.user_id,
                Transaction.account_id != account.id,
                Transaction.currency == account.currency,
                Transaction.deleted_at.is_(None),
                Transaction.status == "posted",
                Transaction.kind.in_(("income", "expense")),
                Transaction.transaction_date.between(lo, hi),
            )
        )
    )
    refunded = set(
        db.scalars(
            select(Transaction.refund_of_transaction_id).where(
                Transaction.user_id == account.user_id,
                Transaction.refund_of_transaction_id.is_not(None),
                Transaction.deleted_at.is_(None),
            )
        )
    )
    other_names = dict(
        db.execute(
            select(Account.id, Account.display_name).where(Account.user_id == account.user_id)
        ).all()
    )
    claim = _Claim(used=set())
    staged: list[ImportRow] = []

    for r in res.rows:
        row = ImportRow(
            batch_id=batch.id,
            user_id=account.user_id,
            row_number=r.row_number,
            transaction_date=r.transaction_date,
            posting_date=r.posting_date,
            direction=r.direction,
            amount_minor=r.amount_minor,
            narration=r.narration,
            external_ref=r.external_ref,
            balance_after_minor=r.balance_after_minor,
            fingerprint=r.fingerprint,
            suggested_kind=r.suggested_kind,
            kind=r.suggested_kind,
            outcome="new",
            include=True,
        )
        staged.append(row)
        if r.error:
            row.outcome, row.include, row.error = "error", False, r.error[:300]
            continue
        dup = known_fp.get(r.fingerprint or "") or (
            known_ref.get(r.external_ref) if r.external_ref else None
        )
        if dup is not None:
            row.outcome, row.include = "duplicate", False
            row.duplicate_of_transaction_id = dup.id
            row.note = (
                "Imported before and later deleted, so it stays out."
                if dup.deleted_at
                else "Already imported."
            )
            continue
        near = _possible_duplicate(r, same_acct, claim)
        if near is not None:
            claim.used.add(near.id)
            row.outcome, row.include = "possible_duplicate", False
            row.duplicate_of_transaction_id = near.id
            label = near.merchant or near.narration or near.kind
            row.note = (
                f"Looks like '{label[:60]}' on {near.transaction_date:%d %b} "
                "(already in Wealthwise)."
            )
            continue

    # Second pass: reversals (may match an earlier row in this file) and own-account transfers.
    new_rows = [x for x in staged if x.outcome == "new"]
    for row in new_rows:
        if row.suggested_kind == "reversal":
            _match_reversal(row, new_rows, same_acct, claim)
        elif row.suggested_kind in ("income", "expense"):
            _match_transfer(row, other_accts, refunded, claim, other_names)

    db.add_all(staged)
    db.flush()
    # Row→row reversal links need ids, so they are resolved after the flush.
    for row in staged:
        target = getattr(row, "_reverses_row", None)
        if target is not None:
            row.reversal_of_row_id = target.id
    suggest_categories(db, account, staged)
    batch.counts = _count(staged, res.skipped)


def suggest_categories(db: Session, account: Account, rows: list[ImportRow]) -> None:
    """Category suggestions for the review screen (same engine as everywhere else)."""
    ctx = cats.load_context(db, account.user_id)
    by_id = {r.id: r for r in rows}
    linked_txn_cats = dict(
        db.execute(
            select(Transaction.id, Transaction.category_id).where(
                Transaction.id.in_(
                    [r.reversal_of_transaction_id for r in rows if r.reversal_of_transaction_id]
                )
            )
        ).all()
    )
    ordered = sorted(rows, key=lambda r: r.reversal_of_row_id is not None)
    for r in ordered:
        if r.outcome in ("error", "duplicate"):
            continue
        linked = None
        if r.kind == "reversal":
            if r.reversal_of_row_id and r.reversal_of_row_id in by_id:
                linked = by_id[r.reversal_of_row_id].category_id
            elif r.reversal_of_transaction_id:
                linked = linked_txn_cats.get(r.reversal_of_transaction_id)
        cats.apply_row(ctx, r, account.id, linked)


def _possible_duplicate(
    r: NormRow, same_acct: list[Transaction], claim: _Claim
) -> Transaction | None:
    best = None
    for t in same_acct:
        if (
            t.id in claim.used
            or t.fingerprint is not None  # imported rows are matched exactly, not fuzzily
            or t.direction != r.direction
            or t.amount_minor != r.amount_minor
            or t.status == "failed"
            or t.kind == "reversal"
        ):
            continue
        gap = abs((t.transaction_date - r.transaction_date).days)  # type: ignore[operator]
        if gap <= MATCH_WINDOW_DAYS and (best is None or gap < best[0]):
            best = (gap, t)
    return best[1] if best else None


def _match_reversal(
    row: ImportRow, new_rows: list[ImportRow], same_acct: list[Transaction], claim: _Claim
) -> None:
    opposite = "debit" if row.direction == "credit" else "credit"
    earliest = row.transaction_date - timedelta(days=REVERSAL_LOOKBACK_DAYS)  # type: ignore[operator]
    # Prefer an original in the same file.
    for cand in sorted(new_rows, key=lambda x: (x.transaction_date, x.row_number), reverse=True):
        if (
            cand is not row
            and cand.direction == opposite
            and cand.amount_minor == row.amount_minor
            and cand.suggested_kind in ("expense", "fee", "income")
            and earliest <= cand.transaction_date <= row.transaction_date  # type: ignore[operator]
            and not getattr(cand, "_reversed_by", None)
        ):
            row._reverses_row = cand  # type: ignore[attr-defined]
            cand._reversed_by = row  # type: ignore[attr-defined]
            row.note = f"Reverses row {cand.row_number} in this file."
            return
    for t in sorted(same_acct, key=lambda x: x.transaction_date, reverse=True):
        if (
            t.id not in claim.used
            and t.direction == opposite
            and t.amount_minor == row.amount_minor
            and t.status == "posted"
            and t.kind in ("expense", "fee", "income")
            and earliest <= t.transaction_date <= row.transaction_date  # type: ignore[operator]
        ):
            claim.used.add(t.id)
            row.reversal_of_transaction_id = t.id
            label = t.merchant or t.narration or t.kind
            row.note = f"Reverses '{label[:60]}' on {t.transaction_date:%d %b}."
            return
    row.kind = row.suggested_kind = "refund" if row.direction == "credit" else "adjustment"
    row.note = (
        "Looks like a reversal, but the original charge wasn't found. Saved as a refund so it "
        "reduces spending."
        if row.direction == "credit"
        else "Looks like a reversal of money received, but the original wasn't found."
    )


def _match_transfer(
    row: ImportRow,
    other_accts: list[Transaction],
    refunded: set[int | None],
    claim: _Claim,
    names: dict[int, str],
) -> None:
    opposite = "debit" if row.direction == "credit" else "credit"
    best = None
    for t in other_accts:
        if (
            t.id in claim.used
            or t.id in refunded
            or t.direction != opposite
            or t.amount_minor != row.amount_minor
            or t.transfer_group_id is not None
        ):
            continue
        gap = abs((t.transaction_date - row.transaction_date).days)  # type: ignore[operator]
        if gap <= MATCH_WINDOW_DAYS and (best is None or gap < best[0]):
            best = (gap, t)
    if best:
        t = best[1]
        claim.used.add(t.id)
        row.transfer_match_transaction_id = t.id
        row.kind = row.suggested_kind = "transfer"
        way = "from" if row.direction == "credit" else "to"
        row.note = (
            f"Matches money {way} {names.get(t.account_id, 'another account')} on "
            f"{t.transaction_date:%d %b}: will be saved as a transfer between your accounts."
        )


def _count(rows: list[ImportRow], skipped: int) -> dict[str, int]:
    c = {"new": 0, "duplicate": 0, "possible_duplicate": 0, "error": 0, "skipped": skipped}
    for r in rows:
        c[r.outcome] += 1
    c["included"] = sum(1 for r in rows if r.include)
    return c


def recount(db: Session, batch: ImportBatch) -> None:
    rows = db.scalars(select(ImportRow).where(ImportRow.batch_id == batch.id)).all()
    batch.counts = _count(list(rows), batch.counts.get("skipped", 0))


def allowed_kinds(row: ImportRow) -> set[str]:
    if row.direction is None:
        return set()
    kinds = set(ALLOWED_KINDS[row.direction])
    if row.transfer_match_transaction_id:
        kinds.add("transfer")
    if row.reversal_of_transaction_id or row.reversal_of_row_id:
        kinds.add("reversal")
    return kinds


# ---------------------------------------------------------------- commit


@dataclass
class CommitResult:
    created: int
    transfers_linked: int
    reversals_linked: int
    opening_balance_set: bool
    reconciliation: dict[str, Any] | None


def commit(
    db: Session,
    batch: ImportBatch,
    account: Account,
    *,
    set_opening_from_statement: bool,
    save_mapping: bool,
) -> CommitResult:
    rows = list(
        db.scalars(
            select(ImportRow)
            .where(ImportRow.batch_id == batch.id, ImportRow.include.is_(True))
            .order_by(ImportRow.transaction_date, ImportRow.row_number)
        )
    )
    if not rows:
        raise unprocessable("Nothing is selected to import.")
    # Rows within the same day must keep the statement's chronological order.
    if _newest_first(db, batch):
        rows.sort(key=lambda r: (r.transaction_date, -r.row_number))

    # Race safety: another import of an overlapping file may have committed meanwhile.
    fps = [r.fingerprint for r in rows if r.fingerprint]
    taken = set(
        db.scalars(
            select(Transaction.fingerprint).where(
                Transaction.account_id == account.id, Transaction.fingerprint.in_(fps)
            )
        )
    )
    if taken:
        raise conflict(
            "Some of these rows were imported in the meantime. Change the column settings "
            "(or re-open the import) to refresh the review, then try again."
        )

    if set_opening_from_statement:
        if batch.statement_opening_balance_minor is None or batch.statement_first_date is None:
            raise unprocessable("This statement has no usable running balance to start from.")
        existing = db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account.id, Transaction.deleted_at.is_(None))
        )
        if existing:
            raise unprocessable(
                "The starting balance can only be taken from a statement for an account with "
                "no transactions yet."
            )

    source = batch.adapter
    acct_ids = {account.id: account.public_id}
    ctx = cats.load_context(db, account.user_id)
    created: dict[int, Transaction] = {}
    side_effects: list[dict[str, Any]] = []
    transfers = reversals = 0
    reason = f"Imported from {batch.filename}"[:200]

    for r in rows:
        kind = r.kind or r.suggested_kind or NATURAL_KIND[r.direction or "debit"]
        t = Transaction(
            user_id=account.user_id,
            account_id=account.id,
            kind=kind,
            direction=r.direction,
            amount_minor=r.amount_minor,
            currency=account.currency,
            status="posted",
            transaction_date=r.transaction_date,
            posting_date=r.posting_date or r.transaction_date,
            narration=r.narration,
            source=source,
            external_ref=r.external_ref,
            fingerprint=r.fingerprint,
            import_batch_id=batch.id,
            is_demo=batch.adapter == "simulated",
        )
        if kind == "transfer":
            other = _lock_live(db, account.user_id, r.transfer_match_transaction_id)
            if (
                other is None
                or other.transfer_group_id is not None
                or other.kind not in ("income", "expense")
                or other.direction == r.direction
                or other.amount_minor != r.amount_minor
            ):
                t.kind = NATURAL_KIND[r.direction or "debit"]
            else:
                group = uuid.uuid4()
                t.transfer_group_id = group
                side_effects.append(
                    {"type": "transfer_link", "txn_id": other.id, "prev_kind": other.kind}
                )
                other_before = snapshot(other, {})
                other.kind = "transfer"
                other.transfer_group_id = group
                other.category_source = "none"  # a transfer's category is fixed
                cats.apply(ctx, other)
                add_revision(
                    db,
                    other,
                    "update",
                    {"kind": [other_before["kind"], "transfer"]},
                    "Matched as a transfer by a statement import",
                )
                transfers += 1
        elif kind == "reversal":
            original: Transaction | None = None
            if r.reversal_of_row_id is not None:
                original = created.get(r.reversal_of_row_id)
                if original is not None and original.status == "posted":
                    add_revision(
                        db, original, "reverse", {"status": ["posted", "reversed"]}, reason
                    )
            elif r.reversal_of_transaction_id is not None:
                original = _lock_live(db, account.user_id, r.reversal_of_transaction_id)
                if original is not None and original.status == "posted":
                    side_effects.append({"type": "reversed", "txn_id": original.id})
                    add_revision(
                        db, original, "reverse", {"status": ["posted", "reversed"]}, reason
                    )
            if original is None or original.status != "posted":
                t.kind = "refund" if r.direction == "credit" else "adjustment"
            else:
                original.status = "reversed"
                t.reverses_transaction_id = original.id
                reversals += 1
        if t.kind not in ALLOWED_KINDS[r.direction or "debit"] | {"transfer", "reversal"}:
            t.kind = NATURAL_KIND[r.direction or "debit"]
        user_cat = r.category_id if r.category_source == "user" else None
        if user_cat is not None and t.category_source != "user":
            cat = ctx.info(user_cat)
            if cat is None or cat.archived or not _fits_kind(cat.kind, t.kind):
                user_cat = None
        if (
            r.category_source == "user"
            and r.category_id is None
            and t.kind not in ("transfer", "reversal", "adjustment")
        ):
            cats.apply(ctx, t, user_uncategorised=True)
        else:
            linked = None
            if t.reverses_transaction_id:
                orig_t = next(
                    (x for x in created.values() if x.id == t.reverses_transaction_id), None
                )
                linked = (
                    orig_t.category_id
                    if orig_t is not None
                    else db.scalar(
                        select(Transaction.category_id).where(
                            Transaction.id == t.reverses_transaction_id
                        )
                    )
                )
            cats.apply(ctx, t, user_category_id=user_cat, linked_category_id=linked)
        db.add(t)
        db.flush()
        created[r.id] = t
        r.transaction_id = t.id
        add_revision(db, t, "create", snapshot(t, acct_ids), reason)

    cats.flush_hits(db, ctx)
    opening_set = False
    if set_opening_from_statement:
        account.opening_balance_minor = batch.statement_opening_balance_minor  # type: ignore[assignment]
        account.opening_balance_date = batch.statement_first_date  # type: ignore[assignment]
        opening_set = True
    if account.source == "manual":
        account.source = "imported"

    rec_out = None
    if (
        batch.statement_closing_balance_minor is not None
        and batch.statement_last_date
        and batch.statement_last_date >= account.opening_balance_date
    ):
        db.flush()
        entries = live_entries(db, account.user_id, [account.id])[account.id]
        rec = reconcile(
            currency=account.currency,
            opening_minor=account.opening_balance_minor,
            opening_date=account.opening_balance_date,
            entries=entries,
            as_of=batch.statement_last_date,
            statement_minor=batch.statement_closing_balance_minor,
        )
        db.add(
            ReconciliationPoint(
                user_id=account.user_id,
                account_id=account.id,
                as_of_date=batch.statement_last_date,
                statement_balance_minor=batch.statement_closing_balance_minor,
                computed_balance_minor=rec.computed_minor,
                source="statement",
                import_batch_id=batch.id,
            )
        )
        rec_out = {
            "as_of": rec.as_of.isoformat(),
            "statement_minor": rec.statement_minor,
            "computed_minor": rec.computed_minor,
            "difference_minor": rec.difference_minor,
            "matches": rec.matches,
        }

    if save_mapping and batch.header_signature and batch.mapping:
        mapping = {k: v for k, v in batch.mapping.items() if k != "from_profile"}
        prof = db.scalar(
            select(ImportProfile).where(
                ImportProfile.account_id == account.id,
                ImportProfile.header_signature == batch.header_signature,
            )
        )
        if prof is None:
            db.add(
                ImportProfile(
                    user_id=account.user_id,
                    account_id=account.id,
                    header_signature=batch.header_signature,
                    mapping=mapping,
                )
            )
        else:
            prof.mapping = mapping

    batch.status = "committed"
    batch.committed_at = utcnow()
    batch.grid = None  # raw cells are no longer needed
    batch.side_effects = side_effects
    batch.counts = {
        **batch.counts,
        "committed": len(created),
        "transfers_linked": transfers,
        "reversals_linked": reversals,
    }
    return CommitResult(len(created), transfers, reversals, opening_set, rec_out)


def _fits_kind(category_kind: str, txn_kind: str) -> bool:
    if txn_kind in ("expense", "fee", "refund"):
        return category_kind == "expense"
    return category_kind == "income" if txn_kind == "income" else False


def _newest_first(db: Session, batch: ImportBatch) -> bool:
    first = db.scalar(
        select(ImportRow.transaction_date)
        .where(ImportRow.batch_id == batch.id, ImportRow.transaction_date.is_not(None))
        .order_by(ImportRow.row_number)
        .limit(1)
    )
    last = db.scalar(
        select(ImportRow.transaction_date)
        .where(ImportRow.batch_id == batch.id, ImportRow.transaction_date.is_not(None))
        .order_by(ImportRow.row_number.desc())
        .limit(1)
    )
    return bool(first and last and first > last)


def _lock_live(db: Session, user_id: int, txn_id: int | None) -> Transaction | None:
    if txn_id is None:
        return None
    return db.scalar(
        select(Transaction)
        .where(
            Transaction.id == txn_id,
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
        )
        .with_for_update()
    )


# ---------------------------------------------------------------- undo


def undo(db: Session, batch: ImportBatch) -> int:
    """Remove every transaction this import created and put back what it changed."""
    now = utcnow()
    mine = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.import_batch_id == batch.id, Transaction.deleted_at.is_(None))
            .with_for_update()
        )
    )
    mine_ids = {t.id for t in mine}
    reason = f"Import of {batch.filename} undone"[:200]
    ctx = cats.load_context(db, batch.user_id)
    for t in mine:
        t.deleted_at = now
        # Free the identity so the same file can be imported again later.
        t.fingerprint = None
        t.external_ref = None
        add_revision(db, t, "delete", {}, reason)

    for fx in batch.side_effects or []:
        other = _lock_live(db, batch.user_id, fx.get("txn_id"))
        if other is None or other.id in mine_ids:
            continue
        if fx["type"] == "transfer_link" and other.kind == "transfer":
            add_revision(db, other, "update", {"kind": ["transfer", fx["prev_kind"]]}, reason)
            other.kind, other.transfer_group_id = fx["prev_kind"], None
            other.category_source = "none"
            cats.apply(ctx, other)
        elif fx["type"] == "reversed" and other.status == "reversed":
            add_revision(db, other, "update", {"status": ["reversed", "posted"]}, reason)
            other.status = "posted"

    db.flush()  # make the reverts above visible to the query below
    # Transfers created by *later* imports may have paired with rows we just removed.
    groups = {t.transfer_group_id for t in mine if t.transfer_group_id}
    if groups:
        for t in db.scalars(
            select(Transaction)
            .where(
                Transaction.transfer_group_id.in_(groups),
                Transaction.deleted_at.is_(None),
                Transaction.user_id == batch.user_id,
            )
            .with_for_update()
        ):
            natural = NATURAL_KIND[t.direction]
            add_revision(
                db,
                t,
                "update",
                {"kind": ["transfer", natural]},
                "Its matching transfer was removed by an undone import",
            )
            t.kind, t.transfer_group_id = natural, None
            t.category_source = "none"
            cats.apply(ctx, t)
    batch.status = "undone"
    batch.finished_at = now
    return len(mine)
