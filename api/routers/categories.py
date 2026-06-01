from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.database import get_db
from api import models, schemas
from proxy.categorizer import Categorizer

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


@router.get("", response_model=List[schemas.CategorySchema])
def list_categories(db: Session = Depends(get_db)):
    return db.query(models.Category).order_by(models.Category.name).all()


@router.post("", response_model=schemas.CategorySchema, status_code=201)
def create_category(payload: schemas.CategoryCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Category).filter(models.Category.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Category name already exists")
    cat = models.Category(name=payload.name, color=payload.color, description=payload.description)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.put("/{category_id}", response_model=schemas.CategorySchema)
def update_category(category_id: int, payload: schemas.CategoryCreate, db: Session = Depends(get_db)):
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat.name = payload.name
    cat.color = payload.color
    cat.description = payload.description
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(cat)
    db.commit()


@router.post("/{category_id}/rules", response_model=schemas.CategoryRuleSchema, status_code=201)
def add_rule(category_id: int, payload: schemas.CategoryRuleCreate, db: Session = Depends(get_db)):
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    rule = models.CategoryRule(
        category_id=category_id,
        pattern=payload.pattern,
        match_type=payload.match_type,
        priority=payload.priority,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(models.CategoryRule).filter(models.CategoryRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()


@router.get("/test-domain")
def test_domain(domain: str = Query(...), db: Session = Depends(get_db)):
    cat = Categorizer(db)
    result = cat.categorize(domain)
    return {"domain": domain, "matched_category": result["name"] if result else None}
