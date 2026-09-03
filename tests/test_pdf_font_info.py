"""
依存を増やしたくないので unittest で。

```sh
uv run python -m unittest discover -s tests -v
```
"""

import unittest

import pymupdf

from pdf_font_info.annotate import (
    AnnotationOptions,
    StyleKey,
    annotate_document,
    build_style_classes,
)
from pdf_font_info.palette import (
    DASH_PATTERNS,
    NAMED_PALETTES,
    Palette,
    distinct_colours,
    parse_palette,
    srgb_to_oklab,
    to_rgb,
)
from pdf_font_info.spans import (
    SpanInfo,
    escape_tsv,
    extract_spans,
    flags_decomposer,
    gen_tsv,
)


def make_doc() -> pymupdf.Document:
    """3 つの style class を含む 1 ページの文書。"""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Heading", fontsize=18, fontname="hebo")
    page.insert_text((72, 130), "body one", fontsize=10, fontname="tiro")
    page.insert_text((72, 150), "body two", fontsize=10, fontname="tiro")
    page.insert_text((72, 170), "code", fontsize=9, fontname="cour", color=(1, 0, 0))
    return doc


class TestSpans(unittest.TestCase):
    def test_escape_tsv_is_reversible_enough(self):
        self.assertEqual(escape_tsv("a\tb\nc\\d"), "a\\tb\\nc\\\\d")
        self.assertNotIn("\n", escape_tsv("a\r\nb"))

    def test_flags_decomposer(self):
        self.assertEqual(flags_decomposer(0), "sans")
        self.assertEqual(
            flags_decomposer(pymupdf.TEXT_FONT_SERIFED | pymupdf.TEXT_FONT_BOLD),
            "serifed,bold",
        )

    def test_extract_and_tsv(self):
        with make_doc() as doc:
            spans = extract_spans(doc)
        self.assertEqual(len(spans), 4)
        self.assertTrue(all(s.page == 1 for s in spans))

        lines = gen_tsv(spans).splitlines()
        self.assertEqual(lines[0], SpanInfo.gen_tsv_header())
        self.assertEqual(len(lines), 5)
        self.assertTrue(all(len(line.split("\t")) == 11 for line in lines))

    def test_colour_is_rendered_as_hex(self):
        with make_doc() as doc:
            spans = extract_spans(doc)
        red = next(s for s in spans if s.font.startswith("Courier"))
        self.assertEqual(red.color_hex, "#ff0000")


class TestStyleClasses(unittest.TestCase):
    def test_grouping_and_ordering(self):
        with make_doc() as doc:
            spans = extract_spans(doc)
        classes = build_style_classes(spans, NAMED_PALETTES["okabe-ito"])

        self.assertEqual(len(classes), 3)
        by_index = sorted(classes.values(), key=lambda c: c.index)
        self.assertEqual([c.index for c in by_index], [1, 2, 3])
        # 出現回数の多いものが 1 番になる
        self.assertEqual(by_index[0].count, 2)
        self.assertEqual(by_index[0].key.font, "Times-Roman")

    def test_colours_cycle_with_a_new_dash_but_indices_do_not(self):
        spans = [
            SpanInfo(
                page=1,
                font=f"Font{i}",
                size=10.0,
                color=0,
                flag_code=0,
                flags="sans",
                x0=0.0,
                y0=0.0,
                x1=1.0,
                y1=1.0,
                text="x",
            )
            for i in range(5)
        ]
        classes = build_style_classes(spans, Palette("t", (0x000000, 0xFFFFFF)))
        indices = sorted(c.index for c in classes.values())
        self.assertEqual(indices, [1, 2, 3, 4, 5])
        by_index = sorted(classes.values(), key=lambda c: c.index)
        # 2 色しかないので 3 番目で色は一周し、破線が変わって区別が付く
        self.assertEqual(by_index[0].rgb, by_index[2].rgb)
        self.assertIsNone(by_index[0].dash)
        self.assertEqual(by_index[2].dash, DASH_PATTERNS[1])

    def test_style_key_rounds_size(self):
        def span(size: float) -> SpanInfo:
            return SpanInfo(
                page=1,
                font="F",
                size=size,
                color=0,
                flag_code=0,
                flags="sans",
                x0=0.0,
                y0=0.0,
                x1=1.0,
                y1=1.0,
                text="x",
            )

        self.assertEqual(StyleKey.of(span(9.999)), StyleKey.of(span(10.001)))


