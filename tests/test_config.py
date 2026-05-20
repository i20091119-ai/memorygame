from pathlib import Path

from mpu.config import COLORS, load_config


def test_loads_default_config():
    cfg = load_config(str(Path(__file__).resolve().parent.parent / "config" / "config.yaml"))
    assert cfg.game.max_level == 20
    assert cfg.game.per_button_timeout_ms == 10000
    assert cfg.sequence_length_for_level(1) == 2
    assert cfg.sequence_length_for_level(20) == 21


def test_level_color_activation():
    cfg = load_config(str(Path(__file__).resolve().parent.parent / "config" / "config.yaml"))
    assert cfg.active_colors_for_level(1) == ["RED", "BLUE"]
    assert cfg.active_colors_for_level(2) == ["RED", "BLUE", "YELLOW"]
    assert cfg.active_colors_for_level(3) == COLORS
    assert cfg.active_colors_for_level(20) == COLORS
