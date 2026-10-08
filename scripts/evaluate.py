"""Сравнивает распознанную страницу с ручной расшифровкой: CER и WER.

Запуск: python evaluate.py gold/1944-01_p016.txt data/layer/1944-01/p016.txt
"""

import sys
from collections.abc import Sequence
from pathlib import Path

from textnorm import normalize, words


def edit_distance(a: Sequence, b: Sequence) -> int:
    """Расстояние Левенштейна между двумя последовательностями.

    Работает и для строк (посимвольно), и для списков слов.
    Храним только предыдущую строку таблицы: память O(len(b)).
    """
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            current.append(min(
                previous[j] + 1,                       # удаление
                current[j - 1] + 1,                    # вставка
                previous[j - 1] + (item_a != item_b),  # замена или совпадение
            ))
        previous = current
    return previous[-1]


def main() -> None:
    gold = Path(sys.argv[1]).read_text(encoding="utf-8")
    hypothesis = Path(sys.argv[2]).read_text(encoding="utf-8")
    # Обе метрики считаем после одинаковой нормализации (регистр, ё, переносы),
    # иначе в ошибки попадёт то, что корпусу безразлично.
    gold_chars, hyp_chars = normalize(gold), normalize(hypothesis)
    gold_words, hyp_words = words(gold), words(hypothesis)
    cer = edit_distance(gold_chars, hyp_chars) / len(gold_chars)
    wer = edit_distance(gold_words, hyp_words) / len(gold_words)
    print(f"символов в эталоне: {len(gold_chars)}, слов: {len(gold_words)}")
    print(f"CER = {cer:.3f}, WER = {wer:.3f}")


if __name__ == "__main__":
    main()
