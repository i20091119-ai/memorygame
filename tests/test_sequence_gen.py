from collections import Counter

from mpu.sequence_gen import SequenceGenerator


def test_length_and_colors():
    g = SequenceGenerator(max_consecutive_same=3, seed=1)
    seq = g.generate(10, ["RED", "BLUE"])
    assert len(seq) == 10
    assert set(seq) <= {"RED", "BLUE"}


def test_no_4_consecutive_same():
    g = SequenceGenerator(max_consecutive_same=3, seed=42)
    for _ in range(200):
        seq = g.generate(50, ["RED", "BLUE", "YELLOW", "GREEN"])
        run = 1
        for i in range(1, len(seq)):
            run = run + 1 if seq[i] == seq[i - 1] else 1
            assert run <= 3, seq


def test_empty_inputs():
    g = SequenceGenerator(seed=0)
    assert g.generate(0, ["RED"]) == []
    assert g.generate(5, []) == []


def test_distribution_roughly_balanced():
    g = SequenceGenerator(seed=7)
    seq = g.generate(4000, ["RED", "BLUE", "YELLOW", "GREEN"])
    counts = Counter(seq)
    for c in ("RED", "BLUE", "YELLOW", "GREEN"):
        assert 800 <= counts[c] <= 1200
