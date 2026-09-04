# OOXML を直接扱う — 複製・削除・並べ替え・テンプレ流し込み

`.pptx` は XML ファイルの ZIP である。python-pptx にできない操作（スライドの複製、削除後の掃除、テンプレの流し込み）は、展開して XML を編集し、再圧縮する。

## 1. 展開と再圧縮

```python
import os, zipfile

zipfile.ZipFile("deck.pptx").extractall("unpacked")
# ... 編集 ...

def pack(src_dir, out_path):
    if os.path.exists(out_path):
        os.remove(out_path)                       # 消さないと削除した部品が古い ZIP に残る
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(src_dir, "[Content_Types].xml"), "[Content_Types].xml")   # 先頭に置く
        for root, _, files in os.walk(src_dir):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, src_dir).replace(os.sep, "/")
                if rel != "[Content_Types].xml":
                    z.write(full, rel)            # パスは展開先からの相対。先頭に unpacked/ を付けない

pack("unpacked", "out.pptx")
from pptx import Presentation
Presentation("out.pptx")                          # 再オープン検査
```

- ZIP 内のパスは `ppt/slides/slide1.xml` のように展開先からの相対にする。ディレクトリ名が先頭に付くと開けない。
- 出力先を先に消す。消さないと削除した部品が古い ZIP に残る。

## 2. 部品の対応

| 場所 | 内容 |
|---|---|
| `ppt/presentation.xml` | スライドの順序（`<p:sldIdLst>`）、スライドサイズ |
| `ppt/_rels/presentation.xml.rels` | `rId` → `slides/slideN.xml` の対応 |
| `ppt/slides/slideN.xml` | 各スライドの図形と文字 |
| `ppt/slides/_rels/slideN.xml.rels` | そのスライドが参照するレイアウト・画像・図表・ノート |
| `ppt/slideLayouts/`, `ppt/slideMasters/` | レイアウトとマスター（プレースホルダの位置と書式） |
| `ppt/theme/theme1.xml` | 配色（`a:clrScheme`）と書体（`a:majorFont` / `a:minorFont`） |
| `ppt/notesSlides/` | 発表者ノート |
| `ppt/charts/`, `ppt/media/` | 図表と画像 |
| `[Content_Types].xml` | 各部品の種類の登録 |

## 3. スライドの複製（テンプレ流し込みの基本）

1. `ppt/slides/slideN.xml` を `slideM.xml`（未使用の番号）にコピーする。
2. `ppt/slides/_rels/slideN.xml.rels` を `slideM.xml.rels` にコピーする。ノートへの参照（`notesSlide`）は削除するか、ノートも複製して付け替える。
3. `[Content_Types].xml` に `<Override PartName="/ppt/slides/slideM.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>` を追加する。
4. `ppt/_rels/presentation.xml.rels` に新しい `rId` で `slides/slideM.xml` を追加する。
5. `ppt/presentation.xml` の `<p:sldIdLst>` に `<p:sldId id="<既存最大+1>" r:id="<新rId>"/>` を挿入したい位置に追加する。
6. 複製したスライドの `slideM.xml` 内の図形 `id` は同じでも開けるが、`cNvPr` の `id` をずらしておくと後の編集で混乱しない。

複製元が図表・SmartArt・埋め込みオブジェクトを持つ場合、複製後の両方が同じ部品を参照する。片方の図表を変えると他方も変わる。図表ごと複製するなら `ppt/charts/chartN.xml` とその rels、`[Content_Types].xml` の登録も複製して付け替える。

## 4. 削除と並べ替え

- 並べ替えは `<p:sldIdLst>` の `<p:sldId>` の順序を変えるだけでよい。
- 削除は `<p:sldIdLst>` から外し、`presentation.xml.rels` の該当行を消し、`slideN.xml`・その rels・ノートを消し、`[Content_Types].xml` の Override を消す。参照が残っていると開けないか修復ダイアログが出る。
- 削除したスライドだけが使っていた画像や図表は `ppt/media/`・`ppt/charts/` に残っても開けるが、ファイルが太る。消すなら他のスライドから参照されていないことを rels で確認する。

**順序**: 追加・削除・並べ替えをすべて済ませてから、内容の編集に入る。複製は元の内容をそのまま写すので、内容を直した後に複製すると直した内容が写る。

## 5. XML 編集の注意

- パーサで往復させると名前空間の接頭辞が書き換わり、開けなくなることがある。`lxml` は保持する。標準の `xml.etree.ElementTree` は保持しないので使わない。文字列置換で済む編集は文字列置換で行う。
- 先頭・末尾に空白がある文字は `<a:t xml:space="preserve">`。
- 箇条書きは1項目1つの `<a:p>`。既存の隣の段落から `<a:pPr>` を写して、行間と箇条書き記号を継承する。
- 箇条書き記号は `<a:buChar>` / `<a:buAutoNum>` / `<a:buNone>` で制御し、本文に「・」を書かない。
- 太字は `<a:rPr b="1">`。タイトル・見出し・行内ラベル（「担当:」など）に付ける。
- 和文の run には `<a:latin>` と `<a:ea>` の両方。
- `<p:presentation>` の子要素の順序を変えない。

## 6. テンプレ流し込みの手順

1. テンプレの全レイアウトとサンプルスライドを描画し、使うレイアウトを決める。同じレイアウトばかり選ばない。
2. 使うスライドを必要枚数だけ複製し、順序を決める（3〜4章）。
3. 各スライドの文字を差し替える。python-pptx で `run.text` を書き換えるのが最も安全。
4. 余った枠（人物枠、項目枠）は画像と文字ごと削除する。
5. 差し替えた文字がテンプレの装飾（下線の長さ、枠の幅）と合わなくなっていないか描画で確認する。
6. 仮置き文言を検索して残っていないことを確認する。

```python
import re
from pptx import Presentation
p = Presentation("out.pptx")
pat = re.compile(r"lorem|ipsum|todo|xxx|ダミー|サンプル|ここに|\[.*?\]", re.I)
for i, s in enumerate(p.slides, 1):
    for sh in s.shapes:
        if sh.has_text_frame and pat.search(sh.text_frame.text):
            print(i, sh.name, sh.text_frame.text[:60])
```

pptx-review の lint も `PLACEHOLDER_TEXT` として同じ検査を行う。

## 7. python-pptx での run 単位編集

```python
from pptx import Presentation
p = Presentation("deck.pptx")
slide = p.slides[2]                       # 0 始まり
for shape in slide.shapes:
    if shape.name == "Title 1":
        para = shape.text_frame.paragraphs[0]
        runs = para.runs
        runs[0].text = "新しいタイトル"      # 最初の run に全文を入れ
        for r in runs[1:]:
            r.text = ""                    # 残りの run は空にする（書式は残る）
p.save("deck-edited.pptx")
```

`shape.name` は描画や lint の結果で確認する。同名が複数あるときは `shape.shape_id` で特定する。

## 8. テーマの読み取り

```python
import zipfile, re
z = zipfile.ZipFile("deck.pptx")
theme = z.read("ppt/theme/theme1.xml").decode("utf-8")
print(re.findall(r'<a:(dk1|lt1|dk2|lt2|accent\d|hlink)>.*?val="([0-9A-Fa-f]{6})"', theme))
print(re.findall(r'<a:(majorFont|minorFont)>.*?<a:latin typeface="([^"]*)".*?<a:ea typeface="([^"]*)"', theme, re.S))
```

読み取った値を `deck/design-lock.md` に転記し、編集ではその外に出ない。
