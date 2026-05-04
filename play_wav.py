import time
import wave
from array import array
from threading import Thread

import pyaudio

from buffers.dual_thread_ring_buffer import RingBufferDualThread
from effects import AudioEffectChain
from filters.chebyshev.chebyshev2_iir_filter_bank import Chebyshev2IirFilterBank
from filters.sinc.sinc_filter_bank import (
    DEFAULT_TAP_COUNT,
    ChebyshevWindowFirFilterBank,
)
from buffers.single_thread_ring_buffer import SingleThreadRingBuffer


DEFAULT_BLOCK_SIZE = 128
DEFAULT_RING_BUFFER_BLOCKS = 8
DEFAULT_PREFILL_BLOCKS = 2
BUFFER_MODE_DUAL_THREAD = "dual_thread"
BUFFER_MODE_SINGLE_THREAD = "single_thread"
FILTER_TYPE_CHEBYSHEV2_IIR = "chebyshev2_iir"
FILTER_TYPE_CHEBYSHEV_WINDOW_FIR = "chebyshev_window_fir"
FILTER_TYPE_CHEBYSHEV = FILTER_TYPE_CHEBYSHEV2_IIR
FILTER_TYPE_SINC = FILTER_TYPE_CHEBYSHEV_WINDOW_FIR
OUTPUT_CHANNELS = 1
BYTES_PER_SAMPLE = 2
DEFAULT_BAND_GAINS_DB = {
    1: 0,
    2: 0,
    3: 0,
    4: 0,
    5: 0,
    6: 0,
}


def clamp_int16(value):
    return max(-32768, min(32767, int(value)))


def stereo_to_mono(samples):
    mono_samples = []

    for index in range(0, len(samples) - 1, 2):
        left = samples[index]
        right = samples[index + 1]
        mono_samples.append((left + right) / 2)

    return mono_samples


def bytes_to_samples(frames, channels):
    samples = array("h")
    samples.frombytes(frames)

    if channels == 2:
        return stereo_to_mono(samples)

    return samples


def samples_to_bytes(samples):
    pcm = array("h")

    for sample in samples:
        pcm.append(clamp_int16(sample))

    return pcm.tobytes()


def build_sinc_filter_bank(sample_rate, taps, band_gains_db=None):
    gains = DEFAULT_BAND_GAINS_DB.copy()
    if band_gains_db is not None:
        gains.update(band_gains_db)

    return ChebyshevWindowFirFilterBank(sample_rate, gains, taps)


def build_chebyshev_filter_bank(sample_rate, band_gains_db=None):
    gains = DEFAULT_BAND_GAINS_DB.copy()
    if band_gains_db is not None:
        gains.update(band_gains_db)

    return Chebyshev2IirFilterBank(sample_rate, gains)


def build_filter_bank(
    sample_rate,
    taps,
    band_gains_db=None,
    filter_type=FILTER_TYPE_CHEBYSHEV2_IIR,
):
    if filter_type == FILTER_TYPE_CHEBYSHEV2_IIR:
        return build_chebyshev_filter_bank(sample_rate, band_gains_db)

    return build_sinc_filter_bank(sample_rate, taps, band_gains_db)


def mix_filter_outputs(filter_outputs):
    mixed_samples = []

    for samples_at_time in zip(*filter_outputs):
        mixed_samples.append(sum(samples_at_time))

    return mixed_samples


def process_samples_with_filter_bank(samples, filters):
    if hasattr(filters, "process_samples"):
        return filters.process_samples(samples)

    filter_outputs = []

    for audio_filter in filters:
        filter_outputs.append(audio_filter.process_samples(samples))

    return mix_filter_outputs(filter_outputs)


