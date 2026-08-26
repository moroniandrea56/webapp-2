"""Test per artwork_renderer.py: dimensioni del render e mappatura colore
(stessa regola caldo/freddo del canvas JS della dashboard)."""

from artwork_renderer import render_artwork


def test_render_artwork_returns_expected_size_and_mode():
    img = render_artwork(asymmetry=0.3, activation=0.5, signature=0.5, size=200)
    assert img.size == (200, 200)
    assert img.mode == "RGB"


def test_positive_asymmetry_is_warmer_than_negative_at_center():
    size = 200
    warm = render_artwork(asymmetry=0.8, activation=0.5, signature=0.5, size=size)
    cool = render_artwork(asymmetry=-0.8, activation=0.5, signature=0.5, size=size)

    cx = cy = size // 2
    warm_r, _, warm_b = warm.getpixel((cx, cy))
    cool_r, _, cool_b = cool.getpixel((cx, cy))

    assert warm_r > warm_b  # asymmetry positiva -> caldo (rosso/arancio dominante)
    assert cool_b > cool_r  # asymmetry negativa -> freddo (blu dominante)
