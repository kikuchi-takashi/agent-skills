#!/usr/bin/env python3
"""既存の PPTX から設計値を抽出し、デザインロック（JSON と Markdown）を書き出す。標準ライブラリのみ。

編集や追加ページを既存のデザインに揃えるための「正」を、目分量ではなく実測で作る。

抽出するもの:
  - テーマの配色と書体、実際に使われている書体と色（用途別の頻度）
  - タイトルの位置・幅・サイズ・太さ・色・揃え（多数派）
  - 本文のサイズの語彙、左端、行間、箇条書き記号
  - 出典・フッターの位置とサイズ
  - 余白、レイアウト名の使用回数
  - 役割ごとの「複製元」（title / body / source）: 新しい要素はこれを複製して作る（本文ページから採る）

使い方:
  python3 extract_style.py deck.pptx [--json-out design-lock.json] [--md-out design-lock.md]

JSON は pptx_lint.py の --lock にそのまま渡せる（fonts / colors / min_font_pt / allow を含む）。
"""

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pptx_lint as L  # noqa: E402


def mode(counter, default=None):
    return counter.most_common(1)[0][0] if counter else default


def shape_role(shape, title_shape, ch):
    if shape is title_shape:
        return "title"
    text = shape["text"].strip()
    box = shape["box"]
    biggest = max((max(p["sizes"]) for p in shape["paragraphs"] if p["sizes"]), default=None)
    if text.startswith(L.FOOTER_PREFIXES) or (box and box[1] > ch - 1.0 and (biggest or 12) <= 11):
        return "source"
    return "body"


def resolve_hex(color, theme):
    if color is None:
        return None
    if color[0] == "srgb":
        return color[1]
    name = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}.get(color[1], color[1])
    return theme.get(name)


