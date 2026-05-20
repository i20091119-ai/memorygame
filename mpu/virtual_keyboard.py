from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Key:
    label: str
    value: str
    rect: Tuple[int, int, int, int]
    last_pressed_ms: int = 0


ROWS = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
    list("1234567890"),
]
KEY_W = 100
KEY_H = 100
KEY_GAP = 12
FN_W = 220
FN_H = 100
DEBOUNCE_MS = 200


def build_keyboard(screen_w: int, screen_h: int) -> List[Key]:
    keys: List[Key] = []
    layout_h = 4 * KEY_H + 3 * KEY_GAP + FN_H + 40
    start_y = screen_h - layout_h - 80

    for row_idx, row in enumerate(ROWS):
        row_w = len(row) * KEY_W + (len(row) - 1) * KEY_GAP
        start_x = (screen_w - row_w) // 2
        y = start_y + row_idx * (KEY_H + KEY_GAP)
        for i, ch in enumerate(row):
            x = start_x + i * (KEY_W + KEY_GAP)
            keys.append(Key(label=ch, value=ch, rect=(x, y, KEY_W, KEY_H)))

    fn_y = start_y + 4 * (KEY_H + KEY_GAP)
    fn_total_w = 3 * FN_W + 2 * 40
    fn_start_x = (screen_w - fn_total_w) // 2
    for i, (label, value) in enumerate(
        [("⌫ DEL", "BACK"), ("CANCEL", "CANCEL"), ("OK", "OK")]
    ):
        x = fn_start_x + i * (FN_W + 40)
        keys.append(Key(label=label, value=value, rect=(x, fn_y, FN_W, FN_H)))

    return keys


def hit_test(keys: List[Key], x: int, y: int, now_ms: int) -> Optional[Key]:
    for k in keys:
        kx, ky, kw, kh = k.rect
        if kx <= x < kx + kw and ky <= y < ky + kh:
            if now_ms - k.last_pressed_ms < DEBOUNCE_MS:
                return None
            k.last_pressed_ms = now_ms
            return k
    return None
