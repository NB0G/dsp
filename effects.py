from collections import deque


class EchoEffect:
    def __init__(self, sample_rate, delay_seconds=0.28, feedback=0.35, mix=0.35):
        delay_samples = max(1, int(sample_rate * delay_seconds))
        self.feedback = feedback
        self.mix = mix
        self.delay_line = deque([0] * delay_samples, maxlen=delay_samples)

    def process_samples(self, samples):
        output = []

        for sample in samples:
            delayed_sample = self.delay_line[0]
            effected_sample = sample + delayed_sample * self.mix
            self.delay_line.append(sample + delayed_sample * self.feedback)
            output.append(effected_sample)

        return output


class ClippingEffect:
    def __init__(self, threshold=28000):
        self.threshold = threshold

    def process_samples(self, samples):
        return [
            max(-self.threshold, min(self.threshold, sample))
            for sample in samples
        ]


class AudioEffectChain:
    def __init__(self, sample_rate):
        self.effects = [
            EchoEffect(sample_rate),
            ClippingEffect(),
        ]

    def process_samples(self, samples):
        processed_samples = samples

        for effect in self.effects:
            processed_samples = effect.process_samples(processed_samples)

        return processed_samples
