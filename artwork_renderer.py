"""
artwork_renderer.py
====================
Rende "il quadro" lato server, ad alta risoluzione — indipendente dallo
schermo del partecipante. Copre due passaggi del funzionamento BrainArt
che il solo canvas del browser non può garantire:

  5. STAMPA IN LOCO   -> serve un file ad alta qualità da mandare in stampa
  6. DOWNLOAD DIGITALE -> il QR consegna una versione alta risoluzione,
                          pronta per i social, non uno screenshot del canvas

Replica in Python (numpy + Pillow) la stessa logica generativa del canvas
JS in dashboard/script.js (colore <- asymmetry, movimento <- activation,
forma <- signature), così l'immagine scaricata/stampata corrisponde a
quella vista a schermo durante l'esperienza.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# (scala del raggio, alpha di picco, sfasamento) di ciascuno dei 3 strati
# sovrapposti — stessi valori di makeBlobPainter() in dashboard/script.js.
_LAYERS = [
    (1.00, 0.55, 0.0),
    (0.84, 0.43, 1.4),
    (0.68, 0.31, 2.8),
]


def _hue_from_asymmetry(asymmetry):
    """Stessa regola del canvas JS: positivo = caldo, negativo = freddo."""
    hue = 18.0 if asymmetry >= 0 else 210.0
    hue += (1 - abs(asymmetry)) * 24.0
    return hue / 360.0


def _hsl_to_rgb_const_hue(hue, saturation, lightness):
    """HSL -> RGB vettorizzato per una tinta (hue) costante e `lightness` ad array.

    Evita un ciclo Python per pixel: con hue e saturation fissi, il settore
    di colore è un unico valore scalare, quindi tutta la conversione si
    riduce a poche operazioni numpy elementwise su `lightness`.
    """
    c = (1 - np.abs(2 * lightness - 1)) * saturation
    hp = (hue % 1.0) * 6.0
    k = 1 - abs((hp % 2) - 1)
    sector = int(hp) % 6

    x = c * k
    m = lightness - c / 2
    zero = np.zeros_like(c)

    sectors = {
        0: (c, x, zero),
        1: (x, c, zero),
        2: (zero, c, x),
        3: (zero, x, c),
        4: (x, zero, c),
        5: (c, zero, x),
    }
    r0, g0, b0 = sectors[sector]
    return r0 + m, g0 + m, b0 + m


def _draw_signature(img):
    """Aggiunge il piccolo wordmark 'BRAINART · Mind Made Art' in basso, centrato.

    Centrato orizzontalmente (non ancorato a un margine) perché l'immagine è
    quadrata ma finisce spesso ritagliata in formati non quadrati (es. la
    card di stampa 10x15, via object-fit:cover): un testo centrato sopravvive
    a un ritaglio simmetrico dei lati, uno ancorato a sinistra no.
    """
    size = img.width
    draw = ImageDraw.Draw(img, "RGBA")
    bottom_margin = round(size * 0.045)
    title_size = max(12, round(size * 0.024))
    sub_size = max(10, round(size * 0.016))

    def _font(px):
        try:
            return ImageFont.load_default(size=px)
        except TypeError:
            # Pillow < 10.1 non supporta 'size' su load_default(): va bene lo
            # stesso, resta leggibile anche col font bitmap a dimensione fissa.
            return ImageFont.load_default()

    title_font = _font(title_size)
    sub_font = _font(sub_size)

    def _centered_x(text, font):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        return (size - text_width) / 2

    title_y = size - bottom_margin - title_size - sub_size - 4
    sub_y = title_y + title_size + 2

    for label, font, y in (("BRAINART", title_font, title_y), ("Mind Made Art", sub_font, sub_y)):
        x = _centered_x(label, font)
        for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            draw.text((x + dx, y + dy), label, font=font, fill=(0, 0, 0, 160))

    draw.text((_centered_x("BRAINART", title_font), title_y), "BRAINART", font=title_font, fill=(255, 255, 255, 235))
    draw.text((_centered_x("Mind Made Art", sub_font), sub_y), "Mind Made Art", font=sub_font, fill=(255, 255, 255, 190))


def render_artwork(asymmetry, activation, signature, size=1600):
    """Renderizza 'il quadro' come immagine PIL RGB di lato `size` pixel."""
    hue = _hue_from_asymmetry(asymmetry)
    lobes = 3 + round(signature * 6)
    amplitude = 0.25 + 0.35 * activation
    base_radius = size * 0.30
    center = size / 2.0

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    dx = xx - center
    dy = yy - center
    theta = np.arctan2(dy, dx)
    r = np.sqrt(dx * dx + dy * dy)

    accum = np.zeros((size, size, 3), dtype=np.float64)

    for radius_scale, peak_alpha, phase in _LAYERS:
        boundary = base_radius * radius_scale * (
            1
            + amplitude * np.sin(lobes * theta + phase) * 0.5
            + amplitude * np.sin(lobes * 1.7 * theta - phase * 1.3) * 0.28
            + amplitude * np.sin(3 * theta) * 0.12
        )
        gradient_extent = max(base_radius * radius_scale * 1.4, 1e-6)
        d = np.clip(r / gradient_extent, 0.0, 1.0)
        inside = r <= boundary

        # stessi color-stop (0 / 0.55 / 1) del gradiente radiale del canvas JS
        lightness_pct = np.where(d < 0.55, 70 - (d / 0.55) * 15, 55 - (d - 0.55) / 0.45 * 10)
        alpha = np.where(
            d < 0.55,
            peak_alpha - (d / 0.55) * (peak_alpha * 0.3),
            peak_alpha * 0.7 * np.clip(1 - (d - 0.55) / 0.45, 0, None),
        )
        alpha = np.where(inside, np.clip(alpha, 0, None), 0.0)

        r_ch, g_ch, b_ch = _hsl_to_rgb_const_hue(
            hue, 0.90, np.clip(lightness_pct, 0, 100) / 100.0
        )
        layer_rgb = np.stack([r_ch, g_ch, b_ch], axis=-1) * 255.0
        # come ctx.globalCompositeOperation = "lighter" nel canvas: additivo
        accum += layer_rgb * alpha[..., None]

    rgb = np.clip(accum, 0, 255).astype(np.uint8)
    img = Image.fromarray(rgb, mode="RGB")
    _draw_signature(img)
    return img


def render_artwork_png_bytes(asymmetry, activation, signature, size=1600):
    """Come render_artwork(), ma restituisce direttamente i byte di un PNG."""
    import io

    img = render_artwork(asymmetry, activation, signature, size=size)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
