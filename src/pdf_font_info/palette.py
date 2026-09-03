"""
style class に割り当てる色 (と破線パターン) を決めるところ。

固定の palette は数が足りない。組版の乱れた文書ほど style class は増えるので、
既定では OKLab 上の farthest-point sampling で必要な数だけ色を作る。

貪欲法なので列は前方安定 (prefix-stable) になっている: n 色を求めたときの先頭 k 色は、
k 色だけを求めたときと一致する。文書に class が増えても既存の class の色は変わらない。

色だけで見分けられるのは、よくて 20 色前後。それを超える分は破線パターンを
第二のチャンネルとして使う (色 x 破線)。それでも足りなければ class 番号が残る。
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache

RGB = tuple[float, float, float]
OKLab = tuple[float, float, float]

# 色が足りなくなったら破線で区別する。PyMuPDF の dashes 文字列。
DASH_PATTERNS: tuple[str | None, ...] = (
    None,  # 実線
    "[2.5 1.5] 0",
    "[0.8 1.6] 0",
    "[4 1.4 0.8 1.4] 0",
)

# 生成に使う候補の格子。細かくしても見分けやすさは頭打ちなので粗くてよい。
_GRID_STEP = 15
# 紙 (白) の上で見えるように、明るすぎ・暗すぎを外す。OKLab の L。
_L_MIN = 0.32
_L_MAX = 0.62
# 白 (紙) と黒 (本文) からも離す。枠が地の色や本文の色に紛れないように。
_AVOIDED = (0xFFFFFF, 0x000000)
# くすんだ色は細い枠線だと見分けがつかないので、彩度の下限も設ける。OKLab の C。
_C_MIN = 0.09
# 生成する色数の上限。色だけで見分けられるのはこのくらいまで。
# これを超えると色は循環し、破線パターンで区別する。
_MAX_GENERATED = 16


def srgb_to_oklab(color: int) -> OKLab:
    """
    sRGB (0xRRGGBB) を OKLab に。
    https://bottosson.github.io/posts/oklab/
    """

    def linear(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r = linear((color >> 16) & 0xFF)
    g = linear((color >> 8) & 0xFF)
    b = linear(color & 0xFF)

    l = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)

    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def _distance2(a: OKLab, b: OKLab) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


@cache
def distinct_colours(n: int) -> tuple[int, ...]:
    """
    OKLab 上で互いにできるだけ離れた n 色を貪欲に選ぶ (Glasbey 1988 と同じ考えかた)。

    紙の白と本文の黒をあらかじめ「選んだ色」として置き、以降は「すでに選んだ色への
    最短距離」が最大になるものを選ぶ。決定的なので、同じ文書からは常に同じ色が出る。
    """
    if n <= 0:
        return ()

    levels = list(range(0, 256, _GRID_STEP))
    if levels[-1] != 255:
        levels.append(255)
    candidates: list[tuple[int, OKLab]] = []
    for r in levels:
        for g in levels:
            for b in levels:
                color = (r << 16) | (g << 8) | b
                lab = srgb_to_oklab(color)
                chroma = math.hypot(lab[1], lab[2])
                if _L_MIN <= lab[0] <= _L_MAX and chroma >= _C_MIN:
                    candidates.append((color, lab))

    avoided = [srgb_to_oklab(c) for c in _AVOIDED]
    nearest = [min(_distance2(lab, a) for a in avoided) for _, lab in candidates]

    chosen: list[int] = []
    for _ in range(min(n, _MAX_GENERATED, len(candidates))):
        best = max(
            range(len(candidates)), key=lambda i: (nearest[i], -candidates[i][0])
        )
        color, lab = candidates[best]
        chosen.append(color)
        for i, (_, other) in enumerate(candidates):
            d = _distance2(lab, other)
            nearest[i] = min(nearest[i], d)

    return tuple(chosen)


@dataclass(frozen=True)
class Palette:
    """n 個の style class に (色, 破線) を割り当てるもの。"""

    name: str
    fixed: tuple[int, ...] | None = None

    def colours(self, n: int) -> tuple[int, ...]:
        if n <= 0:
            return ()
        base = self.fixed if self.fixed is not None else distinct_colours(n)
        if not base:
            raise ValueError(f"empty palette: {self.name}")
        return tuple(base[i % len(base)] for i in range(n))

    def assignments(self, n: int) -> tuple[tuple[int, str | None], ...]:
        """
        色を使い切ったら破線パターンを変えて、色 x 破線 で区別する。
        """
        if n <= 0:
            return ()
        base = self.fixed if self.fixed is not None else distinct_colours(n)
        if not base:
            raise ValueError(f"empty palette: {self.name}")
        out: list[tuple[int, str | None]] = []
        for i in range(n):
            colour = base[i % len(base)]
            dash = DASH_PATTERNS[(i // len(base)) % len(DASH_PATTERNS)]
            out.append((colour, dash))
        return tuple(out)


NAMED_PALETTES: dict[str, Palette] = {
    # 既定。必要な数だけ、互いに離れた色を作る。
    "distinct": Palette("distinct"),
    # 色覚多様性に配慮した Okabe-Ito から、白地で見えにくい黄 (#f0e442) を除いたもの。
    # class が 7 つ以下に収まる文書ならこちらのほうが安全。
    "okabe-ito": Palette(
        "okabe-ito",
        (0x0072B2, 0xD55E00, 0x009E73, 0xCC79A7, 0xE69F00, 0x56B4E9, 0x000000),
    ),
    "bright": Palette(
        "bright",
        (0xFF0000, 0x0000FF, 0x00A000, 0xFF00FF, 0xFF8000, 0x00A0A0, 0x8000FF),
    ),
    # 単色印刷向け。色ではなく破線と class 番号で区別する。
    "mono": Palette("mono", (0x000000,)),
}
DEFAULT_PALETTE = "distinct"


def to_rgb(color: int) -> RGB:
    """0xRRGGBB を PyMuPDF の (r, g, b) 0.0-1.0 に。"""
    return (
        ((color >> 16) & 0xFF) / 255.0,
        ((color >> 8) & 0xFF) / 255.0,
        (color & 0xFF) / 255.0,
    )


def parse_colours(colours: str) -> tuple[int, ...]:
    parsed: list[int] = []
    for raw in colours.split(","):
        token = raw.strip().lstrip("#")
        if not token:
            continue
        try:
            value = int(token, 16)
        except ValueError as e:
            raise ValueError(f"not a hex colour: {raw!r}") from e
        if not 0 <= value <= 0xFFFFFF:
            raise ValueError(f"colour out of range: {raw!r}")
        parsed.append(value)
    if not parsed:
        raise ValueError("no colours given")
    return tuple(parsed)


def parse_palette(scheme: str | None, colours: str | None) -> Palette:
    """
    ``--colour-scheme`` と ``--colours`` から palette を決める。
    ``--colours`` があればそちらが優先。
    """
    if colours:
        return Palette("custom", parse_colours(colours))

    name = scheme or DEFAULT_PALETTE
    if name not in NAMED_PALETTES:
        raise ValueError(f"unknown colour scheme: {name!r}")
    return NAMED_PALETTES[name]


def palette_names() -> Sequence[str]:
    return sorted(NAMED_PALETTES)
