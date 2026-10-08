"""Оценивает качество распознавания без эталона: по странице и по номеру.

Запуск: python quality.py data/layer/1944-01 > layer.csv
"""

import csv
import re
import sys
from pathlib import Path

import pymorphy3

from textnorm import words

MORPH = pymorphy3.MorphAnalyzer()
LATIN_RE = re.compile(r"[a-z]")
CYRILLIC_RE = re.compile(r"[а-яё]")
# Однобуквенные слова, которые в русском тексте законны.
ONE_LETTER = set("авикосуяжбг")
# Короткие слова словарь «узнаёт» слишком охотно (любой слог похож на сокращение),
# поэтому долю словарных считаем только по словам от четырёх букв.
MIN_LEN = 4


def page_metrics(text: str) -> dict[str, float | int]:
    """Считает показатели качества для одной страницы."""
    tokens = words(text)
    latin = [t for t in tokens if LATIN_RE.search(t)]
    long_cyr = [
        t for t in tokens
        if len(t) >= MIN_LEN and CYRILLIC_RE.search(t) and not LATIN_RE.search(t)
    ]
    known = [t for t in long_cyr if MORPH.word_is_known(t)]
    stray = [t for t in tokens if len(t) == 1 and t not in ONE_LETTER]
    return {
        "tokens": len(tokens),
        # Латиница в русском тексте 1940-х — почти всегда ошибка распознавания.
        "latin": len(latin),
        # Одиночные буквы вне списка — мусор от рамок, пятен и картинок.
        "stray": len(stray),
        "long_cyr": len(long_cyr),
        "known": len(known),
    }


def share(part: int, whole: int) -> str:
    return f"{part / whole:.3f}" if whole else ""


def main() -> None:
    pages = sorted(Path(sys.argv[1]).glob("p*.txt"))
    fields = ["page", "tokens", "latin", "stray", "long_cyr", "known",
              "latin_share", "known_share"]
    writer = csv.DictWriter(sys.stdout, fieldnames=fields)
    writer.writeheader()
    total = dict.fromkeys(fields[1:6], 0)
    for path in pages:
        row = page_metrics(path.read_text(encoding="utf-8"))
        for key in total:
            total[key] += row[key]
        writer.writerow({
            "page": path.stem, **row,
            "latin_share": share(row["latin"], row["tokens"]),
            "known_share": share(row["known"], row["long_cyr"]),
        })
    writer.writerow({
        "page": "ALL", **total,
        "latin_share": share(total["latin"], total["tokens"]),
        "known_share": share(total["known"], total["long_cyr"]),
    })


if __name__ == "__main__":
    main()
