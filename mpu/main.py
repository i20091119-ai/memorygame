import argparse
import sys

from .config import default_config_path, load_config
from .game import Game
from .logger import setup_logging
from .rpc_bridge import make_bridge
from .scoreboard import Scoreboard
from .ui import UI


def main() -> int:
    parser = argparse.ArgumentParser(description="GNMC Memory TalkTalk")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--sim", action="store_true", help="force simulation mode")
    parser.add_argument("--windowed", action="store_true", help="run in windowed mode")
    args = parser.parse_args()

    cfg_path = args.config or default_config_path()
    cfg = load_config(cfg_path)
    if args.sim:
        cfg.rpc.simulation_mode = True
    if args.windowed:
        cfg.ui.fullscreen = False

    logger = setup_logging(cfg)
    logger.info("config_loaded path=%s", cfg_path)

    bridge = make_bridge(cfg, logger=logger)
    if not getattr(bridge, "_connected", True) and not cfg.rpc.simulation_mode:
        logger.error("mcu_unreachable")

    try:
        ver = bridge.get_firmware_version()
        logger.info("mcu_firmware version=%s", ver)
        major = int(ver.split(".")[0]) if ver and ver[0].isdigit() else 0
        if major and major < cfg.rpc.mcu_min_fw_major:
            logger.error("mcu_firmware_too_old version=%s", ver)
    except Exception as e:
        logger.warning("mcu_version_check_failed err=%s", e)

    scoreboard = Scoreboard(cfg.scoreboard_path, cfg.scoreboard_max_entries, logger=logger)
    game = Game(cfg, bridge, scoreboard, logger)
    ui = UI(cfg, game, logger)

    try:
        ui.run()
    finally:
        bridge.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
