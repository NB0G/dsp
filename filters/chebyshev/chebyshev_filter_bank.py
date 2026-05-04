from scipy.fft import fftshift, irfft, rfftfreq

from filters.chebyshev.chebyshev_bandpass_filter import chebyshev_band_pass_gain
from filters.chebyshev.chebyshev_highpass_filter import chebyshev_high_pass_gain
from filters.chebyshev.chebyshev_lowpass_filter import (
    DEFAULT_ORDER,
    DEFAULT_RIPPLE_DB,
    chebyshev_low_pass_gain,
)
from util import (
    StreamingFirFilter,
    build_hamming_window,
    db_to_gain,
    make_odd,
    ripple_db_to_epsilon,
)


CHEBYSHEV_BANDS = [
    ("low_pass", 0, 100),
    ("band_pass", 100, 300),
    ("band_pass", 300, 1000),
    ("band_pass", 1000, 3000),
    ("band_pass", 3000, 8000),
    ("high_pass", 8000, 22050),
]
DEFAULT_TAP_COUNT = 2049
DEFAULT_FFT_SIZE = 8192


class ChebyshevFilterBank:
    def __init__(
        self,
        sample_rate,
        band_gains_db,
        order=DEFAULT_ORDER,
        ripple_db=DEFAULT_RIPPLE_DB,
        tap_count=DEFAULT_TAP_COUNT,
        fft_size=DEFAULT_FFT_SIZE,
    ):
        self.sample_rate = sample_rate
        self.order = order
        self.epsilon = ripple_db_to_epsilon(ripple_db)
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
        frequency_response = []

        for frequency_hz in frequencies:
            frequency_response.append(self.combined_gain(frequency_hz))

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
            filter_gain = chebyshev_low_pass_gain(
                frequency_hz,
                high_cutoff_hz,
                self.order,
                self.epsilon,
            )
        elif filter_type == "high_pass":
            filter_gain = chebyshev_high_pass_gain(
                frequency_hz,
                low_cutoff_hz,
                self.order,
                self.epsilon,
            )
        else:
            filter_gain = chebyshev_band_pass_gain(
                frequency_hz,
                low_cutoff_hz,
                high_cutoff_hz,
                self.order,
                self.epsilon,
            )

        return filter_gain * band_gain

    def band_for_frequency(self, frequency_hz):
        nyquist_hz = self.sample_rate / 2

        for band_index, band in enumerate(CHEBYSHEV_BANDS, start=1):
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
