"""
Seed the database with realistic fake traffic data for development/demo.
Usage: python3 scripts/seed_dev_data.py
"""
import sys, os, random
from datetime import datetime, timedelta, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import init_db, SessionLocal
from api import models
from proxy.categorizer import Categorizer

EMPLOYEES = [
    ("alice", "alice@company.com", ["192.168.1.10"]),
    ("bob", "bob@company.com", ["192.168.1.11"]),
    ("carol", "carol@company.com", ["192.168.1.12"]),
    ("dave", "dave@company.com", ["192.168.1.13"]),
]

DOMAINS_WORK = [
    "github.com", "slack.com", "notion.so", "docs.google.com",
    "zoom.us", "stackoverflow.com", "gitlab.com", "jira.atlassian.com",
]
DOMAINS_BREAK = [
    "youtube.com", "reddit.com", "twitter.com", "instagram.com",
    "netflix.com", "facebook.com", "tiktok.com", "twitch.tv",
]
DOMAINS_MIXED = DOMAINS_WORK + DOMAINS_BREAK + [
    "google.com", "wikipedia.org", "medium.com", "news.ycombinator.com",
    "amazon.com", "cnn.com", "bbc.com", "github.com",
]

WORK_START = time(9, 0)
WORK_END = time(18, 0)
LUNCH_START = time(12, 0)
LUNCH_END = time(13, 0)


def classify(dt: datetime) -> str:
    wd = dt.isoweekday()
    if wd >= 6:
        return "outside"
    t = dt.time()
    if not (WORK_START <= t < WORK_END):
        return "outside"
    if LUNCH_START <= t < LUNCH_END:
        return "break"
    return "work"


def main():
    init_db()
    db = SessionLocal()
    cat = Categorizer(db=db)

    # Seed employees + IPs
    emp_objs = {}
    for name, email, ips in EMPLOYEES:
        e = db.query(models.Employee).filter(models.Employee.username == name).first()
        if not e:
            e = models.Employee(username=name, email=email)
            db.add(e)
            db.flush()
            for ip in ips:
                db.add(models.EmployeeIP(employee_id=e.id, ip_address=ip, label="Workstation"))
        emp_objs[name] = e

    db.commit()
    print(f"Employees seeded: {list(emp_objs.keys())}")

    # Generate 7 days of traffic
    now = datetime.utcnow()
    records = []
    for day_offset in range(7):
        day = now - timedelta(days=day_offset)
        for emp_name, emp in emp_objs.items():
            # ~80-200 requests per workday, ~20 on weekends
            count = random.randint(80, 200) if day.isoweekday() < 6 else random.randint(5, 20)
            for _ in range(count):
                hour = random.choices(
                    range(8, 22),
                    weights=[1,5,8,8,4,4,5,8,8,5,3,2,1,1],
                    k=1
                )[0]
                minute = random.randint(0, 59)
                ts = day.replace(hour=hour, minute=minute, second=random.randint(0,59), microsecond=0)
                cls = classify(ts)

                # During break/outside, more likely to visit non-work sites
                if cls == "work":
                    domain = random.choices(DOMAINS_MIXED, weights=[3]*len(DOMAINS_WORK)+[1]*len(DOMAINS_BREAK)+[2]*4, k=1)[0]
                else:
                    domain = random.choice(DOMAINS_BREAK + DOMAINS_MIXED)

                category = cat.categorize(domain)
                proto = random.choice(["https", "https", "https", "http"])
                records.append(models.TrafficLog(
                    timestamp=ts,
                    employee_id=emp.id,
                    src_ip=next((ip for n, _, ips in EMPLOYEES if n == emp_name for ip in ips), "0.0.0.0"),
                    domain=domain,
                    url=f"http://{domain}/" if proto == "http" else None,
                    method=random.choice(["GET", "GET", "GET", "POST"]),
                    protocol=proto,
                    status_code=random.choices([200, 200, 200, 302, 404, 500], weights=[10,10,10,3,1,1], k=1)[0],
                    bytes_sent=random.randint(200, 2000),
                    bytes_received=random.randint(1000, 500000),
                    category_id=category["id"] if category and category.get("id") else None,
                    time_classification=cls,
                ))

    db.bulk_save_objects(records)
    db.commit()
    print(f"Seeded {len(records)} traffic records across 7 days")
    db.close()


if __name__ == "__main__":
    main()