class TestPalette(unittest.TestCase):
    def test_named_scheme(self):
        self.assertEqual(parse_palette("mono", None), NAMED_PALETTES["mono"])

    def test_explicit_colours_win(self):
        self.assertEqual(
            parse_palette("mono", "#ff0000, 00ff00").colours(2), (0xFF0000, 0x00FF00)
        )

    def test_rejects_nonsense(self):
        for scheme, colours in [("nope", None), (None, "#zzzzzz"), (None, "#1000000")]:
            with (
                self.subTest(scheme=scheme, colours=colours),
                self.assertRaises(ValueError),
            ):
                parse_palette(scheme, colours)

    def test_generated_palette_is_prefix_stable(self):
        # class が増えても、すでにある class の色は変わらない
        self.assertEqual(distinct_colours(4), distinct_colours(12)[:4])

    def test_generated_colours_are_distinct_and_legible(self):
        colours = distinct_colours(16)
        self.assertEqual(len(set(colours)), 16)
        for c in colours:
            lightness = srgb_to_oklab(c)[0]
            # 白地でも本文の黒とも紛れない明度に収まっている
            self.assertGreater(lightness, 0.25)
            self.assertLess(lightness, 0.70)

    def test_dashes_extend_the_palette(self):
        assignments = NAMED_PALETTES["distinct"].assignments(40)
        self.assertEqual(len(set(assignments)), 40)

    def test_to_rgb(self):
        self.assertEqual(to_rgb(0x000000), (0.0, 0.0, 0.0))
        self.assertEqual(to_rgb(0xFFFFFF), (1.0, 1.0, 1.0))


class TestAnnotation(unittest.TestCase):
    def test_annotation_adds_drawings_and_a_legend(self):
        with make_doc() as doc:
            spans = extract_spans(doc)
            before = len(doc[0].get_drawings())
            classes = annotate_document(doc, spans, AnnotationOptions(), "test.pdf")

            self.assertEqual(len(classes), 3)
            self.assertEqual(doc.page_count, 2)  # 凡例が 1 ページ増える
            self.assertGreaterEqual(len(doc[0].get_drawings()) - before, len(spans))
            self.assertIn("style classes", str(doc[1].get_text()))

    def test_no_legend(self):
        with make_doc() as doc:
            spans = extract_spans(doc)
            annotate_document(doc, spans, AnnotationOptions(legend=False), "test.pdf")
            self.assertEqual(doc.page_count, 1)

    def test_original_text_is_untouched(self):
        with make_doc() as doc:
            before = str(doc[0].get_text())
            annotate_document(doc, extract_spans(doc), AnnotationOptions(), "t.pdf")
            self.assertIn(before.strip(), str(doc[0].get_text()))

    def test_empty_document(self):
        with pymupdf.open() as doc:
            doc.new_page()
            annotate_document(doc, [], AnnotationOptions(), "empty.pdf")
            self.assertEqual(doc.page_count, 2)
            self.assertIn("no text spans found", str(doc[1].get_text()))

    def test_grid_step_must_be_positive(self):
        with make_doc() as doc, self.assertRaises(ValueError):
            annotate_document(
                doc,
                extract_spans(doc),
                AnnotationOptions(grid=True, grid_step=0),
                "t.pdf",
            )


if __name__ == "__main__":
    unittest.main()
