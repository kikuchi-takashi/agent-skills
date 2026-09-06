#!/usr/bin/env python3
"""高度デザイン用の役割付きカラーパレットを生成する。

主題の意味づけは palette-intent.json に記録し、色の派生、コントラスト調整、
候補比較は決定的な計算で行う。外部APIやネットワークは使わない。
"""

import argparse
import colorsys
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path


HEX_RE = re.compile(r"^#?([0-9A-Fa-f]{6})$")
ROLES = ("bg", "text", "muted", "line", "panel", "primary", "accent")
STRATEGIES = (
    ("complementary", 0.50),
    ("split-complementary", 0.42),
    ("analogous", 0.10),
)


def normalize_hex(value, label="color"):
    if not isinstance(value, str) or not HEX_RE.fullmatch(value.strip()):
        raise ValueError("%s must be 6-digit HEX" % label)
    return HEX_RE.fullmatch(value.strip()).group(1).upper()


def rgb(value):
    value = normalize_hex(value)
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def to_hex(values):
    return "".join("%02X" % round(max(0.0, min(1.0, v)) * 255) for v in values)


def hls(value):
    return colorsys.rgb_to_hls(*rgb(value))


def from_hls(hue, lightness, saturation):
    return to_hex(colorsys.hls_to_rgb(hue % 1.0, max(0, min(1, lightness)),
                                      max(0, min(1, saturation))))


def mix(a, b, amount):
    return to_hex(tuple(x * (1 - amount) + y * amount for x, y in zip(rgb(a), rgb(b))))


def luminance(value):
    def channel(v):
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(value)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(foreground, background, minimum):
    if contrast(foreground, background) >= minimum:
        return foreground
    toward = "000000" if luminance(background) > 0.5 else "FFFFFF"
    best = foreground
    for step in range(1, 21):
        candidate = mix(foreground, toward, step / 20.0)
        best = candidate
        if contrast(candidate, background) >= minimum:
            return candidate
    return best


def color_distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(rgb(a), rgb(b)))) * 255


def simulated_color(value, mode):
    matrices = {
        "protan": ((0.567, 0.433, 0.000), (0.558, 0.442, 0.000),
                   (0.000, 0.242, 0.758)),
        "deutan": ((0.625, 0.375, 0.000), (0.700, 0.300, 0.000),
                   (0.000, 0.300, 0.700)),
    }
    values = rgb(value)
    return tuple(sum(weight * channel for weight, channel in zip(row, values))
                 for row in matrices[mode])


def color_vision_distance(a, b):
    distances = [color_distance(a, b)]
    for mode in ("protan", "deutan"):
        left, right = simulated_color(a, mode), simulated_color(b, mode)
        distances.append(math.sqrt(sum((x - y) ** 2 for x, y in zip(left, right))) * 255)
    return min(distances)


def image_anchor(paths, base):
    if not paths:
        return None
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("reference_images require Pillow") from exc
    counts = {}
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = base / path
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((160, 160))
            for r, g, b in image.getdata():
                maximum, minimum = max(r, g, b), min(r, g, b)
                if maximum < 35 or minimum > 235 or maximum - minimum < 22:
                    continue
                bucket = (round(r / 24) * 24, round(g / 24) * 24, round(b / 24) * 24)
                counts[bucket] = counts.get(bucket, 0) + 1
    if not counts:
        raise ValueError("reference_images contain no usable chromatic color")
    chosen = max(counts, key=lambda c: counts[c] * (max(c) - min(c)))
    return "%02X%02X%02X" % tuple(min(255, value) for value in chosen)


def choose_anchor(intent, intent_path):
    brand = intent.get("brand_colors", [])
    if brand:
        return normalize_hex(brand[0], "brand_colors[0]"), "brand"
    if intent.get("anchor_color"):
        return normalize_hex(intent["anchor_color"], "anchor_color"), "anchor"
    sampled = image_anchor(intent.get("reference_images", []), intent_path.parent)
    if sampled:
        return sampled, "reference-image"
    raise ValueError(
        "auto palette requires brand_colors, anchor_color, or reference_images"
    )


