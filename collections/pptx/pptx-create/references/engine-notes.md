# 生成エンジンの注記 — python-pptx で作る

## 1. 能力の確認と、無いときの手当て

着手時に SKILL.md の工程0で経路を決めている。ここは生成側の細部を書く。

| 必要なもの | 用途 | 無いとき |
|---|---|---|
| python-pptx（lxml、Pillow、XlsxWriter に依存） | 生成・編集 | 不足している依存を勝手にダウンロード・同梱しない。利用可能な導入方法を利用者に示し、導入されるまで生成できないと伝える |
| Pillow | 簡易描画（pptx-review の `render_preview.py`） | 描画確認ができない。lint（標準ライブラリのみ）だけ通し、確認範囲を報告する |
| 和文の書体ファイル（.ttf/.otf） | 簡易描画で字形を出す | 無くても描画は動き、和文は文字幅どおりの灰色バーで代替される。レイアウトの確認には足りる |

**素材の読み込みと加工**は、環境にあるライブラリを使ってよい。元資料の PDF・Word・Excel からの抽出、写真の切り抜きや調整、SVG から PNG への変換などが該当する。使う前に `importlib` で存在と版を確かめる。**ただし出力はネイティブに保つ**——図表は `add_chart`、表は `add_table` で作り、文字を画像に焼かない。

- シェルが使えない環境がある。手順はすべて Python のコードで書き、ZIP の展開や結合も `zipfile` で行う。
- 1回の実行に時間の上限がある環境がある。生成と描画を数枚ずつに分け、途中結果をファイルに残す。
- テンプレのスライド複製は python-pptx にできない。OOXML を直接扱う（pptx-edit の `ooxml-editing.md`）。
- 既存デッキの文言差替は python-pptx の run 単位編集。

いずれの場合も、生成後に必ず再オープン検査と描画確認を行う。

## 2. python-pptx の骨格（`deck/build.py`）

ロックの JSON を読み、定数だけで座標と色を決める。ページ関数は1レイアウト1関数にし、`outline.md` の順に呼ぶ。