class EqualizerPlayer:
    def __init__(
        self,
        file_path,
        buffer_mode=BUFFER_MODE_DUAL_THREAD,
        filter_type=FILTER_TYPE_CHEBYSHEV2_IIR,
        taps=DEFAULT_TAP_COUNT,
        block_size=DEFAULT_BLOCK_SIZE,
        ring_buffer_blocks=DEFAULT_RING_BUFFER_BLOCKS,
        prefill_blocks=DEFAULT_PREFILL_BLOCKS,
        band_gains_db=None,
    ):
        self.file_path = file_path
        self.buffer_mode = buffer_mode
        self.filter_type = filter_type
        self.taps = taps
        self.block_size = block_size
        self.ring_buffer_blocks = ring_buffer_blocks
        self.prefill_blocks = prefill_blocks
        self.band_gains_db = DEFAULT_BAND_GAINS_DB.copy()
        self.filters = []
        self.effects = None
        self.ring_buffer = None
        self.stopped = False

        if band_gains_db is not None:
            self.band_gains_db.update(band_gains_db)

    def set_band_gain(self, band_number, gain_db):
        self.band_gains_db[band_number] = gain_db

        if self.filters:
            if hasattr(self.filters, "set_band_gain"):
                self.filters.set_band_gain(band_number, gain_db)
            else:
                self.filters[band_number - 1].set_gain_db(gain_db)

    def stop(self):
        self.stopped = True

        if self.ring_buffer is not None:
            self.ring_buffer.close()

    def play(self):
        if self.buffer_mode == BUFFER_MODE_SINGLE_THREAD:
            self.play_single_thread()
        else:
            self.play_dual_thread()

    def build_filters(self, sample_rate):
        self.filters = build_filter_bank(
            sample_rate,
            self.taps,
            self.band_gains_db,
            self.filter_type,
        )
        self.effects = AudioEffectChain(sample_rate)

    def process_audio_block(self, samples):
        filtered_samples = process_samples_with_filter_bank(samples, self.filters)
        return self.effects.process_samples(filtered_samples)

    def write_filtered_audio_to_buffer_dual_thread(self, wav_file):
        channels = wav_file.getnchannels()

        frames = wav_file.readframes(self.block_size)
        while frames and not self.stopped:
            samples = bytes_to_samples(frames, channels)
            filtered_samples = self.process_audio_block(samples)
            self.ring_buffer.write(samples_to_bytes(filtered_samples))
            frames = wav_file.readframes(self.block_size)

        self.ring_buffer.close()

    def play_dual_thread(self):
        wav_file = wave.open(self.file_path, "rb")
        sample_rate = wav_file.getframerate()
        self.build_filters(sample_rate)

        bytes_per_block = self.block_size * OUTPUT_CHANNELS * BYTES_PER_SAMPLE
        self.ring_buffer = RingBufferDualThread(
            bytes_per_block * self.ring_buffer_blocks
        )
        prefill_size = bytes_per_block * self.prefill_blocks

        producer = Thread(
            target=self.write_filtered_audio_to_buffer_dual_thread,
            args=(wav_file,),
        )
        producer.start()

        while (
            self.ring_buffer.available() < prefill_size
            and producer.is_alive()
            and not self.stopped
        ):
            time.sleep(0.001)

        def play_from_ring_buffer(in_data, frame_count, time_info, status_flags):
            bytes_needed = frame_count * OUTPUT_CHANNELS * BYTES_PER_SAMPLE
            data, finished = self.ring_buffer.read(bytes_needed)

            if finished or self.stopped:
                return data, pyaudio.paComplete

            return data, pyaudio.paContinue

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=OUTPUT_CHANNELS,
            rate=sample_rate,
            output=True,
            frames_per_buffer=self.block_size,
            stream_callback=play_from_ring_buffer,
            start=False,
        )

        stream.start_stream()

        while stream.is_active() and not self.stopped:
            time.sleep(0.05)

        self.stop()
        stream.stop_stream()
        stream.close()
        audio.terminate()
        producer.join()
        wav_file.close()

    def play_single_thread(self):
        wav_file = wave.open(self.file_path, "rb")
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        self.build_filters(sample_rate)

        bytes_per_block = self.block_size * OUTPUT_CHANNELS * BYTES_PER_SAMPLE
        self.ring_buffer = SingleThreadRingBuffer(
            bytes_per_block * self.ring_buffer_blocks
        )

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=OUTPUT_CHANNELS,
            rate=sample_rate,
            output=True,
            frames_per_buffer=self.block_size,
        )

        frames = wav_file.readframes(self.block_size)
        while frames and not self.stopped:
            samples = bytes_to_samples(frames, channels)
            filtered_samples = self.process_audio_block(samples)
            self.ring_buffer.write(samples_to_bytes(filtered_samples))

            data, finished = self.ring_buffer.read(bytes_per_block)
            stream.write(data)

            if finished:
                break

            frames = wav_file.readframes(self.block_size)

        self.ring_buffer.close()

        while self.ring_buffer.available() > 0 and not self.stopped:
            data, finished = self.ring_buffer.read(bytes_per_block)
            stream.write(data)

            if finished:
                break

        stream.stop_stream()
        stream.close()
        audio.terminate()
        wav_file.close()


def play_wav_with_filter_dual_thread(
    file_path,
    taps=DEFAULT_TAP_COUNT,
    block_size=DEFAULT_BLOCK_SIZE,
    band_gains_db=None,
    ring_buffer_blocks=DEFAULT_RING_BUFFER_BLOCKS,
    prefill_blocks=DEFAULT_PREFILL_BLOCKS,
    filter_type=FILTER_TYPE_CHEBYSHEV2_IIR,
):
    player = EqualizerPlayer(
        file_path,
        BUFFER_MODE_DUAL_THREAD,
        filter_type,
        taps,
        block_size,
        ring_buffer_blocks,
        prefill_blocks,
        band_gains_db,
    )
    player.play()


def play_wav_with_filter_single_thread(
    file_path,
    taps=DEFAULT_TAP_COUNT,
    block_size=DEFAULT_BLOCK_SIZE,
    band_gains_db=None,
    ring_buffer_blocks=DEFAULT_RING_BUFFER_BLOCKS,
    filter_type=FILTER_TYPE_CHEBYSHEV2_IIR,
):
    player = EqualizerPlayer(
        file_path,
        BUFFER_MODE_SINGLE_THREAD,
        filter_type,
        taps,
        block_size,
        ring_buffer_blocks,
        0,
        band_gains_db,
    )
    player.play()


if __name__ == "__main__":
    # play_wav_with_filter_single_thread("audio1.wav")
    play_wav_with_filter_dual_thread("audio.wav")
