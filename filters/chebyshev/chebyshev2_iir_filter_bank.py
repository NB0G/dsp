import math

import numpy as np

from util import StreamingIirFilter, db_to_gain


CHEBYSHEV2_BANDS = [
    (0, 100),
    (100, 300),
    (300, 1000),
    (1000, 3000),
    (3000, 8000),
    (8000, 22050),
]
DEFAULT_ORDER = 4
DEFAULT_STOPBAND_ATTENUATION_DB = 40


def chebyshev2_lowpass_prototype(order, attenuation_db):
    epsilon = 1 / math.sqrt(10 ** (attenuation_db / 10) - 1)
    mu = math.asinh(1 / epsilon) / order
    poles = []
    zeros = []

    for index in range(1, order + 1):
        theta = math.pi * (2 * index - 1) / (2 * order)
        sinh_part = math.sinh(mu) * math.sin(theta)
        cosh_part = math.cosh(mu) * math.cos(theta)
        poles.append(1 / complex(-sinh_part, cosh_part))

        if abs(math.cos(theta)) > 1e-12:
            zeros.append(1j / math.cos(theta))

    gain = abs(np.prod([-pole for pole in poles]) / np.prod([-zero for zero in zeros]))
    return zeros, poles, gain


def prewarp_frequency(frequency_hz, sample_rate):
    limited_frequency = min(frequency_hz, sample_rate / 2 * 0.98)
    return 2 * sample_rate * math.tan(math.pi * limited_frequency / sample_rate)


def scale_lowpass(zeros, poles, gain, cutoff_hz, sample_rate):
    warped_cutoff = prewarp_frequency(cutoff_hz, sample_rate)
    degree = len(poles) - len(zeros)
    return (
        [zero * warped_cutoff for zero in zeros],
        [pole * warped_cutoff for pole in poles],
        gain * warped_cutoff ** degree,
    )


def scale_highpass(zeros, poles, gain, cutoff_hz, sample_rate):
    warped_cutoff = prewarp_frequency(cutoff_hz, sample_rate)
    transformed_zeros = [warped_cutoff / zero for zero in zeros if zero != 0]
    transformed_poles = [warped_cutoff / pole for pole in poles]
    transformed_zeros.extend([0] * (len(transformed_poles) - len(transformed_zeros)))
    return transformed_zeros, transformed_poles, gain


def bilinear_zpk(zeros, poles, gain, sample_rate):
    fs2 = 2 * sample_rate
    digital_zeros = [(fs2 + zero) / (fs2 - zero) for zero in zeros]
    digital_poles = [(fs2 + pole) / (fs2 - pole) for pole in poles]
    digital_zeros.extend([-1] * (len(digital_poles) - len(digital_zeros)))
    digital_gain = gain * np.prod([fs2 - zero for zero in zeros])
    digital_gain /= np.prod([fs2 - pole for pole in poles])
    return digital_zeros, digital_poles, digital_gain.real


def zpk_to_coefficients(zeros, poles, gain):
    b_coefficients = (gain * np.poly(zeros)).real
    a_coefficients = np.poly(poles).real
    return b_coefficients.tolist(), a_coefficients.tolist()


def normalize_iir_gain(b_coefficients, a_coefficients, frequency_hz, sample_rate):
    angle = 2 * math.pi * frequency_hz / sample_rate
    z = complex(math.cos(angle), math.sin(angle))
    numerator = sum(
        coefficient * z ** (-index)
        for index, coefficient in enumerate(b_coefficients)
    )
    denominator = sum(
        coefficient * z ** (-index)
        for index, coefficient in enumerate(a_coefficients)
    )
    gain = abs(numerator / denominator)

    if gain == 0:
        return b_coefficients, a_coefficients

    return [coefficient / gain for coefficient in b_coefficients], a_coefficients


def build_iir_filter(filter_type, cutoff_hz, sample_rate):
    zeros, poles, gain = chebyshev2_lowpass_prototype(
        DEFAULT_ORDER,
        DEFAULT_STOPBAND_ATTENUATION_DB,
    )

    if filter_type == "high_pass":
        zeros, poles, gain = scale_highpass(zeros, poles, gain, cutoff_hz, sample_rate)
        reference_hz = min(cutoff_hz * 2, sample_rate / 2 * 0.9)
    else:
        zeros, poles, gain = scale_lowpass(zeros, poles, gain, cutoff_hz, sample_rate)
        reference_hz = min(cutoff_hz / 2, sample_rate / 2 * 0.9)

    zeros, poles, gain = bilinear_zpk(zeros, poles, gain, sample_rate)
    b_coefficients, a_coefficients = zpk_to_coefficients(zeros, poles, gain)
    b_coefficients, a_coefficients = normalize_iir_gain(
        b_coefficients,
        a_coefficients,
        max(1, reference_hz),
        sample_rate,
    )
    return StreamingIirFilter(b_coefficients, a_coefficients)


class Chebyshev2IirBand:
    def __init__(self, sample_rate, low_cutoff_hz, high_cutoff_hz, gain_db):
        nyquist_hz = sample_rate / 2
        self.gain = db_to_gain(gain_db)
        self.filters = []

        if low_cutoff_hz > 0:
            self.filters.append(build_iir_filter("high_pass", low_cutoff_hz, sample_rate))

        if high_cutoff_hz < nyquist_hz:
            self.filters.append(build_iir_filter("low_pass", high_cutoff_hz, sample_rate))

    def set_gain_db(self, gain_db):
        self.gain = db_to_gain(gain_db)

    def process_samples(self, samples):
        processed_samples = samples

        for audio_filter in self.filters:
            processed_samples = audio_filter.process_samples(processed_samples)

        return [sample * self.gain for sample in processed_samples]


class Chebyshev2IirFilterBank:
    def __init__(self, sample_rate, band_gains_db):
        self.sample_rate = sample_rate
        self.band_gains_db = band_gains_db.copy()
        self.bands = []
        self.rebuild_bands()

    def rebuild_bands(self):
        self.bands = []

        for band_number, (low_cutoff_hz, high_cutoff_hz) in enumerate(
            CHEBYSHEV2_BANDS,
            start=1,
        ):
            self.bands.append(
                Chebyshev2IirBand(
                    self.sample_rate,
                    low_cutoff_hz,
                    high_cutoff_hz,
                    self.band_gains_db[band_number],
                )
            )

    def set_band_gain(self, band_number, gain_db):
        self.band_gains_db[band_number] = gain_db
        self.bands[band_number - 1].set_gain_db(gain_db)

    def process_samples(self, samples):
        band_outputs = [
            band.process_samples(samples)
            for band in self.bands
        ]
        return [
            sum(samples_at_time)
            for samples_at_time in zip(*band_outputs)
        ]
