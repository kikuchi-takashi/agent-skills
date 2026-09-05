# 生成エンジンの注記 — python-pptx で作る

## 1. 前提と、無いときの手当て

| 必要なもの | 用途 | 無いとき |
|---|---|---|
| python-pptx（lxml、Pillow、XlsxWriter に依存） | 生成・編集 | 追加インストールもネットワークも無い環境では、純 Python の python-pptx と XlsxWriter を作業ディレクトリに同梱し、実行の冒頭で `sys.path.insert(0, "vendor")` する。lxml と Pillow はコンパイル済みが必要なので、無ければその環境では生成できない。利用者に伝える |
| Pillow | 描画確認（pptx-review の `render_preview.py`） | 描画確認ができない。lint（標準ライブラリのみ）だけ通し、未確認と報告する |
| 和文の書体ファイル（.ttf/.otf） | 描画確認で字形を出す | 無くても描画は動き、和文は文字幅どおりの灰色バーで代替される。レイアウトの確認には足りる。字形まで見るなら書体ファイルを作業ディレクトリに置く |

- シェルが使えない環境がある。手順はすべて Python のコードで書き、ZIP の展開や結合も `zipfile` で行う。
- 1回の実行に時間の上限がある環境がある。生成と描画を数枚ずつに分け、途中結果をファイルに残す。
- テンプレのスライド複製は python-pptx にできない。OOXML を直接扱う（pptx-edit の `ooxml-editing.md`）。
- 既存デッキの文言差替は python-pptx の run 単位編集。

いずれの場合も、生成後に必ず再オープン検査と描画確認を行う。

## 2. python-pptx の骨格（`deck/build.py`）

ロックの JSON を読み、定数だけで座標と色を決める。ページ関数は1レイアウト1関数にし、`outline.md` の順に呼ぶ。

