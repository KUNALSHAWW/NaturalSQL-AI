"""Verified-query memory: the system gets better the more it is used.

When a person confirms an answer (thumbs up), the question and its SQL are stored. For later
questions the most similar verified examples are retrieved and shown to the model as
few-shot examples. Retrieval uses TF-IDF cosine similarity, so it needs no embedding model.
"""
from __future__ import annotations

import math
import sqlite3
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .schema import tokens


@dataclass
class Example:
    id: int
    question: str
    sql: str
    similarity: float = 0.0


class QueryMemory:
    def __init__(self, path: str | Path = "naturalsql_memory.db"):
        self.path = str(path)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS examples (id INTEGER PRIMARY KEY, db_key TEXT, question TEXT, sql TEXT, "
                "created REAL, uses INTEGER DEFAULT 0, UNIQUE(db_key, question))"
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, check_same_thread=False)

    def add(self, question: str, sql: str, db_key: str = "default") -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO examples (db_key, question, sql, created) VALUES (?,?,?,?) "
                "ON CONFLICT(db_key, question) DO UPDATE SET sql=excluded.sql, created=excluded.created",
                (db_key, question.strip(), sql.strip(), time.time()),
            )

    def all(self, db_key: str = "default") -> list[Example]:
        with self._conn() as c:
            rows = c.execute("SELECT id, question, sql FROM examples WHERE db_key=?", (db_key,)).fetchall()
        return [Example(*r) for r in rows]

    def count(self, db_key: str = "default") -> int:
        return len(self.all(db_key))

    def retrieve(self, question: str, k: int = 3, min_similarity: float = 0.35, db_key: str = "default") -> list[Example]:
        examples = self.all(db_key)
        if not examples:
            return []
        docs = [Counter(tokens(e.question)) for e in examples]
        q = Counter(tokens(question))
        n = len(docs) + 1
        df: Counter = Counter()
        for d in docs + [q]:
            df.update(set(d))
        idf = {t: math.log(1 + n / (1 + c)) for t, c in df.items()}

        def vec(c: Counter) -> dict[str, float]:
            return {t: v * idf[t] for t, v in c.items()}

        def cos(a: dict, b: dict) -> float:
            num = sum(a[t] * b.get(t, 0.0) for t in a)
            den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
            return num / den if den else 0.0

        qv = vec(q)
        scored = [(cos(qv, vec(d)), e) for d, e in zip(docs, examples)]
        scored = [(s, e) for s, e in scored if s >= min_similarity]
        scored.sort(key=lambda t: -t[0])
        out = []
        for s, e in scored[:k]:
            out.append(Example(e.id, e.question, e.sql, s))
        return out
