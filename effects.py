import math


class ReverbEffect:
    def __init__(self, sample_rate, delay_ms=70, feedback=0.35, mix=0.25):
        self.delay_samples = max(1, int(sample_rate * delay_ms / 1000))
        self.feedback = feedback
        self.mix = mix
        self.buffer = [0] * self.delay_samples
        self.index = 0

    def process_samples(self, samples):
        output = []

        for sample in samples:
            delayed_sample = self.buffer[self.index]
            wet_sample = sample + delayed_sample * self.feedback
            self.buffer[self.index] = wet_sample
            self.index = (self.index + 1) % self.delay_samples
            output.append(sample * (1 - self.mix) + delayed_sample * self.mix)

        return output


class VibratoEffect:
    def __init__(self, sample_rate, rate_hz=5, depth_ms=6, base_delay_ms=8):
        self.sample_rate = sample_rate
        self.rate_hz = rate_hz
        self.depth_samples = sample_rate * depth_ms / 1000
        self.base_delay_samples = sample_rate * base_delay_ms / 1000
        self.buffer_size = int(self.base_delay_samples + self.depth_samples + 4)
        self.buffer = [0] * self.buffer_size
        self.write_index = 0
        self.phase = 0

    def process_samples(self, samples):
        output = []

        for sample in samples:
            delay = self.base_delay_samples + self.depth_samples * (
                0.5 + 0.5 * math.sin(self.phase)
            )
            read_position = self.write_index - delay

            while read_position < 0:
                read_position += self.buffer_size

            output.append(self.read_fractional(read_position))
            self.buffer[self.write_index] = sample
            self.write_index = (self.write_index + 1) % self.buffer_size
            self.phase += 2 * math.pi * self.rate_hz / self.sample_rate

            if self.phase >= 2 * math.pi:
                self.phase -= 2 * math.pi

        return output

    def read_fractional(self, position):
        left_index = int(position) % self.buffer_size
        right_index = (left_index + 1) % self.buffer_size
        fraction = position - int(position)

        return (
            self.buffer[left_index] * (1 - fraction)
            + self.buffer[right_index] * fraction
        )


class AudioEffectChain:
    def __init__(self, sample_rate):
        self.effects = [
            ReverbEffect(sample_rate),
            VibratoEffect(sample_rate),
        ]

    def process_samples(self, samples):
        processed_samples = samples

        for effect in self.effects:
            processed_samples = effect.process_samples(processed_samples)

        return processed_samples
