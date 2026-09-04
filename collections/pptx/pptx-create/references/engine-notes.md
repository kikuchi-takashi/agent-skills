# 生成エンジンの注記 — python-pptx を第一候補に

## 1. 選び方

| 条件 | 使うもの |
|---|---|
| 新規作成、Python が使える | python-pptx（第一候補） |
| 新規作成、Node.js しかない | pptxgenjs |
| テンプレのスライドを複製して流し込む | python-pptx はスライド複製ができない。OOXML 直接編集（pptx-edit の `ooxml-editing.md`） |
| 既存デッキの文言差替 | python-pptx の run 単位編集 |

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
        ser._element.find(qn("c:cat")).addprevious(inv)           # 無いと LibreOffice が負の棒を上向きに描く
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
- **プレースホルダのレイアウトを使うと、テーマ由来の書式が混ざる。** 新規作成は白紙レイアウト（index 6）に textbox と shape で組む。テンプレを使うときだけレイアウトのプレースホルダを使う。
- **既定の図形には影と枠線がつく。** `shape.shadow.inherit = False`、`shape.line.fill.background()` を毎回呼ぶ。
- **textbox には内側の余白がある（既定 0.1in / 0.05in）。** 罫線や図形と端をそろえるなら余白を 0 にする。
- **自動縮小に頼らない。** `auto_size = MSO_AUTO_SIZE.NONE` にし、文字数の予算で収める。`SHAPE_TO_FIT_TEXT` は PowerPoint で開き直すまで反映されないことがある。
- **スライドの複製ができない。** 同じ構成のページは関数で再生成する。テンプレのスライド複製が必要なら OOXML を直接扱う。
- **ネイティブ図表の書式は既定が古い。** `chart.has_title`、`chart.has_legend`（単系列は False）、`plot.has_data_labels`、系列の色、目盛線の色（`value_axis.major_gridlines.format.line.color.rgb`）、`category_axis.tick_labels.font.size` を必ず設定する。縦の目盛線は消す。骨格の `bar_chart()` が最低限を行う。
- **負の値の棒は、`<c:invertIfNegative val="0"/>` を系列に明示する。** python-pptx はこれを書かず、LibreOffice はその状態で負の棒を絶対値で上向きに描く。確認画像がデータと違う値を示す（実測: −1.9 が +1.9 に見える）。PowerPoint では正しく出るため、画像だけ見て数値を「直す」と本物を壊す。負の値があるときは項目名の位置を `XL_TICK_LABEL_POSITION.LOW` にして棒と重ねない。
- **図表の文字にも書体を設定する。** `chart.font.name` と `chart.font.size` を設定し、和文ラベルがあるなら `txPr` に `a:ea` を追加する。
- **表のセルにも内側余白がある。** `cell.margin_left` などで統一する。表の既定スタイルは色が強いので、`tbl.first_row = False` にして自分で塗る。
- **画像は縦横比を保つ。** 幅か高さの一方だけ指定する。トリミングは `picture.crop_left` などで行う。
- **SVG と EMF は読めない。** PNG か JPEG に変換してから置く。
- **グループ図形の中の座標は親基準。** 位置検査が要る要素はグループ化しない。
- **色は 6 桁の HEX。** `RGBColor.from_string("1A1A1A")`。`#` は付けない。
- **1 ファイル 1 `Presentation()`。** 使い回さない。
- **ノートは `slide.notes_slide.notes_text_frame`。** 本文の textbox に書かない。

## 4. pptxgenjs を使う場合の注記

- `pres.layout = "LAYOUT_WIDE"`（13.333 × 7.5）をスライド追加前に設定する。既定は 10 × 5.625。
- 色は `"1A1A1A"` の 6 桁。`#` を付けたり 8 桁にしたりするとファイルが壊れる。
- オプションのオブジェクトは呼び出しごとに新しく作る。同じオブジェクトを2回渡すと内部で単位変換され、2回目がずれる。
- 影の `offset` は負にしない。
- 箇条書きは `bullet: true`。本文に「・」を書かない。
- 単系列の図表は `showLegend: false`。積み上げ棒の `dataLabelPosition` は `ctr` / `inEnd` / `inBase` のみ。
- `<p:presentation>` の子要素の順序を後処理で変えない。開けなくなる。
- 生成後に `a:ea` の有無を確認する（`typography-ja.md`）。

## 5. 描画と再オープン

```bash
# 再オープン検査（壊れていれば例外）
python3 -c "from pptx import Presentation; p=Presentation('deck/output.pptx'); print(len(p.slides), 'slides')"

# 描画（LibreOffice → PDF → JPEG）
soffice --headless --convert-to pdf --outdir deck/qa deck/output.pptx
rm -f deck/qa/slide-*.jpg
pdftoppm -jpeg -r 110 deck/qa/output.pdf deck/qa/slide
ls deck/qa/slide-*.jpg
```

- macOS で `soffice` が PATH に無ければ `/Applications/LibreOffice.app/Contents/MacOS/soffice`。
- `pdftoppm` の連番は枚数で桁が変わる（`slide-1.jpg`、`slide-01.jpg`）。古い画像は先に消す。
- 修正後は PDF から作り直す。`.pptx` を直しただけでは画像は変わらない。
- 描画が固まるときは `-env:UserInstallation=file:///tmp/lo-profile` を `soffice` に付けて専用プロファイルで起動する。

## 6. ネイティブを守る

- 図表は `add_chart`、表は `add_table`、図形は `add_shape`。画像化しない。
- 画像にしてよいのは、写真、PowerPoint に無い図（サンキー、ネットワーク図）、ロゴだけ。
- 全面が画像のページを作らない。編集できないデッキは納品物にならない。
