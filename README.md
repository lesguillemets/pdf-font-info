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

## Licence

MIT.

