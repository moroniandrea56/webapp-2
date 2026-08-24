"""
visual_engine.py
=================
Trasforma le metriche in un'opera visiva generativa, in tempo reale.

Questo è un motore "leggero" basato su matplotlib, pensato per testare
subito la pipeline senza installare TouchDesigner. Quando vorrai un
risultato più spettacolare/professionale per un evento reale, la stessa
identica logica di mappatura (colore/complessità/forma) andrà ricreata
in TouchDesigner, che riceverà gli stessi dati via OSC.

Mappatura (coerente con quanto descritto da BrainArt):
- COLORE       <- asymmetry (rosso/caldo = attivazione positiva, blu/freddo = negativa)
- COMPLESSITA  <- activation (più punti, più movimento, più "rumore" visivo)
- FORMA        <- signature (pattern di base, diverso da persona a persona)
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")  # backend non interattivo: necessario per salvare video/gif
                        # in ambienti senza schermo. Se lanci lo script su un
                        # tuo PC con schermo e vuoi la finestra live, rimuovi
                        # questa riga o commentala.
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import colorsys


class BrainArtVisualizer:
    def __init__(self, n_points=800):
        self.n_points = n_points
        self.fig, self.ax = plt.subplots(figsize=(7, 7), facecolor="black")
        self.ax.set_facecolor("black")
        self.ax.set_xlim(-1.2, 1.2)
        self.ax.set_ylim(-1.2, 1.2)
        self.ax.axis("off")
        self.scatter = self.ax.scatter([], [], s=[], c=[])
        self.angle_offset = 0.0

    def _metrics_to_frame(self, metrics):
        asymmetry = metrics["asymmetry"]   # -1 .. 1
        activation = metrics["activation"] # 0 .. 1
        signature = metrics["signature"]   # 0 .. 1

        # Numero di "petali" del pattern dipende dalla firma individuale
        n_lobes = 3 + int(signature * 7)  # tra 3 e 10 lobi

        # Quanto il pattern è denso/mosso dipende dall'attivazione
        n_active_points = int(self.n_points * (0.3 + 0.7 * activation))

        theta = np.linspace(0, 4 * np.pi, n_active_points) + self.angle_offset
        radius = 0.3 + 0.7 * np.abs(np.sin(n_lobes * theta / 2))
        radius *= (0.7 + 0.3 * activation)  # più attivazione = forma più "espansa"

        # piccola variazione casuale per dare organicità
        radius += np.random.normal(0, 0.03, n_active_points)

        x = radius * np.cos(theta)
        y = radius * np.sin(theta)

        # Colore: mappiamo asymmetry (-1..1) su una scala hue
        # positivo (approach) -> caldo (rosso/arancio), negativo (withdrawal) -> freddo (blu)
        hue = 0.05 if asymmetry >= 0 else 0.65
        hue += (1 - abs(asymmetry)) * 0.1

        colors = []
        for i in range(n_active_points):
            brightness = 0.6 + 0.4 * (i / n_active_points)
            r, g, b = colorsys.hsv_to_rgb(hue, 0.85, brightness)
            colors.append((r, g, b))

        sizes = 15 + 40 * activation * np.ones(n_active_points)

        self.angle_offset += 0.02 + 0.05 * activation
        return x, y, sizes, colors

    def update(self, metrics):
        x, y, sizes, colors = self._metrics_to_frame(metrics)
        self.scatter.set_offsets(np.column_stack([x, y]))
        self.scatter.set_sizes(sizes)
        self.scatter.set_color(colors)
        return (self.scatter,)

    def run(self, get_metrics_fn, interval_ms=50, save_path=None, n_frames=200):
        """
        get_metrics_fn: funzione che, chiamata senza argomenti, restituisce
        il dizionario di metriche corrente (asymmetry, activation, signature).

        save_path: se indicato, salva un video invece di aprire una finestra
        interattiva (utile in questo ambiente sandbox).
        """
        def frame_update(_):
            metrics = get_metrics_fn()
            return self.update(metrics)

        anim = animation.FuncAnimation(
            self.fig, frame_update, frames=n_frames,
            interval=interval_ms, blit=True
        )

        if save_path:
            anim.save(save_path, writer="pillow", fps=1000 // interval_ms)
            print(f"Video salvato in: {save_path}")
        else:
            plt.show()
