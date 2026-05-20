import time
from typing import Dict, List, Optional, Tuple

import pygame

from .config import COLORS, AppConfig
from .game import Game, State
from .selftest import (
    APP_VERSION,
    SUBMODE_CONFIRM,
    SUBMODE_MAIN,
    SUBMODE_TIME_SET,
)
from . import virtual_keyboard as vk

COLOR_POSITION = {"RED": 0, "BLUE": 1, "YELLOW": 2, "GREEN": 3}
KEY_TO_COLOR = {
    pygame.K_r: "RED", pygame.K_b: "BLUE",
    pygame.K_y: "YELLOW", pygame.K_g: "GREEN",
    pygame.K_q: "RED", pygame.K_w: "BLUE",
    pygame.K_a: "YELLOW", pygame.K_s: "GREEN",
    pygame.K_LEFT: "YELLOW", pygame.K_UP: "RED",
    pygame.K_RIGHT: "BLUE", pygame.K_DOWN: "GREEN",
}
SHAPES = {"RED": "▲", "BLUE": "●", "YELLOW": "■", "GREEN": "◆"}


def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class UI:
    def __init__(self, cfg: AppConfig, game: Game, logger):
        self.cfg = cfg
        self.game = game
        self.logger = logger
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass

        flags = pygame.FULLSCREEN if cfg.ui.fullscreen else 0
        w, h = cfg.ui.screen_resolution
        self.screen = pygame.display.set_mode((w, h), flags)
        pygame.display.set_caption(cfg.ui.title)
        pygame.mouse.set_visible(False)

        font_path = cfg.ui.font_path or None
        self.font_lg = self._make_font(font_path, 96)
        self.font_md = self._make_font(font_path, 64)
        self.font_sm = self._make_font(font_path, 40)
        self.font_xs = self._make_font(font_path, 32)
        self.font_shape = self._make_font(font_path, 200)

        self.w, self.h = w, h
        self.flash_until: dict[str, float] = {}
        self.keyboard: List[vk.Key] = vk.build_keyboard(w, h)
        self.clock = pygame.time.Clock()
        self.selftest_buttons: Dict[str, pygame.Rect] = {}
        self.time_buttons: Dict[str, pygame.Rect] = {}

    def _make_font(self, path: Optional[str], size: int) -> pygame.font.Font:
        if path:
            try:
                return pygame.font.Font(path, size)
            except (OSError, pygame.error):
                pass
        for name in ["NanumGothic", "Pretendard", "Noto Sans CJK KR", "Noto Sans KR"]:
            try:
                return pygame.font.SysFont(name, size)
            except Exception:
                continue
        return pygame.font.Font(None, size)

    def _color(self, name: str, state: str) -> Tuple[int, int, int]:
        return _hex_to_rgb(self.cfg.colors[name][state])

    def flash(self, color: str, duration_ms: int = 200) -> None:
        self.flash_until[color] = time.monotonic() + duration_ms / 1000.0

    def run(self) -> None:
        self.game.start()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    else:
                        self._handle_keydown(event)
                elif event.type == pygame.KEYUP:
                    self._handle_keyup(event)
                elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                    self._handle_pointer(event)

            self.game.tick()
            self._draw()
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()

    def _handle_keydown(self, event) -> None:
        state = self.game.state
        if state == State.NICKNAME_INPUT:
            if event.key == pygame.K_BACKSPACE:
                self.game.nickname_key("BACK")
            elif event.key == pygame.K_RETURN:
                self.game.nickname_key("OK")
            elif event.key == pygame.K_ESCAPE:
                self.game.nickname_key("CANCEL")
            elif event.unicode and (event.unicode.isalnum()):
                self.game.nickname_key(event.unicode.upper())
            return

        # Dev shortcut: F12 jumps into self-test from ATTRACT.
        if event.key == pygame.K_F12:
            self.game.trigger_selftest()
            return

        color = KEY_TO_COLOR.get(event.key)
        if color and hasattr(self.game.bridge, "emit_button"):
            self.game.bridge.emit_button(color)
            self.flash(color)
        elif color:
            self.game.touch_input_color(color)
            self.flash(color)

    def _handle_keyup(self, event) -> None:
        color = KEY_TO_COLOR.get(event.key)
        if color and hasattr(self.game.bridge, "emit_button_release"):
            self.game.bridge.emit_button_release(color)

    def _handle_pointer(self, event) -> None:
        if event.type == pygame.FINGERDOWN:
            x = int(event.x * self.w)
            y = int(event.y * self.h)
        else:
            x, y = event.pos

        if self.game.state == State.NICKNAME_INPUT:
            now_ms = pygame.time.get_ticks()
            key = vk.hit_test(self.keyboard, x, y, now_ms)
            if key:
                self.game.nickname_key(key.value)
            return

        if self.game.state == State.SELFTEST:
            self._handle_selftest_click(x, y)
            return

        color = self._hit_block(x, y)
        if color:
            self.flash(color)
            if self.game.state == State.USER_INPUT:
                if hasattr(self.game.bridge, "emit_button"):
                    self.game.bridge.emit_button(color)
                else:
                    self.game.touch_input_color(color)
            elif self.game.state == State.ATTRACT:
                self.game.touch_input_color(color)

    def _block_rects(self) -> dict:
        margin_top, margin_bottom = 140, 140
        playable_h = self.h - margin_top - margin_bottom
        block_size = min(self.w // 2 - 80, playable_h // 2 - 40)
        gap = 40
        total_w = 2 * block_size + gap
        total_h = 2 * block_size + gap
        ox = (self.w - total_w) // 2
        oy = margin_top + (playable_h - total_h) // 2
        return {
            "RED": (ox, oy, block_size, block_size),
            "BLUE": (ox + block_size + gap, oy, block_size, block_size),
            "YELLOW": (ox, oy + block_size + gap, block_size, block_size),
            "GREEN": (ox + block_size + gap, oy + block_size + gap, block_size, block_size),
        }

    def _hit_block(self, x: int, y: int) -> Optional[str]:
        for c, (bx, by, bw, bh) in self._block_rects().items():
            if bx <= x < bx + bw and by <= y < by + bh:
                return c
        return None

    def _draw(self) -> None:
        self.screen.fill((10, 10, 14))
        state = self.game.state

        if state == State.ATTRACT:
            self._draw_attract()
        elif state == State.READY:
            self._draw_game(big_overlay=str(self.game.ready_remaining_sec() or "GO!"))
        elif state in (State.SHOW_SEQUENCE, State.USER_INPUT, State.LEVEL_CLEAR):
            overlay = "LEVEL CLEAR!" if state == State.LEVEL_CLEAR else None
            self._draw_game(big_overlay=overlay)
        elif state == State.GAME_OVER:
            self._draw_game(big_overlay="GAME OVER")
        elif state == State.NICKNAME_INPUT:
            self._draw_nickname()
        elif state == State.SELFTEST:
            self._draw_selftest()

        if state == State.ATTRACT:
            self._draw_selftest_hold_hint()

    def _draw_attract(self) -> None:
        self._cycle_attract_flash()
        title = self.font_lg.render(self.cfg.ui.title, True, (240, 240, 240))
        self.screen.blit(title, title.get_rect(center=(self.w // 2, 180)))
        sub = self.font_md.render("아무 버튼이나 누르거나 화면을 터치하세요", True, (200, 200, 200))
        self.screen.blit(sub, sub.get_rect(center=(self.w // 2, 300)))

        blocks = self._block_rects()
        active = self.cfg.active_colors_for_level(1)
        self._draw_blocks(blocks, active)

        y = self.h - 380
        header = self.font_sm.render("TOP 10", True, (180, 180, 180))
        self.screen.blit(header, header.get_rect(center=(self.w // 2, y)))
        for i, e in enumerate(self.game.scoreboard.top(10)):
            line = f"{i+1:>2}. {e.nickname:<12}{e.score:>3}"
            text = self.font_xs.render(line, True, (220, 220, 220))
            self.screen.blit(text, text.get_rect(center=(self.w // 2, y + 50 + i * 38)))

    def _cycle_attract_flash(self) -> None:
        order = ["RED", "BLUE", "YELLOW", "GREEN"]
        slot = int(time.monotonic()) % 4
        self.flash_until[order[slot]] = time.monotonic() + 0.5

    def _draw_game(self, big_overlay: Optional[str] = None) -> None:
        sess = self.game.session
        level = sess.current_level if sess else 1
        score = sess.current_score if sess else 0

        top_bar = pygame.Rect(0, 0, self.w, 90)
        pygame.draw.rect(self.screen, (24, 24, 32), top_bar)
        title = self.font_sm.render(self.cfg.ui.title, True, (230, 230, 230))
        self.screen.blit(title, (40, 22))

        lvl = self.font_sm.render(f"LEVEL: {level}", True, (230, 230, 230))
        self.screen.blit(lvl, lvl.get_rect(midright=(self.w - 320, 45)))

        countdown = self.game.countdown_remaining_sec()
        timer_color = (255, 80, 80) if 0 < countdown <= 3 else (240, 240, 240)
        timer = self.font_sm.render(f"⏱ {countdown:02d}", True, timer_color)
        self.screen.blit(timer, timer.get_rect(midright=(self.w - 80, 45)))

        active = self.cfg.active_colors_for_level(level)
        blocks = self._block_rects()
        self._draw_blocks(blocks, active)

        bottom_bar = pygame.Rect(0, self.h - 90, self.w, 90)
        pygame.draw.rect(self.screen, (24, 24, 32), bottom_bar)
        sc = self.font_sm.render(f"SCORE: {score}", True, (230, 230, 230))
        self.screen.blit(sc, (40, self.h - 70))

        best = self.game.scoreboard.best()
        best_str = f"BEST: {best.score} {best.nickname}" if best else "BEST: -- ---"
        bt = self.font_sm.render(best_str, True, (230, 230, 230))
        self.screen.blit(bt, bt.get_rect(midright=(self.w - 40, self.h - 45)))

        if big_overlay:
            text = self.font_lg.render(big_overlay, True, (255, 240, 240))
            shadow = self.font_lg.render(big_overlay, True, (0, 0, 0))
            rect = text.get_rect(center=(self.w // 2, self.h // 2))
            self.screen.blit(shadow, rect.move(4, 4))
            self.screen.blit(text, rect)
            if self.game.state == State.GAME_OVER and self.game.session:
                sub = self.font_md.render(
                    f"점수: {self.game.session.current_score}", True, (255, 220, 220),
                )
                self.screen.blit(sub, sub.get_rect(center=(self.w // 2, self.h // 2 + 120)))

        self._draw_show_progress()

    def _draw_show_progress(self) -> None:
        if self.game.state != State.SHOW_SEQUENCE or not self.game.session:
            return
        elapsed = time.monotonic() - self.game.state_entered_at
        step = self.cfg.game.show_on_ms + self.cfg.game.show_off_ms
        idx = int(elapsed * 1000 / step)
        if 0 <= idx < len(self.game.session.sequence):
            phase = (elapsed * 1000) % step
            if phase < self.cfg.game.show_on_ms:
                self.flash_until[self.game.session.sequence[idx]] = time.monotonic() + 0.05

    def _draw_blocks(self, blocks: dict, active: List[str]) -> None:
        now = time.monotonic()
        for name, rect in blocks.items():
            if name not in active:
                color = self._color(name, "disabled")
            elif self.flash_until.get(name, 0) > now:
                color = self._color(name, "active")
            else:
                color = self._color(name, "dim")
            pygame.draw.rect(self.screen, color, rect, border_radius=24)
            pygame.draw.rect(self.screen, (240, 240, 240), rect, width=3, border_radius=24)

            if self.cfg.ui.show_colorblind_shapes and name in active:
                shape = self.font_shape.render(SHAPES[name], True, (255, 255, 255))
                cx = rect[0] + rect[2] // 2
                cy = rect[1] + rect[3] // 2
                self.screen.blit(shape, shape.get_rect(center=(cx, cy)))

            label = self.font_md.render(name, True, (255, 255, 255))
            cx = rect[0] + rect[2] // 2
            cy = rect[1] + rect[3] - 60
            self.screen.blit(label, label.get_rect(center=(cx, cy)))

    def _draw_nickname(self) -> None:
        sess = self.game.session
        header = self.font_lg.render("NEW HIGH SCORE!", True, (255, 240, 120))
        self.screen.blit(header, header.get_rect(center=(self.w // 2, 110)))
        if sess:
            sc = self.font_md.render(f"점수: {sess.current_score}", True, (240, 240, 240))
            self.screen.blit(sc, sc.get_rect(center=(self.w // 2, 200)))

        input_rect = pygame.Rect(self.w // 2 - 400, 250, 800, 110)
        pygame.draw.rect(self.screen, (40, 40, 50), input_rect, border_radius=12)
        pygame.draw.rect(self.screen, (200, 200, 200), input_rect, width=3, border_radius=12)
        cursor = "_" if int(time.monotonic() * 2) % 2 == 0 else " "
        text = self.font_md.render(self.game.nickname_buffer + cursor, True, (240, 240, 240))
        self.screen.blit(text, text.get_rect(center=input_rect.center))

        now_ms = pygame.time.get_ticks()
        for k in self.keyboard:
            kx, ky, kw, kh = k.rect
            recent = now_ms - k.last_pressed_ms < 100
            bg = (220, 220, 220) if recent else (60, 60, 72)
            fg = (20, 20, 20) if recent else (240, 240, 240)
            pygame.draw.rect(self.screen, bg, k.rect, border_radius=12)
            pygame.draw.rect(self.screen, (120, 120, 130), k.rect, width=2, border_radius=12)
            label = self.font_sm.render(k.label, True, fg)
            self.screen.blit(label, label.get_rect(center=(kx + kw // 2, ky + kh // 2)))

    # ------------------------------------------------------------------ selftest

    def _draw_selftest_hold_hint(self) -> None:
        held = self.game.held
        from .game import SELFTEST_HOLD_COMBO, SELFTEST_HOLD_SEC

        if not SELFTEST_HOLD_COMBO.issubset(held) or self.game.combo_hold_started_at is None:
            return
        elapsed = time.monotonic() - self.game.combo_hold_started_at
        if elapsed < 0.5:
            return
        rem = max(0.0, SELFTEST_HOLD_SEC - elapsed)
        msg = f"자가진단 모드 진입까지 {rem:0.1f}s"
        text = self.font_md.render(msg, True, (255, 230, 160))
        bg = pygame.Surface((text.get_width() + 60, text.get_height() + 30))
        bg.fill((20, 20, 30))
        bg.set_alpha(220)
        rect = bg.get_rect(center=(self.w // 2, self.h // 2))
        self.screen.blit(bg, rect)
        self.screen.blit(text, text.get_rect(center=rect.center))

    def _draw_selftest(self) -> None:
        st = self.game.selftest
        if st.submode == SUBMODE_CONFIRM:
            self._draw_selftest_main()
            self._draw_selftest_confirm()
        elif st.submode == SUBMODE_TIME_SET:
            self._draw_selftest_time_set()
        else:
            self._draw_selftest_main()

    def _draw_selftest_main(self) -> None:
        st = self.game.selftest
        self.screen.fill((14, 16, 24))

        header = self.font_lg.render("자가진단 모드 (SELF-TEST)", True, (240, 240, 240))
        self.screen.blit(header, header.get_rect(midtop=(self.w // 2, 40)))

        version_lines = [
            f"App: {APP_VERSION}",
            f"MCU FW: {st.mcu_fw_version}",
        ]
        for i, line in enumerate(version_lines):
            t = self.font_sm.render(line, True, (200, 200, 220))
            self.screen.blit(t, (60, 180 + i * 50))

        # Button status panel
        bx, by, bw, bh = 60, 320, self.w - 120, 220
        pygame.draw.rect(self.screen, (28, 30, 42), (bx, by, bw, bh), border_radius=16)
        title = self.font_md.render("버튼/LED 테스트 — 각 버튼을 눌러 확인", True, (240, 240, 240))
        self.screen.blit(title, (bx + 24, by + 16))

        cell_w = (bw - 48) // 4
        for i, c in enumerate(COLORS):
            cx = bx + 24 + i * cell_w
            cy = by + 80
            now = time.monotonic()
            recent = now - st.last_press_ts[c] < 0.5
            base = self._color(c, "active" if recent else "dim")
            sweep_on = COLORS[(st.led_sweep_idx - 1) % 4] == c and (now - st.led_sweep_at) < 0.4
            if sweep_on:
                base = self._color(c, "active")
            pygame.draw.rect(self.screen, base, (cx, cy, cell_w - 20, 100), border_radius=12)
            pygame.draw.rect(self.screen, (200, 200, 200), (cx, cy, cell_w - 20, 100), width=2, border_radius=12)
            label = self.font_sm.render(c, True, (255, 255, 255))
            self.screen.blit(label, label.get_rect(center=(cx + (cell_w - 20) // 2, cy + 30)))
            cnt = self.font_xs.render(f"× {st.button_counts[c]}", True, (255, 255, 255))
            self.screen.blit(cnt, cnt.get_rect(center=(cx + (cell_w - 20) // 2, cy + 75)))

        # Action buttons
        actions = [
            ("RESET", "RESET SCORES", (200, 80, 80)),
            ("TIME", "SET TIME", (80, 140, 200)),
            ("SHUTDOWN", "SHUTDOWN", (180, 100, 60)),
            ("REBOOT", "REBOOT", (180, 140, 60)),
            ("EXIT", "EXIT", (90, 160, 90)),
        ]
        self.selftest_buttons = {}
        btn_w, btn_h = 280, 110
        gap = 30
        total_w = len(actions) * btn_w + (len(actions) - 1) * gap
        sx = (self.w - total_w) // 2
        sy = self.h - 230
        for i, (key, label, color) in enumerate(actions):
            x = sx + i * (btn_w + gap)
            rect = pygame.Rect(x, sy, btn_w, btn_h)
            self.selftest_buttons[key] = rect
            pygame.draw.rect(self.screen, color, rect, border_radius=14)
            pygame.draw.rect(self.screen, (240, 240, 240), rect, width=2, border_radius=14)
            t = self.font_sm.render(label, True, (255, 255, 255))
            self.screen.blit(t, t.get_rect(center=rect.center))

        # Status flash line
        if st.status_message:
            t = self.font_sm.render(st.status_message, True, (255, 240, 160))
            self.screen.blit(t, t.get_rect(midbottom=(self.w // 2, sy - 20)))

        # Hint
        hint = self.font_xs.render("EXIT 를 누르면 ATTRACT 로 복귀합니다.", True, (160, 160, 170))
        self.screen.blit(hint, hint.get_rect(midbottom=(self.w // 2, self.h - 20)))

    def _draw_selftest_confirm(self) -> None:
        st = self.game.selftest
        if not st.confirm:
            return
        overlay = pygame.Surface((self.w, self.h))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(180)
        self.screen.blit(overlay, (0, 0))

        bw, bh = 900, 360
        box = pygame.Rect((self.w - bw) // 2, (self.h - bh) // 2, bw, bh)
        pygame.draw.rect(self.screen, (30, 30, 40), box, border_radius=20)
        pygame.draw.rect(self.screen, (200, 200, 220), box, width=3, border_radius=20)

        title = self.font_md.render("확인", True, (255, 200, 200))
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 30)))
        msg = self.font_sm.render(st.confirm.prompt, True, (240, 240, 240))
        self.screen.blit(msg, msg.get_rect(center=(box.centerx, box.centery - 20)))

        btn_w, btn_h = 240, 90
        gap = 60
        sx = box.centerx - btn_w - gap // 2
        sy = box.y + bh - btn_h - 40
        no_rect = pygame.Rect(sx, sy, btn_w, btn_h)
        yes_rect = pygame.Rect(sx + btn_w + gap, sy, btn_w, btn_h)
        self.selftest_buttons["CONFIRM_NO"] = no_rect
        self.selftest_buttons["CONFIRM_YES"] = yes_rect

        pygame.draw.rect(self.screen, (90, 90, 110), no_rect, border_radius=12)
        pygame.draw.rect(self.screen, (200, 60, 60), yes_rect, border_radius=12)
        pygame.draw.rect(self.screen, (240, 240, 240), no_rect, width=2, border_radius=12)
        pygame.draw.rect(self.screen, (240, 240, 240), yes_rect, width=2, border_radius=12)
        n = self.font_sm.render("취소", True, (240, 240, 240))
        y = self.font_sm.render("확인", True, (255, 255, 255))
        self.screen.blit(n, n.get_rect(center=no_rect.center))
        self.screen.blit(y, y.get_rect(center=yes_rect.center))

    def _draw_selftest_time_set(self) -> None:
        st = self.game.selftest
        self.screen.fill((14, 16, 24))
        header = self.font_lg.render("시각 설정", True, (240, 240, 240))
        self.screen.blit(header, header.get_rect(midtop=(self.w // 2, 80)))

        labels = ["YEAR", "MONTH", "DAY", "HOUR", "MINUTE"]
        values = st.time_fields.values()
        col_w = 260
        total_w = len(labels) * col_w
        sx = (self.w - total_w) // 2
        sy = 280
        self.time_buttons = {}

        for i, (lab, val) in enumerate(zip(labels, values)):
            x = sx + i * col_w
            lt = self.font_sm.render(lab, True, (180, 180, 200))
            self.screen.blit(lt, lt.get_rect(midtop=(x + col_w // 2, sy)))

            up = pygame.Rect(x + col_w // 2 - 60, sy + 60, 120, 80)
            box = pygame.Rect(x + col_w // 2 - 100, sy + 160, 200, 110)
            dn = pygame.Rect(x + col_w // 2 - 60, sy + 290, 120, 80)
            self.time_buttons[f"UP_{i}"] = up
            self.time_buttons[f"DN_{i}"] = dn

            pygame.draw.rect(self.screen, (60, 100, 160), up, border_radius=10)
            pygame.draw.rect(self.screen, (60, 100, 160), dn, border_radius=10)
            pygame.draw.rect(self.screen, (30, 32, 44), box, border_radius=10)
            pygame.draw.rect(self.screen, (200, 200, 220), box, width=2, border_radius=10)

            uplab = self.font_md.render("▲", True, (255, 255, 255))
            dnlab = self.font_md.render("▼", True, (255, 255, 255))
            vlab = self.font_lg.render(str(val).zfill(2 if i > 0 else 4), True, (240, 240, 240))
            self.screen.blit(uplab, uplab.get_rect(center=up.center))
            self.screen.blit(dnlab, dnlab.get_rect(center=dn.center))
            self.screen.blit(vlab, vlab.get_rect(center=box.center))

        # Bottom action buttons
        btn_w, btn_h = 280, 110
        gap = 60
        sx2 = (self.w - 2 * btn_w - gap) // 2
        sy2 = self.h - 200
        cancel = pygame.Rect(sx2, sy2, btn_w, btn_h)
        apply_ = pygame.Rect(sx2 + btn_w + gap, sy2, btn_w, btn_h)
        self.time_buttons["CANCEL"] = cancel
        self.time_buttons["APPLY"] = apply_
        pygame.draw.rect(self.screen, (90, 90, 110), cancel, border_radius=12)
        pygame.draw.rect(self.screen, (60, 160, 90), apply_, border_radius=12)
        pygame.draw.rect(self.screen, (240, 240, 240), cancel, width=2, border_radius=12)
        pygame.draw.rect(self.screen, (240, 240, 240), apply_, width=2, border_radius=12)
        ct = self.font_sm.render("취소", True, (240, 240, 240))
        at = self.font_sm.render("적용", True, (255, 255, 255))
        self.screen.blit(ct, ct.get_rect(center=cancel.center))
        self.screen.blit(at, at.get_rect(center=apply_.center))

        # Preview
        preview = self.font_sm.render(st.time_fields.to_iso(), True, (200, 220, 200))
        self.screen.blit(preview, preview.get_rect(midbottom=(self.w // 2, sy2 - 20)))

    def _handle_selftest_click(self, x: int, y: int) -> None:
        st = self.game.selftest
        if st.submode == SUBMODE_TIME_SET:
            for key, rect in self.time_buttons.items():
                if rect.collidepoint(x, y):
                    if key == "APPLY":
                        st.apply_time()
                    elif key == "CANCEL":
                        st.cancel_time()
                    elif key.startswith("UP_"):
                        st.time_fields.adjust(int(key[3:]), +1)
                    elif key.startswith("DN_"):
                        st.time_fields.adjust(int(key[3:]), -1)
                    return
            return

        if st.submode == SUBMODE_CONFIRM:
            yes = self.selftest_buttons.get("CONFIRM_YES")
            no = self.selftest_buttons.get("CONFIRM_NO")
            if yes and yes.collidepoint(x, y):
                st.confirm_yes()
            elif no and no.collidepoint(x, y):
                st.confirm_no()
            return

        # Main submode
        for key, rect in self.selftest_buttons.items():
            if not rect.collidepoint(x, y):
                continue
            if key == "RESET":
                st.request_reset()
            elif key == "TIME":
                st.request_time_set()
            elif key == "SHUTDOWN":
                st.request_shutdown()
            elif key == "REBOOT":
                st.request_reboot()
            elif key == "EXIT":
                st.exit()
            return
