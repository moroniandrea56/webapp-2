"""Test per eeg_source.py: forma dei dati simulati, ripetibilità e ciclo di stati."""

import numpy as np

from eeg_device import EEGSource
from eeg_source import SimulatedMuseSource


def test_is_an_eeg_source():
    assert issubclass(SimulatedMuseSource, EEGSource)


def test_get_chunk_shape_matches_channels_and_samples():
    src = SimulatedMuseSource(seed=1)
    data, state = src.get_chunk(n_samples=128)
    assert data.shape == (len(SimulatedMuseSource.CHANNELS), 128)
    assert state in ("neutro", "rilassato", "attivato")


def test_same_seed_is_deterministic():
    data_a, _ = SimulatedMuseSource(seed=42).get_chunk(n_samples=64)
    data_b, _ = SimulatedMuseSource(seed=42).get_chunk(n_samples=64)
    np.testing.assert_array_equal(data_a, data_b)


def test_state_cycles_over_simulated_time():
    src = SimulatedMuseSource(seed=1)
    states = [src.get_chunk(n_samples=src.SAMPLE_RATE)[1] for _ in range(15)]
    # 15 secondi attraversano più di un ciclo (ogni stato dura ~4s): deve
    # aver visto più di un solo stato mentale simulato.
    assert len(set(states)) > 1