def palette_for(anchor, surface, strategy, rotation, tone="", supplied_accent=None,
                preserve_anchor=False):
    hue, lightness, saturation = hls(anchor)
    dark = surface == "dark"
    variant = {
        "complementary": (0.00, 0.00, 1.00),
        "split-complementary": (-0.025, -0.035, 0.88),
        "analogous": (0.025, 0.045, 1.10),
    }[strategy]
    hue_shift, lightness_shift, saturation_factor = variant
    tone_lower = tone.lower()
    if any(word in tone_lower for word in ("restrained", "calm", "quiet", "静か", "抑制")):
        saturation_factor *= 0.82
    if any(word in tone_lower for word in ("vivid", "energetic", "bold", "鮮やか", "力強")):
        saturation_factor *= 1.12
    neutral_hue = hue + hue_shift * 0.5
    bg = from_hls(neutral_hue, 0.075 if dark else 0.985,
                  (0.12 if dark else 0.08) * saturation_factor)
    text = from_hls(neutral_hue, 0.94 if dark else 0.10, 0.08)
    muted = from_hls(neutral_hue, 0.70 if dark else 0.39, 0.10 * saturation_factor)
    line = from_hls(neutral_hue, 0.25 if dark else 0.84, 0.12 * saturation_factor)
    panel = from_hls(neutral_hue, 0.14 if dark else 0.94, 0.13 * saturation_factor)
    if preserve_anchor:
        primary = anchor
    else:
        base_lightness = 0.62 if dark else min(0.43, max(0.28, lightness))
        primary = from_hls(
            hue + hue_shift,
            base_lightness + lightness_shift,
            max(0.36, min(0.82, saturation * saturation_factor)),
        )
    primary = ensure_contrast(primary, bg, 3.0)
    if supplied_accent:
        accent = normalize_hex(supplied_accent, "brand_colors[1]")
    else:
        accent = from_hls(hue + rotation, 0.64 if dark else 0.45,
                          max(0.55, saturation))
    accent = ensure_contrast(accent, bg, 3.0)
    if color_vision_distance(primary, accent) < 45:
        alternatives = []
        for alternative_rotation in (0.50, 0.33, 0.67, 0.17):
            value = from_hls(hue + alternative_rotation,
                             0.64 if dark else 0.45, 0.68)
            value = ensure_contrast(value, bg, 3.0)
            alternatives.append(value)
        accent = max(alternatives, key=lambda value: color_vision_distance(primary, value))
    chart_series = [primary, accent]
    for series_rotation in (0.25, 0.75):
        value = from_hls(hue + series_rotation, 0.66 if dark else 0.42, 0.52)
        chart_series.append(ensure_contrast(value, bg, 3.0))
    palette = {
        "bg": bg, "text": ensure_contrast(text, bg, 4.5),
        "muted": ensure_contrast(muted, bg, 4.5), "line": line,
        "panel": panel, "primary": primary, "accent": accent,
    }
    checks = {
        "text_contrast": round(contrast(palette["text"], bg), 2),
        "muted_contrast": round(contrast(palette["muted"], bg), 2),
        "primary_contrast": round(contrast(primary, bg), 2),
        "accent_contrast": round(contrast(accent, bg), 2),
        "primary_accent_distance": round(color_distance(primary, accent), 1),
        "color_vision_distance": round(color_vision_distance(primary, accent), 1),
        "anchor_distance": round(color_distance(anchor, primary), 1),
    }
    score = sum(min(checks[key] / target, 1.0) for key, target in (
        ("text_contrast", 4.5), ("muted_contrast", 4.5),
        ("primary_contrast", 3.0), ("accent_contrast", 3.0),
        ("primary_accent_distance", 80.0), ("color_vision_distance", 55.0),
    ))
    return {"strategy": strategy, "palette": palette,
            "chart_series": chart_series, "checks": checks, "score": round(score, 3)}


