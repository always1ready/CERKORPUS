"""Собирает очищенный текст четырёх пробных номеров по страницам журнала.

Запуск: python prepare.py /путь/к/pdf2010 > отчёт
Читает data/reocr/<номер>/ (сканы) и PDF 2010 года, пишет data/clean/pages.jsonl:
одна запись на печатную страницу с рубрикой, заглавием и автором по оглавлению.
"""

import csv
import itertools
import json
import re
import sys
from pathlib import Path

import pymorphy3
import pymupdf

from textnorm import dehyphenate

ROOT = Path(__file__).parent
MORPH = pymorphy3.MorphAnalyzer()

# Страницы PDF, которые не относятся к содержанию номера: обложки, титулы,
# оглавления, выходные данные.
EXCLUDE = {
    "1944-01": {1, 2, 3, 4, 31, 34, 35, 36},
    "1960-01": {1, 2, 3, 79, 80},
    "1982-01": {1, 3, 91, 92},
}
# На вклейках с иллюстрациями только подписи: столько слов и меньше.
PLATE_TOKENS = {"1944-01": 40, "1960-01": 40, "1982-01": 75}

# Роли шрифтов в номере 2010 года (см. extract_digital.py).
# Оставляем основной текст, врезки с цитатами из выступлений, вопросы интервью,
# заголовки и биографические справки; убираем подписи к фото, сноски,
# колонтитулы, вынесенные цитаты-повторы и выходные данные.
KEEP_2010 = {
    ("MetaPro-MediumItalic", 10), ("MetaPro-Black", 17), ("MetaPro-Black", 19),
    ("MetaPro-Black", 20), ("MetaPro-Black", 40), ("MetaPro-Medium", 14),
    ("BodoniSevITC-Regular", 13), ("MyriadPro-It", 9),
    ("PragmaticaCondLight-Reg", 9), ("Blagovest-One", 27),
}

JUNK_PATTERNS = [
    re.compile(r"^\d{1,3}\*?$"),                     # колонцифра, сигнатура «3*»
    re.compile(r"^\d+\s*Ж\.?\s*М\.?\s*П\.?.*$"),      # сигнатура «3 Ж. М. П. № 1»
]


def is_junk(line: str) -> bool:
    """Строки без связного текста: номера страниц, сигнатуры, обрывки рамок."""
    stripped = line.strip()
    if not stripped:
        return False
    if any(pattern.match(stripped) for pattern in JUNK_PATTERNS):
        return True
    letters = sum(ch.isalpha() for ch in stripped)
    if "(" in stripped or ")" in stripped:
        return False   # хвост библейской ссылки на отдельной строке: «10, 4).»
    if letters == 0:
        return True
    # Короткая строка, где букв меньше половины, — почти всегда мусор распознавания.
    return len(stripped) < 40 and letters / len(stripped) < 0.5


def fix_i_n(word: str) -> str:
    """Исправляет путаницу «и» и «н», если замена даёт единственное словарное слово.

    Нужна для номера 1982 года (мелкий кегль, скан 150 dpi). Имена собственные
    так не исправить: их нет в словаре.
    """
    lower = word.lower()
    if len(lower) < 4 or MORPH.word_is_known(lower):
        return word
    positions = [i for i, ch in enumerate(lower) if ch in "ин"]
    if not positions or len(positions) > 8:
        return word
    for count in (1, 2):
        candidates = set()
        for combo in itertools.combinations(positions, count):
            letters = list(word)
            for i in combo:
                letters[i] = {"и": "н", "н": "и", "И": "Н", "Н": "И"}[letters[i]]
            if MORPH.word_is_known("".join(letters).lower()):
                candidates.add("".join(letters))
        if candidates:
            return candidates.pop() if len(candidates) == 1 else word
    return word


