# AI Maintenance Notes

Этот файл предназначен для будущей нейросети или разработчика, который будет поддерживать проект.

Проект - учебный программный аудиопроигрыватель с 10-полосным эквалайзером, двумя типами кольцевого буфера, двумя типами фильтров и двумя аудиоэффектами.

## Текущее задание

- 1 эффект: реверберация.
- 2 эффект: вибрато.
- Количество полос эквалайзера: 10.
- Основной тип фильтра: КИХ, окно Чебышева.
- Альтернативный тип фильтра: БИХ, Чебышев II рода.

## Ограничение по DSP

Не использовать готовое проектирование фильтра из `scipy.signal`, например:

```python
cheby1
cheby2
butter
sosfilt
lfilter
```

SciPy можно использовать как вычислительный инструмент для FFT и оконных функций, но важная DSP-логика проекта должна оставаться явно видимой в коде.

## Структура

```text
play_wav.py
util.py
effects.py

buffers/
  dual_thread_ring_buffer.py
  single_thread_ring_buffer.py

filters/
  equalizer_bands.py
  sinc/
    sinc_filter_bank.py
  chebyshev/
    chebyshev_filter_bank.py
  chebyshev2/
    chebyshev2_filter_bank.py

ui/
  main_window.py
```

## Главный поток обработки

`EqualizerPlayer` в `play_wav.py` читает WAV, переводит stereo в mono, строит банк фильтров и цепочку эффектов:

```text
read wav -> equalizer filter bank -> reverb -> vibrato -> ring buffer -> PyAudio
```

Эффекты находятся в `effects.py`:

- `ReverbEffect` - задержка с обратной связью и wet/dry mix.
- `VibratoEffect` - модулированная линия задержки с дробным чтением.
- `AudioEffectChain` - применяет реверберацию, затем вибрато.

## Полосы эквалайзера

Единственный источник правды для полос - `filters/equalizer_bands.py`.

```text
1: 0-31 Hz
2: 31-62 Hz
3: 62-125 Hz
4: 125-250 Hz
5: 250-500 Hz
6: 500-1000 Hz
7: 1000-2000 Hz
8: 2000-4000 Hz
9: 4000-8000 Hz
10: 8000-22050 Hz
```

Полоса 1 - НЧ, полосы 2-9 - полосовые, полоса 10 - ВЧ.

## Типы фильтров

Константы в `play_wav.py`:

```python
FILTER_TYPE_CHEBYSHEV_WINDOW_FIR = "chebyshev_window_fir"
FILTER_TYPE_CHEBYSHEV2_IIR = "chebyshev2_iir"
```

Для совместимости старые имена оставлены алиасами:

```python
FILTER_TYPE_SINC = FILTER_TYPE_CHEBYSHEV_WINDOW_FIR
FILTER_TYPE_CHEBYSHEV = FILTER_TYPE_CHEBYSHEV2_IIR
```

### Основной фильтр

`filters/sinc/sinc_filter_bank.py` теперь содержит `ChebyshevWindowFirFilterBank`.

Банк строит суммарную АЧХ 10 полос, получает FIR-ядро через `irfft`, берет центральный участок и применяет окно Чебышева через `build_chebyshev_window(...)` из `util.py`.

### Альтернативный фильтр

`filters/chebyshev2/chebyshev2_filter_bank.py` содержит `Chebyshev2FilterBank`.

Формулы АЧХ Чебышева II рода прописаны явно, без `scipy.signal.cheby2`. Для потоковой обработки используется общий `StreamingFirFilter`, как и в остальных банках проекта.

## UI

Главный файл интерфейса - `ui/main_window.py`.

Интерфейс позволяет:

- выбрать WAV-файл;
- выбрать тип буфера;
- выбрать основной или альтернативный тип фильтра;
- изменить размер аудиоблока, размер кольцевого буфера и предзаполнение;
- изменить усиление каждой из 10 полос от `0 dB` до `-100 dB`;
- запустить и остановить воспроизведение.

## Проверка

Минимальная проверка после изменений:

```powershell
python -m py_compile util.py effects.py play_wav.py ui\main_window.py filters\equalizer_bands.py filters\sinc\*.py filters\chebyshev\*.py filters\chebyshev2\*.py buffers\*.py
```

Если `python` не настроен в PATH, использовать установленный Python 3.12:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m py_compile ...
```
