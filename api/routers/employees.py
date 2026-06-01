from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api import models, schemas

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


@router.get("", response_model=List[schemas.EmployeeSchema])
def list_employees(db: Session = Depends(get_db)):
    return db.query(models.Employee).order_by(models.Employee.username).all()


@router.post("", response_model=schemas.EmployeeSchema, status_code=201)
def create_employee(payload: schemas.EmployeeCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Employee).filter(models.Employee.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    emp = models.Employee(username=payload.username, email=payload.email)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@router.get("/{employee_id}", response_model=schemas.EmployeeSchema)
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    emp = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.put("/{employee_id}", response_model=schemas.EmployeeSchema)
def update_employee(employee_id: int, payload: schemas.EmployeeUpdate, db: Session = Depends(get_db)):
    emp = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if payload.username is not None:
        emp.username = payload.username
    if payload.email is not None:
        emp.email = payload.email
    db.commit()
    db.refresh(emp)
    return emp


@router.delete("/{employee_id}", status_code=204)
def delete_employee(employee_id: int, db: Session = Depends(get_db)):
    emp = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(emp)
    db.commit()


@router.get("/{employee_id}/ips", response_model=List[schemas.EmployeeIPSchema])
def list_employee_ips(employee_id: int, db: Session = Depends(get_db)):
    emp = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp.ips


@router.post("/{employee_id}/ips", response_model=schemas.EmployeeIPSchema, status_code=201)
def add_employee_ip(employee_id: int, payload: schemas.EmployeeIPCreate, db: Session = Depends(get_db)):
    emp = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    ip_entry = models.EmployeeIP(
        employee_id=employee_id,
        ip_address=payload.ip_address,
        label=payload.label,
        active=payload.active,
    )
    db.add(ip_entry)
    db.commit()
    db.refresh(ip_entry)
    return ip_entry


@router.delete("/{employee_id}/ips/{ip_id}", status_code=204)
def delete_employee_ip(employee_id: int, ip_id: int, db: Session = Depends(get_db)):
    ip_entry = db.query(models.EmployeeIP).filter(
        models.EmployeeIP.id == ip_id,
        models.EmployeeIP.employee_id == employee_id,
    ).first()
    if not ip_entry:
        raise HTTPException(status_code=404, detail="IP entry not found")
    db.delete(ip_entry)
    db.commit()