def generate(intent, intent_path):
    basis = intent.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        raise ValueError("palette intent requires non-empty basis")
    accent_meaning = intent.get("accent_meaning", "")
    if accent_meaning and not isinstance(accent_meaning, str):
        raise ValueError("accent_meaning must be a string")
    fonts = intent.get("fonts", ["Yu Gothic"])
    if not isinstance(fonts, list) or not fonts or any(
        not isinstance(font, str) or not font.strip() for font in fonts
    ):
        raise ValueError("fonts must be a non-empty list of names")
    min_font_pt = intent.get("min_font_pt", 12)
    if not isinstance(min_font_pt, (int, float)) or min_font_pt <= 0:
        raise ValueError("min_font_pt must be a positive number")
    brand_colors = intent.get("brand_colors", [])
    reference_images = intent.get("reference_images", [])
    if not isinstance(brand_colors, list):
        raise ValueError("brand_colors must be a list")
    if not isinstance(reference_images, list):
        raise ValueError("reference_images must be a list")
    surface = intent.get("surface", "light")
    if surface not in ("light", "dark"):
        raise ValueError("surface must be light or dark")
    tone = intent.get("tone", "")
    if not isinstance(tone, str):
        raise ValueError("tone must be a string")
    anchor, source = choose_anchor(intent, intent_path)
    brand = intent.get("brand_colors", [])
    supplied_accent = brand[1] if len(brand) > 1 else None
    candidates = []
    for index, (strategy, rotation) in enumerate(STRATEGIES, start=1):
        candidate = palette_for(
            anchor, surface, strategy, rotation, tone=tone,
            supplied_accent=supplied_accent, preserve_anchor=source == "brand"
        )
        candidate["id"] = index
        candidates.append(candidate)
    seed = int(hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8], 16)
    best_score = max(candidate["score"] for candidate in candidates)
    tied = [candidate for candidate in candidates if candidate["score"] == best_score]
    automatic = tied[seed % len(tied)]["id"]
    return {
        "schema_version": "1.0",
        "palette_basis": basis.strip(),
        "accent_meaning": accent_meaning.strip(),
        "anchor": anchor,
        "anchor_source": source,
        "surface": surface,
        "tone": tone.strip(),
        "fonts": fonts,
        "min_font_pt": min_font_pt,
        "automatic_selection": automatic,
        "candidates": candidates,
    }


