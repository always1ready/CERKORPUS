"""Описывает скачанные PDF: тип файла, наличие текстового слоя, разрешение скана.

Запуск: python inventory.py /путь/к/папке/с/pdf inventory.csv
Нужен пакет pymupdf. Файлы только читаются.

По этой таблице решается, какие номера распознавать, а из каких текст
можно взять напрямую, и сколько страниц уйдёт в распознавание.
"""

import csv
import hashlib
import sys
from pathlib import Path

import pymupdf

SAMPLE_PAGES = 8  # столько страниц из середины файла смотрим, чтобы не читать весь номер
# Шрифт-невидимка, которым программы распознавания кладут текст поверх скана.
OCR_FONTS = ("glyphless", "invisible", "hidden")


def sha256(path: Path) -> str:
    """Контрольная сумма: по ней потом видно, что файл не подменён и не скачан дважды."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sample_indexes(page_count: int) -> list[int]:
    """Номера страниц из середины: обложка и вклейки в начале нетипичны."""
    if page_count <= SAMPLE_PAGES:
        return list(range(page_count))
    start = (page_count - SAMPLE_PAGES) // 2
    return list(range(start, start + SAMPLE_PAGES))


def describe(path: Path) -> dict[str, object]:
    """Собирает признаки одного файла."""
    with pymupdf.open(path) as doc:
        indexes = sample_indexes(doc.page_count)
        chars = 0
        scan_pages = 0
        dpis: list[float] = []
        fonts: set[str] = set()
        for index in indexes:
            page = doc[index]
            chars += len(page.get_text().strip())
            fonts.update(font[3] for font in page.get_fonts())
            # Страница-скан — это картинка почти во всю страницу. Их бывает несколько
            # слоёв (фон в низком разрешении, текст в высоком), берём самый подробный.
            page_dpis = []
            for image in page.get_image_info():
                x0, y0, x1, y1 = image["bbox"]
                covered = (x1 - x0) * (y1 - y0) / (page.rect.width * page.rect.height)
                if covered > 0.8:
                    page_dpis.append(image["width"] / ((x1 - x0) / 72))
            if page_dpis:
                scan_pages += 1
                dpis.append(max(page_dpis))
        first = doc[indexes[0]].rect
        metadata = doc.metadata or {}
        row: dict[str, object] = {
            "file": path.name,
            "size_mb": round(path.stat().st_size / 1e6, 1),
            "pages": doc.page_count,
            "page_w_pt": round(first.width),
            "page_h_pt": round(first.height),
            "producer": metadata.get("producer", ""),
            "creator": metadata.get("creator", ""),
            "created": metadata.get("creationDate", ""),
            "chars_per_page": round(chars / len(indexes)),
            "scan_share": round(scan_pages / len(indexes), 2),
            "dpi": round(sorted(dpis)[len(dpis) // 2]) if dpis else "",
            "fonts": len(fonts),
        }
    has_text = row["chars_per_page"] >= 200
    is_scan = row["scan_share"] >= 0.5
    ocr_font = any(mark in name.lower() for name in fonts for mark in OCR_FONTS)
    if is_scan and has_text:
        row["kind"] = "scan+layer"   # скан с чужим распознаванием: распознаём заново
    elif is_scan:
        row["kind"] = "scan"         # скан без текста: распознаём
    elif has_text and not ocr_font:
        row["kind"] = "digital"      # электронная вёрстка: текст берём напрямую
    else:
        row["kind"] = "unclear"      # смотреть глазами
    row["sha256"] = sha256(path)
    return row


def main() -> None:
    folder, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    rows = []
    for path in sorted(folder.rglob("*.pdf")):
        try:
            rows.append(describe(path))
        except Exception as error:  # битый файл не должен останавливать опись
            rows.append({"file": path.name, "kind": f"error: {error}"})
    fields = ["file", "kind", "pages", "dpi", "chars_per_page", "scan_share", "fonts",
              "size_mb", "page_w_pt", "page_h_pt", "producer", "creator", "created", "sha256"]
    with out_path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"файлов: {len(rows)}, таблица: {out_path}")


if __name__ == "__main__":
    main()
