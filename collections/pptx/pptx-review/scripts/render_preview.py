#!/usr/bin/env python3
"""PPTX を Pillow だけで PNG に描く簡易描画。外部ツールを使わない。

目的は「レイアウトの事実」を見ること。位置・大きさ・折り返し・重なり・余白・色の配分を
確認できる精度を狙い、PowerPoint の描画と一致することは狙わない。

描くもの:
  - 背景、矩形・角丸・楕円・線、塗りと枠線（テーマ色は theme1.xml で解決）
  - 文字（段落・箇条書き・揃え・行間・太字・色）。書体ファイルがあればその字形で、
    無い文字（和文書体が無い環境の和文など）は文字幅どおりの灰色バーで代替する
  - 画像（PNG/JPEG。読めない形式は灰色の箱）、表、棒・折れ線・円の図表
  - 箱に収まらない文字は赤い枠で示す

使い方:
  python3 render_preview.py deck.pptx [--out qa/preview] [--slides 1,3-5]
                            [--scale 96] [--font path.ttf] [--sheet]

出力: <out>-NN.png（1枚ずつ）と、--sheet で <out>-sheet.png（一覧）。
標準出力に、使った書体と、赤枠を付けたページを出す。
"""

import argparse
import io
import math
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pptx_lint as L  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow が必要", file=sys.stderr)
    sys.exit(2)

SCHEME_ALIAS = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}
ACCENT_ORDER = ["accent1", "accent2", "accent3", "accent4", "accent5", "accent6"]
DEFAULT_SIZES = {"title": 40, "ctrTitle": 44, "subTitle": 32, "body": 18}
GREEK = (150, 150, 150)


# ---------------------------------------------------------------- 色

def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def apply_mods(rgb, mods):
    r, g, b = [c / 255.0 for c in rgb]
    if "tint" in mods:
        r, g, b = [1 - (1 - c) * mods["tint"] for c in (r, g, b)]
    if "shade" in mods:
        r, g, b = [c * mods["shade"] for c in (r, g, b)]
    if "lumMod" in mods or "lumOff" in mods:
        import colorsys
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        l = l * mods.get("lumMod", 1.0) + mods.get("lumOff", 0.0)
        r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), s)
    return tuple(int(round(max(0.0, min(1.0, c)) * 255)) for c in (r, g, b))


def resolve(color, theme, default=None):
    if color is None:
        return default
    if color[0] == "srgb":
        return hex_rgb(color[1])
    name = SCHEME_ALIAS.get(color[1], color[1])
    base = theme.get(name)
    if base is None:
        return default
    return apply_mods(hex_rgb(base), color[2] if len(color) > 2 else {})


def direct_color(node):
    """fillRef / lnRef のように、solidFill を介さず色要素を直接持つノード用。"""
    srgb = node.find(L.q("a", "srgbClr"))
    if srgb is not None:
        return ("srgb", srgb.get("val", "000000").upper())
    scheme = node.find(L.q("a", "schemeClr"))
    if scheme is not None:
        return ("scheme", scheme.get("val", "tx1"), {})
    return None


# ---------------------------------------------------------------- 書体

class Fonts(object):
    def __init__(self, cjk_path, latin_path):
        self.cjk_path, self.latin_path = cjk_path, latin_path
        self._cache = {}

    def get(self, size_px, prefer_cjk):
        path = self.cjk_path if (prefer_cjk and self.cjk_path) else (self.latin_path or self.cjk_path)
        key = (path, size_px)
        if key not in self._cache:
            try:
                self._cache[key] = ImageFont.truetype(path, max(size_px, 4)) if path else None
            except Exception:
                self._cache[key] = None
        return self._cache[key]

    def drawable(self, ch):
        wide = unicodedata.east_asian_width(ch) in ("W", "F")
        if wide:
            return self.cjk_path is not None
        return self.latin_path is not None or self.cjk_path is not None


def is_wide(ch):
    return unicodedata.east_asian_width(ch) in ("W", "F")


