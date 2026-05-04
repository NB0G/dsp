EQUALIZER_BANDS = [
    (0, 31),
    (31, 62),
    (62, 125),
    (125, 250),
    (250, 500),
    (500, 1000),
    (1000, 2000),
    (2000, 4000),
    (4000, 8000),
    (8000, 22050),
]


def band_filter_type(band_index):
    if band_index == 1:
        return "low_pass"

    if band_index == len(EQUALIZER_BANDS):
        return "high_pass"

    return "band_pass"
