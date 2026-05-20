import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

COLORS = ["RED", "BLUE", "YELLOW", "GREEN"]


@dataclass
class GameConfig:
    max_level: int = 20
    base_sequence_length: int = 2
    per_button_timeout_ms: int = 10000
    show_on_ms: int = 500
    show_off_ms: int = 200
    ready_countdown_sec: int = 3
    level_clear_duration_ms: int = 1500
    game_over_display_ms: int = 3000
    attract_idle_threshold_sec: int = 30
    rng_max_consecutive_same: int = 3


@dataclass
class UIConfig:
    screen_resolution: Tuple[int, int] = (1920, 1080)
    fullscreen: bool = True
    min_font_pt: int = 36
    show_colorblind_shapes: bool = False
    title: str = "경남수학문화관 기억톡톡"
    font_path: str = ""


@dataclass
class RPCConfig:
    serial_port: str = "/dev/ttyACM0"
    baud_rate: int = 115200
    simulation_mode: bool = False
    reconnect_max_attempts: int = 3
    mcu_min_fw_major: int = 1


@dataclass
class AppConfig:
    raw: Dict[str, Any]
    game: GameConfig
    ui: UIConfig
    rpc: RPCConfig
    colors: Dict[str, Dict[str, str]]
    level_color_activation: List[Dict[str, Any]]
    scoreboard_path: str
    scoreboard_max_entries: int
    log_path: str
    log_max_size_mb: int
    log_backup_count: int
    log_level: str
    audio_enabled: bool
    audio_volume_percent: int
    audio_notes: Dict[str, str]

    def active_colors_for_level(self, level: int) -> List[str]:
        last = COLORS[:]
        for row in self.level_color_activation:
            if row["level"] <= level:
                last = list(row["colors"])
        return last

    def sequence_length_for_level(self, level: int) -> int:
        return self.game.base_sequence_length + (level - 1)


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    g = data.get("game", {})
    ui = data.get("ui", {})
    rpc = data.get("rpc", {})
    sb = data.get("scoreboard", {})
    lg = data.get("logging", {})
    au = data.get("audio", {})

    return AppConfig(
        raw=data,
        game=GameConfig(**g),
        ui=UIConfig(
            screen_resolution=tuple(ui.get("screen_resolution", [1920, 1080])),
            fullscreen=ui.get("fullscreen", True),
            min_font_pt=ui.get("min_font_pt", 36),
            show_colorblind_shapes=ui.get("show_colorblind_shapes", False),
            title=ui.get("title", "경남수학문화관 기억톡톡"),
            font_path=ui.get("font_path", ""),
        ),
        rpc=RPCConfig(**rpc),
        colors=data.get("colors", {}),
        level_color_activation=data.get("level_color_activation", []),
        scoreboard_path=sb.get("path", "scoreboard.json"),
        scoreboard_max_entries=sb.get("max_entries", 10),
        log_path=lg.get("path", "game.log"),
        log_max_size_mb=lg.get("max_size_mb", 10),
        log_backup_count=lg.get("backup_count", 3),
        log_level=lg.get("level", "INFO"),
        audio_enabled=au.get("enabled", False),
        audio_volume_percent=au.get("volume_percent", 70),
        audio_notes=au.get("notes", {}),
    )


def default_config_path() -> str:
    env = os.environ.get("MEMORYGAME_CONFIG")
    if env:
        return env
    candidates = [
        "/home/arduino/config.yaml",
        str(Path(__file__).resolve().parent.parent / "config" / "config.yaml"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[-1]