# ---------------------------------------------------------------- 描画本体

class Renderer(object):
    def __init__(self, pkg, scale, fonts):
        self.pkg = pkg
        self.scale = float(scale)
        self.fonts = fonts
        self.theme = L.theme_colors(pkg)
        self.cw, self.ch = L.canvas_size(pkg)
        self.overflows = []

    def px(self, inches):
        return int(round(inches * self.scale))

    def pt_px(self, pt):
        return pt / 72.0 * self.scale

    # ---- スライド
    def render_slide(self, part, index):
        img = Image.new("RGB", (self.px(self.cw), self.px(self.ch)), self.background(part))
        draw = ImageDraw.Draw(img)
        layout = self.pkg.related(part, "/slideLayout")
        master = self.pkg.related(layout, "/slideMaster") if layout and layout in self.pkg.names else None
        layout_pos = L.placeholder_positions(self.pkg, layout) if layout and layout in self.pkg.names else {}
        master_pos = L.placeholder_positions(self.pkg, master) if master and master in self.pkg.names else {}
        shapes = L.collect_shapes(self.pkg, part, layout_pos, master_pos)
        for shape in shapes:
            if shape["box"] is None:
                continue
            try:
                self.draw_shape(img, draw, shape, part, index)
            except Exception as exc:  # 1つの図形で止めない
                x, y, w, h = shape["box"]
                draw.rectangle([self.px(x), self.px(y), self.px(x + w), self.px(y + h)], outline=(200, 0, 0), width=2)
                print("  slide %d: %s の描画に失敗（%s）" % (index, shape["name"] or shape["id"], exc), file=sys.stderr)
        return img

    def background(self, part):
        root = self.pkg.xml(part)
        bg = root.find(".//" + L.q("p", "bg") + "/" + L.q("p", "bgPr"))
        if bg is not None:
            color = resolve(L.color_of(bg), self.theme)
            if color:
                return color
        base = self.theme.get("lt1")
        return hex_rgb(base) if base else (255, 255, 255)

    # ---- 図形の振り分け
    def draw_shape(self, img, draw, shape, part, index):
        kind = shape["kind"]
        if kind == "picture":
            self.draw_picture(img, draw, shape, part)
        elif kind == "table":
            self.draw_table(draw, shape)
        elif kind == "chart":
            self.draw_chart(draw, shape, part)
        elif kind == "graphic":
            self.box_label(draw, shape["box"], "graphic")
        elif kind == "connector":
            self.draw_connector(draw, shape)
        else:
            self.draw_autoshape(draw, shape)
        if shape["text"]:
            self.draw_text(draw, shape, index)

    # ---- 塗りと線
    def fill_and_line(self, el):
        sp_pr = el.find(L.q("p", "spPr"))
        fill = line = None
        line_w = 1
        if sp_pr is not None:
            if sp_pr.find(L.q("a", "noFill")) is None:
                fill = resolve(L.color_of(sp_pr), self.theme)
            ln = sp_pr.find(L.q("a", "ln"))
            if ln is not None:
                if ln.find(L.q("a", "noFill")) is None:
                    line = resolve(L.color_of(ln), self.theme)
                    line_w = max(1, int(round(int(ln.get("w", "9525")) / 9525.0)))
                    if line is None and ln.find(L.q("a", "solidFill")) is None:
                        line = self.style_color(el, "lnRef")
            else:
                line = self.style_color(el, "lnRef")
        if fill is None and (sp_pr is None or sp_pr.find(L.q("a", "noFill")) is None) and L.color_of(sp_pr if sp_pr is not None else el) is None:
            fill = self.style_color(el, "fillRef")
        return fill, line, line_w

    def style_color(self, el, ref):
        style = el.find(L.q("p", "style"))
        if style is None:
            return None
        node = style.find(L.q("a", ref))
        if node is None or node.get("idx", "0") == "0":
            return None
        return resolve(direct_color(node), self.theme)

    def draw_autoshape(self, draw, shape):
        el = shape["el"]
        x, y, w, h = shape["box"]
        fill, line, line_w = self.fill_and_line(el)
        if shape["placeholder"] and fill is None and line is None:
            return
        box = [self.px(x), self.px(y), self.px(x + w), self.px(y + h)]
        geom = shape["geom"] or "rect"
        if geom == "roundRect":
            adj = 16667
            for gd in el.iter(L.q("a", "gd")):
                if gd.get("name") == "adj":
                    try:
                        adj = int(gd.get("fmla", "val 16667").split()[-1])
                    except ValueError:
                        pass
            radius = int(round(min(w, h) * adj / 100000.0 * self.scale))
            draw.rounded_rectangle(box, radius=max(radius, 1), fill=fill, outline=line, width=line_w)
        elif geom == "ellipse":
            draw.ellipse(box, fill=fill, outline=line, width=line_w)
        elif geom == "line":
            self.draw_connector(draw, shape)
        elif geom in ("rect", "flowChartProcess", "snip1Rect", "round1Rect", "round2SameRect") or fill is not None or line is not None:
            if geom not in ("rect", "flowChartProcess"):
                draw.rectangle(box, fill=fill, outline=line or (180, 180, 180), width=line_w)
            else:
                draw.rectangle(box, fill=fill, outline=line, width=line_w)

    def draw_connector(self, draw, shape):
        el = shape["el"]
        x, y, w, h = shape["box"]
        xfrm = el.find(".//" + L.q("a", "xfrm"))
        flip_v = xfrm is not None and xfrm.get("flipV") == "1"
        flip_h = xfrm is not None and xfrm.get("flipH") == "1"
        x0, y0, x1, y1 = self.px(x), self.px(y), self.px(x + w), self.px(y + h)
        if flip_h:
            x0, x1 = x1, x0
        if flip_v:
            y0, y1 = y1, y0
        _, line, line_w = self.fill_and_line(el)
        draw.line([x0, y0, x1, y1], fill=line or (120, 120, 120), width=max(line_w, 1))

    def box_label(self, draw, box, label):
        x, y, w, h = box
        rect = [self.px(x), self.px(y), self.px(x + w), self.px(y + h)]
        draw.rectangle(rect, fill=(225, 225, 225), outline=(170, 170, 170))
        font = self.fonts.get(int(self.pt_px(12)), False)
        if font:
            draw.text((rect[0] + 6, rect[1] + 6), label, fill=(110, 110, 110), font=font)

    # ---- 画像
    def draw_picture(self, img, draw, shape, part):
        el = shape["el"]
        x, y, w, h = shape["box"]
        blip = el.find(".//" + L.q("a", "blip"))
        rid = blip.get(L.q("r", "embed")) if blip is not None else None
        target = self.pkg.rels(part).get(rid, (None, None))[1] if rid else None
        if not target or target not in self.pkg.names:
            self.box_label(draw, shape["box"], "image")
            return
        try:
            pic = Image.open(io.BytesIO(self.pkg.zip.read(target))).convert("RGBA")
        except Exception:
            self.box_label(draw, shape["box"], "image (%s)" % target.rsplit(".", 1)[-1])
            return
        src = el.find(".//" + L.q("a", "srcRect"))
        if src is not None:
            pw, ph = pic.size
            l = int(src.get("l", "0") or 0) / 100000.0
            t = int(src.get("t", "0") or 0) / 100000.0
            r = int(src.get("r", "0") or 0) / 100000.0
            b = int(src.get("b", "0") or 0) / 100000.0
            pic = pic.crop((int(pw * l), int(ph * t), int(pw * (1 - r)), int(ph * (1 - b))))
        size = (max(self.px(w), 1), max(self.px(h), 1))
        pic = pic.resize(size)
        img.paste(pic, (self.px(x), self.px(y)), pic)

    # ---- 表
    def draw_table(self, draw, shape):
        el = shape["el"]
        x, y, w, h = shape["box"]
        tbl = el.find(".//" + L.q("a", "tbl"))
        if tbl is None:
            self.box_label(draw, shape["box"], "table")
            return
        cols = [int(c.get("w", "0")) / L.EMU for c in tbl.findall(L.q("a", "tblGrid") + "/" + L.q("a", "gridCol"))]
        rows = tbl.findall(L.q("a", "tr"))
        cy = y
        for tr in rows:
            rh = int(tr.get("h", "0")) / L.EMU
            cx = x
            for j, tc in enumerate(tr.findall(L.q("a", "tc"))):
                cw_ = cols[j] if j < len(cols) else (w / max(len(cols), 1))
                tcpr = tc.find(L.q("a", "tcPr"))
                fill = resolve(L.color_of(tcpr), self.theme) if tcpr is not None else None
                rect = [self.px(cx), self.px(cy), self.px(cx + cw_), self.px(cy + rh)]
                if fill:
                    draw.rectangle(rect, fill=fill)
                for tag, seg in (("lnL", (rect[0], rect[1], rect[0], rect[3])), ("lnR", (rect[2], rect[1], rect[2], rect[3])),
                                 ("lnT", (rect[0], rect[1], rect[2], rect[1])), ("lnB", (rect[0], rect[3], rect[2], rect[3]))):
                    ln = tcpr.find(L.q("a", tag)) if tcpr is not None else None
                    if ln is None:
                        draw.line(seg, fill=(215, 215, 215), width=1)
                    elif ln.find(L.q("a", "noFill")) is None and int(ln.get("w", "0") or 0) > 0:
                        draw.line(seg, fill=resolve(L.color_of(ln), self.theme, (120, 120, 120)), width=max(1, int(int(ln.get("w")) / 9525)))
                insets = {"l": 0.1, "r": 0.1, "t": 0.05, "b": 0.05}
                if tcpr is not None:
                    for side, attr in (("l", "marL"), ("r", "marR"), ("t", "marT"), ("b", "marB")):
                        if tcpr.get(attr):
                            insets[side] = int(tcpr.get(attr)) / L.EMU
                paras = L.paragraphs(tc.find(L.q("a", "txBody")))
                self.layout_text(draw, (cx, cy, cw_, rh), paras, insets, anchor="t", default_size=14, mark=None)
                cx += cw_
            cy += rh

    # ---- 図表
    def draw_chart(self, draw, shape, part):
        el = shape["el"]
        x, y, w, h = shape["box"]
        rid = None
        for node in el.iter():
            if node.tag.endswith("}chart") and node.get(L.q("r", "id")):
                rid = node.get(L.q("r", "id"))
        target = self.pkg.rels(part).get(rid, (None, None))[1] if rid else None
        if not target or target not in self.pkg.names:
            self.box_label(draw, shape["box"], "chart")
            return
        ns = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
        root = self.pkg.xml(target)
        plot = root.find(".//" + ns + "plotArea")
        if plot is None:
            self.box_label(draw, shape["box"], "chart")
            return
        series, chart_type, bar_dir = [], None, "col"
        for child in plot:
            tag = child.tag.split("}")[-1]
            if tag.endswith("Chart"):
                chart_type = tag
                bd = child.find(ns + "barDir")
                if bd is not None:
                    bar_dir = bd.get("val", "col")
                for i, ser in enumerate(child.findall(ns + "ser")):
                    cats = [pt.findtext(ns + "v") or "" for pt in ser.findall(ns + "cat//" + ns + "pt")]
                    vals = []
                    for pt in ser.findall(ns + "val//" + ns + "pt"):
                        try:
                            vals.append(float(pt.findtext(ns + "v")))
                        except (TypeError, ValueError):
                            vals.append(0.0)
                    sppr = ser.find(ns + "spPr")
                    color = resolve(L.color_of(sppr), self.theme) if sppr is not None else None
                    if color is None:
                        color = hex_rgb(self.theme.get(ACCENT_ORDER[i % 6], "4F81BD"))
                    show_val = ser.find(ns + "dLbls/" + ns + "showVal")
                    if show_val is None:
                        show_val = child.find(ns + "dLbls/" + ns + "showVal")
                    series.append({"cats": cats, "vals": vals, "color": color,
                                   "labels": show_val is not None and show_val.get("val") == "1"})
                break
        if not series or chart_type is None:
            self.box_label(draw, shape["box"], "chart")
            return
        pad = 0.35
        inner = (x + pad, y + pad * 0.6, w - pad * 1.6, h - pad * 2.4)
        font = self.fonts.get(int(self.pt_px(10)), True)
        if chart_type in ("barChart", "bar3DChart"):
            self.draw_bars(draw, inner, series, bar_dir, font)
        elif chart_type in ("lineChart", "areaChart", "scatterChart"):
            self.draw_lines(draw, inner, series, font)
        elif chart_type in ("pieChart", "doughnutChart", "pie3DChart"):
            self.draw_pie(draw, inner, series[0], chart_type.startswith("doughnut"), font)
        else:
            self.box_label(draw, shape["box"], "chart: " + chart_type)

    def draw_bars(self, draw, inner, series, bar_dir, font):
        ix, iy, iw, ih = inner
        all_vals = [v for s in series for v in s["vals"]] or [0.0]
        vmax, vmin = max(max(all_vals), 0.0), min(min(all_vals), 0.0)
        span = (vmax - vmin) or 1.0
        n_cat = max(len(s["vals"]) for s in series)
        n_ser = len(series)
        if bar_dir == "col":
            zero_y = iy + ih * (vmax / span)
            draw.line([self.px(ix), self.px(zero_y), self.px(ix + iw), self.px(zero_y)], fill=(160, 160, 160), width=1)
            slot = iw / max(n_cat, 1)
            bar_w = slot * 0.6 / n_ser
            for i, s in enumerate(series):
                for j, v in enumerate(s["vals"]):
                    bx = ix + j * slot + slot * 0.2 + i * bar_w
                    top = zero_y - ih * (v / span)
                    y0, y1 = sorted([top, zero_y])
                    draw.rectangle([self.px(bx), self.px(y0), self.px(bx + bar_w), self.px(y1)], fill=s["color"])
                    if s["labels"] and font:
                        label = ("%g" % v)
                        ly = y0 - 0.16 if v >= 0 else y1 + 0.02
                        draw.text((self.px(bx), self.px(ly)), label, fill=(60, 60, 60), font=font)
            if font:
                for j, cat in enumerate(series[0]["cats"]):
                    self.text_line(draw, cat, (ix + j * slot + slot * 0.1, iy + ih + 0.22), font, (80, 80, 80))
        else:
            zero_x = ix + iw * (-vmin / span)
            draw.line([self.px(zero_x), self.px(iy), self.px(zero_x), self.px(iy + ih)], fill=(160, 160, 160), width=1)
            slot = ih / max(n_cat, 1)
            bar_h = slot * 0.6 / n_ser
            for i, s in enumerate(series):
                for j, v in enumerate(s["vals"]):
                    by = iy + j * slot + slot * 0.2 + i * bar_h
                    end = zero_x + iw * (v / span)
                    x0, x1 = sorted([zero_x, end])
                    draw.rectangle([self.px(x0), self.px(by), self.px(x1), self.px(by + bar_h)], fill=s["color"])
                    if s["labels"] and font:
                        draw.text((self.px(x1 + 0.03), self.px(by)), "%g" % v, fill=(60, 60, 60), font=font)
            if font:
                for j, cat in enumerate(series[0]["cats"]):
                    self.text_line(draw, cat, (ix - 0.3, iy + j * slot + slot * 0.3), font, (80, 80, 80))

    def draw_lines(self, draw, inner, series, font):
        ix, iy, iw, ih = inner
        all_vals = [v for s in series for v in s["vals"]] or [0.0]
        vmax, vmin = max(all_vals), min(all_vals)
        if vmin > 0:
            vmin = 0.0
        span = (vmax - vmin) or 1.0
        n = max(len(s["vals"]) for s in series)
        draw.line([self.px(ix), self.px(iy + ih), self.px(ix + iw), self.px(iy + ih)], fill=(160, 160, 160))
        for s in series:
            pts = []
            for j, v in enumerate(s["vals"]):
                px_ = ix + (iw * (j + 0.5) / max(n, 1))
                py_ = iy + ih - ih * ((v - vmin) / span)
                pts.append((self.px(px_), self.px(py_)))
            if len(pts) >= 2:
                draw.line(pts, fill=s["color"], width=3)
            for p in pts:
                draw.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=s["color"])
        if font:
            for j, cat in enumerate(series[0]["cats"]):
                self.text_line(draw, cat, (ix + (iw * (j + 0.5) / max(n, 1)) - 0.2, iy + ih + 0.05), font, (80, 80, 80))

    def draw_pie(self, draw, inner, s, doughnut, font):
        ix, iy, iw, ih = inner
        d = min(iw, ih)
        cx, cy = ix + iw / 2, iy + ih / 2
        box = [self.px(cx - d / 2), self.px(cy - d / 2), self.px(cx + d / 2), self.px(cy + d / 2)]
        total = sum(abs(v) for v in s["vals"]) or 1.0
        start = -90.0
        for j, v in enumerate(s["vals"]):
            end = start + 360.0 * abs(v) / total
            color = hex_rgb(self.theme.get(ACCENT_ORDER[j % 6], "4F81BD")) if j else s["color"]
            draw.pieslice(box, start, end, fill=color, outline=(255, 255, 255))
            start = end
        if doughnut:
            r = d * 0.28
            draw.ellipse([self.px(cx - r), self.px(cy - r), self.px(cx + r), self.px(cy + r)], fill=(255, 255, 255))

    def text_line(self, draw, text, pos, font, color):
        if not self.fonts.cjk_path and any(is_wide(c) for c in text):
            width = sum(self.pt_px(10) * (1.0 if is_wide(c) else 0.55) for c in text)
            draw.rectangle([self.px(pos[0]), self.px(pos[1]) + 3, self.px(pos[0]) + width, self.px(pos[1]) + 3 + self.pt_px(7)], fill=GREEK)
        else:
            draw.text((self.px(pos[0]), self.px(pos[1])), text, fill=color, font=font)

    # ---- 文字
    def draw_text(self, draw, shape, index):
        body_pr = shape["body_pr"]
        insets = L.body_insets(body_pr)
        anchor = body_pr.get("anchor", "t") if body_pr is not None else "t"
        wrap = not (body_pr is not None and body_pr.get("wrap") == "none")
        default = DEFAULT_SIZES.get(shape["placeholder"][0], 18) if shape["placeholder"] else 18
        overflow = self.layout_text(draw, shape["box"], shape["paragraphs"], insets, anchor, default, wrap=wrap, mark=True)
        if overflow:
            x, y, w, h = shape["box"]
            draw.rectangle([self.px(x), self.px(y), self.px(x + w), self.px(y + h)], outline=(220, 0, 0), width=2)
            self.overflows.append((index, shape["name"] or shape["id"], overflow))

    def layout_text(self, draw, box, paras, insets, anchor="t", default_size=18, wrap=True, mark=None):
        x, y, w, h = box
        inner_x = x + insets["l"]
        inner_w = max(w - insets["l"] - insets["r"], 0.05)
        inner_y = y + insets["t"]
        inner_h = max(h - insets["t"] - insets["b"], 0.05)
        lines = []  # (units, size_pt, line_spacing, algn, indent_in)
        for para in paras:
            size = max(para["sizes"]) if para["sizes"] else default_size
            units = self.units(para, size)
            avail = inner_w - para["mar_l"]
            first_indent = para["indent"]
            bullet = para["bullet"]
            para_lines = self.wrap_units(units, avail, size, wrap)
            if not para_lines:
                para_lines = [[]]
            for k, ln in enumerate(para_lines):
                lines.append({"units": ln, "size": size, "ls": max(para["line_spacing"], 1.0), "algn": para["algn"],
                              "x_off": para["mar_l"] + (first_indent if k == 0 else 0.0),
                              "bullet": bullet if k == 0 else None, "before": para["before"] if k == 0 else 0.0,
                              "after": para["after"] if k == len(para_lines) - 1 else 0.0})
        if lines:
            lines[-1]["after"] = 0.0
        total_pt = sum(l["size"] * l["ls"] + l["before"] + l["after"] for l in lines)
        total_in = total_pt / 72.0
        if anchor == "ctr":
            cur = inner_y + max((inner_h - total_in) / 2.0, 0)
        elif anchor == "b":
            cur = inner_y + max(inner_h - total_in, 0)
        else:
            cur = inner_y
        for ln in lines:
            cur += ln["before"] / 72.0
            line_h = ln["size"] * ln["ls"] / 72.0
            width_in = sum(u["w"] for u in ln["units"]) / 72.0
            avail = inner_w - ln["x_off"]
            if ln["algn"] == "ctr":
                start_x = inner_x + ln["x_off"] + max((avail - width_in) / 2.0, 0)
            elif ln["algn"] == "r":
                start_x = inner_x + ln["x_off"] + max(avail - width_in, 0)
            else:
                start_x = inner_x + ln["x_off"]
            baseline_y = cur + (line_h - ln["size"] / 72.0) / 2.0
            if ln["bullet"]:
                bx = inner_x + ln["x_off"] - 0.25 if ln["x_off"] > 0.2 else inner_x
                self.put(draw, ln["bullet"] if ln["bullet"] != "#" else "1.", bx, baseline_y, ln["size"], False, (90, 90, 90))
            px_x = start_x
            for u in ln["units"]:
                self.put(draw, u["text"], px_x, baseline_y, u["size"], u["bold"], u["color"])
                px_x += u["w"] / 72.0
            cur += line_h + ln["after"] / 72.0
        overflow = total_in - inner_h
        return overflow if (mark and overflow > 0.05) else None

    def units(self, para, size):
        result = []
        for run in para["runs"]:
            rsize = run["size"] or size
            color = resolve(run["color"], self.theme, (26, 26, 26))
            text = run["text"]
            if text == "\n":
                result.append({"text": "\n", "w": 0, "size": rsize, "bold": False, "color": color})
                continue
            buf = ""
            for ch in text:
                if is_wide(ch):
                    if buf:
                        result.append(self.unit(buf, rsize, run["bold"], color)); buf = ""
                    result.append(self.unit(ch, rsize, run["bold"], color))
                elif ch == " ":
                    if buf:
                        result.append(self.unit(buf, rsize, run["bold"], color)); buf = ""
                    result.append(self.unit(" ", rsize, run["bold"], color))
                else:
                    buf += ch
            if buf:
                result.append(self.unit(buf, rsize, run["bold"], color))
        if not result and para["text"]:
            result.append(self.unit(para["text"], size, False, (26, 26, 26)))
        return result

    def unit(self, text, size, bold, color):
        return {"text": text, "w": L.MEASURER.width(text, size), "size": size, "bold": bold, "color": color}

    def wrap_units(self, units, avail_in, size, wrap):
        avail_pt = avail_in * 72.0
        lines, cur, cur_w = [], [], 0.0
        for u in units:
            if u["text"] == "\n":
                lines.append(cur); cur, cur_w = [], 0.0
                continue
            if wrap and cur and cur_w + u["w"] > avail_pt and u["text"] != " ":
                lines.append(cur); cur, cur_w = [], 0.0
            if wrap and u["w"] > avail_pt and len(u["text"]) > 1:      # 長い英単語は文字で割る
                for ch in u["text"]:
                    piece = dict(u, text=ch, w=L.MEASURER.width(ch, u["size"]))
                    if cur and cur_w + piece["w"] > avail_pt:
                        lines.append(cur); cur, cur_w = [], 0.0
                    cur.append(piece); cur_w += piece["w"]
                continue
            if not cur and u["text"] == " ":
                continue
            cur.append(u); cur_w += u["w"]
        if cur:
            lines.append(cur)
        return lines

    def put(self, draw, text, x_in, y_in, size_pt, bold, color):
        size_px = max(int(round(self.pt_px(size_pt))), 4)
        wide = any(is_wide(c) for c in text)
        font = self.fonts.get(size_px, wide)
        px, py = self.px(x_in), self.px(y_in)
        if font is None or (wide and not self.fonts.cjk_path):
            width = sum(self.pt_px(size_pt) * (1.0 if is_wide(c) else 0.55) for c in text)
            draw.rectangle([px, py + size_px * 0.15, px + width, py + size_px * 0.85], fill=GREEK)
            return
        stroke = max(1, int(size_px / 36)) if (bold and size_px >= 24) else 0
        draw.text((px, py), text, fill=color, font=font, stroke_width=stroke, stroke_fill=color if stroke else None)


