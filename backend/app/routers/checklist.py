from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ChecklistItem
from app.schemas import ChecklistItemIn, ChecklistItemOut

router = APIRouter(prefix="/api/checklist", tags=["checklist"])


@router.get("", response_model=list[ChecklistItemOut])
def list_items(db: Session = Depends(get_db)):
    stmt = select(ChecklistItem).order_by(ChecklistItem.sort_order)
    return list(db.scalars(stmt))


@router.post("", response_model=ChecklistItemOut)
def add_item(item: ChecklistItemIn, db: Session = Depends(get_db)):
    row = ChecklistItem(**item.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    row = db.get(ChecklistItem, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(row)
    db.commit()
    return {"deleted": item_id}
