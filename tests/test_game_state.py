import logging
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mpu.config import load_config
from mpu.game import Game, State
from mpu.scoreboard import Scoreboard


@pytest.fixture
def cfg():
    c = load_config(str(Path(__file__).resolve().parent.parent / "config" / "config.yaml"))
    c.game.ready_countdown_sec = 0
    c.game.level_clear_duration_ms = 0
    c.game.game_over_display_ms = 0
    return c


@pytest.fixture
def game(cfg, tmp_path):
    bridge = MagicMock()
    bridge.tick = MagicMock()
    sb = Scoreboard(str(tmp_path / "s.json"))
    logger = logging.getLogger("test")
    g = Game(cfg, bridge, sb, logger)
    return g


def _drive_show(game):
    game.tick()
    game.bridge.play_sequence.assert_called()
    game._on_sequence_done()
    game.tick()
    assert game.state == State.USER_INPUT


def test_attract_to_ready_on_button(game):
    game.start()
    assert game.state == State.ATTRACT
    game._on_button("RED", 0)
    assert game.state == State.ATTRACT  # press alone is not enough
    game._on_button_release("RED", 0)
    assert game.state == State.READY


def test_full_level_clear_advances(game):
    game.start()
    game._on_button("RED", 0)
    game._on_button_release("RED", 0)
    game.tick()  # READY -> SHOW_SEQUENCE
    assert game.state == State.SHOW_SEQUENCE
    _drive_show(game)
    seq = list(game.session.sequence)
    for c in seq:
        game._on_button(c, 0)
    assert game.state == State.LEVEL_CLEAR
    game.tick()  # advance to next level SHOW_SEQUENCE
    assert game.state == State.SHOW_SEQUENCE
    assert game.session.current_level == 2
    assert game.session.current_score == 1


def test_wrong_input_triggers_game_over(game):
    game.start()
    game._on_button("RED", 0)
    game._on_button_release("RED", 0)
    game.tick()
    _drive_show(game)
    expected = game.session.sequence[0]
    wrong = next(c for c in ["RED", "BLUE"] if c != expected)
    game._on_button(wrong, 0)
    assert game.state == State.GAME_OVER
    assert game.session.game_over_reason == "wrong"


def test_inactive_color_ignored_in_level_1(game):
    game.start()
    game._on_button("RED", 0)
    game._on_button_release("RED", 0)
    game.tick()
    _drive_show(game)
    # Level 1 -> active = RED, BLUE. YELLOW is inactive: must be a no-op.
    game._on_button("YELLOW", 0)
    assert game.state == State.USER_INPUT
    assert game.session.user_input == []


def test_timeout_triggers_game_over(game, cfg):
    game.start()
    game._on_button("RED", 0)
    game._on_button_release("RED", 0)
    game.tick()
    _drive_show(game)
    game.session.timeout_deadline_ts = time.monotonic() - 1
    game.tick()
    assert game.state == State.GAME_OVER
    assert game.session.game_over_reason == "timeout"


def test_game_over_to_nickname_if_qualifies(game):
    game.start()
    game._on_button("RED", 0)
    game._on_button_release("RED", 0)
    game.tick()
    _drive_show(game)
    for c in list(game.session.sequence):
        game._on_button(c, 0)
    # LEVEL_CLEAR -> tick -> next level. Force a quick wrong input next round.
    game.tick()
    _drive_show(game)
    expected = game.session.sequence[0]
    wrong = next(c for c in game.cfg.active_colors_for_level(2) if c != expected)
    game._on_button(wrong, 0)
    assert game.state == State.GAME_OVER
    game.tick()
    assert game.state == State.NICKNAME_INPUT


def test_nickname_buffer_limits(game):
    game.start()
    game._on_button("RED", 0)
    game._on_button_release("RED", 0)
    game.tick()
    _drive_show(game)
    for c in list(game.session.sequence):
        game._on_button(c, 0)
    game.tick()
    _drive_show(game)
    wrong = next(c for c in game.cfg.active_colors_for_level(2) if c != game.session.sequence[0])
    game._on_button(wrong, 0)
    game.tick()
    assert game.state == State.NICKNAME_INPUT

    for ch in "ABCDEFGHIJKLMNOP":
        game.nickname_key(ch)
    assert len(game.nickname_buffer) == 10

    game.nickname_key("BACK")
    assert len(game.nickname_buffer) == 9

    game.nickname_key("CANCEL")
    assert game.state == State.ATTRACT
