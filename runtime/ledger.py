"""CSV 台账：追加写与已完成查询。"""

from __future__ import annotations

import csv
import threading
from datetime import datetime
from pathlib import Path

FIELDS = ["run_id", "idx", "external_no", "stage", "status", "error", "updated_at"]


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def read_done(self, run_id: str) -> set[int]:
        done: set[int] = set()
        if not self.path.exists():
            return done
        with self.path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("run_id") != run_id or row.get("status") != "done":
                    continue
                try:
                    done.add(int(row["idx"]))
                except (KeyError, TypeError, ValueError):
                    continue
        return done

    def append(self, row: dict) -> None:
        record = {field: row.get(field, "") for field in FIELDS}
        record["updated_at"] = record["updated_at"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            new_file = not self.path.exists()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDS)
                if new_file:
                    writer.writeheader()
                writer.writerow(record)