def extract(pkg):
    cw, ch = L.canvas_size(pkg)
    theme = L.theme_colors(pkg)
    slides = L.slide_order(pkg)
    fonts = Counter()
    text_colors, fill_colors, line_colors = Counter(), Counter(), Counter()
    title_boxes, title_sizes, title_bold, title_align, title_colors, title_fonts = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    body_sizes, body_left, body_spacing, bullets, body_colors = Counter(), Counter(), Counter(), Counter(), Counter()
    source_y, source_sizes = Counter(), Counter()
    margins = {"left": [], "right": [], "top": [], "bottom": []}
    layouts = Counter()
    donors = {}
    geoms = Counter()
    per_slide = []
    for index, part in enumerate(slides, start=1):
        if part not in pkg.names:
            continue
        layout = pkg.related(part, "/slideLayout")
        master = pkg.related(layout, "/slideMaster") if layout and layout in pkg.names else None
        if layout and layout in pkg.names:
            name_el = pkg.xml(layout).find(".//" + L.q("p", "cSld"))
            layouts[name_el.get("name", layout) if name_el is not None else layout] += 1
        layout_pos = L.placeholder_positions(pkg, layout) if layout and layout in pkg.names else {}
        master_pos = L.placeholder_positions(pkg, master) if master and master in pkg.names else {}
        shapes = L.collect_shapes(pkg, part, layout_pos, master_pos)
        text_shapes = [s for s in shapes if s["text"] and s["box"] is not None]
        title_shape = next((s for s in shapes if L.is_title(s)), None)
        if title_shape is None and text_shapes:
            band = [s for s in text_shapes if s["box"][1] < ch * 0.30]   # 上部帯だけを候補に（巨大数字を拾わない）
            if band:
                title_shape = max(band, key=lambda s: max((max(p["sizes"]) for p in s["paragraphs"] if p["sizes"]), default=0))
        full_bleed = any(s["kind"] == "shape" and s["filled"] and s["box"] is not None
                         and s["box"][2] >= cw * 0.95 and s["box"][3] >= ch * 0.95 for s in shapes)
        content_rects = [s for s in shapes if s["kind"] == "shape" and s["filled"] and not s["text"]
                         and s["box"] is not None
                         and not (s["box"][2] >= cw * 0.95 and s["box"][3] >= ch * 0.95)]
        is_cover = full_bleed or (len(text_shapes) <= 2 and not content_rects)
        roles = {}
        for s in text_shapes:
            role = shape_role(s, title_shape, ch)
            roles[s["name"] or s["id"]] = role
            x, y, w, h = s["box"]
            for para in s["paragraphs"]:
                if not para["text"].strip():
                    continue
                size = max(para["sizes"]) if para["sizes"] else None
                for run in para["runs"]:
                    if run["text"].strip():
                        hexc = resolve_hex(run["color"], theme)
                        if hexc:
                            text_colors[hexc] += 1
                            if role == "title":
                                title_colors[hexc] += 1
                            elif role == "body":
                                body_colors[hexc] += 1
                for f in para["fonts"]:
                    if not L.THEME_FONT_RE.match(f):
                        fonts[f] += 1
                        if role == "title":
                            title_fonts[f] += 1
                if role == "title":
                    if size:
                        title_sizes[round(size)] += 1
                    title_bold[any(r["bold"] for r in para["runs"] if r["text"].strip())] += 1
                    title_align[para["algn"]] += 1
                elif role == "body":
                    if size:
                        body_sizes[round(size)] += 1
                    body_spacing[round(para["line_spacing"], 2)] += 1
                    if para["bullet"]:
                        bullets[para["bullet"]] += 1
                else:
                    if size:
                        source_sizes[round(size)] += 1
            if role == "title" and not is_cover:
                title_boxes[(round(x, 2), round(y, 2), round(w, 2), round(h, 2))] += 1
            elif role == "body":
                body_left[round(x, 2)] += 1
            elif role == "source":
                source_y[round(y, 2)] += 1
            if not is_cover:
                margins["left"].append(x)
                margins["right"].append(cw - (x + w))
                margins["top"].append(y)
                margins["bottom"].append(ch - (y + h))
            if not is_cover and role not in donors and para_has_sizes(s):
                donors[role] = {"slide": index, "shape": s["name"] or s["id"]}
        for s in shapes:
            if s["kind"] == "shape" and s["filled"]:
                geoms[s["geom"] or "rect"] += 1
                sp_pr = s["el"].find(L.q("p", "spPr"))
                hexc = resolve_hex(L.color_of(sp_pr), theme) if sp_pr is not None else None
                if hexc:
                    fill_colors[hexc] += 1
                ln = sp_pr.find(L.q("a", "ln")) if sp_pr is not None else None
                if ln is not None:
                    hexl = resolve_hex(L.color_of(ln), theme)
                    if hexl:
                        line_colors[hexl] += 1
        per_slide.append({"index": index, "is_cover": is_cover, "roles": roles})

    used_colors = Counter()
    used_colors.update(text_colors); used_colors.update(fill_colors); used_colors.update(line_colors)
    body_size_list = sorted(body_sizes)
    profile = {
        "canvas_in": [round(cw, 3), round(ch, 3)],
        "theme": {"colors": theme, "fonts": L.theme_fonts(pkg)},
        "fonts_used": dict(fonts.most_common()),
        "colors_by_use": {"text": dict(text_colors.most_common(8)), "fill": dict(fill_colors.most_common(8)), "line": dict(line_colors.most_common(8))},
        "title": {
            "box_in": list(mode(title_boxes)) if title_boxes else None,
            "size_pt": mode(title_sizes), "bold": mode(title_bold), "align": mode(title_align, "l"),
            "color": mode(title_colors), "font": mode(title_fonts),
        },
        "body": {
            "sizes_pt": dict(body_sizes.most_common()), "left_x_in": mode(body_left),
            "line_spacing": mode(body_spacing), "bullet": mode(bullets), "color": mode(body_colors),
        },
        "source": {"y_in": mode(source_y), "size_pt": mode(source_sizes)},
        "margins_in": {k: round(min(v), 2) if v else None for k, v in margins.items()},
        "layouts": dict(layouts.most_common()),
        "shape_geometry": dict(geoms.most_common()),
        "donors": donors,
        "slides": per_slide,
    }
    lock = {
        "fonts": [f for f, _ in fonts.most_common()] or [theme.get("minorFont", {}).get("ea") if isinstance(theme.get("minorFont"), dict) else None],
        "colors": [c for c, _ in used_colors.most_common(12)],
        "min_font_pt": min(body_size_list) if body_size_list else 12,
        "allow": [],
        "profile": profile,
    }
    lock["fonts"] = [f for f in lock["fonts"] if f]
    return lock


