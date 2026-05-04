from collections import deque


class EchoEffect:
    def __init__(self, sample_rate, delay_seconds=0.28, feedback=0.35, mix=0.35):
        self.sample_rate = sample_rate
        self.delay_seconds = delay_seconds
        self.feedback = feedback
        self.mix = mix
        self.build_delay_line()

    def build_delay_line(self):
        delay_samples = max(1, int(self.sample_rate * self.delay_seconds))
        self.delay_line = deque([0] * delay_samples, maxlen=delay_samples)

    def set_parameters(self, delay_seconds=None, feedback=None, mix=None):
        if delay_seconds is not None and delay_seconds != self.delay_seconds:
            self.delay_seconds = delay_seconds
            self.build_delay_line()

        if feedback is not None:
            self.feedback = feedback

        if mix is not None:
            self.mix = mix

    def process_samples(self, samples):
        output = []

        for sample in samples:
            delayed_sample = self.delay_line[0]
            effected_sample = sample + delayed_sample * self.mix
            self.delay_line.append(sample + delayed_sample * self.feedback)
            output.append(effected_sample)

        return output


class ClippingEffect:
    def __init__(self, threshold=1000):
        self.threshold = threshold

    def set_parameters(self, threshold=None):
        if threshold is not None:
            self.threshold = threshold

    def process_samples(self, samples):
        return [
            max(-self.threshold, min(self.threshold, sample))
            for sample in samples
        ]


class AudioEffectChain:
    def __init__(
        self,
        sample_rate,
        echo_enabled=True,
        clipping_enabled=True,
        echo_delay_seconds=0.28,
        echo_feedback=0.35,
        echo_mix=0.35,
        clipping_threshold=1000,
    ):
        self.echo_enabled = echo_enabled
        self.clipping_enabled = clipping_enabled
        self.echo = EchoEffect(
            sample_rate,
            delay_seconds=echo_delay_seconds,
            feedback=echo_feedback,
            mix=echo_mix,
        )
        self.clipping = ClippingEffect(threshold=clipping_threshold)

    def set_settings(
        self,
        echo_enabled=None,
        clipping_enabled=None,
        echo_delay_seconds=None,
        echo_feedback=None,
        echo_mix=None,
        clipping_threshold=None,
    ):
        if echo_enabled is not None:
            self.echo_enabled = echo_enabled

        if clipping_enabled is not None:
            self.clipping_enabled = clipping_enabled

        self.echo.set_parameters(
            delay_seconds=echo_delay_seconds,
            feedback=echo_feedback,
            mix=echo_mix,
        )
        self.clipping.set_parameters(threshold=clipping_threshold)

    def process_samples(self, samples):
        processed_samples = samples

        if self.echo_enabled:
            processed_samples = self.echo.process_samples(processed_samples)

        if self.clipping_enabled:
            processed_samples = self.clipping.process_samples(processed_samples)

        return processed_samples
