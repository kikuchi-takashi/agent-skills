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
SIZE = {"cover": 44, "title": 28, "h2": 20, "body": 16, "note": 12, "source": 10}
GAP = 0.3                   # 要素間の最小間隔


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


# --- レイアウト関数（layout-catalog.md の番号に対応） ---

def slide_claim_evidence(prs, title, reading, source, draw_exhibit):
    s = blank(prs)
    page_title(s, title)
    x, w = col(1, 7)
    rect(s, x, BODY_Y, w, BODY_END - BODY_Y, "panel")
    draw_exhibit(s, x + 0.2, BODY_Y + 0.2, w - 0.4, BODY_END - BODY_Y - 0.4)
    rx, rw = col(8, 5)
    text(s, rx, BODY_Y, rw, BODY_END - BODY_Y, reading, SIZE["body"])
    page_source(s, source)
    return s


def build():
    prs = new_deck()
    # outline.md の順にレイアウト関数を呼ぶ
    prs.save("deck/output.pptx")


if __name__ == "__main__":
    build()
```

## 3. python-pptx の落とし穴

- **`text_frame.text = "..."` は書式を消す。** 段落が1つの無書式 run に潰れる。必ず `run.text` に書く。
- **`add_textbox` の既定は折り返し無し（`wrap="none"`）と `spAutoFit`。** そのままだと1行で右へ伸び、箱の大きさも文字に合わせて変わる。必ず `word_wrap = True` と `auto_size = MSO_AUTO_SIZE.NONE` にし、箱の高さは `text_height()` で決める。
- **`normAutofit`（文字の自動縮小）を使わない。** PowerPoint で開いたときだけ縮小され、描画確認とずれる。縮小後のサイズが下限を割る。
- **N 個を横に並べるときは `spread()` で幅を計算する。** 固定幅を N 回置くと、N が増えたときに右端が溢れる。
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
