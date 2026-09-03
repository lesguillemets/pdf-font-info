"""
抽出した span を元の PDF の上に描き込むところ。

同じ (font, size, color, flags) を持つ span を「style class」としてまとめ、
class ごとに色を割り当てて枠を描く。各枠には class 番号を添え、
文書末尾に凡例のページを足す。密度の高いページでも枠が読めるようにするため、
span ごとの詳細ラベルは ``--labels`` を指定したときだけ描く。

色が足りなくなったら破線パターンを第二のチャンネルとして使う (:mod:`pdf_font_info.palette`)。

注釈は本物の PDF annotation ではなく、ページ内容としてそのまま描画する
(``draw_rect`` / ``insert_text``)。ビューアによらず同じ見た目になり、
印刷や画像化でも消えない。元のファイルには手を触れず、常に別名で保存する。
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import pymupdf

from .palette import DEFAULT_PALETTE, NAMED_PALETTES, RGB, Palette, to_rgb
from .spans import SpanInfo

logger = logging.getLogger(__name__)

GRID_COLOR: RGB = (0.80, 0.80, 0.85)
GRID_LABEL_COLOR: RGB = (0.45, 0.45, 0.55)
LEGEND_TEXT_COLOR: RGB = (0.0, 0.0, 0.0)
LEGEND_RULE_COLOR: RGB = (0.75, 0.75, 0.75)


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _latin1_safe(text: str) -> str:
    """base-14 font は latin-1 しか出せないので、はみ出す文字は落とす。"""
    return text.encode("latin-1", errors="replace").decode("latin-1")


@dataclass(frozen=True)
class StyleKey:
    """span をまとめる単位。size は小数第二位まで (TSV の出力と揃える)。"""

    font: str
    size: float
    color: int
    flag_code: int

    @staticmethod
    def of(span: SpanInfo) -> StyleKey:
        return StyleKey(
            font=span.font,
            size=round(span.size, 2),
            color=span.color,
            flag_code=span.flag_code,
        )


@dataclass
class StyleClass:
    key: StyleKey
    flags: str
    index: int = 0  # 1-indexed、凡例の番号
    count: int = 0
    pages: set[int] = field(default_factory=set)
    rgb: RGB = (0.0, 0.0, 0.0)
    dash: str | None = None  # PyMuPDF の dashes 文字列、実線なら None


@dataclass
class AnnotationOptions:
    palette: Palette = NAMED_PALETTES[DEFAULT_PALETTE]
    labels: bool = False
    class_numbers: bool = True
    grid: bool = False
    grid_step: float = 50.0
    legend: bool = True
    # 同じ style class が続く間はキャプションを最初の span にだけ描く
    dedupe_labels: bool = True
    box_width: float = 0.4
    box_opacity: float = 0.85
    label_size: float = 5.0


def build_style_classes(
    spans: Iterable[SpanInfo], palette: Palette
) -> dict[StyleKey, StyleClass]:
    """
    span を style class にまとめ、出現回数の多い順に番号と (色, 破線) を割り当てる。
    色を使い切ったら破線パターンが変わり、それも尽きたら循環する (class 番号は一意)。
    """
    classes: dict[StyleKey, StyleClass] = {}
    for order, span in enumerate(spans):
        key = StyleKey.of(span)
        cls = classes.get(key)
        if cls is None:
            cls = StyleClass(key=key, flags=span.flags, index=order)
            classes[key] = cls
        cls.count += 1
        cls.pages.add(span.page)

    # 出現順を tie-break に使いつつ、多いものから並べる
    first_seen = {key: cls.index for key, cls in classes.items()}
    ordered = sorted(
        classes.values(), key=lambda c: (-c.count, first_seen[c.key], c.key.font)
    )
    for i, (cls, (colour, dash)) in enumerate(
        zip(ordered, palette.assignments(len(ordered)), strict=True)
    ):
        cls.index = i + 1
        cls.rgb = to_rgb(colour)
        cls.dash = dash
    return {cls.key: cls for cls in ordered}


def draw_grid(page: pymupdf.Page, step: float) -> None:
    """
    PDF の座標系 (原点は左上、y は下向き) でグリッドを引く。TSV の x0/y0/x1/y1 と同じ座標。
    """
    if step <= 0:
        raise ValueError(f"grid step must be positive: {step}")
    rect = page.rect
    label_every = 2  # 2 本に 1 本だけ数値を振る

    x = 0.0
    i = 0
    while x <= rect.width:
        page.draw_line(
            pymupdf.Point(x, 0),
            pymupdf.Point(x, rect.height),
            color=GRID_COLOR,
            width=0.25,
        )
        if i % label_every == 0 and x > 0:
            page.insert_text(
                pymupdf.Point(x + 1, 7),
                f"{x:g}",
                fontsize=4,
                fontname="helv",
                color=GRID_LABEL_COLOR,
            )
        x += step
        i += 1

    y = 0.0
    i = 0
    while y <= rect.height:
        page.draw_line(
            pymupdf.Point(0, y),
            pymupdf.Point(rect.width, y),
            color=GRID_COLOR,
            width=0.25,
        )
        if i % label_every == 0 and y > 0:
            page.insert_text(
                pymupdf.Point(2, y - 1),
                f"{y:g}",
                fontsize=4,
                fontname="helv",
                color=GRID_LABEL_COLOR,
            )
        y += step
        i += 1


def _draw_span(
    page: pymupdf.Page,
    span: SpanInfo,
    cls: StyleClass,
    opts: AnnotationOptions,
    *,
    with_caption: bool = True,
) -> None:
    page.draw_rect(
        span.rect,
        color=cls.rgb,
        width=opts.box_width,
        dashes=cls.dash,
        stroke_opacity=opts.box_opacity,
    )
    if not (with_caption and (opts.class_numbers or opts.labels)):
        return

    caption = str(cls.index)
    if opts.labels:
        caption = f"{cls.index}:{cls.key.font} {cls.key.size:g} #{cls.key.color:06x}"

    # 枠の上に置く。上端に余裕がなければ枠の下に回す。
    baseline = span.y0 - 0.8
    if baseline < opts.label_size:
        baseline = span.y1 + opts.label_size
    page.insert_text(
        pymupdf.Point(span.x0, baseline),
        _latin1_safe(caption),
        fontsize=opts.label_size,
        fontname="helv",
        color=cls.rgb,
    )


def draw_legend(
    doc: pymupdf.Document,
    classes: Sequence[StyleClass],
    opts: AnnotationOptions,
    source_name: str,
) -> None:
    """文書の最後に凡例のページを足す。入り切らなければ複数ページに分ける。"""
    template = doc[0].rect if doc.page_count else pymupdf.paper_rect("a4")
    margin = 42.0
    line_height = 13.0
    body_size = 8.0

    rows = [
        (
            cls,
            f"[{cls.index:>3}]  {cls.key.font}",
            f"{cls.key.size:>6.2f}pt  #{cls.key.color:06x}  {cls.flags}",
            f"{_plural(cls.count, 'span')} on {_plural(len(cls.pages), 'page')}",
        )
        for cls in classes
    ]
    if not rows:
        rows = [(None, "no text spans found", "", "")]  # type: ignore[list-item]

    per_page = max(
        1, int((template.height - 2 * margin - 3 * line_height) / line_height)
    )
    for chunk_start in range(0, len(rows), per_page):
        chunk = rows[chunk_start : chunk_start + per_page]
        page = doc.new_page(width=template.width, height=template.height)
        y = margin
        page.insert_text(
            pymupdf.Point(margin, y),
            _latin1_safe(f"pdf-font-info: style classes for {source_name}"),
            fontsize=11,
            fontname="hebo",
            color=LEGEND_TEXT_COLOR,
        )
        y += line_height
        page.insert_text(
            pymupdf.Point(margin, y),
            "font / size / colour / flags, most frequent first",
            fontsize=7,
            fontname="helv",
            color=GRID_LABEL_COLOR,
        )
        y += 6
        page.draw_line(
            pymupdf.Point(margin, y),
            pymupdf.Point(template.width - margin, y),
            color=LEGEND_RULE_COLOR,
            width=0.5,
        )
        y += line_height

        for cls, name, style, count in chunk:
            if cls is not None:
                page.draw_rect(
                    pymupdf.Rect(margin, y - body_size + 1, margin + 9, y + 1),
                    color=cls.rgb,
                    fill=cls.rgb,
                    width=0.4,
                )
                # 破線パターンも凡例に出す
                page.draw_line(
                    pymupdf.Point(margin + 13, y - body_size / 2 + 1),
                    pymupdf.Point(margin + 33, y - body_size / 2 + 1),
                    color=cls.rgb,
                    dashes=cls.dash,
                    width=0.8,
                )
            page.insert_text(
                pymupdf.Point(margin + 40, y),
                _latin1_safe(name),
                fontsize=body_size,
                fontname="helv",
                color=LEGEND_TEXT_COLOR,
            )
            page.insert_text(
                pymupdf.Point(margin + 224, y),
                _latin1_safe(style),
                fontsize=body_size,
                fontname="helv",
                color=LEGEND_TEXT_COLOR,
            )
            page.insert_text(
                pymupdf.Point(template.width - margin - 120, y),
                _latin1_safe(count),
                fontsize=body_size,
                fontname="helv",
                color=GRID_LABEL_COLOR,
            )
            y += line_height


def annotate_document(
    doc: pymupdf.Document,
    spans: Sequence[SpanInfo],
    opts: AnnotationOptions,
    source_name: str = "",
) -> dict[StyleKey, StyleClass]:
    """
    ``doc`` を破壊的に書き換える。呼ぶ側で別名保存すること。
    """
    classes = build_style_classes(spans, opts.palette)
    logger.info(f"{len(spans)} spans in {len(classes)} style classes")

    by_page: dict[int, list[SpanInfo]] = {}
    for span in spans:
        by_page.setdefault(span.page, []).append(span)

    n_pages = doc.page_count
    for page_number in range(1, n_pages + 1):
        page = doc[page_number - 1]
        if opts.grid:
            draw_grid(page, opts.grid_step)
        previous: StyleKey | None = None
        for span in by_page.get(page_number, []):
            key = StyleKey.of(span)
            with_caption = not opts.dedupe_labels or key != previous
            _draw_span(page, span, classes[key], opts, with_caption=with_caption)
            previous = key
        logger.debug(f"annotated page {page_number}")

    if opts.legend:
        draw_legend(doc, list(classes.values()), opts, source_name)
    return classes