```python
import json
import math
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_TICK_LABEL_POSITION
from pptx.oxml.ns import qn
from lxml import etree

LOCK = json.load(open("deck/design-lock.json", encoding="utf-8"))
FONT = LOCK["fonts"][0]
C = {  # design-lock.md の役割名 → HEX
    "bg": "FFFFFF", "text": "1A1A1A", "muted": "5C5C5C",
    "line": "D9D9D6", "panel": "F4F4F2", "primary": "22313F", "accent": "B7282E",
}
W, H = 13.333, 7.5
M = 0.6                     # 余白
COL_W = (W - 2 * M - 0.25 * 11) / 12
TITLE_Y, TITLE_H, BODY_Y, BODY_END, FOOT_Y = 0.6, 1.4, 2.2, 6.6, 6.8
GAP = 0.3                   # 要素間の最小間隔

# 密度モード。design-lock.md の型スケールに対応する。ブリーフで決めた方を選ぶ。
#   talk = 講演型（話者が語る。文字は大きく、枚数は多め）
#   doc  = 資料型（読んで完結する。文字は小さく、枚数は少なめ）
HERO_SIZE = 84              # 大きな数字の上限。実際のサイズは fit_size() で決める
MODE = "doc"
SCALE = {
    "talk": {"cover": 44, "title": 30, "h2": 20, "body": 20, "note": 14, "source": 11},
    "doc":  {"cover": 38, "title": 28, "h2": 16, "body": 16, "note": 12, "source": 10},
}
SIZE = SCALE[MODE]


def col(start, span):
    """列番号（1始まり）と列数から x と幅を返す。"""
    x = M + (start - 1) * (COL_W + 0.25)
    return x, span * COL_W + (span - 1) * 0.25


def text_height(lines, size, line_spacing=1.4, slack_lines=0.5):
    """行数とサイズから箱の高さ（inch）を返す。半行分の余裕を足す。"""
    return (lines + slack_lines) * size * line_spacing / 72.0


def text_width(text, size):
    """1行で描いたときの幅（pt）の概算。全角は size、半角は 0.55×size。"""
    import unicodedata
    return sum(size if unicodedata.east_asian_width(c) in ("W", "F") else size * 0.55 for c in text)


def fit_size(text, w, max_size, min_size=32, step=2):
    """1行で幅 w（inch）に収まる最大サイズを返す。大きな数字のように、
    長さでサイズが決まる要素に使う。本文には使わない（本文は文字を減らす）。"""
    size = int(max_size)
    while size > min_size and text_width(text, size) > w * 72:
        size -= step
    return size


def spread(n, x, total_w, gap=GAP):
    """N 個を横に**等分**したときの (x, 幅) の列を返す。固定幅を N 回並べない。

    等分は既定ではない。項目が並列・無順序・等重みだと言えるときだけ使う。
    どれかが主役なら emphasis(n, hero) を使う。
    """
    w = (total_w - gap * (n - 1)) / max(n, 1)
    if w <= 0:
        raise ValueError("%d 個は幅 %.2f に収まらない。分割する" % (n, total_w))
    return [(x + i * (w + gap), w) for i in range(n)]


def emphasis(n, hero=0, x=M, total_w=None, ratio=1.6, gap=GAP):
    """N 個を横に割るが、hero 番目だけ ratio 倍広くする。

    **等分は既定ではない。** 並べる N 個のうち、どれが主役かをまず決める。
    主役が決まらないなら、それは横に並べる内容ではない（表か箇条書きにする）。
    本当に等価・無順序・等重みのときだけ spread() を使う。
    """
    weights = [ratio if i == hero else 1.0 for i in range(n)]
    return split(weights, x=x, total_w=total_w, gap=gap)


def content_band(top=BODY_Y, bottom=BODY_END):
    """本文の安全領域 (x, y, 幅, 高さ)。タイトル下からフッター上まで。"""
    return (M, top, W - 2 * M, bottom - top)


def split(weights, x=M, total_w=None, gap=GAP):
    """比率で横に割る。(1, 2) なら 1/3 と 2/3。非対称は手置きではなく比率で作る。"""
    total_w = (W - 2 * M) if total_w is None else total_w
    usable = total_w - gap * (len(weights) - 1)
    unit = usable / float(sum(weights))
    out, cx = [], x
    for wgt in weights:
        cw_ = unit * wgt
        out.append((cx, cw_))
        cx += cw_ + gap
    return out


def bleed(side="right", frac=0.5):
    """裁ち落とし領域 (x, y, 幅, 高さ)。写真や一色面を端まで出すときに使う。"""
    if side in ("left", "right"):
        w = W * frac
        return (0 if side == "left" else W - w, 0, w, H)
    h = H * frac
    return (0, 0 if side == "top" else H - h, W, h)


def skeleton(kind):
    """ページ構造の名前 → 領域の辞書。レイアウトは archetype から選ぶ（手置きしない）。

    使える kind: cover / divider / claim-evidence / split-asymmetric / comparison /
                 statement / hero-number / trend / structure / roadmap / before-after /
                 metrics / table / steps / closing / appendix / photo-full / photo-half
    """
    band_x, band_y, band_w, band_h = content_band()
    if kind == "cover":
        return {"canvas": (0, 0, W, H), "title": (0.8, 2.3, W - 1.6, text_height(2, SIZE["cover"])),
                "meta": (0.8, 4.7, W - 1.6, None)}      # 高さは行数から決める（slide_cover）
    if kind == "divider":
        num_h = text_height(1, 84, slack_lines=0)
        return {"canvas": (0, 0, W, H), "number": (0.8, 1.6, 4.0, num_h),
                "lead": (0.8, 1.6 + num_h + 0.3, W - 1.6, text_height(1, 32))}
    if kind == "claim-evidence":
        left, right = split((7, 5))
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "exhibit": (left[0], band_y, left[1], band_h),
                "reading": (right[0], band_y, right[1], band_h),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "split-asymmetric":
        narrow, wide = split((1, 2))
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "aside": (narrow[0], band_y, narrow[1], band_h),
                "main": (wide[0], band_y, wide[1], band_h),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "comparison":
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "columns": [(x, band_y, w, band_h) for x, w in split((1, 1), gap=0.4)],
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "statement":
        return {"line": (1.8, 2.6, W - 3.6, 2.0)}
    if kind == "hero-number":
        left, right = split((5, 7))
        num_h = text_height(1, HERO_SIZE, slack_lines=0)
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "number": (left[0], band_y + 0.3, left[1], num_h),
                "caption": (left[0], band_y + 0.3 + num_h + 0.3, left[1], 0.5),
                "context": (right[0], band_y + 0.3, right[1], num_h),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "trend":                      # 推移: 図を大きく、読み取りを下に敷く
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "exhibit": (band_x, band_y, band_w, band_h - 1.4),
                "reading": (band_x, band_y + band_h - 1.2, band_w, 0.9),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "structure":                  # 構造: 2×2 や樹形。軸ラベルは外側に置く
        cols = split((1, 1), x=band_x + 1.2, total_w=band_w - 1.2, gap=0.3)
        rows_y = vstack([(band_h - 0.9) / 2] * 2, top=band_y, bottom=band_y + band_h - 0.5, gap=0.3)
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "cells": [(cx, ry, cw_, (band_h - 0.9) / 2) for ry in rows_y for cx, cw_ in cols],
                "y_axis": (band_x, band_y, 1.0, band_h - 0.5),
                "x_axis": (band_x + 1.2, band_y + band_h - 0.4, band_w - 1.2, 0.4),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "photo-full":                 # 写真を全面に敷き、下half に薄い面と文字
        return {"photo": bleed("top", 1.0),
                "scrim": (0, H * 0.55, W, H * 0.45),
                "line": (0.8, H * 0.62, W - 3.0, text_height(2, SIZE["cover"])),
                "caption": (0.8, H - 0.9, W - 1.6, 0.4)}
    if kind == "photo-half":                 # 片側に写真、反対側に文字
        left, right = split((5, 7))
        return {"title": (M, TITLE_Y, left[1] + right[0] - M - 0.3, TITLE_H),
                "reading": (left[0], band_y, left[1], band_h),
                "photo": (right[0], band_y, right[1], band_h),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "appendix":                   # 付録: 本編と同じ版面。印はフッター行の右端に置く
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "body": (band_x, band_y, band_w, band_h),
                "source": (M, FOOT_Y, 9.0, 0.35),
                "marker": (W - M - 1.5, FOOT_Y, 1.5, 0.35)}
    if kind == "roadmap":                    # 時系列: 帯を上に、補足を下に
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "band": (band_x, band_y + 0.3, band_w, 2.4),
                "note": (band_x, band_y + 3.2, band_w, 1.2),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "before-after":               # 対比: 左右と、下に読み取り
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "pair": (band_x, band_y, band_w, band_h - 1.4),
                "reading": (band_x, band_y + band_h - 1.2, band_w, 0.9),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "metrics":                    # KPI: 数字を横に並べ、下に文脈
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "row": (band_x, band_y + 0.4, band_w, 2.0),
                "context": (band_x, band_y + 3.0, band_w, 1.6),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "table":
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "table": (band_x, band_y, band_w, band_h - 1.6),
                "reading": (band_x, band_y + band_h - 1.4, band_w, 1.0),
                "source": (M, FOOT_Y, 9.0, 0.35)}
    if kind == "steps":
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "rows": [(M, y, band_w, text_height(1, SIZE["h2"])) for y in
                         vstack([text_height(1, SIZE["h2"])] * 4, top=band_y)]}
    if kind == "closing":
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "asks": (band_x, band_y, band_w, 2.4),
                "risks": (band_x, band_y + 2.8, band_w, 1.4),
                "contact": (M, FOOT_Y, 9.0, 0.35)}
    raise ValueError("未知のページ構造: %s" % kind)


def vstack(heights, top=BODY_Y, bottom=BODY_END, gap=GAP):
    """高さの列を上から積み、各要素の y を返す。収まらなければ例外（黙って重ねない）。"""
    total = sum(heights) + gap * (len(heights) - 1)
    if total > bottom - top + 1e-6:
        raise ValueError("縦に %.2fin 必要だが %.2fin しか無い。文字を減らすか分割する" % (total, bottom - top))
    ys, y = [], top
    for h in heights:
        ys.append(y)
        y += h + gap
    return ys


def bottom_note(lines, size=None, bottom=BODY_END):
    """下端に置く注記の (y, 高さ)。下から積むので本文と衝突しない。"""
    size = size or SIZE["note"]
    h = text_height(len(lines) if isinstance(lines, list) else 1, size)
    return bottom - h, h


def set_font(run, size, color="text", bold=False):
    run.font.name = FONT
    rpr = run._r.get_or_add_rPr()
    ea = rpr.find(qn("a:ea"))
    if ea is None:
        ea = etree.SubElement(rpr, qn("a:ea"))
        latin = rpr.find(qn("a:latin"))
        if latin is not None:
            latin.addnext(ea)
    ea.set("typeface", FONT)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(C[color])


def text(slide, x, y, w, h, lines, size, color="text", bold=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, bullets=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Inches(0)
    for i, line in enumerate(lines if isinstance(lines, list) else [lines]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = 1.4
        p.space_after = Pt(6)
        run = p.add_run()
        run.text = line
        set_font(run, size, color, bold)
        if bullets:
            # 行頭が全角空白なら第2階層として一段下げる
            level = 1 if line.startswith("\u3000") else 0
            if level:
                run.text = line.lstrip("\u3000")
            ppr = p._p.get_or_add_pPr()
            ppr.set("lvl", str(level))
            ppr.set("marL", str(int(Inches(0.3 + 0.35 * level))))
            ppr.set("indent", str(-int(Inches(0.3))))
            bu = etree.SubElement(ppr, qn("a:buChar"))
            bu.set("char", "・" if level == 0 else "–")
    return box


def rect(slide, x, y, w, h, fill=None, rounded=False):
    """四角。**fill=None は面を敷かない**（既定）。面を敷くのは選択であって初期値ではない。"""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        shape.fill.background()       # 透明。文字だけを置くときの既定
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(C[fill])
    shape.line.fill.background()      # 枠線を消す
    shape.shadow.inherit = False      # 既定の影を消す
    return shape


CHART_KINDS = {                            # 用途 → PowerPoint のネイティブ図表
    "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,      # 量の比較
    "bar_stacked": XL_CHART_TYPE.COLUMN_STACKED,  # 内訳つきの比較
    "line": XL_CHART_TYPE.LINE_MARKERS,         # 時間による変化（3時点以上）
    "area": XL_CHART_TYPE.AREA,                 # 積み上がる変化
    "pie": XL_CHART_TYPE.PIE,                   # 全体に対する割合（系列1つ、5区分まで）
    "doughnut": XL_CHART_TYPE.DOUGHNUT,         # 同上。中央に数字を置きたいとき
    "bar_h": XL_CHART_TYPE.BAR_CLUSTERED,       # 項目名が長い比較
}


def chart(slide, x, y, w, h, categories, series, kind="bar", fmt="0.0"):
    """ネイティブ図表。kind は CHART_KINDS の名前。series は [(名前, 値の列), ...]。
    伝えたいことで選ぶ: 比較=bar、変化=line、割合=pie、項目名が長い=bar_h。"""
    data = CategoryChartData()
    data.categories = categories
    for name, values in series:
        data.add_series(name, values)
    chart = slide.shapes.add_chart(CHART_KINDS[kind],
                                   Inches(x), Inches(y), Inches(w), Inches(h), data).chart
    chart.has_title = False
    chart.has_legend = len(series) > 1
    chart.font.name, chart.font.size = FONT, Pt(SIZE["note"])
    for rpr in chart._chartSpace.iter(qn("a:defRPr")):        # 和文ラベル用に ea も付ける
        latin = rpr.find(qn("a:latin"))
        if latin is not None and rpr.find(qn("a:ea")) is None:
            ea = etree.SubElement(rpr, qn("a:ea")); latin.addnext(ea); ea.set("typeface", FONT)
    plot = chart.plots[0]
    circular = kind in ("pie", "doughnut")
    if not circular:
        plot.gap_width = 80
    plot.has_data_labels = True
    plot.data_labels.position = (XL_LABEL_POSITION.OUTSIDE_END if kind in ("bar", "bar_h")
                                 else XL_LABEL_POSITION.CENTER if kind == "pie"
                                 else XL_LABEL_POSITION.ABOVE if kind == "line" else None) or plot.data_labels.position
    plot.data_labels.number_format, plot.data_labels.number_format_is_linked = fmt, False
    if not circular:
        va, ca = chart.value_axis, chart.category_axis
        va.major_gridlines.format.line.color.rgb = RGBColor.from_string(C["line"])
        va.format.line.fill.background()
        va.tick_labels.font.color.rgb = RGBColor.from_string(C["muted"])
        ca.format.line.color.rgb = RGBColor.from_string(C["line"])
        if any(v < 0 for _, values in series for v in values):
            ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW   # 負の棒に項目名が重ならない
    palette = ["primary", "accent", "muted", "line"]
    for i, ser in enumerate(plot.series):
        if circular:                        # 円は区分ごとに色を変える
            for j, point in enumerate(ser.points):
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = RGBColor.from_string(C[palette[j % len(palette)]])
        elif kind in ("line", "area"):
            ser.format.line.color.rgb = RGBColor.from_string(C["primary" if i == 0 else "line"])
            ser.format.line.width = Pt(2.5)
        else:
            ser.format.fill.solid()
            ser.format.fill.fore_color.rgb = RGBColor.from_string(C["primary" if i == 0 else "line"])
        if kind in ("bar", "bar_h", "bar_stacked"):
            inv = etree.SubElement(ser._element, qn("c:invertIfNegative")); inv.set("val", "0")
            ser._element.find(qn("c:cat")).addprevious(inv)       # 無いと PowerPoint 以外のビューアで負の棒が上向きに出ることがある
    return chart


def bar_chart(slide, x, y, w, h, categories, series, fmt="0.0"):
    """縦棒。chart(..., kind="bar") と同じ。"""
    return chart(slide, x, y, w, h, categories, series, kind="bar", fmt=fmt)


def picture(slide, path, x, y, w, h, fit="cover"):
    """枠に合わせて画像を置く。fit="cover" は枠を埋めて余りを切り落とし、
    "contain" は全体を見せて枠内に収める。縦横比は保つ。"""
    from PIL import Image
    with Image.open(path) as img:
        iw, ih = img.size
    box_ratio, img_ratio = w / h, iw / float(ih)
    pic = slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))
    if fit == "cover":                      # 枠を埋め、はみ出す側を切る
        if img_ratio > box_ratio:
            cut = (1 - box_ratio / img_ratio) / 2
            pic.crop_left = pic.crop_right = cut
        else:
            cut = (1 - img_ratio / box_ratio) / 2
            pic.crop_top = pic.crop_bottom = cut
    else:                                   # 全体を見せ、枠の中で中央に置く
        if img_ratio > box_ratio:
            nh = w / img_ratio
            pic.height, pic.top = Inches(nh), Inches(y + (h - nh) / 2)
        else:
            nw = h * img_ratio
            pic.width, pic.left = Inches(nw), Inches(x + (w - nw) / 2)
    return pic


def scrim(slide, x, y, w, h, color="primary", transparency=45):
    """画像の上に文字を置くための薄い面。地と文字のコントラストを確保する。
    画像に直接文字を重ねると読めなくなるので、必ず挟む。"""
    shape = rect(slide, x, y, w, h, color)
    fill = shape.fill.fore_color._xFill.find(qn("a:srgbClr"))
    if fill is not None:
        alpha = etree.SubElement(fill, qn("a:alpha"))
        alpha.set("val", str(int((100 - transparency) * 1000)))
    shape.shadow.inherit = False
    return shape


# --- 図形の中の文字と、図形をつなぐ線 ---

def box_text(slide, x, y, w, h, lines, size=None, fill=None, color="text",
             bold=False, align=PP_ALIGN.LEFT, pad=0.2, min_size=10, rounded=False):
    """文字の入った四角。**図形に直接文字を書かない**。この関数を使う。

    自分で `shape.text_frame.text = ...` と書くと、書体・サイズ・和文書体・
    余白・縦位置がすべて PowerPoint の既定になり、環境ごとに崩れる。
    ここでは枠に収まるサイズを選び、上下中央に置き、和文書体まで指定する。

    **fill の既定は None（面なし）。** カードは「並列・無順序・等重み」の項目に
    対してだけ選ぶ形式で、既定ではない。順序・量・関係・時間・二軸のどれかが
    内容にあるなら、面を敷かずに別の形式にしたほうがほぼ常に強い。
    """
    size = size or SIZE["body"]
    shape = rect(slide, x, y, w, h, fill, rounded=rounded)
    frame = shape.text_frame
    frame.word_wrap = True
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    frame.margin_left = frame.margin_right = Inches(pad)
    frame.margin_top = frame.margin_bottom = Inches(pad * 0.5)
    rows = lines if isinstance(lines, list) else [lines]
    inner_w, inner_h = (w - pad * 2) * 72, (h - pad) * 72
    while size > min_size:                       # 枠に収まる最大サイズを選ぶ
        need = 0
        for row in rows:
            wrapped = max(1, int(math.ceil(text_width(row, size) / inner_w)))
            need += wrapped * size * 1.4
        if need <= inner_h:
            break
        size -= 1
    for i, row in enumerate(rows):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.alignment = align
        para.line_spacing = 1.4
        run = para.add_run()
        run.text = row
        set_font(run, size, color, bold)
    return shape


def _edge_point(shape, side):
    x, y = shape.left / 914400.0, shape.top / 914400.0
    w, h = shape.width / 914400.0, shape.height / 914400.0
    return {"left": (x, y + h / 2), "right": (x + w, y + h / 2),
            "top": (x + w / 2, y), "bottom": (x + w / 2, y + h)}[side]


def connect(slide, a, b, color="line", width_pt=1.5, arrow=True):
    """2つの図形を線で結ぶ。向かい合う辺を自動で選び、ずれていれば直角に折る。

    端点は必ず図形の辺に接する。斜めに空間を横切る線は作らない。
    """
    ax, ay = a.left / 914400.0, a.top / 914400.0
    aw, ah = a.width / 914400.0, a.height / 914400.0
    bx, by = b.left / 914400.0, b.top / 914400.0
    bw, bh = b.width / 914400.0, b.height / 914400.0
    dx, dy = (bx + bw / 2) - (ax + aw / 2), (by + bh / 2) - (ay + ah / 2)
    if abs(dx) >= abs(dy):                       # 横に並んでいる
        start = _edge_point(a, "right" if dx > 0 else "left")
        end = _edge_point(b, "left" if dx > 0 else "right")
        aligned = abs(dy) < 0.15
    else:                                        # 縦に並んでいる
        start = _edge_point(a, "bottom" if dy > 0 else "top")
        end = _edge_point(b, "top" if dy > 0 else "bottom")
        aligned = abs(dx) < 0.15
    kind = MSO_CONNECTOR.STRAIGHT if aligned else MSO_CONNECTOR.ELBOW
    conn = slide.shapes.add_connector(kind, Inches(start[0]), Inches(start[1]),
                                      Inches(end[0]), Inches(end[1]))
    conn.line.color.rgb = RGBColor.from_string(C[color])
    conn.line.width = Pt(width_pt)
    if arrow:                                    # 終端に矢じりを付ける
        ln = conn.line._get_or_add_ln()
        tail = etree.SubElement(ln, qn("a:tailEnd"))
        tail.set("type", "triangle"); tail.set("w", "med"); tail.set("len", "med")
    return conn


# --- 部品（ページの中に置く。原型と組み合わせて使う） ---

def table(slide, x, y, w, rows, col_ratio=None, row_h=0.45, right_align_from=1):
    """罫線は横だけ、見出し行は淡い面。数字の列は右揃え。
    rows は [[見出し...], [値...], ...]。6行×5列までに収める。"""
    n_rows, n_cols = len(rows), len(rows[0])
    frame = slide.shapes.add_table(n_rows, n_cols, Inches(x), Inches(y),
                                   Inches(w), Inches(row_h * n_rows))
    tbl = frame.table
    tbl.first_row = False
    tbl.horz_banding = False
    ratio = col_ratio or [1] * n_cols
    for j, r in enumerate(ratio):
        tbl.columns[j].width = Inches(w * r / float(sum(ratio)))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(C["panel"] if i == 0 else C["bg"])
            para = cell.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.RIGHT if j >= right_align_from else PP_ALIGN.LEFT
            run = para.add_run()
            run.text = str(value)
            set_font(run, SIZE["body"] if i else SIZE["note"], "text" if i else "muted", bold=(i == 0))
            tc_pr = cell._tc.get_or_add_tcPr()
            for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
                ln = etree.SubElement(tc_pr, qn(tag))
                if tag == "a:lnB":                       # 横罫線だけ引く
                    ln.set("w", "6350")
                    fill = etree.SubElement(ln, qn("a:solidFill"))
                    etree.SubElement(fill, qn("a:srgbClr")).set("val", C["line"])
                else:
                    ln.set("w", "0")
                    etree.SubElement(ln, qn("a:noFill"))
    return frame


def timeline(slide, x, y, w, milestones, label_size=None):
    """横一本の時系列。milestones は [(時期, 内容), ...]。5つまで。
    節目は等間隔に置き、端の札が枠から出ないよう内側に寄せる。"""
    label_size = label_size or SIZE["note"]
    n = len(milestones)
    rect(slide, x, y + 0.55, w, 0.02, "line")
    inset = w / (n * 2.0)                                # 端の札を内側に寄せる
    for i, (when, what) in enumerate(milestones):
        cx = x + inset + (w - inset * 2) * (i / float(max(n - 1, 1)))
        dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - 0.07), Inches(y + 0.49),
                                     Inches(0.14), Inches(0.14))
        dot.fill.solid(); dot.fill.fore_color.rgb = RGBColor.from_string(C["accent"])
        dot.line.fill.background(); dot.shadow.inherit = False
        col_w = (w - inset * 2) / max(n - 1, 1) * 0.9
        text(slide, cx - col_w / 2, y, col_w, 0.4, when, label_size, color="muted",
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.BOTTOM)
        text(slide, cx - col_w / 2, y + 0.8, col_w, text_height(2, SIZE["body"]), what,
             SIZE["body"], align=PP_ALIGN.CENTER)
    return y + 0.8 + text_height(2, SIZE["body"])


def flow(slide, x, y, w, h, steps, gap=None, fill="panel", hero=None):
    """処理の流れ。箱を並べ、間を矢印でつなぐ。5つまで。

    等分でよい数少ない形式（工程は等価で、順序だけが意味を持つ）。ただし
    **ある工程が主役なら hero にその番号を渡す**——律速の工程、変えた工程、
    落ちている工程。全部同じ大きさの箱が並ぶページは、たいてい何も言っていない。
    順序が意味を持たないなら箇条書きにする。
    """
    gap = GAP if gap is None else gap
    boxes = (spread(len(steps), x, w, gap=gap) if hero is None
             else emphasis(len(steps), hero, x=x, total_w=w, gap=gap))
    shapes = []
    for i, ((bx, bw), step) in enumerate(zip(boxes, steps)):
        head, body = step if isinstance(step, (tuple, list)) else (step, None)
        rows = [head] + ([body] if body else [])
        shape = box_text(slide, bx, y, bw, h, rows, size=SIZE["body"],
                         fill=("accent" if i == hero else fill), align=PP_ALIGN.LEFT,
                         color=("bg" if i == hero else "text"))
        if body:                                 # 見出しだけ太字にする
            shape.text_frame.paragraphs[0].runs[0].font.bold = True
        shapes.append(shape)
    for a, b in zip(shapes, shapes[1:]):
        connect(slide, a, b)
    return boxes


def metrics(slide, x, y, w, items, size=None, hero=0):
    """数字とラベルを横に並べる。3つまで。数字が主張を支えるときだけ使う。
    items は [(数字, ラベル), ...]。

    **hero の1つだけが大きく、色を持つ。** 同じ大きさの数字が等間隔に3つ並ぶ形は、
    主張の無いページを数字で埋めるときの定型。どれが主役か決まらないなら、
    その3つは横並びではなく表にする。hero=None なら等価に並ぶが、
    3つとも本当に等価な指標だと確かめてから渡す。
    """
    size = size or 44
    cols = (spread(len(items), x, w, gap=0.5) if hero is None
            else emphasis(len(items), hero, x=x, total_w=w, ratio=1.6, gap=0.5))
    num_h = text_height(1, size, slack_lines=0)
    for i, ((cx, cw_), (value, label)) in enumerate(zip(cols, items)):
        lead = (i == hero)
        cap = size if lead else int(size * 0.62)          # 脇は静かにする
        fitted = fit_size(str(value), cw_, cap, min_size=20)
        drop = 0 if lead else num_h - text_height(1, cap, slack_lines=0)
        text(slide, cx, y + drop, cw_, num_h - drop, str(value), fitted,
             color=("accent" if lead else "text"), bold=lead)
        text(slide, cx, y + num_h + 0.15, cw_, 0.4, label, SIZE["note"], color="muted")
    return y + num_h + 0.55


def quote(slide, x, y, w, body, source=None):
    """引用・利用者の声。太い縦線ではなく、字下げと書体で引用だと示す。"""
    text(slide, x, y, w, text_height(3, SIZE["h2"]), body, SIZE["h2"])
    if source:
        text(slide, x, y + text_height(3, SIZE["h2"]), w, 0.4, source, SIZE["note"], color="muted")
    return y + text_height(3, SIZE["h2"]) + 0.5


def before_after(slide, x, y, w, h, before, after, labels=("導入前", "導入後"),
                 weights=(1, 1.5)):
    """対比。左右に並べ、間に矢印を置く。before / after は行の列。

    **左右は等分にしない。** 主張を運ぶのは片側（多くは後）で、そちらを広く取る。
    等分の左右2枚は、どちらを見ればよいかを言っていない。前の状態こそが主張なら
    weights=(1.5, 1) を渡す。面は主役の側にだけ敷き、脇は地のまま置く。
    """
    (lx, lw), (rx, rw) = split(list(weights), x=x, total_w=w, gap=0.8)
    lead = 1 if weights[1] >= weights[0] else 0
    for i, ((bx, bw), label, lines) in enumerate((((lx, lw), labels[0], before),
                                                  ((rx, rw), labels[1], after))):
        text(slide, bx, y, bw, 0.4, label, SIZE["note"], color="muted")
        if i == lead:
            rect(slide, bx, y + 0.5, bw, h - 0.5, "panel")
        pad = 0.25 if i == lead else 0.0
        text(slide, bx + pad, y + 0.75, bw - pad * 2, h - 1.0, lines, SIZE["body"],
             color=("text" if i == lead else "muted"))
    arrow = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(lx + lw + 0.15),
                                   Inches(y + h / 2), Inches(0.5), Inches(0.2))
    arrow.fill.solid(); arrow.fill.fore_color.rgb = RGBColor.from_string(C["accent"])
    arrow.line.fill.background(); arrow.shadow.inherit = False
    return y + h + 0.5


def motif_legend(slide, meaning, x=M, y=None, w=5.0):
    """モチーフの凡例。**主題由来の印を初めて出すページに、必ず1行添える。**

    署名は「見たことのない形」なので、初出で意味を言わないと装飾に見える。
    meaning は形が何を表すかの一文（「太線＝実測、細線＝推計」「■＝取得済、□＝未取得」）。
    凡例そのものは署名の出現回数に数えない。
    """
    y = BODY_END - 0.35 if y is None else y      # 本文領域の下端。埋まっているなら y を渡す
    return text(slide, x, y, w, 0.35, meaning, SIZE["note"], color="muted")


def chrome(slide, page=None, total=None, section=None, logo=None):
    """全ページ共通の細部。ページ番号・章の進行表示・ロゴを定位置に置く。
    静かな層なので、位置と大きさを全ページで変えない。"""
    if section:                                  # 左は page_source() が使うので右に寄せる
        text(slide, W - M - 5.4, FOOT_Y, 4.0, 0.35, section, SIZE["source"],
             color="muted", align=PP_ALIGN.RIGHT)
    if page is not None:
        label = "%d / %d" % (page, total) if total else str(page)
        text(slide, W - M - 1.2, FOOT_Y, 1.2, 0.35, label, SIZE["source"],
             color="muted", align=PP_ALIGN.RIGHT)
    if logo:
        picture(slide, logo, W - M - 1.2, 0.35, 1.2, 0.4, fit="contain")


def notes(slide, body):
    slide.notes_slide.notes_text_frame.text = body


def new_deck():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    return prs


def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])   # 白紙レイアウト


def page_title(slide, title):
    text(slide, M, TITLE_Y, W - 2 * M, TITLE_H, title, SIZE["title"], bold=True)


def page_source(slide, source):
    """出典。フッター左の 6.5in。右側は chrome() の章名とページ番号が使う。"""
    text(slide, M, FOOT_Y, 6.5, 0.35, source, SIZE["source"], color="muted")


# --- レイアウト関数（layout-catalog.md の原型に対応。主役を回すために使い分ける） ---

def slide_cover(prs, title, meta, dark=True):
    s = blank(prs)
    k = skeleton("cover")
    if dark:
        rect(s, *k["canvas"], fill="primary")
    text(s, *k["title"], lines=title, size=SIZE["cover"], color="bg" if dark else "text", bold=True)
    mx, my, mw, _ = k["meta"]                    # 高さは行数から決める（固定だと2行目が溢れる）
    rows = meta if isinstance(meta, list) else [meta]
    text(s, mx, my, mw, text_height(len(rows), 18), lines=rows, size=18,
         color="line" if dark else "muted")
    return s


def slide_divider(prs, number, lead):
    """章扉。デッキ全体で3回まで。濃い面がリズムの節目になる。"""
    s = blank(prs)
    k = skeleton("divider")
    rect(s, *k["canvas"], fill="primary")
    text(s, *k["number"], lines=number, size=84, color="bg", bold=True)
    text(s, *k["lead"], lines=lead, size=32, color="bg", bold=True)
    return s


def slide_claim_evidence(prs, title, reading, source, draw_exhibit, panel=True):
    s = blank(prs)
    k = skeleton("claim-evidence")
    page_title(s, title)
    ex = k["exhibit"]
    if panel:
        rect(s, *ex, fill="panel")
    draw_exhibit(s, ex[0] + 0.2, ex[1] + 0.2, ex[2] - 0.4, ex[3] - 0.4)
    text(s, *k["reading"], lines=reading, size=SIZE["body"])
    page_source(s, source)
    return s


def slide_split(prs, title, aside, main_lines, source=None):
    """1:2 の非対称分割。左に短い視点、右に本体。均等分割の単調さを崩す。"""
    s = blank(prs)
    k = skeleton("split-asymmetric")
    page_title(s, title)
    text(s, *k["aside"], lines=aside, size=SIZE["h2"], color="muted")
    text(s, *k["main"], lines=main_lines, size=SIZE["body"])
    if source:
        page_source(s, source)
    return s


def slide_comparison(prs, title, heads, bodies, note=None, source=None):
    s = blank(prs)
    k = skeleton("comparison")
    page_title(s, title)
    for (cx, cy, cw_, chh), head, body in zip(k["columns"], heads, bodies):
        text(s, cx, cy, cw_, 0.5, head, SIZE["h2"], bold=True)
        text(s, cx, cy + 0.7, cw_, chh - 1.9, body, SIZE["body"], bullets=True)
    if note:
        text(s, M, BODY_END - 1.0, W - 2 * M, 0.9, note, SIZE["body"])
    if source:
        page_source(s, source)
    return s


def slide_statement(prs, line, dark=False):
    """一文だけのページ。密なページの後に置いて息継ぎにする。連発しない。"""
    s = blank(prs)
    if dark:
        rect(s, 0, 0, W, H, "primary")
    k = skeleton("statement")
    text(s, *k["line"], lines=line, size=32, color="bg" if dark else "text",
         bold=True, anchor=MSO_ANCHOR.MIDDLE)
    return s


def slide_hero_number(prs, title, number, caption, context, source=None):
    """数字が主張そのものであるときだけ。1デッキで2〜3回まで。"""
    s = blank(prs)
    k = skeleton("hero-number")
    page_title(s, title)
    size = fit_size(number, k["number"][2], HERO_SIZE)   # 長い数字は自動で下げる
    text(s, *k["number"], lines=number, size=size, color="accent", bold=True)
    text(s, *k["caption"], lines=caption, size=SIZE["body"], color="muted")
    text(s, *k["context"], lines=context, size=SIZE["body"], anchor=MSO_ANCHOR.BOTTOM)
    if source:
        page_source(s, source)
    return s


def slide_steps(prs, title, steps):
    """番号つきの手順。5つまで。番号・時期・内容の3列は同じ高さで中央に揃える。"""
    s = blank(prs)
    k = skeleton("steps")
    page_title(s, title)
    for (rx, ry, rw, rh), (num, when, what) in zip(k["rows"], steps):
        text(s, rx, ry, 0.6, rh, num, SIZE["h2"], color="accent", bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, rx + 0.7, ry, 2.4, rh, when, SIZE["body"], color="muted", anchor=MSO_ANCHOR.MIDDLE)
        text(s, rx + 3.2, ry, rw - 3.2, rh, what, SIZE["body"], anchor=MSO_ANCHOR.MIDDLE)
    return s


def slide_table(prs, title, rows, reading=None, col_ratio=None, source=None):
    """表。精密な値を照合させるときに使う。傾向を見せたいなら図にする。"""
    s = blank(prs)
    k = skeleton("table")
    page_title(s, title)
    table(s, k["table"][0], k["table"][1], k["table"][2], rows, col_ratio=col_ratio)
    if reading:
        text(s, *k["reading"], lines=reading, size=SIZE["body"])
    if source:
        page_source(s, source)
    return s


def slide_trend(prs, title, categories, series, reading, source=None, kind="line"):
    """推移。時点が3つ以上あるときに使う。2つなら比較にする。"""
    s = blank(prs)
    k = skeleton("trend")
    page_title(s, title)
    chart(s, *k["exhibit"], categories=categories, series=series, kind=kind)
    text(s, *k["reading"], lines=reading, size=SIZE["body"])
    if source:
        page_source(s, source)
    return s


def slide_structure(prs, title, cells, axes=None, source=None):
    """構造。2×2 の4象限。cells は [(見出し, 説明), ...] を4つ。
    axes は (縦軸ラベル, 横軸ラベル)。関係が本当にあるときだけ使う。"""
    s = blank(prs)
    k = skeleton("structure")
    page_title(s, title)
    for (cx, cy, cw_, chh), (head, desc) in zip(k["cells"], cells):
        rect(s, cx, cy, cw_, chh, "panel")
        text(s, cx + 0.25, cy + 0.2, cw_ - 0.5, 0.4, head, SIZE["h2"], bold=True)
        text(s, cx + 0.25, cy + 0.75, cw_ - 0.5, chh - 1.0, desc, SIZE["body"])
    if axes:
        text(s, *k["y_axis"], lines=axes[0], size=SIZE["note"], color="muted",
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(s, *k["x_axis"], lines=axes[1], size=SIZE["note"], color="muted", align=PP_ALIGN.CENTER)
    if source:
        page_source(s, source)
    return s


def slide_photo_full(prs, image, line, caption=None):
    """写真を全面に敷き、下半分に薄い面を挟んで文字を置く。
    薄い面を省くと文字が読めなくなるので必ず入れる。"""
    s = blank(prs)
    k = skeleton("photo-full")
    picture(s, image, *k["photo"], fit="cover")
    scrim(s, *k["scrim"])
    text(s, *k["line"], lines=line, size=SIZE["cover"], color="bg", bold=True)
    if caption:
        text(s, *k["caption"], lines=caption, size=SIZE["note"], color="line")
    return s


def slide_photo_half(prs, title, reading, image, source=None):
    """片側に写真、反対側に文字。写真は枠を埋めて切り落とす。"""
    s = blank(prs)
    k = skeleton("photo-half")
    page_title(s, title)
    text(s, *k["reading"], lines=reading, size=SIZE["body"])
    picture(s, image, *k["photo"], fit="cover")
    if source:
        page_source(s, source)
    return s


def slide_appendix(prs, title, body, source=None):
    """付録。結論の後ろに置く。本編と同じロックを使う。"""
    s = blank(prs)
    k = skeleton("appendix")
    text(s, *k["title"], lines=title, size=SIZE["title"], bold=True)
    text(s, *k["marker"], lines="付録", size=SIZE["note"], color="muted", align=PP_ALIGN.RIGHT)
    text(s, *k["body"], lines=body, size=SIZE["body"])
    if source:
        page_source(s, source)
    return s


def slide_roadmap(prs, title, milestones, note=None, source=None):
    """時系列。工程やロードマップ。節目は5つまで。"""
    s = blank(prs)
    k = skeleton("roadmap")
    page_title(s, title)
    timeline(s, k["band"][0], k["band"][1], k["band"][2], milestones)
    if note:
        text(s, *k["note"], lines=note, size=SIZE["body"])
    if source:
        page_source(s, source)
    return s


def slide_before_after(prs, title, before, after, reading=None, labels=("導入前", "導入後"), source=None):
    """対比。変化そのものが主張のときに使う。"""
    s = blank(prs)
    k = skeleton("before-after")
    page_title(s, title)
    before_after(s, *k["pair"], before=before, after=after, labels=labels)
    if reading:
        text(s, *k["reading"], lines=reading, size=SIZE["body"])
    if source:
        page_source(s, source)
    return s


def slide_metrics(prs, title, items, context=None, source=None):
    """KPI を横に並べる。3つまで。数字が主張を支えるときだけ。"""
    s = blank(prs)
    k = skeleton("metrics")
    page_title(s, title)
    metrics(s, k["row"][0], k["row"][1], k["row"][2], items)
    if context:
        text(s, *k["context"], lines=context, size=SIZE["body"])
    if source:
        page_source(s, source)
    return s


def slide_closing(prs, title, asks, risks=None, contact=None):
    """結論・依頼。質疑の間これが画面に残る。"""
    s = blank(prs)
    k = skeleton("closing")
    page_title(s, title)
    text(s, *k["asks"], lines=asks, size=SIZE["body"])
    if risks:
        text(s, *k["risks"], lines=risks, size=SIZE["body"], color="muted")
    if contact:
        page_source(s, contact)
    return s


def build():
    prs = new_deck()
    # outline.md の順にレイアウト関数を呼ぶ。同じ関数を3枚以上続けない。
    # 主役を回す: 図 → 文 → 数字 → 表 → 図。濃い面（cover/divider/statement dark）は3回まで。
    prs.save("deck/output.pptx")


if __name__ == "__main__":
    build()
```

