# スライド実装仕様書 — 構成を座標コードへ渡す契約

`outline.json` は「何を伝えるか」、`design-lock.json` は「どう見せるか」を固定する。`implementation-spec.json` はその2つを、`build.py` が実装できるページ単位の契約へ落とす。生成後に推測で作らず、**構成とデザインロックが確定してから、最初のPPTXを書き出す前**に作る。

## 必須項目

```json
{
  "slides": [
    {
      "n": 1,
      "title": "問い合わせの半数は、3つの迷いから生まれる",
      "archetype": "claim-evidence",
      "preview_priority": "cover",
      "implementation": {
        "function": "slide_claim_evidence",
        "regions": ["title", "hero-number", "evidence", "source"],
        "content_bindings": {
          "hero-number": "問い合わせの50%",
          "evidence": "迷い3分類と各件数",
          "source": "集計期間と母数"
        },
        "overflow": "fit_text",
        "design_intent": "50%を主役にし、3分類を一段弱く読ませる"
      }
    }
  ]
}
```

- `n` / `title`: `outline.json` と一致させる。
- `archetype`: 構成で選んだ原型。勝手に別形式へ変えない。
- `function`: `engine-notes.md` の `slide_*` 関数。
- `regions`: ページ上の意味領域。図形名の羅列ではなく、役割で書く。
- `content_bindings`: どの内容をどの領域へ置くか。
- `overflow`: `place` / `fit_text` / `fixed-native` / `not-applicable` のいずれか。
- `design_intent`: 何を主役にし、何を弱め、どの順で読ませるか。
- `preview_priority`: `cover` / `dense` / `data` / `standard`。`standard` 以外を事前preview対象とする。

## 事前previewの選び方

- 3ページ以下は全ページを事前previewする。
- 4ページ以上は最低3ページ。表紙があれば表紙、最も密な本文、図表・写真を含むページを必ず含める。
- 新しい原型、未検証の図形、長文、複雑な図表など高リスクなページは最低枚数に加える。
- 個別画像と一覧画像の両方を見てから全ページ生成へ進む。個別で収まり、一覧でデッキの方向とリズムを見る。

検査済みの人向け表示を同時に作る。

```python
import subprocess, sys
subprocess.run([
    sys.executable, "<skills>/pptx-create/scripts/check_implementation_spec.py",
    "deck/implementation-spec.json", "--outline", "deck/outline.json",
    "--md-out", "deck/implementation-spec.md"
], check=True)
```

代表ページを `deck/qa/pre-preview-NN.png` と `deck/qa/pre-preview-sheet.png` に描画して個別・一覧の両方を確認したら、仕様書の直下に証跡を追記する。

```json
{
  "pre_preview_review": {
    "status": "pass",
    "sheet_evidence": "一覧でタイトル位置・余白・密度の方向が揃うことを確認",
    "slides": {
      "1": "表紙を個別表示し、タイトルの折返しと署名を確認",
      "4": "最密ページを個別表示し、文字切れと要素間隔を確認",
      "7": "図表ページを個別表示し、凡例・軸・主役を確認"
    }
  }
}
```

全ページ生成へ進む直前に、画像の存在とページ固有の所見を再検査する。

```python
subprocess.run([
    sys.executable, "<skills>/pptx-create/scripts/check_implementation_spec.py",
    "deck/implementation-spec.json", "--outline", "deck/outline.json",
    "--preview-prefix", "deck/qa/pre-preview"
], check=True)
```

## 生成後の対応表とは別物

仕様書は予定であり、合格証ではない。生成・描画後に `qa_evidence.py init` を実行し、実物のページ部品・図形数・個別previewを含む `design-implementation-map.md` を作る。そこで各ページの実装一致を確認して初めて、設計と実装が対応したと言える。
