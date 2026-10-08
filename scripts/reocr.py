"""Распознаёт страницы PDF заново, только русской моделью Tesseract.

Запуск: python reocr.py 1944-01.pdf data/reocr/1944-01 /путь/к/tessdata
Нужны: tesseract, модель rus.traineddata (tessdata_best), пакет pymupdf.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

DPI = 300  # сканы сделаны в 600 dpi; 300 хватает для кегля журнала и вдвое быстрее


def ocr_page(page: pymupdf.Page, tessdata: Path) -> str:
    """Рендерит страницу в серое изображение и отдаёт его Tesseract."""
    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "page.png"
        page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY).save(image)
        # -l rus без eng: в готовом слое смешанная модель подменяет
        # кириллицу латиницей («В» → «B», «Иосиф» → «eer»).
        # Цена: настоящие латинские вставки будут испорчены, но в ЖМП 1940-х их почти нет.
        result = subprocess.run(
            ["tesseract", str(image), "stdout",
             "--tessdata-dir", str(tessdata), "-l", "rus", "--psm", "3"],
            capture_output=True, check=True,
        )
    return result.stdout.decode("utf-8")


def main() -> None:
    pdf, out_dir, tessdata = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf) as doc:
        for number, page in enumerate(doc, start=1):
            text = ocr_page(page, tessdata)
            (out_dir / f"p{number:03d}.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
