# pdf-font-info

Extract text spans and basic font information from PDF files into TSV files.

The extraction is based on MuPDF.

## Usage

Run directly from the repository:

```sh
uv run pdf-font-info file.pdf
```

Multiple PDFs can be given at once:

```sh
uv run pdf-font-info file1.pdf file2.pdf
```

Alternatively, install it as a command-line tool:

```sh
uv tool install .
pdf-font-info file.pdf
```

Output is written next to each input file:

```text
file.pdf
file.pdf.font-info.tsv
```

Existing output files are not overwritten.

Use `-v` for informational logging and `-vv` for debug logging:

```sh
uv run pdf-font-info -v file.pdf
```

With `--annotate`, an annotated copy of the PDF is written alongside the TSV:

```sh
uv run pdf-font-info --annotate file.pdf
```

```text
file.pdf
file.pdf.font-info.tsv
file.pdf.font-annotated.pdf
```

`--annotate-only` writes the annotated PDF and skips the TSV.

## Output

The TSV contains the following columns:

```text
page
font
size
color
flag_code
flags
x0
y0
x1
y1
text
```

`page` is 1-indexed.

`size` and bounding-box coordinates are written to two decimal places.

`flag_code` is the raw PyMuPDF font-flags value. `flags` is a human-readable representation, for example:

```text
serifed,bold
sans,italic
superscript,sans
```

Tabs, line breaks, carriage returns, and backslashes in extracted text are escaped so that each span occupies one physical TSV line.

The bounding-box coordinates are those returned by PyMuPDF for each text span.

## Annotated PDF

`--annotate` draws the font information onto a copy of the document.

Spans that share a `(font, size, colour, flags)` tuple form a *style class*.
Each class is given a colour and a number; every span is boxed in its class
colour and the number is written by the box, so a page can be read at a glance
even where the text is dense. A legend listing the classes, most frequent
first, is appended at the end of the document:

```text
[  1]  NimbusRoman-Regular    10.00pt  #000000  serifed          412 spans on 9 pages
[  2]  NimbusRoman-Bold       14.00pt  #000000  serifed,bold       9 spans on 4 pages
[  3]  NimbusMono-Regular      9.00pt  #444444  sans,monospaced   37 spans on 2 pages
```

A run of consecutive spans in the same class is captioned once, at its first
span; `--label-every-span` captions all of them.

The annotations are drawn as ordinary page content rather than as PDF
annotation objects, so they survive printing and rasterising and look the same
in every viewer. The input file is never modified.

| flag | effect |
| --- | --- |
| `--annotate`, `-a` | also write `*.font-annotated.pdf` |
| `--annotate-only`, `-A` | write the annotated PDF and not the TSV |
| `--labels` | write font, size and colour by each box, not just the class number |
| `--label-every-span` | caption every span rather than once per run |
| `--no-class-numbers` | draw bare boxes |
| `--no-legend` | do not append the legend page(s) |
| `--label-size PT` | size of the captions (default: 5) |
| `--grid` | overlay a coordinate grid |
| `--grid-step PT` | grid spacing (default: 50) |
| `--colour-scheme NAME` | `okabe-ito` (default), `bright` or `mono` |
| `--colours HEX,HEX,...` | explicit palette, e.g. `'#0072b2,#d55e00'` |

`--color-scheme` and `--colors` are accepted as aliases.

The grid is drawn in the PDF coordinate system used elsewhere in the output:
the origin is the top left of the page, `y` increases downwards, and the units
are points, so the numbers along the edges can be read against the `x0`, `y0`,
`x1` and `y1` columns of the TSV.

The default palette is the Okabe-Ito qualitative palette, minus the yellow that
is hard to see on white. Where a document has more style classes than the
palette has colours the colours repeat; the class numbers stay unique.

## Licence

MIT.

