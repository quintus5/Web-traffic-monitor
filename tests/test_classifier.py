import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from proxy.classifier import TimeClassifier


class MockBreak:
    def __init__(self, start, end):
        from datetime import time
        self.break_start = time(*start)
        self.break_end = time(*end)


class MockSchedule:
    def __init__(self):
        from datetime import time
        self.timezone = "UTC"
        self.work_days = "[1,2,3,4,5]"
        self.work_start = time(9, 0)
        self.work_end = time(18, 0)
        self.breaks = [MockBreak((12, 0), (13, 0))]


class MockClassifier(TimeClassifier):
    def __init__(self):
        super().__init__(db=None)
        self._schedule = MockSchedule()
        self._loaded_at = float('inf')

    def _load(self):
        pass  # already loaded


def test_work_time():
    clf = MockClassifier()
    dt = datetime(2025, 6, 2, 10, 30)  # Monday 10:30 UTC
    assert clf.classify(dt) == "work"


def test_break_time():
    clf = MockClassifier()
    dt = datetime(2025, 6, 2, 12, 15)  # Monday 12:15 UTC — lunch
    assert clf.classify(dt) == "break"


def test_outside_after_hours():
    clf = MockClassifier()
    dt = datetime(2025, 6, 2, 20, 0)  # Monday 20:00 UTC — after work
    assert clf.classify(dt) == "outside"


def test_outside_weekend():
    clf = MockClassifier()
    dt = datetime(2025, 6, 7, 10, 0)  # Saturday 10:00 UTC
    assert clf.classify(dt) == "outside"


def test_work_start_boundary():
    clf = MockClassifier()
    dt = datetime(2025, 6, 2, 9, 0)  # Monday 09:00 — exactly work start
    assert clf.classify(dt) == "work"


def test_before_work():
    clf = MockClassifier()
    dt = datetime(2025, 6, 2, 8, 59)  # Monday 08:59 — just before work
    assert clf.classify(dt) == "outside"
