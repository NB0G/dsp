import math


DEFAULT_EFFECT_SETTINGS = {
    "reverb_enabled": True,
    "reverb_delay_ms": 70,
    "reverb_feedback": 0.35,
    "reverb_mix": 0.25,
    "vibrato_enabled": True,
    "vibrato_rate_hz": 5.0,
    "vibrato_depth_ms": 6.0,
    "vibrato_mix": 0.45,
}


def clamp(value, low, high):
    return max(low, min(high, value))


class ReverbEffect:
    def __init__(self, sample_rate, delay_ms=70, feedback=0.35, mix=0.25):
        self.sample_rate = sample_rate
        self.enabled = True
        self.buffer = []
        self.index = 0
        self.set_parameters(delay_ms, feedback, mix)

    def set_parameters(self, delay_ms=None, feedback=None, mix=None):
        if delay_ms is not None:
            self.delay_ms = clamp(float(delay_ms), 1, 1000)
        if feedback is not None:
            self.feedback = clamp(float(feedback), 0, 0.95)
        if mix is not None:
            self.mix = clamp(float(mix), 0, 1)

        self.delay_samples = max(1, int(self.sample_rate * self.delay_ms / 1000))
        if len(self.buffer) != self.delay_samples:
            old_buffer = self.buffer
            self.buffer = [0] * self.delay_samples
            for index, sample in enumerate(old_buffer[-self.delay_samples:]):
                self.buffer[index] = sample
            self.index %= self.delay_samples

    def set_enabled(self, enabled):
        self.enabled = enabled

    def process_samples(self, samples):
        if not self.enabled or self.mix <= 0:
            return list(samples)

        output = []

        for sample in samples:
            delayed_sample = self.buffer[self.index]
            wet_sample = sample + delayed_sample * self.feedback
            self.buffer[self.index] = wet_sample
            self.index = (self.index + 1) % self.delay_samples
            output.append(sample * (1 - self.mix) + delayed_sample * self.mix)

        return output


class VibratoEffect:
    def __init__(
        self,
        sample_rate,
        rate_hz=5,
        depth_ms=6,
        base_delay_ms=8,
        mix=0.45,
    ):
        self.sample_rate = sample_rate
        self.enabled = True
        self.buffer = []
        self.write_index = 0
        self.phase = 0
        self.set_parameters(rate_hz, depth_ms, base_delay_ms, mix)

    def set_parameters(
        self,
        rate_hz=None,
        depth_ms=None,
        base_delay_ms=None,
        mix=None,
    ):
        if rate_hz is not None:
            self.rate_hz = clamp(float(rate_hz), 0.1, 20)
        if depth_ms is not None:
            self.depth_ms = clamp(float(depth_ms), 0, 30)
        if base_delay_ms is not None:
            self.base_delay_ms = clamp(float(base_delay_ms), 1, 50)
        if mix is not None:
            self.mix = clamp(float(mix), 0, 1)

        self.depth_samples = self.sample_rate * self.depth_ms / 1000
        self.base_delay_samples = self.sample_rate * self.base_delay_ms / 1000
        self.buffer_size = max(
            2,
            int(self.base_delay_samples + self.depth_samples + 4),
        )
        if len(self.buffer) != self.buffer_size:
            old_buffer = self.buffer
            self.buffer = [0] * self.buffer_size
            for index, sample in enumerate(old_buffer[-self.buffer_size:]):
                self.buffer[index] = sample
            self.write_index %= self.buffer_size

    def set_enabled(self, enabled):
        self.enabled = enabled

    def process_samples(self, samples):
        if not self.enabled or self.mix <= 0 or self.depth_samples <= 0:
            return list(samples)

        output = []

        for sample in samples:
            delay = self.base_delay_samples + self.depth_samples * (
                0.5 + 0.5 * math.sin(self.phase)
            )
            read_position = self.write_index - delay

            while read_position < 0:
                read_position += self.buffer_size

            wet_sample = self.read_fractional(read_position)
            output.append(sample * (1 - self.mix) + wet_sample * self.mix)
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
    def __init__(self, sample_rate, settings=None):
        self.reverb = ReverbEffect(sample_rate)
        self.vibrato = VibratoEffect(sample_rate)
        self.effects = [self.reverb, self.vibrato]
        self.set_settings(settings or {})

    def set_settings(self, settings):
        effect_settings = DEFAULT_EFFECT_SETTINGS.copy()
        effect_settings.update(settings)

        self.reverb.set_enabled(effect_settings["reverb_enabled"])
        self.reverb.set_parameters(
            delay_ms=effect_settings["reverb_delay_ms"],
            feedback=effect_settings["reverb_feedback"],
            mix=effect_settings["reverb_mix"],
        )
        self.vibrato.set_enabled(effect_settings["vibrato_enabled"])
        self.vibrato.set_parameters(
            rate_hz=effect_settings["vibrato_rate_hz"],
            depth_ms=effect_settings["vibrato_depth_ms"],
            mix=effect_settings["vibrato_mix"],
        )

    def process_samples(self, samples):
        processed_samples = samples

        for effect in self.effects:
            processed_samples = effect.process_samples(processed_samples)

        return processed_samples
