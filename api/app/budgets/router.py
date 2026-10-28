"""Monthly budgets (Phase 6). Every figure is computed live by app.ledger.engine."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit.service import record as audit
from app.auth.sessions import CurrentAuth, client_ip, require_auth
from app.budgets import service as svc
from app.categorise import service as cats
from app.db.models import MAX_MINOR, Budget, BudgetLine, Category
from app.db.session import get_db
from app.finance.schemas import Strict
from app.finance.service import not_found, today_for, unprocessable
from app.ledger.engine import add_months, normalise_thresholds

router = APIRouter(prefix="/api/budgets", tags=["budgets"])

MAX_LINES = 60
MIN_MONTH, MAX_MONTH = date(2000, 1, 1), date(2100, 12, 1)


# ---------------------------------------------------------------- schemas


class LineOut(BaseModel):
    id: str
    category_id: uuid.UUID | None  # None = overall limit
    name: str
    color: str
    archived: bool
    planned_minor: int
    rollover_minor: int
    spent_minor: int
    available_minor: int
    remaining_minor: int
    percent_used: int | None
    threshold_reached: int | None
    over: bool
    projected_minor: int | None
    projected_over: bool
    safe_per_day_minor: int | None
    days_left: int
    status: Literal["ok", "threshold", "over"]


class UnbudgetedOut(BaseModel):
    category_id: uuid.UUID | None
    name: str
    color: str
    net_spending: int


class BudgetOut(BaseModel):
    id: uuid.UUID
    rollover_enabled: bool
    alert_thresholds: list[int]  # effective
    thresholds_overridden: bool
    lines: list[LineOut]
    overall: LineOut | None
    total_planned: int  # sum of category lines (excludes the overall limit)
    total_spending: int  # all net spending this month (R8)
    budgeted_spending: int
    unbudgeted_spending: int
    unbudgeted: list[UnbudgetedOut]
    attention_count: int  # lines that reached a threshold or are over


class BudgetPageOut(BaseModel):
    month: date
    today: date
    currency: str
    default_thresholds: list[int]
    previous_month_has_budget: bool
    budget: BudgetOut | None


class SuggestionMonth(BaseModel):
    month: date
    net_spending: int


class SuggestionOut(BaseModel):
    category_id: uuid.UUID
    name: str
    color: str
    amount_minor: int
    months: list[SuggestionMonth]


class SuggestionsOut(BaseModel):
    month: date
    based_on: list[date]
    suggestions: list[SuggestionOut]


def _thresholds(v: list[int] | None) -> list[int] | None:
    if v is None:
        return None
    if not 1 <= len(v) <= 5:
        raise ValueError("Use between 1 and 5 thresholds.")
    try:
        return list(normalise_thresholds(v))
    except ValueError as exc:
        raise ValueError("Thresholds must be whole percentages from 1 to 200.") from exc


class BudgetCreateIn(Strict):
    month: date
    start: Literal["blank", "copy_previous", "suggested"] = "blank"
    rollover_enabled: bool = False
    alert_thresholds: list[Annotated[int, Field(strict=True)]] | None = None

    _t = field_validator("alert_thresholds")(_thresholds)


class BudgetPatchIn(Strict):
    rollover_enabled: bool | None = None
    alert_thresholds: list[Annotated[int, Field(strict=True)]] | None = None

    _t = field_validator("alert_thresholds")(_thresholds)


class LineIn(Strict):
    category_id: uuid.UUID | None = None
    planned_minor: int = Field(gt=0, le=MAX_MINOR, strict=True)


class LinesIn(Strict):
    lines: list[LineIn] = Field(max_length=MAX_LINES)


# ---------------------------------------------------------------- helpers


def _month(m: date) -> date:
    m = svc.first_of_month(m)
    if not MIN_MONTH <= m <= MAX_MONTH:
        raise unprocessable("Choose a month between 2000 and 2100.")
    return m


def _get_budget(db: Session, user_id: int, public_id: uuid.UUID) -> Budget:
    b = db.scalar(
        select(Budget)
        .where(Budget.user_id == user_id, Budget.public_id == public_id)
        .options(selectinload(Budget.lines))
    )
    if b is None:
        raise not_found("Budget")
    return b


def _find(db: Session, user_id: int, month: date, currency: str = "NGN") -> Budget | None:
    return db.scalar(
        select(Budget)
        .where(Budget.user_id == user_id, Budget.month == month, Budget.currency == currency)
        .options(selectinload(Budget.lines))
    )


def _line_out(r: svc.LineResult) -> LineOut:
    s = r.status
    c = r.category
    return LineOut(
        id=r.line_public_id,
        category_id=c.public_id if c else None,
        name=c.name if c else "Overall spending limit",
        color=c.color if c else "#64748b",
        archived=bool(c and c.is_archived),
        planned_minor=s.planned_minor,
        rollover_minor=s.rollover_minor,
        spent_minor=s.spent_minor,
        available_minor=s.available_minor,
        remaining_minor=s.remaining_minor,
        percent_used=s.percent_used,
        threshold_reached=s.threshold_reached,
        over=s.over,
        projected_minor=s.projected_minor,
        projected_over=s.projected_over,
        safe_per_day_minor=s.safe_per_day_minor,
        days_left=s.days_left,
        status="over" if s.over else "threshold" if s.threshold_reached else "ok",
    )


def _page(db: Session, auth: CurrentAuth, month: date) -> BudgetPageOut:
    user = auth.user
    today = today_for(user)
    budget = _find(db, user.id, month)
    prev = _find(db, user.id, add_months(month, -1))
    out = None
    if budget is not None:
        r = svc.evaluate(db, budget, user, today)
        lines = [_line_out(x) for x in r.lines]
        overall = _line_out(r.overall) if r.overall else None
        out = BudgetOut(
            id=budget.public_id,
            rollover_enabled=budget.rollover_enabled,
            alert_thresholds=list(r.thresholds),
            thresholds_overridden=bool(budget.alert_thresholds),
            lines=lines,
            overall=overall,
            total_planned=sum(x.planned_minor for x in lines),
            total_spending=r.total_spending,
            budgeted_spending=r.budgeted_spending,
            unbudgeted_spending=r.total_spending - r.budgeted_spending,
            unbudgeted=[
                UnbudgetedOut(
                    category_id=c.public_id if c else None,
                    name=c.name if c else "Uncategorised",
                    color=c.color if c else "#94a3b8",
                    net_spending=amount,
                )
                for c, amount in r.unbudgeted
            ],
            attention_count=sum(
                1 for x in [*lines, *([overall] if overall else [])] if x.status != "ok"
            ),
        )
    return BudgetPageOut(
        month=month,
        today=today,
        currency="NGN",
        default_thresholds=list(svc.effective_thresholds(None, user)),
        previous_month_has_budget=prev is not None,
        budget=out,
    )


def _resolve_category(db: Session, user_id: int, public_id: uuid.UUID) -> Category:
    c = cats.get_category(db, user_id, public_id)
    if c.kind != "expense":
        raise unprocessable(f"“{c.name}” is not a spending category, so it can't be budgeted.")
    return c


# ---------------------------------------------------------------- endpoints


@router.get("", response_model=BudgetPageOut)
def get_budget(
    month: date | None = None,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> BudgetPageOut:
    """The budget for a month (default: this month in the user's timezone), with live
    figures. `budget` is null when no budget has been set for that month."""
    return _page(db, auth, _month(month or today_for(auth.user)))


@router.get("/suggestions", response_model=SuggestionsOut)
def get_suggestions(
    month: date | None = None,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> SuggestionsOut:
    today = today_for(auth.user)
    m = _month(month or today)
    res = svc.suggestions(db, auth.user.id, m, today)
    return SuggestionsOut(
        month=m,
        based_on=svc.suggestion_months(m, today),
        suggestions=[
            SuggestionOut(
                category_id=s.category.public_id,
                name=s.category.name,
                color=s.category.color,
                amount_minor=s.amount_minor,
                months=[SuggestionMonth(month=mm, net_spending=v) for mm, v in s.months],
            )
            for s in res
        ],
    )


@router.post("", response_model=BudgetPageOut, status_code=status.HTTP_201_CREATED)
def create_budget(
    body: BudgetCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> BudgetPageOut:
    uid = auth.user.id
    month = _month(body.month)
    if _find(db, uid, month) is not None:
        raise unprocessable("There is already a budget for this month.")
    b = Budget(
        user_id=uid,
        month=month,
        rollover_enabled=body.rollover_enabled,
        alert_thresholds=body.alert_thresholds,
    )
    db.add(b)
    db.flush()
    if body.start == "copy_previous":
        prev = _find(db, uid, add_months(month, -1))
        if prev is None:
            raise unprocessable("There is no budget for the previous month to copy.")
        archived = {
            c.id
            for c in db.scalars(
                select(Category).where(Category.user_id == uid, Category.is_archived.is_(True))
            )
        }
        for line in prev.lines:
            if line.category_id not in archived:
                db.add(
                    BudgetLine(
                        user_id=uid,
                        budget_id=b.id,
                        category_id=line.category_id,
                        planned_minor=line.planned_minor,
                    )
                )
    elif body.start == "suggested":
        for s in svc.suggestions(db, uid, month, today_for(auth.user)):
            db.add(
                BudgetLine(
                    user_id=uid,
                    budget_id=b.id,
                    category_id=s.category.id,
                    planned_minor=s.amount_minor,
                )
            )
    audit(
        db,
        "budget.created",
        user_id=uid,
        ip=client_ip(request),
        target_type="budget",
        target_id=str(b.public_id),
        details={"month": month.isoformat(), "start": body.start},
    )
    db.commit()
    db.expire_all()
    return _page(db, auth, month)


@router.patch("/{budget_id}", response_model=BudgetPageOut)
def update_budget(
    budget_id: uuid.UUID,
    body: BudgetPatchIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> BudgetPageOut:
    b = _get_budget(db, auth.user.id, budget_id)
    changed = []
    if "rollover_enabled" in body.model_fields_set and body.rollover_enabled is not None:
        b.rollover_enabled = body.rollover_enabled
        changed.append("rollover_enabled")
    if "alert_thresholds" in body.model_fields_set:  # null = use Settings again
        b.alert_thresholds = body.alert_thresholds
        changed.append("alert_thresholds")
    if changed:
        audit(
            db,
            "budget.updated",
            user_id=auth.user.id,
            ip=client_ip(request),
            target_type="budget",
            target_id=str(b.public_id),
            details={"fields": changed},
        )
        db.commit()
    return _page(db, auth, b.month)


@router.put("/{budget_id}/lines", response_model=BudgetPageOut)
def replace_lines(
    budget_id: uuid.UUID,
    body: LinesIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> BudgetPageOut:
    """Replace every line of a budget in one go (what the edit form saves)."""
    uid = auth.user.id
    b = _get_budget(db, uid, budget_id)
    existing = {line.category_id for line in b.lines}
    wanted: dict[int | None, int] = {}
    for item in body.lines:
        cid = None
        if item.category_id is not None:
            c = _resolve_category(db, uid, item.category_id)
            if c.is_archived and c.id not in existing:
                raise unprocessable(f"“{c.name}” is archived. Unarchive it to budget for it.")
            cid = c.id
        if cid in wanted:
            raise unprocessable("Each category can only appear once in a budget.")
        wanted[cid] = item.planned_minor
    for row in list(b.lines):
        if row.category_id not in wanted:
            b.lines.remove(row)
        else:
            row.planned_minor = wanted.pop(row.category_id)
    for cid, planned in wanted.items():
        b.lines.append(BudgetLine(user_id=uid, category_id=cid, planned_minor=planned))
    audit(
        db,
        "budget.lines_saved",
        user_id=uid,
        ip=client_ip(request),
        target_type="budget",
        target_id=str(b.public_id),
        details={"lines": len(body.lines)},
    )
    db.commit()
    db.expire_all()
    return _page(db, auth, b.month)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    budget_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> Response:
    b = _get_budget(db, auth.user.id, budget_id)
    audit(
        db,
        "budget.deleted",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="budget",
        target_id=str(b.public_id),
        details={"month": b.month.isoformat()},
    )
    db.delete(b)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
