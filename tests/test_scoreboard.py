import json
import os
from pathlib import Path

from mpu.scoreboard import Scoreboard


def test_empty_qualifies(tmp_path: Path):
    sb = Scoreboard(str(tmp_path / "s.json"))
    assert sb.qualifies(1)
    assert not sb.qualifies(0)


def test_insert_and_ordering(tmp_path: Path):
    sb = Scoreboard(str(tmp_path / "s.json"), max_entries=3)
    sb.insert("A", 10)
    sb.insert("B", 20)
    sb.insert("C", 15)
    assert [(e.nickname, e.score) for e in sb.top()] == [("B", 20), ("C", 15), ("A", 10)]


def test_tie_breaker_existing_above(tmp_path: Path):
    sb = Scoreboard(str(tmp_path / "s.json"))
    sb.insert("FIRST", 10)
    sb.insert("SECOND", 10)
    assert sb.entries[0].nickname == "FIRST"
    assert sb.entries[1].nickname == "SECOND"


def test_max_entries_truncation(tmp_path: Path):
    sb = Scoreboard(str(tmp_path / "s.json"), max_entries=2)
    sb.insert("A", 1)
    sb.insert("B", 2)
    sb.insert("C", 3)
    assert len(sb.entries) == 2
    assert [e.nickname for e in sb.entries] == ["C", "B"]


def test_qualifies_when_below_max(tmp_path: Path):
    sb = Scoreboard(str(tmp_path / "s.json"), max_entries=10)
    sb.insert("X", 100)
    assert sb.qualifies(1)


def test_qualifies_when_full(tmp_path: Path):
    sb = Scoreboard(str(tmp_path / "s.json"), max_entries=2)
    sb.insert("A", 10)
    sb.insert("B", 5)
    assert not sb.qualifies(4)
    assert sb.qualifies(6)


def test_atomic_persistence(tmp_path: Path):
    path = tmp_path / "s.json"
    sb = Scoreboard(str(path))
    sb.insert("HELLO", 7)

    sb2 = Scoreboard(str(path))
    assert len(sb2.entries) == 1
    assert sb2.entries[0].nickname == "HELLO"

    with open(path) as f:
        data = json.load(f)
    assert "version" in data and "scores" in data
    assert "rank" not in data["scores"][0]


def test_corrupted_recovers_from_backup(tmp_path: Path):
    path = tmp_path / "s.json"
    sb = Scoreboard(str(path))
    sb.insert("OK", 5)
    sb.insert("OK2", 6)  # second save creates .bak from the first
    with open(path, "w") as f:
        f.write("not json{")
    sb2 = Scoreboard(str(path))
    assert sb2.entries and sb2.entries[0].nickname == "OK"


def test_nickname_normalization(tmp_path: Path):
    sb = Scoreboard(str(tmp_path / "s.json"))
    sb.insert("toolongnickname12345", 1)
    assert sb.entries[0].nickname == "TOOLONGNIC"
    sb.insert("  ", 2)
    assert sb.entries[0].nickname == "ANONYMOUS"
