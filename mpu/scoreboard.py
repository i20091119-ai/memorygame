import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

SCHEMA_VERSION = "1.2"


@dataclass
class ScoreEntry:
    nickname: str
    score: int
    date: str

    def to_dict(self) -> dict:
        return {"nickname": self.nickname, "score": self.score, "date": self.date}

    @classmethod
    def from_dict(cls, d: dict) -> "ScoreEntry":
        return cls(nickname=d["nickname"], score=int(d["score"]), date=d["date"])


class Scoreboard:
    def __init__(self, path: str, max_entries: int = 10, logger=None):
        self.path = path
        self.max_entries = max_entries
        self.logger = logger
        self.entries: List[ScoreEntry] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self.entries = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.entries = [ScoreEntry.from_dict(e) for e in data.get("scores", [])]
        except (json.JSONDecodeError, KeyError, OSError) as e:
            if self.logger:
                self.logger.warning("scoreboard_load_failed err=%s", e)
            self._try_recover_backup()

    def _try_recover_backup(self) -> None:
        bak = self.path + ".bak"
        if os.path.exists(bak):
            try:
                with open(bak, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.entries = [ScoreEntry.from_dict(e) for e in data.get("scores", [])]
                if self.logger:
                    self.logger.info("scoreboard_recovered_from_backup")
                return
            except (json.JSONDecodeError, OSError):
                pass
        self.entries = []

    def _save(self) -> None:
        payload = {
            "version": SCHEMA_VERSION,
            "last_updated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "scores": [e.to_dict() for e in self.entries],
        }
        target = Path(self.path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            try:
                shutil.copy2(target, str(target) + ".bak")
            except OSError:
                pass

        fd, tmp_path = tempfile.mkstemp(
            prefix=target.name + ".",
            suffix=".tmp",
            dir=str(target.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def qualifies(self, score: int) -> bool:
        if score <= 0:
            return False
        if len(self.entries) < self.max_entries:
            return True
        return score > self.entries[-1].score

    def insert(self, nickname: str, score: int) -> int:
        nickname = (nickname or "ANONYMOUS").strip().upper()[:10] or "ANONYMOUS"
        entry = ScoreEntry(
            nickname=nickname,
            score=score,
            date=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        )

        insert_idx = len(self.entries)
        for i, e in enumerate(self.entries):
            if entry.score > e.score:
                insert_idx = i
                break
        self.entries.insert(insert_idx, entry)
        del self.entries[self.max_entries :]
        self._save()
        return insert_idx + 1

    def top(self, n: Optional[int] = None) -> List[ScoreEntry]:
        if n is None:
            return list(self.entries)
        return self.entries[:n]

    def best(self) -> Optional[ScoreEntry]:
        return self.entries[0] if self.entries else None

    def reset(self) -> None:
        if os.path.exists(self.path):
            try:
                shutil.copy2(self.path, self.path + ".reset.bak")
            except OSError:
                pass
        self.entries = []
        self._save()
