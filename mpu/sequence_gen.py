import os
import random
from typing import List


class SequenceGenerator:
    def __init__(self, max_consecutive_same: int = 3, seed: int | None = None):
        self.max_consecutive_same = max_consecutive_same
        if seed is None:
            seed = int.from_bytes(os.urandom(8), "big")
        self.rng = random.Random(seed)

    def generate(self, length: int, active_colors: List[str]) -> List[str]:
        if length <= 0 or not active_colors:
            return []
        seq: List[str] = []
        run = 0
        last = None
        for _ in range(length):
            choices = list(active_colors)
            if last is not None and run >= self.max_consecutive_same - 1:
                choices = [c for c in choices if c != last] or choices
            pick = self.rng.choice(choices)
            run = run + 1 if pick == last else 1
            last = pick
            seq.append(pick)
        return seq
