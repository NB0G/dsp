# AI Maintenance Notes

Этот файл предназначен для будущей нейросети или разработчика, который будет поддерживать проект.

Проект - учебный программный аудиопроигрыватель с 6-полосным эквалайзером, двумя типами кольцевого буфера, двумя семействами фильтров и двумя последовательными звуковыми эффектами.

## Задание проекта

- 1 эффект: эхо.
- 2 эффект: клиппинг.
- Количество полос эквалайзера: 6.
- Основной тип фильтра: БИХ Чебышева II рода.
- Альтернативный тип фильтра: КИХ с окном Чебышева.

## Главное ограничение

Нельзя использовать готовое проектирование фильтра из `scipy.signal`, например:

```python
cheby1
cheby2
butter
sosfilt
lfilter
```

SciPy и NumPy допустимы как вычислительные инструменты, но не как готовый генератор Чебышевского фильтра.

## Структура проекта

```text
play_wav.py
effects.py
util.py

buffers/
  dual_thread_ring_buffer.py
  single_thread_ring_buffer.py

filters/
  sinc/
    sinc_filter_bank.py
    lowpass_sinc_filter.py
    bandpass_filter.py
    highpass_sinc_filter.py

  chebyshev/
    chebyshev2_iir_filter_bank.py
    chebyshev_filter_bank.py
    chebyshev_lowpass_filter.py
    chebyshev_bandpass_filter.py
    chebyshev_highpass_filter.py

ui/
  main_window.py
```

## `play_wav.py`

Главный модуль воспроизведения.

Содержит:

- чтение WAV;
- перевод stereo в mono;
- конвертацию PCM bytes <-> samples;
- выбор типа буфера;
- выбор типа фильтра;
- запуск воспроизведения через PyAudio;
- класс `EqualizerPlayer`;
- применение цепочки эффектов после эквалайзера.

Важные константы:

```python
BUFFER_MODE_DUAL_THREAD = "dual_thread"
BUFFER_MODE_SINGLE_THREAD = "single_thread"
FILTER_TYPE_CHEBYSHEV2_IIR = "chebyshev2_iir"
FILTER_TYPE_CHEBYSHEV_WINDOW_FIR = "chebyshev_window_fir"
```

`FILTER_TYPE_CHEBYSHEV` и `FILTER_TYPE_SINC` оставлены как алиасы для совместимости со старым кодом.

## Эффекты

Главный файл:

```text
effects.py
```

Цепочка эффектов применяется в таком порядке:

```text
equalizer -> echo -> clipping -> output
```

`EchoEffect` хранит delay-line между блоками, поэтому эхо не сбрасывается на границах аудиоблоков.

`ClippingEffect` ограничивает амплитуду перед записью в PCM.

## БИХ Чебышева II рода

Главный файл:

```text
filters/chebyshev/chebyshev2_iir_filter_bank.py
```

Это основной фильтр проекта. Он строит 6-полосный банк потоковых IIR-фильтров.

Реализация не вызывает `scipy.signal.cheby2`. В коде явно задается аналоговый прототип Чебышева II рода, затем выполняется частотное масштабирование и билинейное преобразование. Потоковая фильтрация выполняется классом `StreamingIirFilter` из `util.py`.

## КИХ с окном Чебышева

Главный файл:

```text
filters/sinc/sinc_filter_bank.py
```

Это альтернативный фильтр проекта. Он строит FIR-ядро по желаемой 6-полосной АЧХ через `irfft`, затем применяет окно Чебышева из `build_chebyshev_window(...)`.

Старое имя `HammingSincFilterBank` оставлено как алиас, чтобы старые импорты не ломались.

## Полосы эквалайзера

```text
1: 0-100 Hz
2: 100-300 Hz
3: 300-1000 Hz
4: 1000-3000 Hz
5: 3000-8000 Hz
6: 8000-22050 Hz
```

Полоса 1 - НЧ.

Полосы 2-5 - полосовые.

Полоса 6 - ВЧ.

## UI

Главный файл:

```text
ui/main_window.py
```

Интерфейс позволяет:

- выбрать WAV-файл;
- выбрать тип буфера;
- выбрать тип фильтра;
- изменить размер аудиоблока;
- изменить число блоков кольцевого буфера;
- изменить предзаполнение;
- изменить усиление каждой из 6 полос от `0 dB` до `-100 dB`;
- старт/стоп воспроизведения.

## Проверка после изменений

Минимальная проверка:

```powershell
python -m py_compile util.py effects.py play_wav.py ui\main_window.py filters\sinc\*.py filters\chebyshev\*.py buffers\*.py
```

Запуск UI:

```powershell
python ui\main_window.py
```

## Стиль проекта

Это учебный проект. Код должен быть простым и понятным.

Не прятать важную DSP-математику за готовыми библиотечными генераторами, если по ТЗ требуется реализация формулы или алгоритма.
