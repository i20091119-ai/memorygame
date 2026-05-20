import time
from typing import List, Optional, Tuple

import pygame

from .config import COLORS, AppConfig
from .game import Game, State
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

        color = KEY_TO_COLOR.get(event.key)
        if color and hasattr(self.game.bridge, "emit_button"):
            self.game.bridge.emit_button(color)
            self.flash(color)
        elif color:
            self.game.touch_input_color(color)
            self.flash(color)

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
