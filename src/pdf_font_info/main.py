import argparse
import logging
from pathlib import Path

import pymupdf

from .spans import extract_spans, gen_tsv

logger = logging.getLogger(__name__)

TSV_SUFFIX = ".font-info.tsv"


def generate_font_info(f: Path) -> str:
    if not f.is_file():
        raise ValueError(f"Not a file: {f}")
    with pymupdf.open(f) as doc:
        return gen_tsv(extract_spans(doc))


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
        result_file = f.with_suffix(f.suffix + TSV_SUFFIX)
        if result_file.exists():  # ファイルがあったら上書きはやめておく
            # todo: 大サービスで比較する？
            logger.error(f"not overriding {result_file} in processing {f}: skipping")
            continue
        else:
            tsv_data = generate_font_info(f)
            logger.info(f"writing to {result_file}")
            with result_file.open("w") as resultwriter:
                resultwriter.write(tsv_data)
            logger.info(f"successfully written to {result_file}")
