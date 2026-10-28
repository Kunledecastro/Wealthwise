import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth.sessions import CurrentAuth, client_ip, require_auth
from app.categorise import service as cats
from app.categorise.defaults import LOCKED_SLUGS
from app.categorise.engine import Facts, Rule, norm_pattern, rule_matches, suggest_pattern
from app.db.models import (
    Account,
    Category,
    CategoryRule,
    ImportRow,
    Transaction,
)
from app.db.session import get_db
from app.finance.service import get_account, get_txn, to_entry, today_for, unprocessable
from app.finance.summary import month_bounds
from app.ledger.engine import by_category

router = APIRouter(prefix="/api/categories", tags=["categories"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


HEX = r"^#[0-9a-fA-F]{6}$"


class CategoryIn(Strict):
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["expense", "income"]
    color: str = Field(default="#94a3b8", pattern=HEX)


class CategoryPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, pattern=HEX)
    is_archived: bool | None = None


class MergeIn(Strict):
    into_id: uuid.UUID


class CategoryOut(BaseModel):
    id: uuid.UUID
    slug: str | None
    name: str
    kind: str
    color: str
    is_archived: bool
    locked: bool
    transaction_count: int
    rule_count: int


class RuleIn(Strict):
    category_id: uuid.UUID
    match_type: Literal["contains", "starts_with", "equals"] = "contains"
    pattern: str = Field(min_length=2, max_length=100)
    direction: Literal["debit", "credit"] | None = None
    account_id: uuid.UUID | None = None
    priority: int = Field(default=100, ge=1, le=1000)
    apply_to_existing: bool = False
    created_from: Literal["manual", "user_correction"] = "manual"

    @field_validator("pattern")
    @classmethod
    def _pat(cls, v: str) -> str:
        v = norm_pattern(v)
        if len(v) < 2:
            raise ValueError("Use at least 2 characters.")
        return v


class RulePatch(Strict):
    category_id: uuid.UUID | None = None
    match_type: Literal["contains", "starts_with", "equals"] | None = None
    pattern: str | None = Field(default=None, min_length=2, max_length=100)
    priority: int | None = Field(default=None, ge=1, le=1000)
    is_active: bool | None = None

    @field_validator("pattern")
    @classmethod
    def _pat(cls, v: str | None) -> str | None:
        return norm_pattern(v) if v else v


class RulePreviewIn(Strict):
    category_id: uuid.UUID
    match_type: Literal["contains", "starts_with", "equals"] = "contains"
    pattern: str = Field(min_length=2, max_length=100)
    direction: Literal["debit", "credit"] | None = None
    account_id: uuid.UUID | None = None


class RuleOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    match_type: str
    pattern: str
    direction: str | None
    account_id: uuid.UUID | None
    account_name: str | None
    priority: int
    created_from: str
    is_active: bool
    hit_count: int


class RuleCreatedOut(RuleOut):
    applied_to: int


class BulkCategoriseIn(Strict):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    category_id: uuid.UUID | None = None
    uncategorised: bool = False
    accept_suggestions: bool = False


class BulkOut(BaseModel):
    updated: int
    skipped: int


class SuggestionOut(BaseModel):
    pattern: str | None
    match_type: str
    category_id: uuid.UUID | None
    category_name: str | None
    similar_count: int


class ByCategoryRow(BaseModel):
    category_id: uuid.UUID | None
    name: str
    color: str
    kind: str | None
    gross_spending: int
    refunds: int
    net_spending: int
    income: int
    transaction_count: int


class ByCategoryOut(BaseModel):
    date_from: date
    date_to: date
    currency: str
    rows: list[ByCategoryRow]


# ---------------------------------------------------------------- helpers


def _counts(db: Session, user_id: int) -> tuple[dict[int | None, int], dict[int, int]]:
    txn = dict(
        db.execute(
            select(Transaction.category_id, func.count())
            .where(Transaction.user_id == user_id, Transaction.deleted_at.is_(None))
            .group_by(Transaction.category_id)
        ).all()
    )
    rules = dict(
        db.execute(
            select(CategoryRule.category_id, func.count())
            .where(CategoryRule.user_id == user_id)
            .group_by(CategoryRule.category_id)
        ).all()
    )
    return txn, rules


def _cat_out(c: Category, txn: dict[int | None, int], rules: dict[int, int]) -> CategoryOut:
    return CategoryOut(
        id=c.public_id,
        slug=c.slug,
        name=c.name,
        kind=c.kind,
        color=c.color,
        is_archived=c.is_archived,
        locked=c.slug in LOCKED_SLUGS,
        transaction_count=txn.get(c.id, 0),
        rule_count=rules.get(c.id, 0),
    )


def _rule_out(db: Session, r: CategoryRule) -> RuleOut:
    c = db.get(Category, r.category_id)
    if c is None:  # pragma: no cover - FK guarantees this
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found.")
    a = db.get(Account, r.account_id) if r.account_id else None
    return RuleOut(
        id=r.public_id,
        category_id=c.public_id,
        category_name=c.name,
        match_type=r.match_type,
        pattern=r.pattern,
        direction=r.direction,
        account_id=a.public_id if a else None,
        account_name=a.display_name if a else None,
        priority=r.priority,
        created_from=r.created_from,
        is_active=r.is_active,
        hit_count=r.hit_count,
    )


def _get_rule(db: Session, user_id: int, rule_id: uuid.UUID) -> CategoryRule:
    r = db.scalar(
        select(CategoryRule).where(
            CategoryRule.user_id == user_id, CategoryRule.public_id == rule_id
        )
    )
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found.")
    return r


def _matching(db: Session, user_id: int, rule: Rule, category: Category) -> list[Transaction]:
    """Live transactions the rule would change: matching, automatic (never the user's own
    choices), of a type that fits the category, and not already in that category."""
    rows = db.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
            Transaction.category_source.in_(("none", "system", "rule")),
            Transaction.kind.in_(("income", "expense", "refund")),
        )
    )
    out = []
    for t in rows:
        f = Facts(t.kind, t.direction, t.narration, t.merchant, t.merchant_normalised, t.account_id)
        if cats.fits(category, t.kind) and t.category_id != category.id and rule_matches(rule, f):
            out.append(t)
    return out


