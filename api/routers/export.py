import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from api.database import get_db
from api import models

router = APIRouter(prefix="/api/v1/export", tags=["export"])


@router.get("/csv")
def export_csv(
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    employee_id: Optional[int] = None,
    classification: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.TrafficLog).options(
        joinedload(models.TrafficLog.employee),
        joinedload(models.TrafficLog.category),
    )
    if from_dt:
        q = q.filter(models.TrafficLog.timestamp >= from_dt)
    if to_dt:
        q = q.filter(models.TrafficLog.timestamp <= to_dt)
    if employee_id:
        q = q.filter(models.TrafficLog.employee_id == employee_id)
    if classification:
        q = q.filter(models.TrafficLog.time_classification == classification)

    rows = q.order_by(models.TrafficLog.timestamp.desc()).limit(50000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "employee", "src_ip", "domain", "url",
        "method", "protocol", "status_code", "bytes_sent",
        "bytes_received", "category", "classification",
    ])
    for r in rows:
        writer.writerow([
            r.timestamp.isoformat(),
            r.employee.username if r.employee else "",
            r.src_ip,
            r.domain,
            r.url or "",
            r.method or "",
            r.protocol,
            r.status_code or "",
            r.bytes_sent,
            r.bytes_received,
            r.category.name if r.category else "",
            r.time_classification,
        ])

    output.seek(0)
    filename = f"traffic_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/pdf")
def export_pdf(
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Generate a PDF summary report using WeasyPrint."""
    try:
        from weasyprint import HTML
        from jinja2 import Environment, FileSystemLoader
        import os

        # Gather summary data
        from sqlalchemy import func
        top_sites_q = db.query(
            models.TrafficLog.domain,
            func.count(models.TrafficLog.id).label("count"),
        )
        if from_dt:
            top_sites_q = top_sites_q.filter(models.TrafficLog.timestamp >= from_dt)
        if to_dt:
            top_sites_q = top_sites_q.filter(models.TrafficLog.timestamp <= to_dt)
        if employee_id:
            top_sites_q = top_sites_q.filter(models.TrafficLog.employee_id == employee_id)

        top_sites = top_sites_q.group_by(models.TrafficLog.domain).order_by(
            func.count(models.TrafficLog.id).desc()
        ).limit(20).all()

        template_dir = os.path.join(os.path.dirname(__file__), "../../frontend/templates")
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template("report.html")
        html_content = template.render(
            top_sites=top_sites,
            from_dt=from_dt,
            to_dt=to_dt,
            generated_at=datetime.utcnow(),
        )
        pdf_bytes = HTML(string=html_content).write_pdf()

        filename = f"traffic_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ImportError:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=501,
            detail="PDF export requires WeasyPrint. Install it or use CSV export instead."
        )
