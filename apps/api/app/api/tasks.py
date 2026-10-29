"""Tasks & Reminders API.

A task is an action the user plans to take. Completing one records the action
only - it never changes fees, money or goal outcomes by itself (spec 4.9).
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.goal import Goal
from app.models.tasks import Task
from app.models.user import User
from app.schemas.tasks import (
    SnoozeRequest,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    TaskUrgency,
)
from app.services import urgency as urgency_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_OPEN_STATUSES = {"proposed", "pending", "in_progress"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _task_out(task: Task) -> TaskOut:
    out = TaskOut.model_validate(task)
    out.is_overdue = (
        task.due_on is not None
        and task.due_on < date.today()
        and task.status in _OPEN_STATUSES
    )
    out.urgency = TaskUrgency(**urgency_service.score(task.priority, task.due_on, task.status))
    return out


def _get_task(db: Session, task_id: int, user_id: int) -> Task:
    task = get_owned(db, Task, task_id, user_id)
    if task.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    return task


def _validate_goal(db: Session, user: User, goal_id: int | None) -> None:
    if goal_id is not None:
        get_owned(db, Goal, goal_id, user.id)


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    goal_id: int | None = Query(default=None),
    sort: str | None = Query(default=None, pattern="^(urgency|due)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Task).where(Task.user_id == user.id, Task.deleted_at.is_(None))
    if status_filter:
        query = query.where(Task.status == status_filter)
    if goal_id is not None:
        query = query.where(Task.goal_id == goal_id)
    tasks = db.scalars(
        query.order_by(Task.due_on.asc().nullslast(), Task.created_at.desc())
    ).all()
    outs = [_task_out(t) for t in tasks]
    if sort == "urgency":
        # Most pressing first; ties fall back to the due-order the query gave,
        # so an unsettled earlier task leads among equals.
        outs.sort(key=lambda o: -o.urgency.score)
    return outs


@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _validate_goal(db, user, body.goal_id)
    task = Task(user_id=user.id, **body.model_dump())
    if task.status == "completed":
        task.completed_at = _now()
    db.add(task)
    db.commit()
    return _task_out(task)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    return _task_out(_get_task(db, task_id, user.id))


@router.put("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    task = _get_task(db, task_id, user.id)
    data = body.model_dump(exclude_unset=True)
    _validate_goal(db, user, data.get("goal_id"))
    for field, value in data.items():
        setattr(task, field, value)
    if "status" in data:
        task.completed_at = _now() if task.status == "completed" else None
    db.commit()
    return _task_out(task)


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Records the action as done. Touches no fees, money or goal figures."""
    task = _get_task(db, task_id, user.id)
    task.status = "completed"
    task.completed_at = _now()
    db.commit()
    return _task_out(task)


@router.post("/{task_id}/reopen", response_model=TaskOut)
def reopen_task(task_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    task = _get_task(db, task_id, user.id)
    task.status = "pending"
    task.completed_at = None
    db.commit()
    return _task_out(task)


@router.post("/{task_id}/snooze", response_model=TaskOut)
def snooze_task(task_id: int, body: SnoozeRequest, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """Push the due date forward by `days` (from today if overdue or unset)."""
    task = _get_task(db, task_id, user.id)
    if task.status not in _OPEN_STATUSES:
        raise HTTPException(status_code=409, detail="Only open tasks can be snoozed")
    base = max(task.due_on, date.today()) if task.due_on else date.today()
    task.due_on = base + timedelta(days=body.days)
    db.commit()
    return _task_out(task)


@router.post("/from-goal/{goal_id}", response_model=TaskOut, status_code=201)
def create_task_from_goal(goal_id: int, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """Turn a goal into a proposed next-action task (user approves it)."""
    goal = get_owned(db, Goal, goal_id, user.id)
    task = Task(
        user_id=user.id,
        title=f"Work on: {goal.name}",
        goal_id=goal.id,
        status="proposed",
        priority=goal.priority,
        due_on=goal.deadline,
    )
    db.add(task)
    db.commit()
    return _task_out(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, confirm: bool = Query(default=False),
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Deletion requires confirm=true")
    task = _get_task(db, task_id, user.id)
    task.deleted_at = _now()
    db.commit()
    return None
