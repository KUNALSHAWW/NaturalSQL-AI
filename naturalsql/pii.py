"""Mask sensitive columns in query results (column-name based, configurable)."""
from __future__ import annotations

import re

from .config import DEFAULT_MASK_PATTERNS


class Masker:
    def __init__(self, patterns: tuple[str, ...] = DEFAULT_MASK_PATTERNS):
        self._re = re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE) if patterns else None

    def is_sensitive(self, column: str) -> bool:
        return bool(self._re and self._re.search(column))

    @staticmethod
    def _mask(value, column: str):
        if value is None:
            return None
        s = str(value)
        if "@" in s:                                  # email: keep first character and the domain
            user, _, domain = s.partition("@")
            return f"{user[:1]}***@{domain}"
        digits = re.sub(r"\D", "", s)
        if len(digits) >= 6:                           # phone, card, id numbers: keep the last two digits
            return "*" * (len(s) - 2) + s[-2:]
        return "***"

    def apply(self, columns: list[str], rows: list[tuple]) -> tuple[list[tuple], list[str]]:
        idx = [i for i, c in enumerate(columns) if self.is_sensitive(c)]
        if not idx:
            return rows, []
        out = []
        for r in rows:
            r = list(r)
            for i in idx:
                r[i] = self._mask(r[i], columns[i])
            out.append(tuple(r))
        return out, [columns[i] for i in idx]