## 3. python-pptx の落とし穴

- **`text_frame.text = "..."` は書式を消す。** 段落が1つの無書式 run に潰れる。必ず `run.text` に書く。
- **`add_textbox` の既定は折り返し無し（`wrap="none"`）と `spAutoFit`。** そのままだと1行で右へ伸び、箱の大きさも文字に合わせて変わる。必ず `word_wrap = True` と `auto_size = MSO_AUTO_SIZE.NONE` にし、箱の高さは `text_height()` で決める。
- **`normAutofit`（文字の自動縮小）を使わない。** PowerPoint で開いたときだけ縮小され、描画確認とずれる。縮小後のサイズが下限を割る。
- **等分は既定ではない。** N 個を横に並べる前に、どれが主役かを決める。主役があるなら `emphasis(n, hero)`、本当に等価・無順序・等重みのときだけ `spread()`。主役が決まらない N 個は、横並びではなく表か箇条書きにする内容である。固定幅を N 回置くのは、どちらの場合も間違い（N が増えると右端が溢れる）。
- **面（カード）は既定ではない。** `box_text()` と `rect()` の `fill` の既定は `None`（面なし）。内容に順序・量・関係・時間・二軸のどれかがあるなら、面で囲むより別の形式のほうがほぼ常に強い。角丸の面を並べてよいのは、項目が並列・無順序・等重みのときだけ。
- **`MODE` は最初に決める。** 講演型と資料型でサイズが違う。途中で変えると型スケールが混ざる。lint の `--mode` にも同じ値を渡す。
- **縦に積むときは `vstack()`、下端の注記は `bottom_note()`、本文の範囲は `content_band()`。** 手で y を置くと、文言が1行増えた瞬間に重なる。`vstack()` は収まらないと例外を出すので、黙って重ならない。
- **大きな数字は `fit_size()` でサイズを決める。** 「1,200万円」のように長い数字は 84pt では収まらない。本文には使わない（本文が収まらないときは文字を減らす）。
- **図形に文字を入れるときは `box_text()` を使う。** `shape.text_frame.text = "..."` と直接書くと、書体・サイズ・和文書体・余白・縦位置がすべて PowerPoint の既定になり、受け手の環境で崩れる。文字は上に貼り付き、和文は代替書体になる。`box_text()` は枠に収まるサイズを選び、上下中央に置き、和文書体まで指定する。
- **図形を線で結ぶときは `connect()` を使う。** `add_connector` を座標で直接呼ぶと、端点が辺からずれ、段違いのときに斜め線が空間を横切る。`connect()` は向かい合う辺を自動で選び、ずれていれば直角に折り、端点を必ず辺に接させる。
- **プレースホルダのレイアウトを使うと、テーマ由来の書式が混ざる。** 新規作成は白紙レイアウト（index 6）に textbox と shape で組む。テンプレを使うときだけレイアウトのプレースホルダを使う。
- **既定の図形には影と枠線がつく。** `shape.shadow.inherit = False`、`shape.line.fill.background()` を毎回呼ぶ。
- **textbox には内側の余白がある（既定 0.1in / 0.05in）。** 罫線や図形と端をそろえるなら余白を 0 にする。
- **自動縮小に頼らない。** `auto_size = MSO_AUTO_SIZE.NONE` にし、文字数の予算で収める。`SHAPE_TO_FIT_TEXT` は PowerPoint で開き直すまで反映されないことがある。
- **スライドの複製ができない。** 同じ構成のページは関数で再生成する。テンプレのスライド複製が必要なら OOXML を直接扱う。
- **ネイティブ図表の書式は既定が古い。** `chart.has_title`、`chart.has_legend`（単系列は False）、`plot.has_data_labels`、系列の色、目盛線の色（`value_axis.major_gridlines.format.line.color.rgb`）、`category_axis.tick_labels.font.size` を必ず設定する。縦の目盛線は消す。骨格の `bar_chart()` が最低限を行う。
- **負の値の棒は、`<c:invertIfNegative val="0"/>` を系列に明示する。** python-pptx はこれを書かず、PowerPoint 以外のビューアでは負の棒が絶対値で上向きに描かれることがある（実測: −1.9 が +1.9 に見える）。受け手がそのビューアで開くと数値が違って見える。負の値があるときは項目名の位置を `XL_TICK_LABEL_POSITION.LOW` にして棒と重ねない。
- **図表の文字にも書体を設定する。** `chart.font.name` と `chart.font.size` を設定し、和文ラベルがあるなら `txPr` に `a:ea` を追加する。
- **表のセルにも内側余白がある。** `cell.margin_left` などで統一する。表の既定スタイルは色が強いので、`tbl.first_row = False` にして自分で塗る。
- **画像は縦横比を保つ。** 幅か高さの一方だけ指定する。トリミングは `picture.crop_left` などで行う。
- **SVG と EMF は読めない。** PNG か JPEG に変換してから置く。
- **グループ図形の中の座標は親基準。** 位置検査が要る要素はグループ化しない。
- **色は 6 桁の HEX。** `RGBColor.from_string("1A1A1A")`。`#` は付けない。
- **1 ファイル 1 `Presentation()`。** 使い回さない。
- **ノートは `slide.notes_slide.notes_text_frame`。** 本文の textbox に書かない。