# ---------------------------------------------------------------- categories


@router.get("", response_model=list[CategoryOut])
def list_categories(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> list[CategoryOut]:
    stmt = select(Category).where(Category.user_id == auth.user.id)
    if not include_archived:
        stmt = stmt.where(Category.is_archived.is_(False))
    txn, rules = _counts(db, auth.user.id)
    rows = db.scalars(stmt.order_by(Category.kind, Category.sort_order, Category.name))
    return [_cat_out(c, txn, rules) for c in rows]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> CategoryOut:
    n_cats = db.scalar(
        select(func.count()).select_from(Category).where(Category.user_id == auth.user.id)
    )
    if (n_cats or 0) >= 200:
        raise unprocessable("Category limit reached (200).")
    if db.scalar(
        select(Category.id).where(Category.user_id == auth.user.id, Category.name == body.name)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a category with that name.")
    c = Category(
        user_id=auth.user.id, name=body.name, kind=body.kind, color=body.color, sort_order=500
    )
    db.add(c)
    db.flush()
    audit(
        db,
        "category.created",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="category",
        target_id=str(c.public_id),
    )
    db.commit()
    return _cat_out(c, {}, {})


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: uuid.UUID,
    body: CategoryPatch,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> CategoryOut:
    c = cats.get_category(db, auth.user.id, category_id)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if changes.get("is_archived") and c.slug in LOCKED_SLUGS:
        raise unprocessable("This category is used automatically and can't be archived.")
    if (
        "name" in changes
        and changes["name"].lower() != c.name.lower()
        and db.scalar(
            select(Category.id).where(
                Category.user_id == auth.user.id, Category.name == changes["name"]
            )
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a category with that name.")
    for k, v in changes.items():
        setattr(c, k, v)
    if changes:
        audit(
            db,
            "category.updated",
            user_id=auth.user.id,
            ip=client_ip(request),
            target_type="category",
            target_id=str(c.public_id),
            details={"fields": sorted(changes)},
        )
        db.commit()
    txn, rules = _counts(db, auth.user.id)
    return _cat_out(c, txn, rules)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> Response:
    c = cats.get_category(db, auth.user.id, category_id)
    if c.slug in LOCKED_SLUGS:
        raise unprocessable("This category is used automatically and can't be deleted.")
    used = db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.category_id == c.id)
    )
    if used:
        raise unprocessable("This category has transactions. Archive it, or merge it into another.")
    db.execute(
        update(ImportRow)
        .where(ImportRow.category_id == c.id)
        .values(category_id=None, category_source="none")
    )
    audit(
        db,
        "category.deleted",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="category",
        target_id=str(c.public_id),
    )
    db.delete(c)  # its rules are removed with it
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{category_id}/merge", response_model=CategoryOut)
def merge_category(
    category_id: uuid.UUID,
    body: MergeIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> CategoryOut:
    """Move every transaction and rule from this category into another, then delete it."""
    src = cats.get_category(db, auth.user.id, category_id)
    dst = cats.get_category(db, auth.user.id, body.into_id)
    if src.id == dst.id:
        raise unprocessable("Choose a different category to merge into.")
    if src.slug in LOCKED_SLUGS:
        raise unprocessable("This category is used automatically and can't be merged away.")
    if src.kind != dst.kind:
        raise unprocessable(
            "You can only merge into a category of the same type (spending or income)."
        )
    if dst.is_archived:
        raise unprocessable("Unarchive the target category first.")
    moved = db.execute(  # type: ignore[attr-defined]
        update(Transaction)
        .where(Transaction.user_id == auth.user.id, Transaction.category_id == src.id)
        .values(category_id=dst.id)
    ).rowcount
    db.execute(
        update(CategoryRule)
        .where(CategoryRule.user_id == auth.user.id, CategoryRule.category_id == src.id)
        .values(category_id=dst.id)
    )
    db.execute(
        update(ImportRow)
        .where(ImportRow.user_id == auth.user.id, ImportRow.category_id == src.id)
        .values(category_id=dst.id)
    )
    audit(
        db,
        "category.merged",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="category",
        target_id=str(src.public_id),
        details={"into": str(dst.public_id), "moved": moved},
    )
    db.delete(src)
    db.commit()
    txn, rules = _counts(db, auth.user.id)
    return _cat_out(dst, txn, rules)


# ---------------------------------------------------------------- rules


@router.get("/rules", response_model=list[RuleOut])
def list_rules(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(require_auth)
) -> list[RuleOut]:
    rows = db.scalars(
        select(CategoryRule)
        .where(CategoryRule.user_id == auth.user.id)
        .order_by(CategoryRule.priority, CategoryRule.id)
    )
    return [_rule_out(db, r) for r in rows]


def _rule_from(
    db: Session, user_id: int, body: RuleIn | RulePreviewIn
) -> tuple[Rule, Category, int | None]:
    c = cats.get_category(db, user_id, body.category_id)
    if c.kind == "transfer":
        raise unprocessable("Transfers are categorised automatically.")
    if c.is_archived:
        raise unprocessable("That category is archived.")
    acct_id = get_account(db, user_id, body.account_id).id if body.account_id else None
    direction = body.direction or ("credit" if c.kind == "income" else None)
    return (
        Rule(0, c.id, body.match_type, norm_pattern(body.pattern), direction, acct_id),
        c,
        acct_id,
    )


@router.post("/rules/preview", response_model=BulkOut)
def preview_rule(
    body: RulePreviewIn,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> BulkOut:
    rule, cat, _ = _rule_from(db, auth.user.id, body)
    return BulkOut(updated=len(_matching(db, auth.user.id, rule, cat)), skipped=0)


@router.post("/rules", response_model=RuleCreatedOut, status_code=status.HTTP_201_CREATED)
def create_rule(
    body: RuleIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> RuleCreatedOut:
    rule, cat, acct_id = _rule_from(db, auth.user.id, body)
    n_rules = db.scalar(
        select(func.count()).select_from(CategoryRule).where(CategoryRule.user_id == auth.user.id)
    )
    if (n_rules or 0) >= 500:
        raise unprocessable("Rule limit reached (500).")
    r = CategoryRule(
        user_id=auth.user.id,
        category_id=cat.id,
        match_type=body.match_type,
        pattern=rule.pattern,
        direction=rule.direction,
        account_id=acct_id,
        priority=body.priority,
        created_from=body.created_from,
    )
    db.add(r)
    db.flush()
    applied = 0
    if body.apply_to_existing:
        targets = _matching(
            db,
            auth.user.id,
            Rule(r.id, cat.id, r.match_type, r.pattern, r.direction, r.account_id, r.priority),
            cat,
        )
        applied = cats.recategorise(db, auth.user.id, targets)
    audit(
        db,
        "category_rule.created",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="category_rule",
        target_id=str(r.public_id),
        details={"from": body.created_from, "applied_to": applied},
    )
    db.commit()
    db.refresh(r)
    return RuleCreatedOut(**_rule_out(db, r).model_dump(), applied_to=applied)


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: uuid.UUID,
    body: RulePatch,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> RuleOut:
    r = _get_rule(db, auth.user.id, rule_id)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "category_id" in changes:
        c = cats.get_category(db, auth.user.id, changes.pop("category_id"))
        if c.kind == "transfer" or c.is_archived:
            raise unprocessable("Choose an active spending or income category.")
        r.category_id = c.id
    for k, v in changes.items():
        setattr(r, k, v)
    audit(
        db,
        "category_rule.updated",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="category_rule",
        target_id=str(r.public_id),
    )
    db.commit()
    return _rule_out(db, r)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> Response:
    r = _get_rule(db, auth.user.id, rule_id)
    audit(
        db,
        "category_rule.deleted",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="category_rule",
        target_id=str(r.public_id),
    )
    db.delete(r)  # transactions keep their category; "Re-apply" re-runs the remaining rules
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reapply", response_model=BulkOut)
def reapply(
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> BulkOut:
    """Re-run your rules and built-in recognition over every transaction you haven't
    categorised yourself."""
    changed = cats.recategorise(db, auth.user.id)
    audit(
        db,
        "category.reapplied",
        user_id=auth.user.id,
        ip=client_ip(request),
        details={"changed": changed},
    )
    db.commit()
    return BulkOut(updated=changed, skipped=0)


# ---------------------------------------------------------------- review & bulk


@router.get("/review-count")
def review_count(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(require_auth)
) -> dict[str, int]:
    n = db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.user_id == auth.user.id,
            Transaction.deleted_at.is_(None),
            Transaction.needs_review.is_(True),
        )
    )
    return {"count": n or 0}


@router.post("/assign", response_model=BulkOut)
def bulk_assign(
    body: BulkCategoriseIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> BulkOut:
    """Set one category on many transactions, mark them deliberately uncategorised, or
    accept the suggested categories as they are."""
    modes = sum([body.category_id is not None, body.uncategorised, body.accept_suggestions])
    if modes != 1:
        raise unprocessable("Choose a category, 'uncategorised', or accepting the suggestions.")
    txns = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == auth.user.id,
                Transaction.public_id.in_(body.ids),
                Transaction.deleted_at.is_(None),
            )
            .with_for_update()
        )
    )
    if len(txns) != len(set(body.ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found.")
    cat = cats.get_category(db, auth.user.id, body.category_id) if body.category_id else None
    ctx = cats.load_context(db, auth.user.id)
    updated = skipped = 0
    for t in txns:
        if t.kind in ("transfer", "reversal", "adjustment"):
            skipped += 1
            continue
        if cat is not None:
            if cat.is_archived or not cats.fits(cat, t.kind):
                skipped += 1
                continue
            cats.apply(ctx, t, user_category_id=cat.id)
        elif body.uncategorised:
            cats.apply(ctx, t, user_uncategorised=True)
        else:
            if t.category_id is None:
                skipped += 1
                continue
            cats.apply(ctx, t, user_category_id=t.category_id)
        updated += 1
    audit(
        db,
        "category.assigned",
        user_id=auth.user.id,
        ip=client_ip(request),
        details={"updated": updated, "skipped": skipped},
    )
    db.commit()
    return BulkOut(updated=updated, skipped=skipped)


@router.get("/suggestion", response_model=SuggestionOut)
def rule_suggestion(
    transaction_id: uuid.UUID,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> SuggestionOut:
    """After you categorise a transaction: offer a rule for its merchant, and say how many
    similar transactions it would also change."""
    t = get_txn(db, auth.user.id, transaction_id, lock=False)
    pattern = suggest_pattern(t.merchant_normalised)
    cat = db.get(Category, t.category_id) if t.category_id else None
    similar = 0
    if pattern and cat is not None and cat.kind != "transfer":
        rule = Rule(0, cat.id, "contains", pattern, "credit" if cat.kind == "income" else None)
        similar = len(_matching(db, auth.user.id, rule, cat))
    return SuggestionOut(
        pattern=pattern,
        match_type="contains",
        category_id=cat.public_id if cat else None,
        category_name=cat.name if cat else None,
        similar_count=similar,
    )


# ---------------------------------------------------------------- spending by category

ledger_router = APIRouter(prefix="/api/ledger", tags=["ledger"])


@ledger_router.get("/by-category", response_model=ByCategoryOut)
def spending_by_category(
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: uuid.UUID | None = None,
    currency: Annotated[str, Query(min_length=3, max_length=3)] = "NGN",
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> ByCategoryOut:
    d0, d1 = month_bounds(today_for(auth.user))
    date_from, date_to = date_from or d0, date_to or d1
    if date_to < date_from:
        raise unprocessable("The end date must be on or after the start date.")
    stmt = select(Transaction).where(
        Transaction.user_id == auth.user.id,
        Transaction.deleted_at.is_(None),
        Transaction.transaction_date.between(date_from, date_to),
    )
    if account_id:
        stmt = stmt.where(Transaction.account_id == get_account(db, auth.user.id, account_id).id)
    totals = by_category((to_entry(t) for t in db.scalars(stmt)), date_from, date_to)
    catmap = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == auth.user.id))}
    rows = []
    for (cur, cid), t in totals.items():
        if cur != currency.upper():
            continue
        c = catmap.get(cid) if cid else None
        rows.append(
            ByCategoryRow(
                category_id=c.public_id if c else None,
                name=c.name if c else "Uncategorised",
                color=c.color if c else "#cbd5e1",
                kind=c.kind if c else None,
                gross_spending=t.gross_spending,
                refunds=t.refunds,
                net_spending=t.net_spending,
                income=t.income,
                transaction_count=t.transaction_count,
            )
        )
    rows.sort(key=lambda r: (-r.net_spending, -r.income, r.name))
    return ByCategoryOut(date_from=date_from, date_to=date_to, currency=currency.upper(), rows=rows)
