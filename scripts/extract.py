"""Достаёт из PDF готовый текстовый слой, по файлу на страницу.

Запуск: python extract.py 1944-01.pdf data/layer/1944-01
Нужна утилита pdftotext (пакет poppler-utils).
"""

import subprocess
import sys
from pathlib import Path


def extract_pages(pdf: Path) -> list[str]:
    """Возвращает тексты страниц в порядке следования в PDF."""
    # pdftotext разделяет страницы символом перевода формата (\f).
    # Без ключа -layout текст идёт потоком, без выравнивания пробелами:
    # для одноколоночной вёрстки ранних номеров этого достаточно.
    result = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True, check=True,
    )
    pages = result.stdout.decode("utf-8").split("\f")
    # После последней страницы тоже стоит \f, поэтому хвост пустой.
    return pages[:-1] if pages and not pages[-1].strip() else pages


def main() -> None:
    pdf, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    for number, text in enumerate(extract_pages(pdf), start=1):
        # Нумеруем по страницам PDF, а не по печатной пагинации:
        # соответствие между ними устанавливается отдельно (обложка, титул).
        (out_dir / f"p{number:03d}.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
