# 既存デザインに合わせる — 目分量で作らない

修正や追加ページが「浮く」原因は、既存の設計値を読み取らずに、その場で妥当に見える値を書いてしまうことにある。既存デッキには必ず設計値があり、それは測れる。測ってから書く。

## 1. 設計値を抽出する（着手前に必ず）

```python
import subprocess, sys
subprocess.run([sys.executable, "<skills>/pptx-review/scripts/extract_style.py", "deck.pptx",
                "--json-out", "deck/design-lock.json", "--md-out", "deck/design-lock.md"])
```

`design-lock.md` に、タイトルの位置・幅・サイズ・太さ・色・揃え、本文のサイズの語彙・左端・行間・箇条書き記号、出典の位置とサイズ、余白、使用中の書体と色、レイアウトの使用回数、そして**レイアウトごとの**役割別複製元が入る。

この文書が「正」になる。以降の判断はここを参照し、記憶や見た目の印象で決めない。

## 2. 同じレイアウトの複製元から作る

`design-lock.md` の「レイアウト別の設計値と複製元」から、編集対象と同じレイアウト名のtitle/body/sourceを選ぶ。全体多数派の複製元は旧形式との互換用であり、比較ページの本文へ通常本文ページの複製元を流用しない。該当レイアウトに複製元が無ければ、図形単位ではなくページ全体を複製するか、実装仕様書を作って再設計する。

単一段落の文言差替は、直接 `run.text` を操作せず、安全経路を使う。書式・座標・text frameが変わらず、自動伸長・自動縮小がなく、必要寸法が箱の90%以下のときだけ出力される。

```bash
python3 <skills>/pptx-edit/scripts/safe_text_replace.py deck/original.pptx deck/edited.pptx \
  --slide 6 --shape-id 12 --text-file deck/replacement.txt
```

複数段落や箇条書きは、このスクリプトが意図的に拒否する。段落構造を維持して個別にrunを変え、直後にedit contract付きの `layout_guard` を通す。

次の低水準例が必要なのは、relationshipを持たない基本図形を同一レイアウト内で追加する場合だけである。画像、図表、SmartArt、埋め込みオブジェクト、動画、ハイパーリンク付き図形を別スライドへ要素単位でコピーしてはいけない。

```python
import copy
from pptx import Presentation
from pptx.util import Inches

prs = Presentation("deck.pptx")
donor = next(sh for sh in prs.slides[2].shapes if sh.name == "本文 3")   # design-lock.md の複製元
target = prs.slides[5]
new_el = copy.deepcopy(donor._element)
target.shapes._spTree.append(new_el)
# 同じレイアウト内で、契約に記載した位置だけ変え、書式は触らない
new_shape = target.shapes[-1]
# 複製元の位置も一緒に写るので、必ず置き直す。書式（書体・サイズ・色・行間）だけを引き継ぐ。
new_shape.left = Inches(0.6)                                             # design-lock.md の本文左端
new_shape.top = Inches(2.2)                                              # design-lock.md の本文開始
new_shape.width = Inches(12.13)
new_shape.height = Inches((3 + 0.5) * 16 * 1.4 / 72)                     # (行数+0.5) × サイズ × 行間 ÷ 72
for para in new_shape.text_frame.paragraphs:
    if para.runs:
        para.runs[0].text = "新しい文言"
        for r in para.runs[1:]:
            r.text = ""
```

画像・図表などrelationshipを持つ要素が必要なら、要素ではなくスライド全体と関連部品を `ooxml-editing.md` の手順で複製する。画像だけを差し替える場合は、新しい画像を `add_picture` で追加して元図形の位置・寸法・crop・回転・重ね順を移し、元図形を削除する。図表は同じスライド上で `replace_data` し、系列数やカテゴリ数を変えた場合は軸・凡例・ラベルをPowerPoint互換描画で確認する。

複製すれば、書体・サイズ・色・行間・箇条書き記号・余白が引き継がれる。ただし座標を変える必要が無いなら、位置と大きさも含めて触らない。位置変更が必要なときだけedit contractに期待する変更を書き、`layout_guard --contract --strict` で照合する。ゼロから `add_textbox` するとPowerPointの既定書式が入り、そのページだけ浮く。

**複製できないときだけ**、`design-lock.md` の値を明示的に指定して作る。その場合も値は文書から写す。

## 3. 新しいページはレイアウトごと複製する

ページを足すときは、同じ役割・同じレイアウトの既存ページを `scripts/clone_slide.py` で複製してから中身を差し替える（`ooxml-editing.md` 3節）。空白ページに要素を並べない。図表・SmartArt・OLE・動画・アニメーションを含み安全複製が拒否された場合は、共有部品のまま続行しない。

- 主張＋証拠の追加 → 既存の主張＋証拠ページを複製
- 比較の追加 → 既存の比較ページを複製
- 該当する役割が既存に無い → 最も構造の近いページを複製し、要らない要素を削る

## 4. 揃えるべき値の優先順位

同じにできないときは、次の順で守る。上ほど、ずれたときに目立つ。

1. **タイトルの位置と大きさ。** ページを送ったときに動くと、それだけで雑に見える
2. **本文の左端。** 縦の揃え線が崩れると全体が乱れて見える
3. **文字サイズの語彙。** 16pt の本文の中に 17pt が混ざると、理由の無い差として読まれる
4. **色。** 既存の色に近いが違う色は、最も気づかれる不統一
5. **余白と要素間の間隔**
6. **行間、箇条書き記号、太字の使い方**
7. **角の処理（角丸か直角か）、罫線の太さ**

## 5. 確認する

```python
import subprocess, sys
subprocess.run([sys.executable, "<skills>/pptx-review/scripts/pptx_lint.py", "deck-edited.pptx",
                "--lock", "deck/design-lock.json", "--baseline", "deck/before/lint.json",
                "--json-out", "deck/qa/lint.json"])
```

統一性の指摘（`TITLE_POSITION_DRIFT`、`TITLE_SIZE_DRIFT`、`MARGIN_DRIFT`、`BODY_SIZE_DRIFT`、`PALETTE_DRIFT`）が**自分の触ったページに出ていたら、直してから納品する。** これらは「多数派から外れた」ことを示す指摘なので、元から揃っていないデッキでは既存ページにも出る。`--baseline` を付ければ、元からあったものは判定から外れる。

描画の一覧（`render_preview.py --sheet`）を見て、触ったページが他と同じ骨格に見えるかを最後に確かめる。1枚ずつ見ると気づかない。

## 6. 意図的にずらすとき

強調のために既存と変える場合は、`design-lock.json` の `allow` に理由つきで登録し、報告にも書く。

```json
{"allow": [{"code": "PALETTE_DRIFT", "slide": 7, "reason": "警告色。利用者の指示による"}]}
```

登録せずに「意図的です」と述べるだけでは、次に触る人には伝わらない。
