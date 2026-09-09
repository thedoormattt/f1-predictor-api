"""A tiny in-memory stand-in for the Supabase client, for tests."""

from typing import Any


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store: dict[str, list[dict]], table: str):
        self._store = store
        self._table = table
        self._rows = list(store.get(table, []))
        self._pending: list[dict] | None = None
        self._embed: str | None = None

    def _value(self, row: dict, field: str):
        """Resolve `races.type` style fields through the joined races row."""
        if "." not in field:
            return row.get(field)
        _, col = field.split(".", 1)
        race = next(
            (r for r in self._store.get("races", []) if r["id"] == row.get("race_id")),
            None,
        )
        return race.get(col) if race else None

    # ── read ──────────────────────────────────────────────
    def select(self, cols: str = "*", *_, **__):
        if "!inner(" in cols:
            self._embed = cols
        return self

    def eq(self, field: str, value: Any):
        self._rows = [r for r in self._rows if self._value(r, field) == value]
        return self

    def gte(self, field: str, value: Any):
        self._rows = [r for r in self._rows if str(self._value(r, field)) >= str(value)]
        return self

    def lte(self, field: str, value: Any):
        self._rows = [r for r in self._rows if str(self._value(r, field)) <= str(value)]
        return self

    def lt(self, field: str, value: Any):
        self._rows = [r for r in self._rows if str(self._value(r, field)) < str(value)]
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n: int):
        self._rows = self._rows[:n]
        return self

    def single(self):
        return self

    # ── write ─────────────────────────────────────────────
    def upsert(self, payload, on_conflict: str = "", **__):
        rows = payload if isinstance(payload, list) else [payload]
        keys = [k.strip() for k in on_conflict.split(",") if k.strip()]
        table = self._store.setdefault(self._table, [])
        written = []
        for row in rows:
            match = None
            if keys:
                for existing in table:
                    if all(existing.get(k) == row.get(k) for k in keys):
                        match = existing
                        break
            if match is not None:
                match.update(row)
                written.append(match)
            else:
                new = {"id": len(table) + 1, **row}
                table.append(new)
                written.append(new)
        self._pending = written
        return self

    def insert(self, payload, **__):
        rows = payload if isinstance(payload, list) else [payload]
        table = self._store.setdefault(self._table, [])
        written = []
        for row in rows:
            new = {"id": len(table) + 1, **row}
            table.append(new)
            written.append(new)
        self._pending = written
        return self

    def update(self, payload, **__):
        for row in self._rows:
            row.update(payload)
        self._pending = self._rows
        return self

    def execute(self):
        if self._pending is not None:
            return _Response(self._pending)
        if self._embed:
            # Resolve `predictions.select("*, races!inner(...)")` against races.
            races = {r["id"]: r for r in self._store.get("races", [])}
            out = []
            for row in self._rows:
                race = races.get(row.get("race_id"))
                if race:
                    out.append({**row, "races": race})
            return _Response(out)
        return _Response(self._rows)


class FakeSupabase:
    """Holds tables as plain lists of dicts; queries mimic the supabase-py chain."""

    def __init__(self, **tables: list[dict]):
        self.store: dict[str, list[dict]] = {k: list(v) for k, v in tables.items()}

    def table(self, name: str) -> _Query:
        self.store.setdefault(name, [])
        return _Query(self.store, name)
