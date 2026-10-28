"""Database side of categorisation: load a user's categories and rules, apply the pure
engine to transactions, seed defaults, and re-run rules in bulk."""

import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.categorise.defaults import DEFAULT_CATEGORIES
from app.categorise.engine import (
    CategoryInfo,
    Facts,
    Result,
    Rule,
    categorise,
    needs_review,
    normalise_merchant,
)
from app.db.models import Category, CategoryRule, ImportRow, Transaction, utcnow

RECOMPUTABLE = ("none", "system", "rule", "linked")


@dataclass
class Context:
    categories: dict[int, CategoryInfo]
    rules: list[Rule]
    hits: Counter[int]

    def info(self, category_id: int | None) -> CategoryInfo | None:
        return self.categories.get(category_id) if category_id else None


def seed_defaults(db: Session, user_id: int) -> None:
    existing = set(db.scalars(select(Category.slug).where(Category.user_id == user_id)))
    for i, (slug, name, kind, color) in enumerate(DEFAULT_CATEGORIES):
        if slug not in existing:
            db.add(
                Category(
                    user_id=user_id, slug=slug, name=name, kind=kind, color=color, sort_order=i * 10
                )
            )


def load_context(db: Session, user_id: int) -> Context:
    cats = {
        c.id: CategoryInfo(c.id, c.slug, c.kind, c.name, c.is_archived)
        for c in db.scalars(select(Category).where(Category.user_id == user_id))
    }
    rules = [
        Rule(r.id, r.category_id, r.match_type, r.pattern, r.direction, r.account_id, r.priority)
        for r in db.scalars(
            select(CategoryRule).where(
                CategoryRule.user_id == user_id, CategoryRule.is_active.is_(True)
            )
        )
    ]
    return Context(cats, rules, Counter())


def _facts(
    t: Transaction | ImportRow,
    kind: str,
    direction: str,
    merchant: str | None,
    account_id: int,
    linked: int | None,
    user_cat: int | None,
) -> Facts:
    return Facts(
        kind=kind,
        direction=direction,
        narration=t.narration,
        merchant=merchant,
        merchant_normalised=t.merchant_normalised,
        account_id=account_id,
        linked_category_id=linked,
        user_category_id=user_cat,
    )


def _store(t: Transaction | ImportRow, r: Result, kind: str) -> None:
    t.category_id = r.category_id
    t.category_source = r.source
    t.category_confidence = r.confidence
    t.category_reason = r.reason[:200] if r.reason else None
    t.category_rule_id = r.rule_id
    if isinstance(t, Transaction):
        t.needs_review = needs_review(kind, r)


def apply(
    ctx: Context,
    t: Transaction,
    *,
    linked_category_id: int | None = None,
    user_category_id: int | None = None,
    user_uncategorised: bool = False,
) -> None:
    """(Re)categorise one transaction in memory. Respects an existing user choice unless a
    new explicit choice is passed."""
    t.merchant_normalised = normalise_merchant(t.merchant or t.narration)
    if user_uncategorised:
        _store(t, Result(None, "user", 100, "You left this uncategorised"), t.kind)
        return
    if user_category_id is None and t.category_source == "user":
        return
    r = categorise(
        _facts(
            t, t.kind, t.direction, t.merchant, t.account_id, linked_category_id, user_category_id
        ),
        ctx.categories,
        ctx.rules,
    )
    if r.rule_id:
        ctx.hits[r.rule_id] += 1
    _store(t, r, t.kind)


def apply_row(ctx: Context, row: ImportRow, account_id: int, linked: int | None = None) -> None:
    """Suggest a category for an import review row (unless the user already chose one)."""
    row.merchant_normalised = normalise_merchant(row.narration)
    if row.category_source == "user" or not row.direction or not row.kind:
        return
    kind = row.kind
    r = categorise(
        _facts(row, kind, row.direction, None, account_id, linked, None), ctx.categories, ctx.rules
    )
    _store(row, r, kind)


def flush_hits(db: Session, ctx: Context) -> None:
    now = utcnow()
    for rule_id, n in ctx.hits.items():
        db.execute(
            update(CategoryRule)
            .where(CategoryRule.id == rule_id)
            .values(hit_count=CategoryRule.hit_count + n, last_hit_at=now)
        )
    ctx.hits.clear()


def linked_category(db: Session, t: Transaction) -> int | None:
    target = t.reverses_transaction_id or t.refund_of_transaction_id
    if not target:
        return None
    return db.scalar(
        select(Transaction.category_id).where(
            Transaction.id == target, Transaction.user_id == t.user_id
        )
    )


def recategorise(
    db: Session,
    user_id: int,
    txns: Sequence[Transaction] | None = None,
    *,
    only_sources: Iterable[str] = RECOMPUTABLE,
) -> int:
    """Re-run rules over transactions (never touching the user's own choices). Linked
    refunds/reversals are done after everything else so they inherit fresh categories.
    Returns how many transactions changed category."""
    ctx = load_context(db, user_id)
    if txns is None:
        txns = list(
            db.scalars(
                select(Transaction).where(
                    Transaction.user_id == user_id,
                    Transaction.deleted_at.is_(None),
                    Transaction.category_source.in_(tuple(only_sources)),
                )
            )
        )
    by_id = {t.id: t for t in txns}
    changed = 0
    linked_kinds = [t for t in txns if t.reverses_transaction_id or t.refund_of_transaction_id]
    plain = [t for t in txns if t not in linked_kinds]
    for t in plain:
        before = t.category_id
        apply(ctx, t)
        changed += before != t.category_id
    for t in linked_kinds:
        target = t.reverses_transaction_id or t.refund_of_transaction_id
        orig = by_id.get(target) if target else None
        linked = orig.category_id if orig is not None else linked_category(db, t)
        before = t.category_id
        apply(ctx, t, linked_category_id=linked)
        changed += before != t.category_id
    flush_hits(db, ctx)
    return changed


def fits(cat: Category, kind: str) -> bool:
    if kind in ("expense", "fee", "refund"):
        return cat.kind == "expense"
    if kind == "income":
        return cat.kind == "income"
    return False


def get_category(db: Session, user_id: int, public_id: uuid.UUID) -> Category:
    c = db.scalar(
        select(Category).where(Category.user_id == user_id, Category.public_id == public_id)
    )
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found.")
    return c


def choose(db: Session, user_id: int, public_id: uuid.UUID, kind: str) -> Category:
    """Validate an explicit category choice for a transaction of `kind`."""
    c = get_category(db, user_id, public_id)
    if c.is_archived:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That category is archived.")
    if not fits(c, kind):
        need = "an income" if kind == "income" else "a spending"
        if kind in ("transfer", "reversal", "adjustment"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Transfers, reversals and adjustments get their category automatically.",
            )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Choose {need} category for this type."
        )
    return c
