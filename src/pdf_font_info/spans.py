"""
PDF から text span を取り出して構造化するところ。

TSV 出力 (:mod:`pdf_font_info.main`) と PDF への注釈 (:mod:`pdf_font_info.annotate`)
の両方がここを共有する。
"""

import logging
from dataclasses import dataclass, fields
from typing import Any

import pymupdf

logger = logging.getLogger(__name__)

# https://pymupdf.readthedocs.io/en/latest/recipes-text.html#how-to-analyze-font-characteristics
TEXT_EXTRACTION_FLAGS = 11


@dataclass(frozen=True)
class SpanInfo:
    """
    ある span の情報をまとめたやつ
    """

    page: int  # 1-indexed
    font: str
    size: float
    color: int
    flag_code: int
    flags: str
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @staticmethod
    def gen_tsv_header() -> str:
        return "\t".join(f.name for f in fields(SpanInfo))

    def gen_tsv_line(self) -> str:
        return "\t".join(
            [
                str(self.page),
                self.font,
                f"{self.size:.2f}",
                self.color_hex,
                str(self.flag_code),
                self.flags,
                f"{self.x0:.2f}",
                f"{self.y0:.2f}",
                f"{self.x1:.2f}",
                f"{self.y1:.2f}",
                self.text,
            ]
        )

    @property
    def color_hex(self) -> str:
        return f"#{self.color:06x}"

    @property
    def rect(self) -> pymupdf.Rect:
        return pymupdf.Rect(self.x0, self.y0, self.x1, self.y1)

    @staticmethod
    def from_span(span: dict[str, Any], page_index: int) -> SpanInfo:
        """
        page_index は 0-indexed
        """

        x0, y0, x1, y1 = span["bbox"]
        return SpanInfo(
            page=page_index + 1,
            font=span["font"],
            size=span["size"],
            color=span["color"],
            flag_code=span["flags"],
            flags=flags_decomposer(span["flags"]),
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            text=escape_tsv(span["text"]),
        )


def extract_spans(doc: pymupdf.Document) -> list[SpanInfo]:
    """
    文書全体の span を順に取り出す。
    """
    spans: list[SpanInfo] = []
    for page in doc.pages():  # TODO: specify page range from command line argument
        logger.info(f"processing {page.number}")
        blocks = page.get_text("dict", flags=TEXT_EXTRACTION_FLAGS)["blocks"]
        for block in blocks:
            for line in block["lines"]:
                for span in line["spans"]:
                    spans.append(SpanInfo.from_span(span, page_index=page.number))
        logger.info(f"processed {page.number}")
    return spans


def gen_tsv(spans: list[SpanInfo]) -> str:
    return "\n".join([SpanInfo.gen_tsv_header(), *(s.gen_tsv_line() for s in spans)])


def flags_decomposer(flags: int) -> str:
    """
    Make font flags human readable. from the doc:
    https://pymupdf.readthedocs.io/en/latest/recipes-text.html#how-to-analyze-font-characteristics
    """
    l = []

    if flags & pymupdf.TEXT_FONT_SUPERSCRIPT:
        l.append("superscript")
    if flags & pymupdf.TEXT_FONT_ITALIC:
        l.append("italic")
    if flags & pymupdf.TEXT_FONT_SERIFED:
        l.append("serifed")
    else:
        l.append("sans")
    if flags & pymupdf.TEXT_FONT_MONOSPACED:
        l.append("monospaced")
    if flags & pymupdf.TEXT_FONT_BOLD:
        l.append("bold")

    return ",".join(l)


def escape_tsv(text: str) -> str:
    """
    めっちゃ雑だけど一応……
    """
    return (
        text.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
