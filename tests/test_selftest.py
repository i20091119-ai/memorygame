import logging
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mpu.config import load_config
from mpu.game import SELFTEST_HOLD_SEC, Game, State
from mpu.scoreboard import Scoreboard
from mpu.selftest import (
    SUBMODE_CONFIRM,
    SUBMODE_MAIN,
    SUBMODE_TIME_SET,
    TimeFields,
)


@pytest.fixture
def cfg():
    return load_config(str(Path(__file__).resolve().parent.parent / "config" / "config.yaml"))


@pytest.fixture
def game(cfg, tmp_path):
    bridge = MagicMock()
    bridge.tick = MagicMock()
    bridge.get_firmware_version = MagicMock(return_value="1.0.0")
    sb = Scoreboard(str(tmp_path / "s.json"))
    logger = logging.getLogger("test")
    g = Game(cfg, bridge, sb, logger)
    g.start()
    return g


def test_combo_hold_enters_selftest(game, monkeypatch):
    t0 = time.monotonic()
    game._on_button("RED", 0)
    game._on_button("GREEN", 0)
    assert game.combo_hold_started_at is not None
    # Simulate 5 seconds later
    game.combo_hold_started_at = t0 - (SELFTEST_HOLD_SEC + 0.1)
    game.tick()
    assert game.state == State.SELFTEST


def test_partial_combo_does_not_enter(game):
    game._on_button("RED", 0)
    game._on_button("BLUE", 0)  # wrong combo
    game.tick()
    assert game.state == State.ATTRACT
    assert game.combo_hold_started_at is None
    # Releasing all buttons starts a normal game
    game._on_button_release("RED", 0)
    game._on_button_release("BLUE", 0)
    assert game.state == State.READY


def test_release_clears_combo(game):
    game._on_button("RED", 0)
    game._on_button("GREEN", 0)
    assert game.combo_hold_started_at is not None
    game._on_button_release("RED", 0)
    assert game.combo_hold_started_at is None


def test_selftest_button_counts(game):
    game.trigger_selftest()
    assert game.state == State.SELFTEST
    game._on_button("RED", 0)
    game._on_button("BLUE", 0)
    game._on_button("RED", 0)
    st = game.selftest
    assert st.button_counts["RED"] == 2
    assert st.button_counts["BLUE"] == 1
    assert st.button_counts["YELLOW"] == 0


def test_selftest_reset_scoreboard(game, tmp_path):
    game.scoreboard.insert("HIGH", 18)
    assert game.scoreboard.entries
    game.trigger_selftest()
    game.selftest.request_reset()
    assert game.selftest.submode == SUBMODE_CONFIRM
    game.selftest.confirm_yes()
    assert game.selftest.submode == SUBMODE_MAIN
    assert game.scoreboard.entries == []


def test_selftest_exit_returns_to_attract(game):
    game.trigger_selftest()
    game.selftest.exit()
    assert game.state == State.ATTRACT


def test_confirm_no_cancels(game):
    game.trigger_selftest()
    game.scoreboard.insert("X", 5)
    game.selftest.request_reset()
    game.selftest.confirm_no()
    assert game.selftest.submode == SUBMODE_MAIN
    assert game.scoreboard.entries  # unchanged


def test_time_fields_bounds():
    tf = TimeFields(2026, 5, 20, 14, 30)
    tf.adjust(1, -10)  # month
    assert tf.month == 1
    tf.adjust(1, +50)
    assert tf.month == 12
    tf.adjust(3, -25)  # hour
    assert tf.hour == 0
    tf.adjust(3, +100)
    assert tf.hour == 23


def test_time_iso_format():
    tf = TimeFields(2026, 5, 20, 9, 5)
    assert tf.to_iso() == "2026-05-20 09:05:00"


def test_time_set_flow(game):
    game.trigger_selftest()
    game.selftest.request_time_set()
    assert game.selftest.submode == SUBMODE_TIME_SET
    game.selftest.cancel_time()
    assert game.selftest.submode == SUBMODE_MAIN


def test_shutdown_request_creates_confirm(game):
    game.trigger_selftest()
    game.selftest.request_shutdown()
    assert game.selftest.submode == SUBMODE_CONFIRM
    assert game.selftest.confirm.action == "SHUTDOWN"


def test_reboot_request_creates_confirm(game):
    game.trigger_selftest()
    game.selftest.request_reboot()
    assert game.selftest.submode == SUBMODE_CONFIRM
    assert game.selftest.confirm.action == "REBOOT"