## 4. 描画と再オープン

```python
# 再オープン検査（壊れていれば例外）
from pptx import Presentation
print(len(Presentation("deck/output.pptx").slides), "slides")
```

```python
# 描画（pptx-review 同梱。Pillow のみ。<skills> は導入先のスキルディレクトリ）
import subprocess, sys
subprocess.run([sys.executable, "<skills>/pptx-review/scripts/render_preview.py", "deck/output.pptx",
                "--out", "deck/qa/preview", "--sheet"], check=True)
# 数枚ずつ描くなら --slides 1-4 のように分ける。書体ファイルがあれば --font path.ttf
```

- 出力は `deck/qa/preview-01.png` … と一覧 `deck/qa/preview-sheet.png`。標準出力に、使った書体と、はみ出しで赤枠を付けたページが出る。
- 和文の書体が無い環境では和文が灰色バーになる。位置・折り返し・重なり・余白はそのまま確認できる。字形（禁則、記号の欠け）は書体ファイルを置いて確認する。
- この描画は PowerPoint と同じではない。図表は値と色を簡略に描き、影・グラデーション・効果は描かない。「ぎりぎり収まる」は溢れると判断する。
- 修正後は `.pptx` を作り直してから再描画する。

## 5. ネイティブを守る

- 図表は `add_chart`、表は `add_table`、図形は `add_shape`。画像化しない。
- 画像にしてよいのは、写真、PowerPoint に無い図（サンキー、ネットワーク図）、ロゴだけ。
- 全面が画像のページを作らない。編集できないデッキは納品物にならない。
