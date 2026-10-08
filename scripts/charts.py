"""Статичные графики для страницы о пробном корпусе ЖМП.

Запуск: python charts.py site/data site/img
Читает сводные таблицы analysis.py, пишет PNG.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

# Токены оформления: поверхность, текст, сетка, ряды.
SURFACE = "#ffffff"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e6e5e1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
BLUE = SERIES[0]
ISSUES = ["1944-01", "1960-01", "1982-01", "2010-01"]
LABEL = {"1944-01": "1944, № 1", "1960-01": "1960, № 1", "1982-01": "1982, № 1", "2010-01": "2010, № 1"}

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "text.color": TEXT,
    "axes.labelcolor": TEXT_2,
    "xtick.color": TEXT_2,
    "ytick.color": TEXT,
    "axes.edgecolor": GRID,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})
DPI = 200


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def clean_axes(ax, grid_axis: str = "x") -> None:
    """Сетка — тонкие сплошные линии на заднем плане, рамки нет."""
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def hbar(ax, y: float, value: float, height: float, color: str, left: float = 0.0) -> None:
    """Горизонтальный столбик со скруглённым концом и прямым основанием."""
    if value <= 0:
        return
    x_span = ax.get_xlim()[1] - ax.get_xlim()[0]
    radius = min(x_span * 0.006, value / 2)
    ax.add_patch(FancyBboxPatch(
        (left, y - height / 2), value, height,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        mutation_aspect=height / (radius * 2) if radius else 1,
        facecolor=color, edgecolor="none"))
    # Основание прямое: перекрываем скругление у оси прямоугольником.
    ax.add_patch(Rectangle((left, y - height / 2), min(value, radius * 2), height,
                           facecolor=color, edgecolor="none"))


def save(fig, path: Path) -> None:
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


# --- 1. Ключевые слова ---------------------------------------------------

def keywords(data: Path, img: Path, top: int = 10) -> None:
    rows = read(data / "keywords.csv")
    fig, axes = plt.subplots(2, 2, figsize=(8.5, 7.2), sharex=False)
    for ax, issue in zip(axes.flat, ISSUES):
        items = [r for r in rows if r["issue"] == issue][:top][::-1]
        values = [float(r["ipm10k"]) for r in items]
        rest = [float(r["ipm10k_rest"]) for r in items]
        ax.set_xlim(0, max(values) * 1.25)
        ax.set_ylim(-0.6, len(items) - 0.4)
        for y, (v, r) in enumerate(zip(values, rest)):
            hbar(ax, y, v, 0.55, BLUE)
            # Серая черта — та же лемма в трёх других номерах.
            ax.plot([r, r], [y - 0.38, y + 0.38], color=TEXT_2, linewidth=1.6, solid_capstyle="butt")
        ax.set_yticks(range(len(items)), [r["lemma"] for r in items])
        ax.set_title(LABEL[issue], loc="left", fontsize=10, fontweight="bold", color=TEXT)
        clean_axes(ax)
        ax.set_xlabel("на 10 тыс. слов")
    fig.text(0.0, -0.03, "Синий столбик — частота леммы в номере; серая черта — средняя частота в трёх других номерах.",
             color=TEXT_2, fontsize=8.5)
    fig.tight_layout(w_pad=2.2, h_pad=2.0)
    save(fig, img / "keywords.png")


# --- 2. Церковнославянские формы по рубрикам ----------------------------

def slavonic(data: Path, img: Path) -> None:
    rows = read(data / "slavonic_rubric.csv")
    rows = [r for r in rows if r["rubric"] != "(вне оглавления)"]
    rows.sort(key=lambda r: float(r["per10k"]))
    labels = [f'{r["issue"][:4]} · {r["rubric"]}' for r in rows]
    values = [float(r["per10k"]) for r in rows]
    fig, ax = plt.subplots(figsize=(8, 0.26 * len(rows) + 0.8))
    ax.set_xlim(0, max(values) * 1.15)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    for y, v in enumerate(values):
        hbar(ax, y, v, 0.62, BLUE)
        ax.text(v + max(values) * 0.01, y, f"{v:.0f}".replace(".", ","), va="center",
                fontsize=8, color=TEXT_2)
    ax.set_yticks(range(len(rows)), labels, fontsize=8.5)
    ax.set_xlabel("церковнославянских форм на 10 тыс. слов")
    clean_axes(ax)
    save(fig, img / "slavonic.png")


# --- 3. Библейские ссылки ------------------------------------------------

def bible(data: Path, img: Path) -> None:
    rows = read(data / "bible_groups.csv")
    groups = ["Евангелия", "Деяния", "Послания", "Апокалипсис", "Псалтирь", "Ветхий Завет"]
    value = {(r["issue"], r["group"]): float(r["per10k"]) for r in rows}
    count = defaultdict(int)
    for r in rows:
        count[r["issue"]] += int(r["count"])
    fig, ax = plt.subplots(figsize=(8, 2.6))
    totals = [sum(value[(i, g)] for g in groups) for i in ISSUES]
    ax.set_xlim(0, max(totals) * 1.18)
    ax.set_ylim(-0.6, len(ISSUES) - 0.4)
    gap = max(totals) * 0.004   # 2 px просвета между сегментами
    for y, issue in enumerate(reversed(ISSUES)):
        left = 0.0
        for k, group in enumerate(groups):
            v = value[(issue, group)]
            if v > 0:
                ax.add_patch(Rectangle((left, y - 0.3), max(v - gap, 0), 0.6,
                                       facecolor=SERIES[k], edgecolor="none"))
                left += v
        ax.text(left + max(totals) * 0.01, y, f"{count[issue]} ссыл.", va="center",
                fontsize=8, color=TEXT_2)
    ax.set_yticks(range(len(ISSUES)), [LABEL[i] for i in reversed(ISSUES)])
    ax.set_xlabel("ссылок на 10 тыс. слов")
    clean_axes(ax)
    handles = [Rectangle((0, 0), 1, 1, facecolor=SERIES[k]) for k in range(len(groups))]
    ax.legend(handles, groups, ncol=6, frameon=False, loc="lower left",
              bbox_to_anchor=(0, 1.02), fontsize=8, handlelength=1, handleheight=1,
              columnspacing=1.2)
    save(fig, img / "bible.png")


# --- 4. Богослужебная терминология ---------------------------------------

def liturgy(data: Path, img: Path) -> None:
    rows = read(data / "liturgy.csv")
    groups = list(dict.fromkeys(r["group"] for r in rows))
    value = {(r["group"], r["issue"]): float(r["per10k"]) for r in rows}
    fig, axes = plt.subplots(2, 3, figsize=(9, 4.4), sharex=True)
    top = max(value.values()) * 1.25
    for ax, group in zip(axes.flat, groups):
        ax.set_xlim(0, top)
        ax.set_ylim(-0.6, 3.6)
        for y, issue in enumerate(reversed(ISSUES)):
            v = value[(group, issue)]
            hbar(ax, y, v, 0.6, BLUE)
            ax.text(v + top * 0.015, y, f"{v:.1f}".replace(".", ","), va="center",
                    fontsize=7.5, color=TEXT_2)
        ax.set_yticks(range(4), [i[:4] for i in reversed(ISSUES)])
        ax.set_title(group, loc="left", fontsize=8.5, color=TEXT)
        clean_axes(ax)
    for ax in axes[1]:
        ax.set_xlabel("на 10 тыс. слов")
    fig.tight_layout(h_pad=1.6, w_pad=1.6)
    save(fig, img / "liturgy.png")


# --- 5. Устройство номера ------------------------------------------------

def structure(data: Path, img: Path) -> None:
    rows = read(data / "structure.csv")
    fig, axes = plt.subplots(2, 2, figsize=(8.5, 6.4))
    for ax, issue in zip(axes.flat, ISSUES):
        items = [r for r in rows if r["issue"] == issue][::-1]
        values = [float(r["share"]) for r in items]
        ax.set_xlim(0, 60)
        ax.set_ylim(-0.6, 7.6)
        offset = 8 - len(items)   # выравниваем панели по верху
        for k, v in enumerate(values):
            y = k + offset
            hbar(ax, y, v, 0.6, BLUE)
            ax.text(v + 1, y, f"{v:.0f}%", va="center", fontsize=7.5, color=TEXT_2)
        labels = [r["rubric"].replace(" (без заголовка рубрики)", "*") for r in items]
        ax.set_yticks([k + offset for k in range(len(items))], [_wrap(l, 22) for l in labels],
                      fontsize=7.5)
        ax.set_ylim(-0.6, len(items) - 0.4 + offset)
        ax.set_title(LABEL[issue], loc="left", fontsize=10, fontweight="bold")
        ax.set_xticks([0, 20, 40])
        clean_axes(ax)
        ax.set_xlabel("доля страниц, %")
    fig.tight_layout(w_pad=1.4, h_pad=2.0)
    save(fig, img / "structure.png")


def _wrap(text: str, width: int) -> str:
    words, lines, line = text.split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    return "\n".join(lines)


# --- 6. Поместные Церкви и инославные общины -----------------------------

def churches(data: Path, img: Path) -> None:
    rows = read(data / "churches.csv")
    names = list(dict.fromkeys(r["church"] for r in rows))
    count = {(r["church"], r["issue"]): int(r["count"]) for r in rows}
    fig, ax = plt.subplots(figsize=(6.4, 0.3 * len(names) + 0.9))
    biggest = max(count.values())
    for y, name in enumerate(reversed(names)):
        for x, issue in enumerate(ISSUES):
            c = count[(name, issue)]
            if c:
                ax.scatter(x, y, s=18 + 520 * c / biggest, color=BLUE, edgecolors=SURFACE,
                           linewidths=1.5, zorder=3)
                ax.text(x + 0.22, y, str(c), va="center", fontsize=7.5, color=TEXT_2)
            else:
                ax.scatter(x, y, s=6, color=GRID, zorder=2)
    ax.set_xticks(range(4), [LABEL[i] for i in ISSUES])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(names)), list(reversed(names)))
    ax.set_xlim(-0.5, 3.7)
    ax.set_ylim(-0.7, len(names) - 0.3)
    clean_axes(ax, grid_axis="y")
    save(fig, img / "churches.png")


# --- 7. Круг авторов -----------------------------------------------------

def authors(data: Path, img: Path) -> None:
    rows = read(data / "authors.csv")
    groups = ["архиереи", "клирики", "сан не указан", "без подписи"]
    value = {(r["issue"], r["group"]): int(r["items"]) for r in rows}
    fig, ax = plt.subplots(figsize=(8, 2.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.6, 3.6)
    for y, issue in enumerate(reversed(ISSUES)):
        total = sum(value[(issue, g)] for g in groups)
        left = 0.0
        for k, group in enumerate(groups):
            share = value[(issue, group)] / total * 100
            if share:
                ax.add_patch(Rectangle((left, y - 0.3), share - 0.4, 0.6,
                                       facecolor=SERIES[k], edgecolor="none"))
                if share >= 9:
                    ax.text(left + share / 2, y, str(value[(issue, group)]), ha="center",
                            va="center", fontsize=8, color=TEXT if k in (2, 3) else "#ffffff")
                left += share
        ax.text(101, y, f"{total} мат.", va="center", fontsize=8, color=TEXT_2)
    ax.set_yticks(range(4), [LABEL[i] for i in reversed(ISSUES)])
    ax.set_xlabel("доля материалов в оглавлении, %")
    clean_axes(ax)
    handles = [Rectangle((0, 0), 1, 1, facecolor=SERIES[k]) for k in range(4)]
    ax.legend(handles, groups, ncol=4, frameon=False, loc="lower left",
              bbox_to_anchor=(0, 1.02), fontsize=8, handlelength=1, handleheight=1)
    save(fig, img / "authors.png")


def main() -> None:
    data, img = Path(sys.argv[1]), Path(sys.argv[2])
    img.mkdir(parents=True, exist_ok=True)
    for chart in (keywords, slavonic, bible, liturgy, structure, churches, authors):
        chart(data, img)
    print("графики:", ", ".join(sorted(p.name for p in img.glob("*.png"))))


if __name__ == "__main__":
    main()