# ---------------------------------------------------------------- 入口

def parse_slides(spec, n):
    if not spec:
        return list(range(1, n + 1))
    result = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            result.extend(range(int(a), int(b) + 1))
        else:
            result.append(int(part))
    return [i for i in result if 1 <= i <= n]


def contact_sheet(images, out_path, cols=4):
    if not images:
        return
    w, h = images[0].size
    tw, th = w // 3, h // 3
    rows = int(math.ceil(len(images) / float(cols)))
    sheet = Image.new("RGB", (cols * (tw + 12) + 12, rows * (th + 12) + 12), (235, 235, 235))
    for i, img in enumerate(images):
        thumb = img.resize((tw, th))
        sheet.paste(thumb, (12 + (i % cols) * (tw + 12), 12 + (i // cols) * (th + 12)))
    sheet.save(out_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="PPTX の簡易描画（Pillow のみ）")
    parser.add_argument("pptx")
    parser.add_argument("--out", default="preview", help="出力の接頭辞（<out>-NN.png）")
    parser.add_argument("--slides", help="描くページ。例: 1,3-5")
    parser.add_argument("--scale", type=float, default=96.0, help="1インチあたりの画素数（既定 96 → 16:9 で 1280×720）")
    parser.add_argument("--font", help="書体ファイル（.ttf/.otf/.ttc）。省略時は和文対応の書体を探す")
    parser.add_argument("--sheet", action="store_true", help="一覧画像 <out>-sheet.png も作る")
    args = parser.parse_args(argv)

    pkg = L.Package(args.pptx)
    cjk, latin = L.find_fonts()
    if args.font:
        cjk = args.font
    fonts = Fonts(cjk, latin)
    L.MEASURER.__init__(cjk or latin)
    slides = L.slide_order(pkg)
    targets = parse_slides(args.slides, len(slides))
    renderer = Renderer(pkg, args.scale, fonts)
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    images = []
    width = max(2, len(str(len(slides))))
    for index in targets:
        part = slides[index - 1]
        if part not in pkg.names:
            print("  slide %d: 部品が無い" % index, file=sys.stderr)
            continue
        img = renderer.render_slide(part, index)
        path = "%s-%s.png" % (args.out, str(index).zfill(width))
        img.save(path)
        images.append(img)
        print(path)
    if args.sheet:
        contact_sheet(images, args.out + "-sheet.png")
        print(args.out + "-sheet.png")
    print("fonts: cjk=%s latin=%s%s" % (cjk or "なし（和文は灰色バーで代替）", latin or "なし",
                                        "" if cjk else "。字形の確認には書体ファイルを --font で渡す"))
    if renderer.overflows:
        print("overflow（赤枠）:")
        for index, name, amount in renderer.overflows:
            print("  slide %d %s: %.2fin 超過" % (index, name, amount))
    return 0


if __name__ == "__main__":
    sys.exit(main())
