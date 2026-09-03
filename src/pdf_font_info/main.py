import argparse
import logging
from pathlib import Path

import pymupdf

from .annotate import (
    DEFAULT_PALETTE,
    PALETTES,
    AnnotationOptions,
    annotate_document,
    parse_palette,
)
from .spans import extract_spans, gen_tsv

logger = logging.getLogger(__name__)

TSV_SUFFIX = ".font-info.tsv"
ANNOTATED_SUFFIX = ".font-annotated.pdf"


def generate_font_info(f: Path) -> str:
    """
    後方互換のために残してある: PDF から TSV の中身を作って返す。
    """
    if not f.is_file():
        raise ValueError(f"Not a file: {f}")
    with pymupdf.open(f) as doc:
        return gen_tsv(extract_spans(doc))


def process(
    f: Path,
    *,
    want_tsv: bool,
    want_annotation: bool,
    annotation_options: AnnotationOptions,
) -> None:
    if not f.is_file():
        raise ValueError(f"Not a file: {f}")

    tsv_file = f.with_suffix(f.suffix + TSV_SUFFIX)
    annotated_file = f.with_suffix(f.suffix + ANNOTATED_SUFFIX)

    # ファイルがあったら上書きはやめておく
    # todo: 大サービスで比較する？
    if want_tsv and tsv_file.exists():
        logger.error(f"not overriding {tsv_file} in processing {f}: skipping")
        want_tsv = False
    if want_annotation and annotated_file.exists():
        logger.error(f"not overriding {annotated_file} in processing {f}: skipping")
        want_annotation = False
    if not (want_tsv or want_annotation):
        return

    with pymupdf.open(f) as doc:
        spans = extract_spans(doc)

        if want_tsv:
            logger.info(f"writing to {tsv_file}")
            with tsv_file.open("w") as resultwriter:
                resultwriter.write(gen_tsv(spans))
            logger.info(f"successfully written to {tsv_file}")

        if want_annotation:
            annotate_document(doc, spans, annotation_options, source_name=f.name)
            logger.info(f"writing to {annotated_file}")
            doc.save(annotated_file, garbage=3, deflate=True)
            logger.info(f"successfully written to {annotated_file}")


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

    annotation = parser.add_argument_group(
        "annotation", f"draw the font info onto a copy of the PDF (*{ANNOTATED_SUFFIX})"
    )
    annotation.add_argument(
        "--annotate",
        "-a",
        action="store_true",
        help="also write an annotated copy of each PDF",
    )
    annotation.add_argument(
        "--annotate-only",
        "-A",
        action="store_true",
        help="write the annotated PDF and not the TSV",
    )
    annotation.add_argument(
        "--labels",
        action="store_true",
        help="write font/size/colour by every span, not just the style class number",
    )
    annotation.add_argument(
        "--label-every-span",
        dest="dedupe_labels",
        action="store_false",
        help="caption every span; by default a run of spans in the same style "
        "class is captioned once",
    )
    annotation.add_argument(
        "--no-class-numbers",
        dest="class_numbers",
        action="store_false",
        help="draw bare boxes, without the style class number",
    )
    annotation.add_argument(
        "--no-legend",
        dest="legend",
        action="store_false",
        help="do not append the legend page(s)",
    )
    annotation.add_argument(
        "--label-size",
        type=float,
        default=5.0,
        metavar="PT",
        help="size of the class numbers / labels drawn by each box (default: 5)",
    )
    annotation.add_argument(
        "--grid",
        action="store_true",
        help="overlay a coordinate grid, in the same coordinates as the TSV",
    )
    annotation.add_argument(
        "--grid-step",
        type=float,
        default=50.0,
        metavar="PT",
        help="grid spacing in points (default: 50)",
    )
    annotation.add_argument(
        "--colour-scheme",
        "--color-scheme",
        dest="colour_scheme",
        choices=sorted(PALETTES),
        default=DEFAULT_PALETTE,
        help=f"palette for the style classes (default: {DEFAULT_PALETTE})",
    )
    annotation.add_argument(
        "--colours",
        "--colors",
        dest="colours",
        metavar="HEX,HEX,...",
        help="explicit palette, e.g. '#0072b2,#d55e00'; overrides --colour-scheme",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
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

    want_annotation = args.annotate or args.annotate_only
    want_tsv = not args.annotate_only

    try:
        palette = parse_palette(args.colour_scheme, args.colours)
    except ValueError as e:
        parser.error(str(e))
    if want_annotation and args.grid_step <= 0:
        parser.error("--grid-step must be positive")

    annotation_options = AnnotationOptions(
        palette=palette,
        labels=args.labels,
        class_numbers=args.class_numbers,
        grid=args.grid,
        grid_step=args.grid_step,
        legend=args.legend,
        label_size=args.label_size,
        dedupe_labels=args.dedupe_labels,
    )

    for f in args.pdfs:
        process(
            f,
            want_tsv=want_tsv,
            want_annotation=want_annotation,
            annotation_options=annotation_options,
        )
