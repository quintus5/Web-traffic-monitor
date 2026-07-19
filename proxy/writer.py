"""
Background thread that drains the proxy queue and bulk-inserts records into SQLite.
Runs in the same process as mitmproxy; uses its own SQLAlchemy session.
"""
import threading
import time
import logging
from datetime import datetime
from queue import Queue, Empty
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, OperationalError

logger = logging.getLogger(__name__)


class IPCache:
    """Maps src_ip → employee_id, refreshed every `ttl` seconds."""

    def __init__(self, session_factory, ttl: int = 60):
        self._factory = session_factory
        self._ttl = ttl
        self._map: dict = {}
        self._loaded_at: float = 0.0
        self._lock = threading.Lock()

    def get(self, ip: str) -> Optional[int]:
        now = time.monotonic()
        if now - self._loaded_at > self._ttl:
            self._refresh()
        return self._map.get(ip)

    def _refresh(self):
        db = None
        try:
            db = self._factory()
            from api import models
            rows = db.query(models.EmployeeIP).filter(models.EmployeeIP.active == True).all()
            with self._lock:
                self._map = {r.ip_address: r.employee_id for r in rows}
                self._loaded_at = time.monotonic()
        except Exception as e:
            logger.warning("IP cache refresh failed: %s", e)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass


class DatabaseWriter(threading.Thread):
    def __init__(self, queue: Queue, db_url: str, batch_size: int = 100, flush_interval: float = 0.2):
        super().__init__(daemon=True, name="db-writer")
        self._queue = queue
        self._db_url = db_url
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._stop_event = threading.Event()
        # Retry policy for transient commit failures (e.g. "database is locked").
        self._max_commit_attempts = 3
        self._retry_backoff = 0.5

        engine = create_engine(db_url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def set_pragmas(conn, _):
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            # Enforce FKs like the API engine so a category/employee deleted
            # mid-flight can't leave dangling category_id/employee_id references.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # Ensure the schema exists. Without this, launching the proxy standalone
        # (mitmdump --scripts proxy/addon.py) against a fresh DB would create an
        # empty file and silently drop every intercepted request.
        from api.database import Base
        from api import models  # noqa: F401 — registers ORM tables on Base
        Base.metadata.create_all(bind=engine)

        self._SessionFactory = sessionmaker(bind=engine)
        self._ip_cache = IPCache(self._SessionFactory)

        # Import categorizer and classifier here; they use DB sessions
        from proxy.categorizer import Categorizer
        from proxy.classifier import TimeClassifier
        self._categorizer_cls = Categorizer
        self._classifier_cls = TimeClassifier

    def stop(self):
        self._stop_event.set()

    def run(self):
        logger.info("DatabaseWriter started")
        db = self._SessionFactory()
        cat = self._categorizer_cls(db=db)
        clf = self._classifier_cls(db=db)

        pending: list = []
        last_flush = time.monotonic()

        while not self._stop_event.is_set():
            # Collect items from queue
            try:
                item = self._queue.get(timeout=self._flush_interval)
                pending.append(item)
            except Empty:
                pass

            now = time.monotonic()
            should_flush = (
                len(pending) >= self._batch_size
                or (pending and (now - last_flush) >= self._flush_interval)
            )

            if should_flush and pending:
                self._flush(pending, db, cat, clf)
                pending.clear()
                last_flush = time.monotonic()

        # Drain remaining items on shutdown
        while not self._queue.empty():
            try:
                pending.append(self._queue.get_nowait())
            except Empty:
                break
        if pending:
            self._flush(pending, db, cat, clf)

        db.close()
        logger.info("DatabaseWriter stopped")

    def _flush(self, items: list, db, cat, clf):
        from api import models
        records = []
        for item in items:
            try:
                # Response-hook items only carry status/bytes and cannot be
                # reliably matched back to their request row in a batch writer.
                # Skipping them avoids inserting duplicate, half-populated rows.
                if item.get("_update"):
                    continue
                domain = item.get("domain", "")
                timestamp = item.get("timestamp", datetime.utcnow())
                src_ip = item.get("src_ip", "")

                employee_id = self._ip_cache.get(src_ip)
                category = cat.categorize(domain)
                classification = clf.classify(timestamp)

                records.append(models.TrafficLog(
                    timestamp=timestamp,
                    employee_id=employee_id,
                    src_ip=src_ip,
                    domain=domain,
                    url=item.get("url"),
                    method=item.get("method"),
                    protocol=item.get("protocol", "https"),
                    status_code=item.get("status_code"),
                    bytes_sent=item.get("bytes_sent", 0),
                    bytes_received=item.get("bytes_received", 0),
                    category_id=category["id"] if category and category.get("id") else None,
                    time_classification=classification,
                ))
            except Exception as e:
                logger.warning("Failed to build record: %s", e)

        if records:
            self._commit_records(db, records)

    def _commit_records(self, db, records: list):
        """Persist a batch, tolerating transient locks and individual bad rows.

        The fast path is a single bulk insert. On a transient "database is
        locked" error we retry the whole batch; on any other failure we fall
        back to inserting rows one at a time so one poison row (or a category
        deleted mid-flight) can't discard every valid row batched with it."""
        for attempt in range(1, self._max_commit_attempts + 1):
            try:
                db.bulk_save_objects(records)
                db.commit()
                logger.debug("Flushed %d records", len(records))
                return
            except OperationalError as e:
                db.rollback()
                if attempt < self._max_commit_attempts and "locked" in str(e).lower():
                    time.sleep(self._retry_backoff * attempt)
                    continue
                logger.warning("Bulk flush failed (%s); inserting rows individually", e)
                break
            except Exception as e:
                db.rollback()
                logger.warning("Bulk flush failed (%s); inserting rows individually", e)
                break

        saved = sum(1 for rec in records if self._insert_single(db, rec))
        lost = len(records) - saved
        if lost:
            logger.error("Flush permanently dropped %d of %d records", lost, len(records))
        else:
            logger.info("Recovered all %d records via per-record fallback", saved)

    def _insert_single(self, db, rec) -> bool:
        for attempt in range(1, self._max_commit_attempts + 1):
            try:
                db.add(rec)
                db.commit()
                return True
            except IntegrityError:
                # Most likely a category_id/employee_id that was deleted between
                # categorization and insert. Null the FKs and keep the row as
                # uncategorized rather than losing the traffic record entirely.
                db.rollback()
                if rec.category_id is None and rec.employee_id is None:
                    return False
                rec.category_id = None
                rec.employee_id = None
                try:
                    db.add(rec)
                    db.commit()
                    return True
                except Exception:
                    db.rollback()
                    return False
            except OperationalError as e:
                db.rollback()
                if attempt < self._max_commit_attempts and "locked" in str(e).lower():
                    time.sleep(self._retry_backoff * attempt)
                    continue
                return False
            except Exception:
                db.rollback()
                return False
        return False
