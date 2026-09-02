import argparse
import logging
from dataclasses import dataclass, fields
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)


def generate_font_info(f: Path) -> str:
    if not (f.is_file()):
        raise ValueError(f"Not a file: {f}")
    results = [SpanInfo.gen_csv_header()]
    with pymupdf.open(f) as doc:
        for page in doc.pages():  # TODO: specify page range from command line argument
            logger.info(f"processing {page.number}")
            # https://pymupdf.readthedocs.io/en/latest/recipes-text.html#how-to-analyze-font-characteristics
            blocks = page.get_text("dict", flags=11)["blocks"]
            for block in blocks:
                for line in block["lines"]:
                    for span in line["spans"]:
                        span_info = SpanInfo.from_span(span, page_index=page.number)
                        results.append(span_info.gen_csv_line())

            logger.info(f"processed {page.number}")
    return "\n".join(results)


@dataclass
class SpanInfo:
    """
    ある span の情報をまとめたやつ
    """

    page: int  # 1-indexed
    font: str
    size: float
    color: int | float | str  # not sure
    flag_code: int
    flags: str
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @staticmethod
    def gen_csv_header() -> str:
        return "\t".join(f.name for f in fields(SpanInfo))

    def gen_csv_line(self):
        return "\t".join(
            [
                str(self.page),
                self.font,
                f"{self.size:.2f}",
                str(self.color),
                str(self.flag_code),
                self.flags,
                f"{self.x0:.2f}",
                f"{self.y0:.2f}",
                f"{self.x1:.2f}",
                f"{self.y1:.2f}",
                self.text,
            ]
        )

    @staticmethod
    def from_span(span, page_index: int) -> SpanInfo:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="pdf into text+font info tsv")
    parser.add_argument("pdfs", nargs="+", type=Path, metavar="PDF")
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="-v for INFO, -vv for DEBUG",
    )
    return parser


def main():
    args = build_parser().parse_args()
    # --verbose でログのレベル変更
    log_level = {
        0: logging.WARNING,
        1: logging.INFO,
    }.get(args.verbose, logging.DEBUG)  # list に safe-get がないから……

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    logging.getLogger(__package__).setLevel(log_level)

    for f in args.pdfs:
        tsv_data = generate_font_info(f)
        result_file = f.with_suffix(f.suffix + ".font-info.tsv")
        if result_file.exists():
            logger.error(f"not overriding {result_file} in processing {f}: skipping")
            continue
        else:
            logger.info(f"writing to {result_file}")
            with result_file.open("w") as resultwriter:
                resultwriter.write(tsv_data)
            logger.info(f"successfully written to {result_file}")
