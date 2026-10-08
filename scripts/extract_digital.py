"""Достаёт текст из PDF электронной вёрстки вместе со шрифтом каждой строки.

Запуск: python extract_digital.py 2010-01.pdf data/digital/2010-01.tsv
Нужен пакет pymupdf.

Для номеров, свёрстанных на компьютере, распознавание не нужно: текст в файле
настоящий. Задача другая — не перемешать основной текст с врезками, подписями
и колонтитулами. Шрифт строки позволяет развести их уже после извлечения.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

import pymupdf


def line_records(page: pymupdf.Page) -> list[tuple[int, str, float, str]]:
    """Возвращает строки страницы: номер блока, шрифт, кегль, текст.

    Порядок блоков берём как в файле, без сортировки по координатам.
    InDesign пишет текст по цепочкам связанных фреймов, поэтому статья идёт
    подряд, даже когда она перетекает через колонки и иллюстрации.
    Сортировка по координатам (sort=True) эту связность разрушает.
    """
    records = []
    for block_number, block in enumerate(page.get_text("dict")["blocks"]):
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"])
            if not text.strip():
                continue
            # Шрифт строки — тот, которым набрано больше всего знаков.
            # Так выделенная полужирным дата в начале абзаца остаётся в основном тексте.
            weights: Counter[tuple[str, float]] = Counter()
            for span in line["spans"]:
                weights[(span["font"], round(span["size"]))] += len(span["text"])
            (font, size), _ = weights.most_common(1)[0]
            records.append((block_number, font, size, text))
    return records


def main() -> None:
    pdf, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf) as doc, out_path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, delimiter="\t")
        writer.writerow(["page", "block", "font", "size", "text"])
        for page_number, page in enumerate(doc, start=1):
            for record in line_records(page):
                writer.writerow([page_number, *record])


if __name__ == "__main__":
    main()
