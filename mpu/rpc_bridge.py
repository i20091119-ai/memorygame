"""RPC bridge to STM32 MCU.

Wire protocol (newline-delimited ASCII over Serial @ 115200 baud):

  MPU -> MCU
    LIGHT <color> <ms>           single LED pulse
    PLAY <colors> <on_ms> <off_ms>   sequence playback (colors: RBYG chars)
    ALL <ON|OFF>
    ATTRACT <ON|OFF>
    ARM <colors> <timeout_ms>    enable rejection blink for inactive colors
    DISARM
    SELFTEST
    VERSION

  MCU -> MPU
    BTN <color> <ts_ms>          button pressed event (always emitted)
    REL <color> <ts_ms>          button released event (always emitted)
    SEQDONE                      sequence playback complete
    OK
    ERR <message>
    VER <major>.<minor>.<patch>
    SELFTEST <OK|ERR> [details]

Color codes: R B Y G  (RED BLUE YELLOW GREEN)
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, List, Optional

CHAR_TO_COLOR = {"R": "RED", "B": "BLUE", "Y": "YELLOW", "G": "GREEN"}
COLOR_TO_CHAR = {v: k for k, v in CHAR_TO_COLOR.items()}


class RPCError(Exception):
    pass


class RPCBridge:
    def __init__(self, port: str, baud: int, logger=None):
        self.port = port
        self.baud = baud
        self.logger = logger
        self._ser = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ack_q: "queue.Queue[str]" = queue.Queue()
        self._button_cb: Optional[Callable[[str, int], None]] = None
        self._release_cb: Optional[Callable[[str, int], None]] = None
        self._seqdone_cb: Optional[Callable[[], None]] = None
        self._connected = False

    def connect(self) -> None:
        import serial  # type: ignore

        self._ser = serial.Serial(self.port, self.baud, timeout=0.1)
        time.sleep(2.0)
        self._stop.clear()
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()
        self._connected = True

    def close(self) -> None:
        self._stop.set()
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def on_button(self, cb: Callable[[str, int], None]) -> None:
        self._button_cb = cb

    def on_button_release(self, cb: Callable[[str, int], None]) -> None:
        self._release_cb = cb

    def on_sequence_done(self, cb: Callable[[], None]) -> None:
        self._seqdone_cb = cb

    def _write(self, line: str) -> None:
        if self._ser is None:
            raise RPCError("not connected")
        self._ser.write((line + "\n").encode("ascii"))

    def _command(self, line: str, timeout: float = 1.0) -> str:
        while not self._ack_q.empty():
            try:
                self._ack_q.get_nowait()
            except queue.Empty:
                break
        self._write(line)
        try:
            return self._ack_q.get(timeout=timeout)
        except queue.Empty:
            raise RPCError(f"ack timeout: {line}")

    def _rx_loop(self) -> None:
        buf = b""
        while not self._stop.is_set():
            try:
                data = self._ser.read(64) if self._ser else b""
            except Exception as e:
                if self.logger:
                    self.logger.warning("rpc_read_error err=%s", e)
                self._connected = False
                return
            if not data:
                continue
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._dispatch(line.decode("ascii", errors="replace").strip())

    def _dispatch(self, line: str) -> None:
        if not line:
            return
        parts = line.split()
        tag = parts[0]
        if tag in ("BTN", "REL") and len(parts) >= 3:
            color = CHAR_TO_COLOR.get(parts[1].upper())
            try:
                ts = int(parts[2])
            except ValueError:
                return
            if not color:
                return
            cb = self._button_cb if tag == "BTN" else self._release_cb
            if cb:
                cb(color, ts)
        elif tag == "SEQDONE":
            if self._seqdone_cb:
                self._seqdone_cb()
        else:
            self._ack_q.put(line)

    def light_button(self, color: str, duration_ms: int) -> None:
        c = COLOR_TO_CHAR[color]
        self._command(f"LIGHT {c} {int(duration_ms)}")

    def play_sequence(self, colors: List[str], on_ms: int, off_ms: int) -> None:
        s = "".join(COLOR_TO_CHAR[c] for c in colors)
        self._command(f"PLAY {s} {int(on_ms)} {int(off_ms)}")

    def set_all_leds(self, on: bool) -> None:
        self._command(f"ALL {'ON' if on else 'OFF'}")

    def attract_mode_leds(self, enable: bool) -> None:
        self._command(f"ATTRACT {'ON' if enable else 'OFF'}")

    def arm_input(self, active_colors: List[str], timeout_ms: int) -> None:
        s = "".join(COLOR_TO_CHAR[c] for c in active_colors)
        self._command(f"ARM {s} {int(timeout_ms)}")

    def disarm_input(self) -> None:
        self._command("DISARM")

    def selftest(self) -> str:
        return self._command("SELFTEST", timeout=5.0)

    def get_firmware_version(self) -> str:
        resp = self._command("VERSION")
        parts = resp.split()
        if len(parts) >= 2 and parts[0] == "VER":
            return parts[1]
        raise RPCError(f"bad version response: {resp}")


class SimulatedBridge:
    """Standalone simulator used when no MCU is present.

    Triggers `on_button` from keyboard input handled in the UI layer; this class
    just acknowledges commands and emits SEQDONE on a timer.
    """

    def __init__(self, logger=None):
        self.logger = logger
        self._button_cb: Optional[Callable[[str, int], None]] = None
        self._release_cb: Optional[Callable[[str, int], None]] = None
        self._seqdone_cb: Optional[Callable[[], None]] = None
        self._seqdone_at: Optional[float] = None
        self._connected = True

    def connect(self) -> None:
        if self.logger:
            self.logger.info("rpc_simulation_mode")

    def close(self) -> None:
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def on_button(self, cb):
        self._button_cb = cb

    def on_button_release(self, cb):
        self._release_cb = cb

    def on_sequence_done(self, cb):
        self._seqdone_cb = cb

    def emit_button(self, color: str) -> None:
        if self._button_cb:
            self._button_cb(color, int(time.monotonic() * 1000))

    def emit_button_release(self, color: str) -> None:
        if self._release_cb:
            self._release_cb(color, int(time.monotonic() * 1000))

    def tick(self) -> None:
        if self._seqdone_at is not None and time.monotonic() >= self._seqdone_at:
            self._seqdone_at = None
            if self._seqdone_cb:
                self._seqdone_cb()

    def light_button(self, color, duration_ms): pass
    def set_all_leds(self, on): pass
    def attract_mode_leds(self, enable): pass
    def arm_input(self, active_colors, timeout_ms): pass
    def disarm_input(self): pass
    def selftest(self): return "SELFTEST OK"
    def get_firmware_version(self): return "1.0.0-sim"

    def play_sequence(self, colors, on_ms, off_ms):
        total = (on_ms + off_ms) * len(colors) / 1000.0
        self._seqdone_at = time.monotonic() + total


def make_bridge(cfg, logger=None):
    if cfg.rpc.simulation_mode:
        return SimulatedBridge(logger=logger)
    try:
        bridge = RPCBridge(cfg.rpc.serial_port, cfg.rpc.baud_rate, logger=logger)
        bridge.connect()
        return bridge
    except Exception as e:
        if logger:
            logger.warning("rpc_connect_failed_fallback_sim err=%s", e)
        return SimulatedBridge(logger=logger)