```python
import json
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE
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


def spread(n, x, total_w, gap=GAP):
    """N 個を横に等分したときの (x, 幅) の列を返す。固定幅を N 回並べない。"""
    w = (total_w - gap * (n - 1)) / max(n, 1)
    if w <= 0:
        raise ValueError("%d 個は幅 %.2f に収まらない。分割する" % (n, total_w))
    return [(x + i * (w + gap), w) for i in range(n)]


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
                 statement / hero-number / table / steps / closing
    """
    band_x, band_y, band_w, band_h = content_band()
    if kind == "cover":
        return {"canvas": (0, 0, W, H), "title": (0.8, 2.3, W - 1.6, text_height(2, SIZE["cover"])),
                "meta": (0.8, 4.7, W - 1.6, 0.5)}
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
        num_h = text_height(1, 84, slack_lines=0)
        return {"title": (M, TITLE_Y, W - 2 * M, TITLE_H),
                "number": (left[0], band_y + 0.3, left[1], num_h),
                "caption": (left[0], band_y + 0.3 + num_h + 0.3, left[1], 0.5),
                "context": (right[0], band_y + 0.3, right[1], num_h),
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
            ppr = p._p.get_or_add_pPr()
            ppr.set("marL", str(int(Inches(0.3))))
            ppr.set("indent", str(-int(Inches(0.3))))
            bu = etree.SubElement(ppr, qn("a:buChar"))
            bu.set("char", "・")
    return box


def rect(slide, x, y, w, h, fill, rounded=False):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(C[fill])
    shape.line.fill.background()      # 枠線を消す
    shape.shadow.inherit = False      # 既定の影を消す
    return shape


def bar_chart(slide, x, y, w, h, categories, series, fmt="0.0"):
    """ネイティブの縦棒。series は [(名前, 値の列), ...]。主系列だけ主色。"""
    data = CategoryChartData()
    data.categories = categories
    for name, values in series:
        data.add_series(name, values)
    chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,
                                   Inches(x), Inches(y), Inches(w), Inches(h), data).chart
    chart.has_title = False
    chart.has_legend = len(series) > 1
    chart.font.name, chart.font.size = FONT, Pt(SIZE["note"])
    for rpr in chart._chartSpace.iter(qn("a:defRPr")):        # 和文ラベル用に ea も付ける
        latin = rpr.find(qn("a:latin"))
        if latin is not None and rpr.find(qn("a:ea")) is None:
            ea = etree.SubElement(rpr, qn("a:ea")); latin.addnext(ea); ea.set("typeface", FONT)
    plot = chart.plots[0]
    plot.gap_width = 80
    plot.has_data_labels = True
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    plot.data_labels.number_format, plot.data_labels.number_format_is_linked = fmt, False
    va, ca = chart.value_axis, chart.category_axis
    va.major_gridlines.format.line.color.rgb = RGBColor.from_string(C["line"])
    va.format.line.fill.background()
    va.tick_labels.font.color.rgb = RGBColor.from_string(C["muted"])
    ca.format.line.color.rgb = RGBColor.from_string(C["line"])
    has_negative = any(v < 0 for _, values in series for v in values)
    if has_negative:
        ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW     # 負の棒に項目名が重ならない
    for i, ser in enumerate(plot.series):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = RGBColor.from_string(C["primary" if i == 0 else "line"])
        inv = etree.SubElement(ser._element, qn("c:invertIfNegative")); inv.set("val", "0")
        ser._element.find(qn("c:cat")).addprevious(inv)           # 無いと PowerPoint 以外のビューアで負の棒が上向きに出ることがある
    return chart


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
    text(slide, M, FOOT_Y, 9, 0.35, source, SIZE["source"], color="muted")


# --- レイアウト関数（layout-catalog.md の原型に対応。主役を回すために使い分ける） ---

def slide_cover(prs, title, meta, dark=True):
    s = blank(prs)
    k = skeleton("cover")
    if dark:
        rect(s, *k["canvas"], fill="primary")
    text(s, *k["title"], lines=title, size=SIZE["cover"], color="bg" if dark else "text", bold=True)
    text(s, *k["meta"], lines=meta, size=18, color="line" if dark else "muted")
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
    text(s, *k["number"], lines=number, size=84, color="accent", bold=True)
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
- **N 個を横に並べるときは `spread()` で幅を計算する。** 固定幅を N 回置くと、N が増えたときに右端が溢れる。
- **`MODE` は最初に決める。** 講演型と資料型でサイズが違う。途中で変えると型スケールが混ざる。lint の `--mode` にも同じ値を渡す。
- **縦に積むときは `vstack()`、下端の注記は `bottom_note()`、本文の範囲は `content_band()`。** 手で y を置くと、文言が1行増えた瞬間に重なる。`vstack()` は収まらないと例外を出すので、黙って重ならない。
- **プレースホルダのレイアウトを使うと、テーマ由来の書式が混ざる。** 新規作成は白紙レイアウト（index 6）に textbox と shape で組む。テンプレを使うときだけレイアウトのプレースホルダを使う。
- **既定の図形には影と枠線がつく。** `shape.shadow.inherit = False`、`shape.line.fill.background()` を毎回呼ぶ。
- **textbox には内側の余白がある（既定 0.1in / 0.05in）。** 罫線や図形と端をそろえるなら余白を 0 にする。
- **自動縮小に頼らない。** `auto_size = MSO_AUTO_SIZE.NONE` にし、文字数の予算で収める。`SHAPE_TO_FIT_TEXT` は PowerPoint で開き直すまで反映されないことがある。
- **スライドの複製ができない。** 同じ構成のページは関数で再生成する。テンプレのスライド複製が必要なら OOXML を直接扱う。
- **ネイティブ図表の書式は既定が古い。** `chart.has_title`、`chart.has_legend`（単系列は False）、`plot.has_data_labels`、系列の色、目盛線の色（`value_axis.major_gridlines.format.line.color.rgb`）、`category_axis.tick_labels.font.size` を必ず設定する。縦の目盛線は消す。骨格の `bar_chart()` が最低限を行う。
- **負の値の棒は、`<c:invertIfNegative val="0"/>` を系列に明示する。** python-pptx はこれを書かず、PowerPoint 以外のビューア（LibreOffice など）では負の棒が絶対値で上向きに描かれる（実測: −1.9 が +1.9 に見える）。受け手がそのビューアで開くと数値が違って見える。負の値があるときは項目名の位置を `XL_TICK_LABEL_POSITION.LOW` にして棒と重ねない。
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
