import math
from collections import deque

from scipy.fft import irfft, next_fast_len, rfft, rfftfreq

try:
    import numpy as np
except ImportError:
    np = None


def make_odd(value):
    if value % 2 == 0:
        return value + 1
    return value


def sinc_value(sample_offset, cutoff_ratio):
    if sample_offset == 0:
        return 2 * cutoff_ratio

    return math.sin(2 * math.pi * cutoff_ratio * sample_offset) / (
        math.pi * sample_offset
    )


def build_hamming_window(size):
    return [
        0.54 - 0.46 * math.cos(2 * math.pi * index / (size - 1))
        for index in range(size)
    ]


def build_chebyshev_window(size, attenuation_db=80):
    if size <= 1:
        return [1]

    if np is None:
        return build_hamming_window(size)

    order = size - 1
    beta = math.cosh(
        math.acosh(10 ** (abs(attenuation_db) / 20)) / order
    )
    coefficients = []

    for index in range(size):
        value = beta * math.cos(math.pi * index / size)
        if abs(value) <= 1:
            coefficient = math.cos(order * math.acos(value))
        else:
            coefficient = math.cosh(order * math.acosh(abs(value)))
            if value < -1 and order % 2 == 1:
                coefficient = -coefficient

        coefficients.append(coefficient)

    window = np.fft.fft(coefficients).real
    window = np.fft.fftshift(window)
    window = window / max(abs(window))

    return window.tolist()


def apply_window(kernel, window):
    return [
        kernel_value * window_value
        for kernel_value, window_value in zip(kernel, window)
    ]


def normalize_kernel(kernel):
    kernel_sum = sum(kernel)
    if kernel_sum == 0:
        return kernel

    return [kernel_value / kernel_sum for kernel_value in kernel]


def db_to_gain(db):
    return 10 ** (db / 20)


def chebyshev_polynomial(order, x):
    if order == 0:
        return 1

    if order == 1:
        return x

    previous = 1
    current = x

    for _index in range(2, order + 1):
        next_value = 2 * x * current - previous
        previous = current
        current = next_value

    return current


def ripple_db_to_epsilon(ripple_db):
    return math.sqrt(10 ** (ripple_db / 10) - 1)


def chebyshev_gain_by_ratio(frequency_ratio, order, epsilon):
    chebyshev_value = chebyshev_polynomial(order, frequency_ratio)

    return 1 / math.sqrt(1 + epsilon * epsilon * chebyshev_value * chebyshev_value)


def chebyshev_gain(frequency_hz, cutoff_hz, order, epsilon):
    return chebyshev_gain_by_ratio(frequency_hz / cutoff_hz, order, epsilon)


def apply_frequency_filter(samples, sample_rate, gain_function, gain_db=0):
    gain = db_to_gain(gain_db)
    sample_count = len(samples)
    spectrum = rfft(samples)
    frequencies = rfftfreq(sample_count, 1 / sample_rate)

    for index, frequency_hz in enumerate(frequencies):
        spectrum[index] *= gain_function(frequency_hz) * gain

    return irfft(spectrum, sample_count).tolist()


def convolve(samples, kernel, gain_db=0):
    center = len(kernel) // 2
    gain = db_to_gain(gain_db)
    output = []

    for sample_index in range(len(samples)):
        filtered_sample = 0

        for kernel_index, kernel_value in enumerate(kernel):
            input_index = sample_index - kernel_index + center
            if 0 <= input_index < len(samples):
                filtered_sample += samples[input_index] * kernel_value

        output.append(filtered_sample * gain)

    return output


class StreamingFirFilter:
    def __init__(self, kernel, gain_db=0):
        self.kernel = kernel
        self.kernel_fft_by_size = {}
        self.history = deque([0] * len(kernel), maxlen=len(kernel))
        self.set_gain_db(gain_db)

    def set_gain_db(self, gain_db):
        self.gain_db = gain_db
        self.gain = db_to_gain(gain_db)

    def process_sample(self, sample):
        self.history.appendleft(sample)
        filtered_sample = 0

        for sample_value, kernel_value in zip(self.history, self.kernel):
            filtered_sample += sample_value * kernel_value

        return filtered_sample * self.gain

    def process_samples(self, samples):
        if np is not None:
            return self.process_samples_fast(samples)

        return [self.process_sample(sample) for sample in samples]

    def process_samples_fast(self, samples):
        samples = list(samples)
        if not samples:
            return []

        history_size = len(self.kernel)
        previous_count = history_size - 1
        previous_samples = []

        if previous_count > 0:
            previous_samples = list(reversed(self.history))[-previous_count:]

        extended_samples = previous_samples + samples
        filtered_samples = self.convolve_block(extended_samples)
        start = history_size - 1
        end = start + len(samples)
        newest_history = extended_samples[-history_size:]
        self.history = deque(reversed(newest_history), maxlen=history_size)

        return (filtered_samples[start:end] * self.gain).tolist()

    def convolve_block(self, samples):
        if len(self.kernel) <= 128:
            return np.convolve(samples, self.kernel, mode="full")

        output_size = len(samples) + len(self.kernel) - 1
        fft_size = next_fast_len(output_size)
        kernel_fft = self.kernel_fft_by_size.get(fft_size)

        if kernel_fft is None:
            kernel_fft = rfft(self.kernel, fft_size)
            self.kernel_fft_by_size[fft_size] = kernel_fft

        samples_fft = rfft(samples, fft_size)
        return irfft(samples_fft * kernel_fft, fft_size)[:output_size]


class StreamingIirFilter:
    def __init__(self, b_coefficients, a_coefficients):
        if a_coefficients[0] == 0:
            raise ValueError("First IIR denominator coefficient must be non-zero")

        a0 = a_coefficients[0]
        self.b = [coefficient / a0 for coefficient in b_coefficients]
        self.a = [coefficient / a0 for coefficient in a_coefficients]
        self.state = [0] * (max(len(self.a), len(self.b)) - 1)

    def process_sample(self, sample):
        output = self.b[0] * sample

        if self.state:
            output += self.state[0]

        for index in range(1, len(self.state)):
            b_value = self.b[index] if index < len(self.b) else 0
            a_value = self.a[index] if index < len(self.a) else 0
            self.state[index - 1] = self.state[index] + b_value * sample - a_value * output

        if self.state:
            last_index = len(self.state)
            b_value = self.b[last_index] if last_index < len(self.b) else 0
            a_value = self.a[last_index] if last_index < len(self.a) else 0
            self.state[-1] = b_value * sample - a_value * output

        return output

    def process_samples(self, samples):
        return [self.process_sample(sample) for sample in samples]


class BlockFrequencyFilter:
    def __init__(self, sample_rate, gain_function, gain_db=0):
        self.sample_rate = sample_rate
        self.gain_function = gain_function
        self.set_gain_db(gain_db)

    def set_gain_db(self, gain_db):
        self.gain_db = gain_db
        self.gain = db_to_gain(gain_db)

    def process_samples(self, samples):
        return apply_frequency_filter(
            samples,
            self.sample_rate,
            self.gain_function,
            self.gain_db,
        )
