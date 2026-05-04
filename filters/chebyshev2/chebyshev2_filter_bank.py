import math

from scipy.fft import fftshift, irfft, rfftfreq

from filters.equalizer_bands import EQUALIZER_BANDS, band_filter_type
from util import (
    StreamingFirFilter,
    build_hamming_window,
    chebyshev_polynomial,
    db_to_gain,
    make_odd,
)


CHEBYSHEV2_BANDS = [
    (band_filter_type(index), low_hz, high_hz)
    for index, (low_hz, high_hz) in enumerate(EQUALIZER_BANDS, start=1)
]
DEFAULT_ORDER = 4
DEFAULT_STOPBAND_ATTENUATION_DB = 40
DEFAULT_TAP_COUNT = 2049
DEFAULT_FFT_SIZE = 8192


def stopband_attenuation_db_to_epsilon(attenuation_db):
    return 1 / math.sqrt(10 ** (attenuation_db / 10) - 1)


def chebyshev2_low_pass_gain(frequency_hz, cutoff_hz, order, epsilon):
    if frequency_hz <= cutoff_hz:
        return 1

    ratio = frequency_hz / cutoff_hz
    chebyshev_value = chebyshev_polynomial(order, ratio)
    if chebyshev_value == 0:
        return 0

    return 1 / math.sqrt(1 + 1 / (epsilon * epsilon * chebyshev_value ** 2))


def chebyshev2_high_pass_gain(frequency_hz, cutoff_hz, order, epsilon):
    if frequency_hz >= cutoff_hz:
        return 1

    if frequency_hz == 0:
        return 0

    ratio = cutoff_hz / frequency_hz
    chebyshev_value = chebyshev_polynomial(order, ratio)
    if chebyshev_value == 0:
        return 0

    return 1 / math.sqrt(1 + 1 / (epsilon * epsilon * chebyshev_value ** 2))


def chebyshev2_band_pass_gain(frequency_hz, low_cutoff_hz, high_cutoff_hz, order, epsilon):
    if low_cutoff_hz <= frequency_hz <= high_cutoff_hz:
        return 1

    if frequency_hz == 0:
        return 0

    center_frequency = math.sqrt(low_cutoff_hz * high_cutoff_hz)
    bandwidth = high_cutoff_hz - low_cutoff_hz
    ratio = abs(
        (frequency_hz * frequency_hz - center_frequency * center_frequency)
        / (bandwidth * frequency_hz)
    )

    if ratio <= 1:
        return 1

    chebyshev_value = chebyshev_polynomial(order, ratio)
    if chebyshev_value == 0:
        return 0

    return 1 / math.sqrt(1 + 1 / (epsilon * epsilon * chebyshev_value ** 2))


class Chebyshev2FilterBank:
    def __init__(
        self,
        sample_rate,
        band_gains_db,
        order=DEFAULT_ORDER,
        attenuation_db=DEFAULT_STOPBAND_ATTENUATION_DB,
        tap_count=DEFAULT_TAP_COUNT,
        fft_size=DEFAULT_FFT_SIZE,
    ):
        self.sample_rate = sample_rate
        self.order = order
        self.epsilon = stopband_attenuation_db_to_epsilon(attenuation_db)
        self.tap_count = make_odd(tap_count)
        self.fft_size = max(fft_size, self.tap_count * 4)
        self.band_gains_db = band_gains_db.copy()
        self.band_gains = {}

        for band_number, gain_db in self.band_gains_db.items():
            self.band_gains[band_number] = db_to_gain(gain_db)

        self.filter = StreamingFirFilter([0] * self.tap_count)
        self.rebuild_kernel()

    def set_band_gain(self, band_number, gain_db):
        self.band_gains_db[band_number] = gain_db
        self.band_gains[band_number] = db_to_gain(gain_db)
        self.rebuild_kernel()

    def rebuild_kernel(self):
        frequencies = rfftfreq(self.fft_size, 1 / self.sample_rate)
        frequency_response = [
            self.combined_gain(frequency_hz)
            for frequency_hz in frequencies
        ]
        impulse_response = fftshift(irfft(frequency_response, self.fft_size)).tolist()
        center = len(impulse_response) // 2
        half_taps = self.tap_count // 2
        kernel = impulse_response[center - half_taps:center + half_taps + 1]
        window = build_hamming_window(len(kernel))

        self.filter.kernel = [
            kernel_value * window_value
            for kernel_value, window_value in zip(kernel, window)
        ]
        self.filter.kernel_fft_by_size = {}

    def combined_gain(self, frequency_hz):
        band_index, band = self.band_for_frequency(frequency_hz)
        if band is None:
            return 0

        filter_type, low_cutoff_hz, high_cutoff_hz = band
        band_gain = self.band_gains[band_index]

        if filter_type == "low_pass":
            filter_gain = chebyshev2_low_pass_gain(
                frequency_hz,
                high_cutoff_hz,
                self.order,
                self.epsilon,
            )
        elif filter_type == "high_pass":
            filter_gain = chebyshev2_high_pass_gain(
                frequency_hz,
                low_cutoff_hz,
                self.order,
                self.epsilon,
            )
        else:
            filter_gain = chebyshev2_band_pass_gain(
                frequency_hz,
                low_cutoff_hz,
                high_cutoff_hz,
                self.order,
                self.epsilon,
            )

        return filter_gain * band_gain

    def band_for_frequency(self, frequency_hz):
        nyquist_hz = self.sample_rate / 2

        for band_index, band in enumerate(CHEBYSHEV2_BANDS, start=1):
            filter_type, low_cutoff_hz, high_cutoff_hz = band
            high_cutoff_hz = min(high_cutoff_hz, nyquist_hz)

            if filter_type == "high_pass":
                if low_cutoff_hz <= frequency_hz <= nyquist_hz:
                    return band_index, band
            elif low_cutoff_hz <= frequency_hz < high_cutoff_hz:
                return band_index, band

        return None, None

    def process_samples(self, samples):
        return self.filter.process_samples(samples)
