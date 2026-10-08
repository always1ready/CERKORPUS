"""Расчёты для страницы о пробном корпусе ЖМП.

Запуск: python analysis.py site/data
Читает data/clean/pages.jsonl и meta/toc_*.tsv, пишет сводные таблицы CSV.
Тексты журнала в выходные таблицы не попадают, только счётчики и короткие формы.
"""

import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pymorphy3

import slavonic
from textnorm import words

ROOT = Path(__file__).parent
MORPH = pymorphy3.MorphAnalyzer()
ISSUES = ["1944-01", "1960-01", "1982-01", "2010-01"]
LAST_PAGE = {"1944-01": 31, "1960-01": 79, "1982-01": 80, "2010-01": 80}


def load_pages() -> list[dict]:
    with (ROOT / "data" / "clean" / "pages.jsonl").open(encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def write(path: Path, header: list[str], rows: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


_lemmas: dict[str, tuple[str, set, bool]] = {}


def lemma(word: str) -> tuple[str, set, bool]:
    """Лемма, граммемы и признак словарности; кэшируем, слов немного."""
    if word not in _lemmas:
        parse = MORPH.parse(word)[0]
        _lemmas[word] = (parse.normal_form, set(parse.tag.grammemes), MORPH.word_is_known(word))
    return _lemmas[word]


# --- Объём ---------------------------------------------------------------

def volume(pages: list[dict], out: Path) -> dict[str, int]:
    sizes = {}
    rows = []
    for issue in ISSUES:
        issue_pages = [p for p in pages if p["issue"] == issue]
        n = sum(len(words(p["text"])) for p in issue_pages)
        sizes[issue] = n
        rows.append([issue, len(issue_pages), n])
    write(out / "volume.csv", ["issue", "pages", "words"], rows)
    return sizes


# --- Ключевые слова ------------------------------------------------------

SKIP_POS = {"PREP", "CONJ", "PRCL", "NPRO", "INTJ", "NUMR"}
# Имена собственные исключены: им посвящён раздел об иерархах.
SKIP_TAGS = {"Name", "Surn", "Patr", "Geox", "Orgn", "Abbr", "Init"}


def log_likelihood(a: int, b: int, n1: int, n2: int) -> float:
    """Статистика G² (Даннинг 1993) для слова с частотами a и b в двух подкорпусах."""
    e1 = n1 * (a + b) / (n1 + n2)
    e2 = n2 * (a + b) / (n1 + n2)
    return 2 * ((a * math.log(a / e1) if a else 0) + (b * math.log(b / e2) if b else 0))


def keywords(pages: list[dict], out: Path, top: int = 12) -> None:
    counts = {issue: Counter() for issue in ISSUES}
    for page in pages:
        for word in words(page["text"]):
            if len(word) < 3 or not re.fullmatch("[а-яё]+", word):
                continue
            norm, tags, known = lemma(word)
            if known and not tags & SKIP_POS and not tags & SKIP_TAGS:
                counts[page["issue"]][norm] += 1
    rows = []
    for issue in ISSUES:
        rest = Counter()
        for other in ISSUES:
            if other != issue:
                rest.update(counts[other])
        n1, n2 = sum(counts[issue].values()), sum(rest.values())
        scored = []
        for word, a in counts[issue].items():
            b = rest[word]
            if a >= 5 and a / n1 > b / n2:
                scored.append((log_likelihood(a, b, n1, n2), word, a, b))
        scored.sort(reverse=True)
        for g2, word, a, b in scored[:top]:
            rows.append([issue, word, a, round(a / n1 * 1e4, 1), round(b / n2 * 1e4, 1), round(g2, 1)])
    write(out / "keywords.csv", ["issue", "lemma", "freq", "ipm10k", "ipm10k_rest", "g2"], rows)


# --- Церковнославянские формы --------------------------------------------

def slavonic_forms(pages: list[dict], sizes: dict, out: Path) -> None:
    by_issue = Counter()
    by_rubric = Counter()
    rubric_words = Counter()
    forms = defaultdict(Counter)
    for page in pages:
        found = slavonic.find(page["text"])
        by_issue[page["issue"]] += len(found)
        key = (page["issue"], page["rubric"])
        by_rubric[key] += len(found)
        rubric_words[key] += len(words(page["text"]))
        forms[page["issue"]].update(found)
    write(out / "slavonic_issue.csv", ["issue", "forms", "per10k", "examples"],
          [[i, by_issue[i], round(by_issue[i] / sizes[i] * 1e4, 1),
            ", ".join(w for w, _ in forms[i].most_common(8))] for i in ISSUES])
    write(out / "slavonic_rubric.csv", ["issue", "rubric", "forms", "words", "per10k"],
          [[i, r, by_rubric[(i, r)], n, round(by_rubric[(i, r)] / n * 1e4, 1)]
           for (i, r), n in sorted(rubric_words.items()) if n >= 500])


# --- Речевой этикет ------------------------------------------------------

ETIQUETTE = {
    "Святейший (во всех формах)": r"\bСвятейш\w*",
    "Блаженнейший": r"\bБлаженнейш\w*",
    "Высокопреосвященнейший / Высокопреосвященство": r"\bВысокопреосвящен\w*",
    "Преосвященный / Преосвященство": r"\bПреосвящен\w*",
    "«Патриарх Московский и всея Руси»": r"Патриарх\w*\s+Московск\w+\s+и\s+всея\s+Руси",
    "«Ваше Святейшество / Блаженство»": r"Ваше\w*\s+(Святейшеств|Блаженств)\w*",
    "«Возлюбленные о Господе…»": r"[Вв]озлюбленн\w+\s+о\s+Господе",
    "«о Христе»": r"\bо\s+Христе\b",
    "«по благословению»": r"\bпо\s+благословению\b",
    "«многая лета»": r"[Мм]ногая\s+лета",
}


def etiquette(pages: list[dict], sizes: dict, out: Path) -> None:
    rows = []
    for name, pattern in ETIQUETTE.items():
        regex = re.compile(pattern)
        for issue in ISSUES:
            text = "\n".join(p["text"] for p in pages if p["issue"] == issue)
            count = len(regex.findall(re.sub(r"\s+", " ", text)))
            rows.append([name, issue, count, round(count / sizes[issue] * 1e4, 1)])
    write(out / "etiquette.csv", ["formula", "issue", "count", "per10k"], rows)


# --- Слово «мир» ---------------------------------------------------------

def mir_collocations(pages: list[dict], out: Path, top: int = 8) -> None:
    """Устойчивые сочетания со словом «мир» (лемма) в окне ±2 слова."""
    stop = {"и", "в", "во", "на", "с", "со", "к", "о", "об", "за", "по", "от", "для",
            "не", "что", "как", "а", "но", "же", "бы", "его", "ее", "их", "это", "который",
            "этот", "весь", "мир", "из", "у", "при"}
    rows = []
    for issue in ISSUES:
        collocates = Counter()
        total = 0
        for page in pages:
            if page["issue"] != issue:
                continue
            tokens = words(page["text"])
            norms = [lemma(t)[0] for t in tokens]
            for i, norm in enumerate(norms):
                if norm != "мир":
                    continue
                total += 1
                for j in range(max(0, i - 2), min(len(norms), i + 3)):
                    if j != i and norms[j] not in stop and len(norms[j]) > 2:
                        collocates[norms[j]] += 1
        for word, count in collocates.most_common(top):
            rows.append([issue, total, word, count])
    write(out / "mir.csv", ["issue", "mir_total", "collocate", "count"], rows)


# --- Библейские ссылки ---------------------------------------------------

BOOKS = {
    # Евангелия
    "Мф": ("Мф", "Евангелия"), "Матф": ("Мф", "Евангелия"), "Мк": ("Мк", "Евангелия"),
    "Мр": ("Мк", "Евангелия"), "Лк": ("Лк", "Евангелия"), "Лук": ("Лк", "Евангелия"),
    "Ин": ("Ин", "Евангелия"), "Иоан": ("Ин", "Евангелия"), "Иоанна": ("Ин", "Евангелия"),
    # Деяния и послания
    "Деян": ("Деян", "Деяния"),
    "Рим": ("Рим", "Послания"), "Кор": ("Кор", "Послания"), "Гал": ("Гал", "Послания"),
    "Еф": ("Еф", "Послания"), "Ефес": ("Еф", "Послания"), "Флп": ("Флп", "Послания"),
    "Фил": ("Флп", "Послания"), "Кол": ("Кол", "Послания"), "Колос": ("Кол", "Послания"),
    "Фес": ("Фес", "Послания"), "Сол": ("Фес", "Послания"), "Тим": ("Тим", "Послания"),
    "Тит": ("Тит", "Послания"), "Евр": ("Евр", "Послания"), "Иак": ("Иак", "Послания"),
    "Пет": ("Пет", "Послания"), "Петр": ("Пет", "Послания"), "Иуд": ("Иуд", "Послания"),
    "Откр": ("Откр", "Апокалипсис"), "Апок": ("Откр", "Апокалипсис"),
    # Ветхий Завет
    "Быт": ("Быт", "Ветхий Завет"), "Исх": ("Исх", "Ветхий Завет"),
    "Лев": ("Лев", "Ветхий Завет"), "Чис": ("Чис", "Ветхий Завет"),
    "Числ": ("Чис", "Ветхий Завет"), "Втор": ("Втор", "Ветхий Завет"),
    "Пс": ("Пс", "Псалтирь"), "Псал": ("Пс", "Псалтирь"),
    "Притч": ("Притч", "Ветхий Завет"), "Еккл": ("Еккл", "Ветхий Завет"),
    "Песн": ("Песн", "Ветхий Завет"), "Ис": ("Ис", "Ветхий Завет"),
    "Исаии": ("Ис", "Ветхий Завет"), "Иер": ("Иер", "Ветхий Завет"),
    "Иез": ("Иез", "Ветхий Завет"), "Дан": ("Дан", "Ветхий Завет"),
    "Даниил": ("Дан", "Ветхий Завет"), "Ос": ("Ос", "Ветхий Завет"),
    "Иоил": ("Иоил", "Ветхий Завет"), "Мих": ("Мих", "Ветхий Завет"),
    "Авв": ("Авв", "Ветхий Завет"), "Аввак": ("Авв", "Ветхий Завет"),
    "Зах": ("Зах", "Ветхий Завет"), "Мал": ("Мал", "Ветхий Завет"),
    "Иов": ("Иов", "Ветхий Завет"), "Вар": ("Вар", "Ветхий Завет"),
    "Варух": ("Вар", "Ветхий Завет"), "Прем": ("Прем", "Ветхий Завет"),
    "Сир": ("Сир", "Ветхий Завет"),
}
# Ссылка: [номер] Книга[.] глава, стих — внутри скобок, возможно через «;».
REF = re.compile(r"(?:(?<=\()|(?<=;\s)|(?<=см\.\s))(?:([1-4])\s?)?([А-Я][а-я]{1,6})\.?,?\s+(\d{1,3})\s*,\s*\d")


def bible(pages: list[dict], sizes: dict, out: Path) -> None:
    books = Counter()
    groups = Counter()
    examples = {}
    for page in pages:
        text = re.sub(r"\s+", " ", page["text"])
        for match in REF.finditer(text):
            abbr = match.group(2)
            if abbr not in BOOKS:
                continue
            book, group = BOOKS[abbr]
            books[(page["issue"], book)] += 1
            groups[(page["issue"], group)] += 1
            examples.setdefault((page["issue"], abbr), match.group(0))
    write(out / "bible_books.csv", ["issue", "book", "count"],
          [[i, b, c] for (i, b), c in sorted(books.items(), key=lambda x: (x[0][0], -x[1]))])
    order = ["Евангелия", "Деяния", "Послания", "Апокалипсис", "Псалтирь", "Ветхий Завет"]
    write(out / "bible_groups.csv", ["issue", "group", "count", "per10k"],
          [[i, g, groups[(i, g)], round(groups[(i, g)] / sizes[i] * 1e4, 1)]
           for i in ISSUES for g in order])
    write(out / "bible_formats.csv", ["issue", "abbr", "example"],
          [[i, a, e] for (i, a), e in sorted(examples.items())])


# --- Святые отцы и подвижники ------------------------------------------

FATHERS = {
    "Иоанн Златоуст": r"Златоуст",
    "Василий Великий": r"Васили\w*\s+Велик",
    "Григорий Богослов": r"Григори\w*\s+Богослов",
    "Афанасий Великий": r"Афанаси\w*\s+Велик",
    "Кирилл Александрийский": r"Кирилл\w*\s+Александрийск",
    "Иоанн Дамаскин": r"Дамаскин",
    "Ириней Лионский": r"Ирине\w*,?\s+(еп\.\s+)?Лионск",
    "Максим Исповедник": r"Максим\w*\s+Исповедник",
    "Симеон Новый Богослов": r"Симеон\w*\s+Нов\w+\s+Богослов",
    "Григорий Палама": r"Палам",
    "Ефрем Сирин": r"Ефре\w*\s+Сирин",
    "Исаак Сирин": r"Исаак\w*\s+Сирин",
    "Иоанн Лествичник": r"Лествичник",
    "Игнатий Богоносец": r"Игнати\w*\s+Богонос",
    "Сергий Радонежский": r"Серги\w*\s+Радонежск|[Пп]реподобн\w+\s+Серги",
    "Серафим Саровский": r"Серафим\w*\s+Саровск",
    "Феофан Затворник": r"Феофан\w*\s+Затворник|Затворник\w*\s+Вышенск",
    "Игнатий (Брянчанинов)": r"Брянчанинов",
    "Иоанн Кронштадтский": r"Кронштадтск",
    "Тихон Задонский": r"Тихон\w*\s+Задонск",
    "Филарет Московский": r"святител\w+\s+Филарет|Филарет\w*\s+Московск|Филарет\w*\s+\(Дроздов",
    "Паисий Величковский": r"Величковск",
    "Иосиф Волоцкий": r"Иосиф\w*\s+Волоцк",
    "Нил Сорский": r"Нил\w*\s+Сорск",
    "Патриарх Гермоген": r"Гермоген",
}


def fathers(pages: list[dict], out: Path) -> None:
    rows = []
    for name, pattern in FATHERS.items():
        regex = re.compile(pattern)
        for issue in ISSUES:
            text = re.sub(r"\s+", " ", "\n".join(p["text"] for p in pages if p["issue"] == issue))
            count = len(regex.findall(text))
            if count:
                rows.append([name, issue, count])
    write(out / "fathers.csv", ["name", "issue", "count"], rows)


# --- Богослужебная терминология ----------------------------------------

LITURGY = {
    "литургия, Евхаристия": r"\b(литурги|Литурги|евхарист|Евхарист)\w*",
    "всенощное бдение, вечерня, утреня": r"\b(всенощн|вечерн|утрен)\w*",
    "молебен, панихида, акафист": r"\b(молебен|молебн|панихид|акафист)\w*",
    "тропарь, кондак, стихира, канон, ирмос": r"\b(тропар|кондак|стихир|ирмос|канон[аеуо]?м?\b)\w*",
    "хиротония, наречение, рукоположение": r"\b(хиротони|наречени|рукоположи|рукоположе)\w*",
    "сослужение, сослужащие": r"\bсослуж\w*",
}


def liturgy_terms(pages: list[dict], sizes: dict, out: Path) -> None:
    rows = []
    for name, pattern in LITURGY.items():
        regex = re.compile(pattern)
        for issue in ISSUES:
            text = "\n".join(p["text"] for p in pages if p["issue"] == issue)
            count = len(regex.findall(text))
            rows.append([name, issue, count, round(count / sizes[issue] * 1e4, 1)])
    write(out / "liturgy.csv", ["group", "issue", "count", "per10k"], rows)


# --- Устройство номера ---------------------------------------------------

def toc(issue: str) -> list[dict]:
    with (ROOT / "meta" / f"toc_{issue}.tsv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file, delimiter="\t"))
    for row in rows:
        row["page"] = int(row["page"])
    return rows


def structure(out: Path) -> None:
    """Число страниц под каждой рубрикой: от начала материала до начала следующего."""
    rows = []
    for issue in ISSUES:
        entries = sorted(toc(issue), key=lambda r: r["page"])
        pages = Counter()
        order = []
        for k, entry in enumerate(entries):
            end = entries[k + 1]["page"] if k + 1 < len(entries) else LAST_PAGE[issue] + 1
            pages[entry["rubric"]] += end - entry["page"]
            if entry["rubric"] not in order:
                order.append(entry["rubric"])
        total = sum(pages.values())
        for position, rubric in enumerate(order):
            rows.append([issue, position, rubric, pages[rubric], round(pages[rubric] / total * 100, 1)])
    write(out / "structure.csv", ["issue", "order", "rubric", "pages", "share"], rows)


# --- Авторы --------------------------------------------------------------

def author_group(author: str) -> str:
    if not author:
        return "без подписи"
    a = author.lower()
    if re.search(r"патриарх|митрополит|архиепископ|епископ", a):
        return "архиереи"
    if re.search(r"протоиерей|прот\.|священник|свящ\.|иеромонах|игумен|архимандрит|иеродиакон|диакон", a):
        return "клирики"
    return "сан не указан"


def authors(out: Path) -> None:
    rows = []
    for issue in ISSUES:
        groups = Counter(author_group(entry["author"]) for entry in toc(issue)
                         if entry["rubric"] != "(вне оглавления)" or entry["author"])
        for group in ["архиереи", "клирики", "сан не указан", "без подписи"]:
            rows.append([issue, group, groups[group]])
    write(out / "authors.csv", ["issue", "group", "items"], rows)


# --- Поместные Церкви и инославные общины -------------------------------

CHURCHES = {
    "Константинопольская": r"Константинопол\w*",
    "Александрийская": r"Александрийск\w*\s+(Патриарх|Церк|Православн)",
    "Антиохийская": r"Антиохийск\w*|Антиохии\s+и\s+всего\s+Востока",
    "Иерусалимская": r"Иерусалимск\w*\s+(Патриарх|Церк|Православн)|Патриарх\w*\s+Иерусалимск",
    "Грузинская": r"Грузинск\w*",
    "Сербская": r"Сербск\w*",
    "Румынская": r"Румынск\w*",
    "Болгарская": r"Болгарск\w*",
    "Кипрская": r"Кипрск\w*",
    "Элладская": r"Элладск\w*|Эллад\w*",
    "Польская": r"Польск\w*\s+(Православн|Автокефальн)",
    "Чехословацкая": r"Чехословацк\w*\s+(Православн|Церк)|Пражск\w*",
    "Американская": r"Американск\w*\s+(Православн|Церк)|всей\s+Америки",
    "Римско-Католическая": r"Католическ\w*|Римск\w+\s+Пап|Ватикан",
    "Лютеранские и евангелические": r"Лютеран\w*|Евангелическ\w*",
    "Англиканская": r"Англиканск\w*|Кентерберийск\w*",
    "Старообрядцы": r"старообряд\w*|Старообряд\w*",
}


def churches(pages: list[dict], out: Path) -> None:
    rows = []
    for name, pattern in CHURCHES.items():
        regex = re.compile(pattern)
        for issue in ISSUES:
            text = re.sub(r"\s+", " ", "\n".join(p["text"] for p in pages if p["issue"] == issue))
            rows.append([name, issue, len(regex.findall(text))])
    write(out / "churches.csv", ["church", "issue", "count"], rows)


# --- Иерархи -------------------------------------------------------------

RANK = re.compile(r"\b([Пп]атриарх|[Мм]итрополит|[Аа]рхиепископ|[Ее]пископ|[Кк]атоликос)[а-я]*\b")
CAPITAL = re.compile(r"[А-ЯЁ][а-яё]+")
# Имена на -а и -я в именительном падеже, которые правило ниже испортило бы.
NAME_EXCEPTIONS = {"Ион": "Иона", "Или": "Илия", "Сав": "Савва", "Никит": "Никита"}


def nominative(form: str) -> str:
    """Имя архиерея в именительном падеже.

    Сначала спрашиваем pymorphy3 (мужское имя с пометой Name); редких
    церковных имён в словаре нет, для них отбрасываем падежное окончание.
    """
    for parse in MORPH.parse(form):
        if {"Name", "masc"} <= set(parse.tag.grammemes):
            inflected = parse.inflect({"nomn", "sing"})
            if inflected:
                name = inflected.word.capitalize()
                return NAME_EXCEPTIONS.get(name, name)
    for ending, replacement in (("ием", "ий"), ("ию", "ий"), ("ия", "ий"), ("ии", "ий"),
                                ("ом", ""), ("ою", "а"), ("ой", "а"), ("у", ""), ("а", ""),
                                ("е", ""), ("ы", "а")):
        if form.endswith(ending) and len(form) - len(ending) >= 3:
            stem = form[: -len(ending)] + replacement
            return NAME_EXCEPTIONS.get(stem, stem)
    return form


def hierarch_names(text: str) -> list[tuple[str, str]]:
    """Пары (сан, имя): после сана пропускаем титулы на -ский/-цкий и союз «и»."""
    found = []
    for match in RANK.finditer(text):
        tail = text[match.end(): match.end() + 80].split()
        for token in tail[:6]:
            word = token.strip(",.;:()«»")
            if word in {"и", "всея", "всего", "Руси", "Востока"} or re.match(
                    r"(Святейш|Блаженнейш|Высокопреосвящен|Преосвящен)", word):
                continue
            if not CAPITAL.fullmatch(word):
                break
            if re.search(r"(ск|цк)(ий|ого|ому|им|ом|ая|ой|ую|ий)$", word):
                continue
            found.append((match.group(1).capitalize(), nominative(word)))
            break
    return found


def hierarchs(pages: list[dict], out: Path, top: int = 6) -> None:
    rows = []
    for issue in ISSUES:
        mentions = Counter()
        for page in pages:
            if page["issue"] == issue:
                mentions.update(hierarch_names(re.sub(r"\s+", " ", page["text"])))
        # Один человек упоминается с разными санами (митрополит → патриарх); ведущим
        # считаем самый частый сан для данного имени в номере.
        by_name = Counter()
        rank_of = {}
        for (rank, name), count in mentions.most_common():
            by_name[name] += count
            rank_of.setdefault(name, rank)
        for name, count in by_name.most_common(top):
            rows.append([issue, len(by_name), rank_of[name], name, count])
    write(out / "hierarchs.csv", ["issue", "distinct", "rank", "name", "count"], rows)


# --- Наречения и хиротонии ----------------------------------------------

CONSECRATION = re.compile(
    r"(наречени\w*|хиротони\w*)\s+(?:\w+\s+){0,3}?"
    r"(архимандрит\w*|игумен\w*|иеромонах\w*|протоиере\w*)\s+([А-ЯЁ][а-яё]+)\s*"
    r"(\([А-ЯЁ][а-яё]+\))?\s+во?\s+епископ\w*\s+([А-ЯЁ][а-яё]+(?:-\s?[А-ЯЁ][а-яё]+)?)"
)


def see_nominative(form: str) -> str:
    """«Павлово-Посадского» → «Павлово-Посадский»."""
    form = re.sub(r"-\s+", "-", form)
    return re.sub(r"(с|ц)кого$", r"\1кий", form)


def consecrations(pages: list[dict], out: Path) -> None:
    """Пример извлечения событий: кто и на какую кафедру наречён или хиротонисан."""
    rows = []
    seen = set()
    for page in pages:
        text = re.sub(r"\s+", " ", page["text"])
        for match in CONSECRATION.finditer(text):
            name = nominative(match.group(3))
            surname = (match.group(4) or "").strip("()")
            see = see_nominative(match.group(5))
            key = (page["issue"], name, see)
            if key in seen:
                continue
            seen.add(key)
            rank = re.sub(r"(а|у|ом)$", "", match.group(2))
            rows.append([page["issue"], page["page"], rank, name, surname, see])
    write(out / "consecrations.csv", ["issue", "page", "rank_before", "name", "surname", "see"], rows)


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    pages = load_pages()
    sizes = volume(pages, out)
    keywords(pages, out)
    slavonic_forms(pages, sizes, out)
    etiquette(pages, sizes, out)
    mir_collocations(pages, out)
    bible(pages, sizes, out)
    fathers(pages, out)
    liturgy_terms(pages, sizes, out)
    structure(out)
    authors(out)
    churches(pages, out)
    hierarchs(pages, out)
    consecrations(pages, out)
    print("таблицы:", ", ".join(sorted(p.name for p in out.glob("*.csv"))))


if __name__ == "__main__":
    main()