def read_toc(issue: str) -> list[dict[str, str]]:
    with (ROOT / "meta" / f"toc_{issue}.tsv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file, delimiter="\t"))
    for row in rows:
        row["page"] = int(row["page"])
    return sorted(rows, key=lambda row: row["page"])


def toc_entry(toc: list[dict], page: int | None) -> dict:
    """Статья, к которой относится страница: последняя, начавшаяся не позже неё.

    Если на странице начинается несколько материалов, страница целиком
    отходит к последнему из них. Для подсчётов по рубрикам этого хватает.
    """
    current = {"rubric": "(вне оглавления)", "author": "", "title": ""}
    for row in toc:
        if page is not None and row["page"] <= page:
            current = row
    return current


def printed_number(lines: list[str]) -> int | None:
    """Печатный номер страницы: строка из одних цифр внизу или вверху страницы."""
    candidates = [l.strip() for l in lines[-3:] + lines[:1] if l.strip()]
    for line in reversed(candidates):
        if re.fullmatch(r"\d{1,3}", line):
            return int(line)
    return None


def assign_numbers(detected: list[int | None]) -> list[int | None]:
    """Восстанавливает печатные номера по распознанным колонцифрам.

    Распознанному номеру верим, если он больше предыдущего не более чем на 3
    (пропущенный оборот вклейки даёт скачок на 2); иначе это ошибка
    распознавания, и берём предыдущий плюс один. Начальные страницы без
    номера получают номера назад от первого распознанного.
    """
    numbers: list[int | None] = []
    previous = None
    for value in detected:
        if previous is None:
            number = value
        elif value is not None and 1 <= value - previous <= 3:
            number = value
        else:
            number = previous + 1
        numbers.append(number)
        if number is not None:
            previous = number
    first = next((i for i, n in enumerate(numbers) if n is not None), None)
    if first is not None:
        for i in range(first - 1, -1, -1):
            numbers[i] = numbers[i + 1] - 1
    return numbers


def scanned_pages(issue: str) -> list[dict]:
    """Страницы скана: текст без мусора и печатный номер."""
    raw_pages = []
    for path in sorted((ROOT / "data" / "reocr" / issue).glob("p*.txt")):
        pdf_page = int(path.stem[1:])
        raw = path.read_text(encoding="utf-8")
        lines = [l for l in raw.splitlines() if l.strip()]
        # Вклейки с иллюстрациями: в 1982 году подписи к ним длиннее.
        is_plate = len(raw.split()) < PLATE_TOKENS[issue]
        excluded = pdf_page in EXCLUDE[issue]
        raw_pages.append((pdf_page, lines, is_plate, excluded))
    # Номера восстанавливаем только по страницам основного текста.
    body = [p for p in raw_pages if not p[2] and not p[3]]
    if issue == "1944-01":
        numbers = [p[0] - 2 for p in body]   # сдвиг постоянный, колонцифры распознаются плохо
    else:
        numbers = assign_numbers([printed_number(p[1]) for p in body])
    if issue == "1982-01":
        # Фронтиспис (с. 2 PDF) вне пагинации.
        numbers = [None if p[0] == 2 else n for p, n in zip(body, numbers)]
    pages = []
    for (pdf_page, lines, _, _), number in zip(body, numbers):
        text = "\n".join(l for l in lines if not is_junk(l))
        if issue == "1982-01":
            text = re.sub(r"[А-Яа-яЁё]+", lambda m: fix_i_n(m.group()), text)
        pages.append({"pdf_page": pdf_page, "page": number, "text": text})
    return pages


def digital_pages(pdf: Path) -> list[dict]:
    """Страницы электронной вёрстки 2010 года: развороты делим по середине."""
    by_page: dict[int, list[str]] = {}
    with pymupdf.open(pdf) as doc:
        for pdf_page, page in enumerate(doc, start=1):
            is_spread = page.rect.width > page.rect.height
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    weights: dict[tuple[str, int], int] = {}
                    for span in line["spans"]:
                        key = (span["font"], round(span["size"]))
                        weights[key] = weights.get(key, 0) + len(span["text"])
                    if not weights:
                        continue
                    font = max(weights, key=weights.get)
                    if not (font[0].startswith("CharterITC") or font in KEEP_2010):
                        continue
                    text = "".join(span["text"] for span in line["spans"])
                    if not text.strip():
                        continue
                    if pdf_page == 1:
                        number = 1
                    elif pdf_page == doc.page_count:
                        number = 2 * pdf_page - 2
                    else:
                        left = line["bbox"][0] < page.rect.width / 2
                        number = 2 * pdf_page - 2 if left or not is_spread else 2 * pdf_page - 1
                    by_page.setdefault(number, []).append(text)
    return [{"pdf_page": (n + 2) // 2, "page": n, "text": "\n".join(lines)}
            for n, lines in sorted(by_page.items())]


def main() -> None:
    pdf2010 = Path(sys.argv[1]) / "2010-01.pdf"
    out_dir = ROOT / "data" / "clean"
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for issue in ("1944-01", "1960-01", "1982-01", "2010-01"):
        toc = read_toc(issue)
        # В 2010 году оглавление на с. 4 отсекается по шрифту, обращение редакции остаётся.
        pages = digital_pages(pdf2010) if issue == "2010-01" else scanned_pages(issue)
        for page in pages:
            entry = toc_entry(toc, page["page"])
            records.append({
                "issue": issue, "year": int(issue[:4]), **page,
                "rubric": entry["rubric"], "title": entry["title"],
                "author": entry["author"],
                "text": dehyphenate(page["text"]),
            })
        mapped = [p["page"] for p in pages]
        print(issue, "страниц:", len(pages), "печатные:", mapped[0], "…", mapped[-1],
              "без номера:", sum(m is None for m in mapped))
    with (out_dir / "pages.jsonl").open("w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
