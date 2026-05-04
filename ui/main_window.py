import os
import sys

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from filters.equalizer_bands import EQUALIZER_BANDS
from play_wav import (
    BUFFER_MODE_DUAL_THREAD,
    BUFFER_MODE_SINGLE_THREAD,
    DEFAULT_BLOCK_SIZE,
    DEFAULT_PREFILL_BLOCKS,
    DEFAULT_RING_BUFFER_BLOCKS,
    EqualizerPlayer,
    FILTER_TYPE_CHEBYSHEV2_IIR,
    FILTER_TYPE_CHEBYSHEV_WINDOW_FIR,
)


BANDS = [
    (index, f"{low_hz}-{high_hz}")
    for index, (low_hz, high_hz) in enumerate(EQUALIZER_BANDS, start=1)
]


class PlayerWorker(QObject):
    finished = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        file_path,
        buffer_mode,
        filter_type,
        block_size,
        ring_buffer_blocks,
        prefill_blocks,
        band_gains_db,
        effect_settings,
    ):
        super().__init__()
        self.player = EqualizerPlayer(
            file_path=file_path,
            buffer_mode=buffer_mode,
            filter_type=filter_type,
            block_size=block_size,
            ring_buffer_blocks=ring_buffer_blocks,
            prefill_blocks=prefill_blocks,
            band_gains_db=band_gains_db,
            effect_settings=effect_settings,
        )

    def run(self):
        try:
            self.player.play()
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()

    def stop(self):
        self.player.stop()

    def set_band_gain(self, band_number, gain_db):
        self.player.set_band_gain(band_number, gain_db)

    def set_effect_settings(self, effect_settings):
        self.player.set_effect_settings(effect_settings)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DSP Equalizer")
        self.file_path = ""
        self.worker = None
        self.thread = None
        self.reset_requested = False
        self.gain_labels = {}
        self.gain_sliders = {}

        self.build_ui()

    def build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)

        layout.addWidget(self.build_file_group())
        layout.addWidget(self.build_buffer_group())
        layout.addWidget(self.build_effect_group())
        layout.addWidget(self.build_band_group())
        layout.addLayout(self.build_buttons())

        self.setCentralWidget(central)
        self.resize(1080, 680)

    def build_file_group(self):
        group = QGroupBox("Файл")
        layout = QHBoxLayout(group)

        self.file_label = QLabel("Файл не выбран")
        browse_button = QPushButton("Выбрать WAV")
        browse_button.clicked.connect(self.choose_file)

        layout.addWidget(self.file_label, 1)
        layout.addWidget(browse_button)
        return group

    def build_buffer_group(self):
        group = QGroupBox("Буфер и фильтр")
        layout = QGridLayout(group)

        self.buffer_mode = QComboBox()
        self.buffer_mode.addItem("Двухпоточный", BUFFER_MODE_DUAL_THREAD)
        self.buffer_mode.addItem("Однопоточный", BUFFER_MODE_SINGLE_THREAD)

        self.filter_type = QComboBox()
        self.filter_type.addItem(
            "КИХ, окно Чебышева",
            FILTER_TYPE_CHEBYSHEV_WINDOW_FIR,
        )
        self.filter_type.addItem(
            "БИХ, Чебышев II рода",
            FILTER_TYPE_CHEBYSHEV2_IIR,
        )

        self.block_size = QSpinBox()
        self.block_size.setRange(64, 8192)
        self.block_size.setSingleStep(64)
        self.block_size.setValue(DEFAULT_BLOCK_SIZE)

        self.ring_buffer_blocks = QSpinBox()
        self.ring_buffer_blocks.setRange(1, 128)
        self.ring_buffer_blocks.setValue(DEFAULT_RING_BUFFER_BLOCKS)

        self.prefill_blocks = QSpinBox()
        self.prefill_blocks.setRange(0, 64)
        self.prefill_blocks.setValue(DEFAULT_PREFILL_BLOCKS)

        layout.addWidget(QLabel("Тип буфера"), 0, 0)
        layout.addWidget(self.buffer_mode, 0, 1)
        layout.addWidget(QLabel("Тип фильтра"), 0, 2)
        layout.addWidget(self.filter_type, 0, 3)
        layout.addWidget(QLabel("Размер блока"), 1, 0)
        layout.addWidget(self.block_size, 1, 1)
        layout.addWidget(QLabel("Блоков в кольце"), 1, 2)
        layout.addWidget(self.ring_buffer_blocks, 1, 3)
        layout.addWidget(QLabel("Предзаполнение"), 2, 0)
        layout.addWidget(self.prefill_blocks, 2, 1)

        return group

    def build_effect_group(self):
        group = QGroupBox("Эффекты")
        layout = QGridLayout(group)

        self.reverb_enabled = QCheckBox("Реверберация")
        self.reverb_enabled.setChecked(True)
        self.reverb_delay_ms = self.build_double_spinbox(1, 1000, 70, 1, " мс")
        self.reverb_feedback = self.build_double_spinbox(0, 95, 35, 1, " %")
        self.reverb_mix = self.build_double_spinbox(0, 100, 25, 1, " %")

        self.vibrato_enabled = QCheckBox("Вибрато")
        self.vibrato_enabled.setChecked(True)
        self.vibrato_rate_hz = self.build_double_spinbox(0.1, 20, 5, 0.1, " Гц")
        self.vibrato_depth_ms = self.build_double_spinbox(0, 30, 6, 0.5, " мс")
        self.vibrato_mix = self.build_double_spinbox(0, 100, 45, 1, " %")

        layout.addWidget(self.reverb_enabled, 0, 0)
        layout.addWidget(QLabel("Задержка"), 0, 1)
        layout.addWidget(self.reverb_delay_ms, 0, 2)
        layout.addWidget(QLabel("Обратная связь"), 0, 3)
        layout.addWidget(self.reverb_feedback, 0, 4)
        layout.addWidget(QLabel("Mix"), 0, 5)
        layout.addWidget(self.reverb_mix, 0, 6)

        layout.addWidget(self.vibrato_enabled, 1, 0)
        layout.addWidget(QLabel("Частота"), 1, 1)
        layout.addWidget(self.vibrato_rate_hz, 1, 2)
        layout.addWidget(QLabel("Глубина"), 1, 3)
        layout.addWidget(self.vibrato_depth_ms, 1, 4)
        layout.addWidget(QLabel("Mix"), 1, 5)
        layout.addWidget(self.vibrato_mix, 1, 6)

        controls = [
            self.reverb_enabled,
            self.reverb_delay_ms,
            self.reverb_feedback,
            self.reverb_mix,
            self.vibrato_enabled,
            self.vibrato_rate_hz,
            self.vibrato_depth_ms,
            self.vibrato_mix,
        ]
        for control in controls:
            if isinstance(control, QCheckBox):
                control.stateChanged.connect(self.change_effect_settings)
            else:
                control.valueChanged.connect(self.change_effect_settings)

        return group

    def build_double_spinbox(self, low, high, value, step, suffix):
        spinbox = QDoubleSpinBox()
        spinbox.setRange(low, high)
        spinbox.setSingleStep(step)
        spinbox.setValue(value)
        spinbox.setSuffix(suffix)
        spinbox.setDecimals(1 if isinstance(step, float) and step < 1 else 0)
        return spinbox

    def build_band_group(self):
        group = QGroupBox("10 полос эквалайзера, дБ")
        layout = QHBoxLayout(group)

        for band_number, label_text in BANDS:
            band_layout = QVBoxLayout()
            title = QLabel(label_text)
            title.setAlignment(Qt.AlignCenter)

            value_label = QLabel("0 dB")
            value_label.setAlignment(Qt.AlignCenter)

            slider = QSlider(Qt.Vertical)
            slider.setRange(-100, 0)
            slider.setValue(0)
            slider.valueChanged.connect(
                lambda value, band=band_number: self.change_band_gain(band, value)
            )

            self.gain_labels[band_number] = value_label
            self.gain_sliders[band_number] = slider

            band_layout.addWidget(title)
            band_layout.addWidget(slider, 1)
            band_layout.addWidget(value_label)
            layout.addLayout(band_layout)

        return group

    def build_buttons(self):
        layout = QHBoxLayout()

        self.play_button = QPushButton("Старт")
        self.stop_button = QPushButton("Стоп")
        self.stop_button.setEnabled(False)
        self.status_label = QLabel("Готово")

        self.play_button.clicked.connect(self.start_playback)
        self.stop_button.clicked.connect(self.reset_playback)

        layout.addStretch(1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.play_button)
        layout.addWidget(self.stop_button)

        return layout

    def choose_file(self):
        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Выбрать WAV",
            os.getcwd(),
            "WAV files (*.wav)",
        )

        if file_path:
            self.file_path = file_path
            self.file_label.setText(file_path)

    def current_band_gains(self):
        return {
            band_number: slider.value()
            for band_number, slider in self.gain_sliders.items()
        }

    def current_effect_settings(self):
        return {
            "reverb_enabled": self.reverb_enabled.isChecked(),
            "reverb_delay_ms": self.reverb_delay_ms.value(),
            "reverb_feedback": self.reverb_feedback.value() / 100,
            "reverb_mix": self.reverb_mix.value() / 100,
            "vibrato_enabled": self.vibrato_enabled.isChecked(),
            "vibrato_rate_hz": self.vibrato_rate_hz.value(),
            "vibrato_depth_ms": self.vibrato_depth_ms.value(),
            "vibrato_mix": self.vibrato_mix.value() / 100,
        }

    def change_band_gain(self, band_number, gain_db):
        self.gain_labels[band_number].setText(f"{gain_db} dB")

        if self.worker is not None:
            self.worker.set_band_gain(band_number, gain_db)

    def change_effect_settings(self, *_args):
        if self.worker is not None:
            self.worker.set_effect_settings(self.current_effect_settings())

    def start_playback(self):
        if not self.file_path:
            self.status_label.setText("Выберите WAV-файл")
            return

        if self.worker is not None:
            return

        self.reset_requested = False
        self.thread = QThread()
        self.worker = PlayerWorker(
            file_path=self.file_path,
            buffer_mode=self.buffer_mode.currentData(),
            filter_type=self.filter_type.currentData(),
            block_size=self.block_size.value(),
            ring_buffer_blocks=self.ring_buffer_blocks.value(),
            prefill_blocks=self.prefill_blocks.value(),
            band_gains_db=self.current_band_gains(),
            effect_settings=self.current_effect_settings(),
        )
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.playback_failed)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.playback_finished)

        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Воспроизведение")
        self.thread.start()

    def reset_playback(self):
        self.reset_requested = True
        self.stop_button.setEnabled(False)
        self.status_label.setText("Сброс")

        if self.worker is not None:
            self.worker.stop()
        else:
            self.playback_finished()

    def playback_finished(self):
        self.worker = None
        finished_thread = self.thread
        self.thread = None

        if finished_thread is not None:
            finished_thread.deleteLater()

        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        if self.reset_requested:
            self.status_label.setText("Сброшено")
        else:
            self.status_label.setText("Готово")

    def playback_failed(self, message):
        self.status_label.setText(f"Ошибка: {message}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
