import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from .config import COLORS, AppConfig

APP_VERSION = "1.2.0"

SUBMODE_MAIN = "MAIN"
SUBMODE_CONFIRM = "CONFIRM"
SUBMODE_TIME_SET = "TIME_SET"
SUBMODE_DONE = "DONE"  # post-action status (e.g., reset complete)


@dataclass
class ConfirmRequest:
    action: str        # "RESET" | "SHUTDOWN" | "REBOOT"
    prompt: str
    on_confirm: Callable[[], str]


@dataclass
class TimeFields:
    year: int
    month: int
    day: int
    hour: int
    minute: int
    cursor: int = 0  # 0..4

    @classmethod
    def from_now(cls) -> "TimeFields":
        n = datetime.now()
        return cls(n.year, n.month, n.day, n.hour, n.minute)

    def values(self) -> List[int]:
        return [self.year, self.month, self.day, self.hour, self.minute]

    def adjust(self, idx: int, delta: int) -> None:
        bounds = [(2025, 2099), (1, 12), (1, 31), (0, 23), (0, 59)]
        v = self.values()
        lo, hi = bounds[idx]
        v[idx] = max(lo, min(hi, v[idx] + delta))
        self.year, self.month, self.day, self.hour, self.minute = v

    def to_iso(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d} {self.hour:02d}:{self.minute:02d}:00"


class SelfTest:
    """Operator self-diagnostic controller (SRS 4.9)."""

    def __init__(self, cfg: AppConfig, bridge, scoreboard, logger):
        self.cfg = cfg
        self.bridge = bridge
        self.scoreboard = scoreboard
        self.logger = logger
        self.submode: str = SUBMODE_MAIN
        self.entered_at: float = 0.0
        self.button_counts: Dict[str, int] = {c: 0 for c in COLORS}
        self.last_press_ts: Dict[str, float] = {c: 0.0 for c in COLORS}
        self.led_sweep_idx: int = 0
        self.led_sweep_at: float = 0.0
        self.mcu_fw_version: str = "unknown"
        self.confirm: Optional[ConfirmRequest] = None
        self.status_message: str = ""
        self.status_until: float = 0.0
        self.time_fields: TimeFields = TimeFields.from_now()
        self.exit_callback: Optional[Callable[[], None]] = None

    def enter(self, exit_cb: Callable[[], None]) -> None:
        self.exit_callback = exit_cb
        self.entered_at = time.monotonic()
        self.submode = SUBMODE_MAIN
        self.button_counts = {c: 0 for c in COLORS}
        self.last_press_ts = {c: 0.0 for c in COLORS}
        self.led_sweep_idx = 0
        self.led_sweep_at = self.entered_at
        self.confirm = None
        self.status_message = ""
        self.time_fields = TimeFields.from_now()
        try:
            self.bridge.attract_mode_leds(False)
            self.bridge.set_all_leds(False)
            self.bridge.disarm_input()
        except Exception:
            pass
        try:
            self.mcu_fw_version = self.bridge.get_firmware_version()
        except Exception:
            self.mcu_fw_version = "unknown"
        self.logger.info("selftest_enter mcu_fw=%s", self.mcu_fw_version)

    def exit(self) -> None:
        self.logger.info("selftest_exit")
        if self.exit_callback:
            self.exit_callback()

    def on_button(self, color: str) -> None:
        if color not in self.button_counts:
            return
        self.button_counts[color] += 1
        self.last_press_ts[color] = time.monotonic()
        try:
            self.bridge.light_button(color, 200)
        except Exception:
            pass

    def tick(self) -> None:
        now = time.monotonic()
        if now - self.led_sweep_at > 0.6:
            color = COLORS[self.led_sweep_idx]
            try:
                self.bridge.light_button(color, 400)
            except Exception:
                pass
            self.led_sweep_idx = (self.led_sweep_idx + 1) % 4
            self.led_sweep_at = now
        if self.status_until and now > self.status_until:
            self.status_message = ""
            self.status_until = 0.0

    # ------------------------------------------------------------------ actions

    def request_reset(self) -> None:
        self.confirm = ConfirmRequest(
            action="RESET",
            prompt="스코어보드를 초기화합니다. 확인하시겠습니까?",
            on_confirm=self._do_reset,
        )
        self.submode = SUBMODE_CONFIRM

    def request_shutdown(self) -> None:
        self.confirm = ConfirmRequest(
            action="SHUTDOWN",
            prompt="시스템을 종료합니다. 확인하시겠습니까?",
            on_confirm=self._do_shutdown,
        )
        self.submode = SUBMODE_CONFIRM

    def request_reboot(self) -> None:
        self.confirm = ConfirmRequest(
            action="REBOOT",
            prompt="시스템을 재부팅합니다. 확인하시겠습니까?",
            on_confirm=self._do_reboot,
        )
        self.submode = SUBMODE_CONFIRM

    def request_time_set(self) -> None:
        self.time_fields = TimeFields.from_now()
        self.submode = SUBMODE_TIME_SET

    def confirm_yes(self) -> None:
        if not self.confirm:
            return
        msg = self.confirm.on_confirm()
        self.confirm = None
        self.submode = SUBMODE_MAIN
        self._flash_status(msg)

    def confirm_no(self) -> None:
        self.confirm = None
        self.submode = SUBMODE_MAIN

    def apply_time(self) -> None:
        iso = self.time_fields.to_iso()
        msg = self._run_root_cmd(["date", "-s", iso], success="시각 설정 완료")
        self.submode = SUBMODE_MAIN
        self._flash_status(f"{msg} ({iso})")

    def cancel_time(self) -> None:
        self.submode = SUBMODE_MAIN

    def _do_reset(self) -> str:
        try:
            self.scoreboard.reset()
            self.logger.info("scoreboard_reset_via_selftest")
            return "스코어보드 초기화 완료"
        except OSError as e:
            self.logger.error("scoreboard_reset_failed err=%s", e)
            return f"초기화 실패: {e}"

    def _do_shutdown(self) -> str:
        return self._run_root_cmd(
            ["shutdown", "-h", "now"], success="시스템 종료 명령 실행"
        )

    def _do_reboot(self) -> str:
        return self._run_root_cmd(["reboot"], success="재부팅 명령 실행")

    def _run_root_cmd(self, argv: List[str], success: str) -> str:
        try:
            subprocess.Popen(
                ["sudo", "-n"] + argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.logger.info("root_cmd_dispatched cmd=%s", " ".join(argv))
            return success
        except FileNotFoundError:
            self.logger.warning("root_cmd_failed cmd=%s err=no_sudo", " ".join(argv))
            return "권한 없음 (dev 환경)"
        except Exception as e:
            self.logger.error("root_cmd_failed cmd=%s err=%s", " ".join(argv), e)
            return f"실행 실패: {e}"

    def _flash_status(self, msg: str, seconds: float = 4.0) -> None:
        self.status_message = msg
        self.status_until = time.monotonic() + seconds
