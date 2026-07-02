import json
import os
import uuid
from datetime import datetime, timezone


class FeedbackStore:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "feedback.json")
        if not os.path.exists(self.path):
            self._write([])

    def _read(self) -> list:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: list) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add(self, entry: dict) -> str:
        data = self._read()
        fb_id = str(uuid.uuid4())[:8]
        entry.update({"id": fb_id, "created_at": datetime.now(timezone.utc).isoformat()})
        data.append(entry)
        self._write(data)
        return fb_id

    def get_all(self) -> list:
        return self._read()
