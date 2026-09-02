import argparse
import logging
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)


def generate_font_info(f: Path):
    if not (f.is_file()):
        raise ValueError(f"Not a file: {f}")
    results = []
    with pymupdf.open(f) as doc:
        for page in doc:
            print(page.number)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="pdf into text+font info tsv")
    parser.add_argument("pdfs", nargs="+", type=Path, metavar="PDF")
    return parser


def main():
    args = build_parser().parse_args()
    for f in args.pdfs:
        generate_font_info(f)
