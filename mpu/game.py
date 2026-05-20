import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional

from .config import COLORS, AppConfig
from .sequence_gen import SequenceGenerator


class State(Enum):
    BOOT = auto()
    ERROR = auto()
    ATTRACT = auto()
    READY = auto()
    SHOW_SEQUENCE = auto()
    USER_INPUT = auto()
    LEVEL_CLEAR = auto()
    GAME_OVER = auto()
    NICKNAME_INPUT = auto()
    SELFTEST = auto()


@dataclass
class Session:
    session_id: str
    current_level: int = 1
    current_score: int = 0
    sequence: List[str] = field(default_factory=list)
    user_input: List[str] = field(default_factory=list)
    last_input_ts: float = 0.0
    timeout_deadline_ts: float = 0.0
    game_over_reason: str = ""


class Game:
    def __init__(self, cfg: AppConfig, bridge, scoreboard, logger):
        self.cfg = cfg
        self.bridge = bridge
        self.scoreboard = scoreboard
        self.logger = logger
        self.seq_gen = SequenceGenerator(cfg.game.rng_max_consecutive_same)

        self.state: State = State.BOOT
        self.state_entered_at: float = time.monotonic()
        self.last_user_activity: float = time.monotonic()
        self.session: Optional[Session] = None
        self.pending_show_done: bool = False
        self.nickname_buffer: str = ""
        self.nickname_started_at: float = 0.0
        self.show_idx: int = 0
        self.selftest_result: str = ""
        self.error_message: str = ""

        bridge.on_button(self._on_button)
        bridge.on_sequence_done(self._on_sequence_done)

    def start(self) -> None:
        self.logger.info("app_start ver=1.2.0")
        self._enter_attract()

    def _enter(self, state: State) -> None:
        self.logger.info("state_change to=%s", state.name)
        self.state = state
        self.state_entered_at = time.monotonic()

    def _enter_attract(self) -> None:
        try:
            self.bridge.attract_mode_leds(True)
        except Exception as e:
            self.logger.warning("attract_leds_failed err=%s", e)
        self._enter(State.ATTRACT)
        self.session = None
        self.pending_show_done = False

    def _enter_ready(self) -> None:
        try:
            self.bridge.attract_mode_leds(False)
        except Exception:
            pass
        self.session = Session(session_id=str(uuid.uuid4()))
        self.logger.info("session_start sid=%s", self.session.session_id)
        self._enter(State.READY)

    def _start_level(self, level: int) -> None:
        assert self.session is not None
        self.session.current_level = level
        active = self.cfg.active_colors_for_level(level)
        length = self.cfg.sequence_length_for_level(level)
        self.session.sequence = self.seq_gen.generate(length, active)
        self.session.user_input = []
        self.show_idx = 0
        self.pending_show_done = False
        self.logger.info(
            "level_start sid=%s level=%d seq=%s",
            self.session.session_id, level, ",".join(self.session.sequence),
        )
        self._enter(State.SHOW_SEQUENCE)
        try:
            self.bridge.play_sequence(
                self.session.sequence,
                self.cfg.game.show_on_ms,
                self.cfg.game.show_off_ms,
            )
        except Exception as e:
            self.logger.warning("play_sequence_failed err=%s", e)
            self.pending_show_done = True

    def _enter_user_input(self) -> None:
        assert self.session is not None
        active = self.cfg.active_colors_for_level(self.session.current_level)
        try:
            self.bridge.arm_input(active, self.cfg.game.per_button_timeout_ms)
        except Exception as e:
            self.logger.warning("arm_input_failed err=%s", e)
        now = time.monotonic()
        self.session.last_input_ts = now
        self.session.timeout_deadline_ts = now + self.cfg.game.per_button_timeout_ms / 1000.0
        self._enter(State.USER_INPUT)

    def _enter_level_clear(self) -> None:
        assert self.session is not None
        self.session.current_score = self.session.current_level
        try:
            self.bridge.disarm_input()
        except Exception:
            pass
        self.logger.info(
            "level_clear sid=%s level=%d",
            self.session.session_id, self.session.current_level,
        )
        self._enter(State.LEVEL_CLEAR)

    def _enter_game_over(self, reason: str) -> None:
        assert self.session is not None
        self.session.game_over_reason = reason
        try:
            self.bridge.disarm_input()
        except Exception:
            pass
        self.logger.info(
            "game_over sid=%s score=%d reason=%s",
            self.session.session_id, self.session.current_score, reason,
        )
        self._enter(State.GAME_OVER)

    def _enter_nickname(self) -> None:
        self.nickname_buffer = ""
        self.nickname_started_at = time.monotonic()
        self._enter(State.NICKNAME_INPUT)

    def _commit_score(self, nickname: str) -> None:
        assert self.session is not None
        try:
            rank = self.scoreboard.insert(nickname, self.session.current_score)
            self.logger.info(
                "high_score sid=%s nickname=%s score=%d rank=%d",
                self.session.session_id, nickname or "ANONYMOUS",
                self.session.current_score, rank,
            )
        except OSError as e:
            self.logger.error("scoreboard_save_failed err=%s", e)
        self._enter_attract()

    def _on_button(self, color: str, ts_ms: int) -> None:
        self._note_activity()
        if self.state == State.ATTRACT:
            self._enter_ready()
            return
        if self.state == State.USER_INPUT:
            self._handle_user_input(color)
            return

    def _on_sequence_done(self) -> None:
        if self.state == State.SHOW_SEQUENCE:
            self.pending_show_done = True

    def _handle_user_input(self, color: str) -> None:
        assert self.session is not None
        active = self.cfg.active_colors_for_level(self.session.current_level)
        if color not in active:
            self.logger.debug("input_rejected_inactive color=%s", color)
            return

        idx = len(self.session.user_input)
        expected = self.session.sequence[idx]
        self.session.user_input.append(color)
        rt_ms = int((time.monotonic() - self.session.last_input_ts) * 1000)
        ok = color == expected
        self.logger.debug(
            "input sid=%s level=%d idx=%d pressed=%s expected=%s ok=%s rt_ms=%d",
            self.session.session_id, self.session.current_level,
            idx, color, expected, ok, rt_ms,
        )

        try:
            self.bridge.light_button(color, 200)
        except Exception:
            pass

        if not ok:
            self._enter_game_over("wrong")
            return

        now = time.monotonic()
        self.session.last_input_ts = now
        self.session.timeout_deadline_ts = now + self.cfg.game.per_button_timeout_ms / 1000.0

        if len(self.session.user_input) == len(self.session.sequence):
            if self.session.current_level >= self.cfg.game.max_level:
                self.session.current_score = self.cfg.game.max_level
                self._enter_game_over("cleared")
            else:
                self._enter_level_clear()

    def _note_activity(self) -> None:
        self.last_user_activity = time.monotonic()

    def touch_input_color(self, color: str) -> None:
        """Touch on screen color blocks; mirrored to button event for USER_INPUT only."""
        if self.state == State.USER_INPUT:
            self._on_button(color, int(time.monotonic() * 1000))
        elif self.state == State.ATTRACT:
            self._enter_ready()

    def nickname_key(self, ch: str) -> None:
        if self.state != State.NICKNAME_INPUT:
            return
        self._note_activity()
        self.nickname_started_at = time.monotonic()
        if ch == "BACK":
            self.nickname_buffer = self.nickname_buffer[:-1]
        elif ch == "OK":
            self._commit_score(self.nickname_buffer or "ANONYMOUS")
        elif ch == "CANCEL":
            self._commit_score("ANONYMOUS")
        elif len(ch) == 1 and (ch.isalnum()) and len(self.nickname_buffer) < 10:
            self.nickname_buffer += ch.upper()

    def tick(self) -> None:
        if hasattr(self.bridge, "tick"):
            self.bridge.tick()

        now = time.monotonic()
        elapsed = now - self.state_entered_at

        if self.state == State.READY:
            if elapsed >= self.cfg.game.ready_countdown_sec:
                self._start_level(1)
            return

        if self.state == State.SHOW_SEQUENCE:
            if self.pending_show_done:
                self._enter_user_input()
            return

        if self.state == State.USER_INPUT:
            if now >= self.session.timeout_deadline_ts:
                self._enter_game_over("timeout")
            return

        if self.state == State.LEVEL_CLEAR:
            if elapsed * 1000 >= self.cfg.game.level_clear_duration_ms:
                self._start_level(self.session.current_level + 1)
            return

        if self.state == State.GAME_OVER:
            if elapsed * 1000 >= self.cfg.game.game_over_display_ms:
                if self.session and self.scoreboard.qualifies(self.session.current_score):
                    self._enter_nickname()
                else:
                    self._enter_attract()
            return

        if self.state == State.NICKNAME_INPUT:
            if now - self.nickname_started_at > 30.0:
                self._commit_score("ANONYMOUS")
            return

        if self.state == State.ATTRACT:
            return

    def countdown_remaining_sec(self) -> int:
        if self.state != State.USER_INPUT or self.session is None:
            return 0
        rem = self.session.timeout_deadline_ts - time.monotonic()
        return max(0, int(rem + 0.999))

    def ready_remaining_sec(self) -> int:
        if self.state != State.READY:
            return 0
        rem = self.cfg.game.ready_countdown_sec - (time.monotonic() - self.state_entered_at)
        return max(0, int(rem + 0.999))