def para_has_sizes(shape):
    return any(p["sizes"] for p in shape["paragraphs"])


def to_markdown(lock, path):
    p = lock["profile"]
    t, b, s = p["title"], p["body"], p["source"]

    def fmt_box(box):
        return "x %.2f, y %.2f, 幅 %.2f, 高さ %.2f" % tuple(box) if box else "（検出なし）"

    lines = [
        "# デザインロック（%s から抽出）" % os.path.basename(path),
        "",
        "この値が「正」。編集や追加ページはここから外れない。外れる必要があるときはこの文書を直し、理由を書く。",
        "",
        "## 書体",
        "- 使用中: " + (", ".join("%s（%d）" % (f, n) for f, n in p["fonts_used"].items()) or "明示指定なし（テーマ既定）"),
        "- テーマ: 見出し %s / 本文 %s" % (p["theme"]["fonts"].get("majorFont"), p["theme"]["fonts"].get("minorFont")),
        "",
        "## 色（用途別、頻度順）",
        "- 文字: " + (", ".join("%s（%d）" % kv for kv in p["colors_by_use"]["text"].items()) or "なし"),
        "- 塗り: " + (", ".join("%s（%d）" % kv for kv in p["colors_by_use"]["fill"].items()) or "なし"),
        "- 線: " + (", ".join("%s（%d）" % kv for kv in p["colors_by_use"]["line"].items()) or "なし"),
        "- テーマ: " + ", ".join("%s=%s" % kv for kv in p["theme"]["colors"].items()),
        "",
        "## タイトル（本文ページの多数派）",
        "- 箱: " + fmt_box(t["box_in"]),
        "- サイズ %s pt、太字 %s、揃え %s、色 %s、書体 %s" % (t["size_pt"], t["bold"], t["align"], t["color"], t["font"]),
        "",
        "## 本文",
        "- サイズの語彙: " + (", ".join("%s pt（%d）" % kv for kv in b["sizes_pt"].items()) or "なし"),
        "- 左端 x %s、行間 %s、箇条書き記号 %s、色 %s" % (b["left_x_in"], b["line_spacing"], b["bullet"] or "なし", b["color"]),
        "",
        "## 出典・フッター",
        "- y %s、サイズ %s pt" % (s["y_in"], s["size_pt"]),
        "",
        "## 余白（本文ページの最小値）",
        "- 左 %s / 右 %s / 上 %s / 下 %s" % tuple(p["margins_in"][k] for k in ("left", "right", "top", "bottom")),
        "",
        "## レイアウトと図形",
        "- レイアウト: " + (", ".join("%s（%d）" % kv for kv in p["layouts"].items()) or "なし"),
        "- 塗り図形の形: " + (", ".join("%s（%d）" % kv for kv in p["shape_geometry"].items()) or "なし"),
        "",
        "## 複製元（新しい要素はこれを複製して文言だけ変える）",
    ]
    for role, d in p["donors"].items():
        lines.append("- %s: スライド %d の「%s」" % (role, d["slide"], d["shape"]))
    lines += ["", "## 変更履歴", "- 抽出時点の値。変更するときは日付と理由を追記する。", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="PPTX から設計値を抽出してデザインロックを作る")
    parser.add_argument("pptx")
    parser.add_argument("--json-out", help="design-lock.json の書き出し先（pptx_lint --lock に渡せる）")
    parser.add_argument("--md-out", help="design-lock.md の書き出し先")
    args = parser.parse_args(argv)
    pkg = L.Package(args.pptx)
    lock = extract(pkg)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(lock, fh, ensure_ascii=False, indent=2)
        print(args.json_out)
    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(lock, args.pptx))
        print(args.md_out)
    if not args.json_out and not args.md_out:
        print(to_markdown(lock, args.pptx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
