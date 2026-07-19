"""
Domain categorizer using a layered lookup:
1. Exact domain match
2. Suffix match (domain ends with pattern)
3. Default: None (uncategorized)

Category data is loaded from the DB and cached with a TTL.
Also used standalone (from config/categories.json) during DB seeding.
"""
import re
import time
from typing import Optional, Dict, List

# Category rule patterns are admin-supplied, so an arbitrary regex could trigger
# catastrophic backtracking (ReDoS) and hang the categorizer — which runs on the
# hot path for every proxied request. We reject patterns that apply a quantifier
# to a group that already contains one (the classic "(a+)+" signature) and cap
# the length of both the pattern and the string we run it against.
MAX_PATTERN_LENGTH = 255
MAX_REGEX_INPUT = 255
_UNSAFE_REGEX = re.compile(r"\([^()]*[*+{][^()]*\)\s*[*+{]")


def is_safe_regex(pattern: str) -> bool:
    """Best-effort screen for catastrophic-backtracking regexes (no timeout lib
    available). Rejects nested quantifiers and over-long patterns."""
    if len(pattern) > MAX_PATTERN_LENGTH:
        return False
    return _UNSAFE_REGEX.search(pattern) is None


class Categorizer:
    def __init__(self, db=None, ttl: int = 30):
        self._db = db
        self._ttl = ttl
        self._loaded = False
        self._cache_loaded_at: float = 0.0
        self._exact: Dict[str, dict] = {}
        self._suffix: List[tuple] = []  # (pattern, category_dict)
        self._regex: List[tuple] = []

    def _load(self):
        now = time.monotonic()
        # Reuse the in-memory rule tables until the TTL expires.
        if self._loaded and (now - self._cache_loaded_at) < self._ttl:
            return

        if self._db is not None:
            self._load_from_db()
        else:
            self._load_from_json()
        self._loaded = True
        self._cache_loaded_at = now

    def _load_from_db(self):
        from api import models
        rules = (
            self._db.query(models.CategoryRule, models.Category)
            .join(models.Category)
            .order_by(models.CategoryRule.priority.desc())
            .all()
        )
        self._exact.clear()
        self._suffix.clear()
        self._regex.clear()
        for rule, cat in rules:
            cat_dict = {"id": cat.id, "name": cat.name, "color": cat.color}
            if rule.match_type == "exact":
                # Rules arrive priority-desc; keep the first (highest priority)
                # so a later, lower-priority duplicate can't override it.
                self._exact.setdefault(rule.pattern.lower(), cat_dict)
            elif rule.match_type == "suffix":
                self._suffix.append((rule.pattern.lower(), cat_dict))
            elif rule.match_type == "regex":
                if not is_safe_regex(rule.pattern):
                    continue
                try:
                    self._regex.append((re.compile(rule.pattern, re.I), cat_dict))
                except re.error:
                    pass

    def _load_from_json(self):
        import json, os
        json_path = os.path.join(os.path.dirname(__file__), "../config/categories.json")
        with open(json_path) as f:
            data = json.load(f)

        cat_map = {c["name"]: c for c in data.get("categories", [])}
        self._exact.clear()
        self._suffix.clear()
        self._regex.clear()

        for rule in sorted(data.get("rules", []), key=lambda r: r.get("priority", 0), reverse=True):
            cat_name = rule["category"]
            cat = cat_map.get(cat_name, {"name": cat_name, "color": "#6b7280", "id": None})
            cat_dict = {"id": cat.get("id"), "name": cat["name"], "color": cat.get("color", "#6b7280")}
            mt = rule.get("match_type", "suffix")
            pat = rule["pattern"].lower()
            if mt == "exact":
                self._exact.setdefault(pat, cat_dict)
            elif mt == "suffix":
                self._suffix.append((pat, cat_dict))
            elif mt == "regex":
                if not is_safe_regex(pat):
                    continue
                try:
                    self._regex.append((re.compile(pat, re.I), cat_dict))
                except re.error:
                    pass

    def categorize(self, domain: str) -> Optional[dict]:
        self._load()
        domain = domain.lower().rstrip(".")

        # 1. Exact match
        if domain in self._exact:
            return self._exact[domain]

        # 2. Suffix match — domain ends with ".pattern" or equals pattern
        for pattern, cat in self._suffix:
            if domain == pattern or domain.endswith("." + pattern):
                return cat

        # 3. Regex (bounded input length as defense-in-depth against ReDoS)
        if self._regex and len(domain) <= MAX_REGEX_INPUT:
            for compiled, cat in self._regex:
                if compiled.search(domain):
                    return cat

        return None

    def invalidate(self):
        """Force cache refresh on next call (e.g. after rule update)."""
        self._loaded = False
        self._cache_loaded_at = 0.0