def write_json(path, data, force):
    if path.exists() and not force:
        raise FileExistsError("output exists: %s; use --force to replace it" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_lock(intent, generated, selection):
    if selection == "auto":
        selection = generated["automatic_selection"]
    else:
        selection = int(selection)
    candidate = next((c for c in generated["candidates"] if c["id"] == selection), None)
    if candidate is None:
        raise ValueError("selection must be auto, 1, 2, or 3")
    return {
        "fonts": intent.get("fonts", ["Yu Gothic"]),
        "palette_basis": "%s。自動生成: %s（基準色 %s）" % (
            generated["palette_basis"], candidate["strategy"], generated["anchor"]
        ),
        "palette": candidate["palette"],
        "chart_series": candidate["chart_series"],
        "min_font_pt": intent.get("min_font_pt", 12),
        "allow": [],
        "palette_generation": {
            "strategy": candidate["strategy"],
            "anchor": generated["anchor"],
            "anchor_source": generated["anchor_source"],
            "surface": generated["surface"],
            "tone": generated["tone"],
            "candidate": candidate["id"],
            "score": candidate["score"],
            "checks": candidate["checks"],
            "accent_meaning": generated["accent_meaning"],
        },
    }


def preview_deck(path, generated, intent, force):
    if path.exists() and not force:
        raise FileExistsError("output exists: %s; use --force to replace it" % path)
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
    except ImportError as exc:
        raise ValueError("--preview-pptx requires python-pptx") from exc

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    font = intent.get("fonts", ["Yu Gothic"])[0]

    def box(slide, x, y, w, h, color):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(color)
        shape.line.fill.background()
        return shape

    def label(slide, x, y, w, h, value, size, color, bold=False):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        frame = shape.text_frame
        frame.margin_left = frame.margin_right = Inches(0)
        frame.margin_top = frame.margin_bottom = Inches(0)
        paragraph = frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.LEFT
        run = paragraph.add_run()
        run.text = value
        run.font.name, run.font.size, run.font.bold = font, Pt(size), bold
        run.font.color.rgb = RGBColor.from_string(color)

    for candidate in generated["candidates"]:
        palette = candidate["palette"]
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box(slide, 0, 0, 13.333, 7.5, palette["primary"])
        label(slide, 0.8, 1.4, 11.7, 0.5, "候補 %d — %s" % (
            candidate["id"], candidate["strategy"]), 16, palette["bg"])
        label(slide, 0.8, 2.2, 10.8, 1.8, generated["palette_basis"], 34,
              palette["bg"], True)
        label(slide, 0.8, 5.8, 10.8, 0.5, "accentは意味のある箇所だけに使う",
              18, palette["accent"], True)

        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box(slide, 0, 0, 13.333, 7.5, palette["bg"])
        label(slide, 0.6, 0.6, 12.1, 1.2,
              "候補%dは、主張と証拠の階層を色でも分ける" % candidate["id"],
              28, palette["text"], True)
        box(slide, 0.6, 2.2, 7.2, 3.9, palette["panel"])
        for i, role in enumerate(ROLES):
            x = 0.8 + i * 0.92
            box(slide, x, 2.6, 0.68, 0.68, palette[role])
            label(slide, x, 3.4, 0.82, 0.35, role, 9, palette["muted"])
        label(slide, 8.3, 2.3, 4.3, 0.6, "読み取り", 16,
              palette["primary"], True)
        label(slide, 8.3, 3.1, 4.2, 1.5,
              "本文は背景とのコントラストを保ち、強調色は結論だけに使う。",
              18, palette["text"])
        label(slide, 8.3, 5.1, 4.2, 0.5,
              "contrast %.2f / accent distance %.1f" % (
                  candidate["checks"]["text_contrast"],
                  candidate["checks"]["primary_accent_distance"]),
              11, palette["muted"])
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description="主題・ブランド・画像からpalette候補を生成する")
    parser.add_argument("intent", type=Path, help="palette-intent.json")
    parser.add_argument("--candidates-out", type=Path, help="3候補のJSON")
    parser.add_argument("--preview-pptx", type=Path, help="各候補の表紙と本文を並べたPPTX")
    parser.add_argument("--select", choices=("auto", "1", "2", "3"), help="design-lockへ採用する候補")
    parser.add_argument("--lock-out", type=Path, help="選択済みdesign-lock.json")
    parser.add_argument("--force", action="store_true", help="既存の出力ファイルを置き換える")
    args = parser.parse_args(argv)
    try:
        intent = json.loads(args.intent.read_text(encoding="utf-8"))
        if not isinstance(intent, dict):
            raise ValueError("palette intent must be a JSON object")
        generated = generate(intent, args.intent)
        if args.candidates_out:
            write_json(args.candidates_out, generated, args.force)
        if args.preview_pptx:
            preview_deck(args.preview_pptx, generated, intent, args.force)
        if args.select or args.lock_out:
            if not args.select or not args.lock_out:
                raise ValueError("--select and --lock-out must be used together")
            write_json(args.lock_out, make_lock(intent, generated, args.select), args.force)
        if not (args.candidates_out or args.preview_pptx or args.lock_out):
            print(json.dumps(generated, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
