---
name: pptx-edit
description: "既存のPowerPoint（.pptx/.potx）を、元のデザインに揃えたまま編集する。設計値を機械的に抽出し、既存要素を複製して作ることで、修正したページだけ浮くことを防ぐ。文言の差替、スライドの追加・削除・並べ替え、テンプレへの流し込み、図表データの更新、生成AIっぽい装飾の除去、体裁の修正に使う。「このPPTを直して」「スライド3を修正」「テンプレに流し込んで」「AIっぽさを消して」など、既存ファイルがあるときに使う。新規作成は pptx-create、配色やデザイン方針は pptx-design、監査だけなら pptx-review。"
license: MIT
compatibility: "Python 3.9+ と python-pptx（lxml、Pillow）。構造変更は zipfile と XML 編集。設計値の抽出・検査・描画は pptx-review 同梱のスクリプト。図表・SmartArt・画像を含む場合、最終合格にはPowerPoint互換描画が必要。"
metadata:
  version: "1.8.0"
  publisher: "agent-skills"
  bundle: pptx-suite
---

# pptx-edit — 既存デッキを、そのデザインのまま直す

`pptx-design`、`pptx-create`、`pptx-edit`、`pptx-review` は `pptx-suite` として一体配布する。抽出・lint・描画では、同じインストール先にある `pptx-review/scripts/` を使う。デザイン方針の考え方（避けるもの・書体・署名）は `pptx-design` が持つ。4スキルの一部だけを配布・導入しない。

## 原則

1. **元ファイルを上書きしない。** 別名で保存し、元は残す。
2. **既存のデザインシステムがロックである。** テーマの色・書体・レイアウトの外に出ない。新しい色や書体を足すなら利用者に確認する。
3. **変える範囲を先に決め、書く。** 「ついでに」直さない。
4. **構造の変更は内容の変更より先に行う。** 追加・削除・並べ替えを済ませてから文言を触る。
5. **合格は描画画像と lint で示す。** 触ったページは必ず描画して見る。

## 工程

### 0. 能力の確認（着手時に1回）

pptx-create の工程0と同じ表で経路を決める。`python-pptx` が無ければ編集できないので、その時点で利用者に伝える。確認した版は報告に残す。

### 1. 把握（`deck/before/`）

- 全ページを描画し（pptx-review の `render_preview.py --sheet`）、一覧を見る。
- テキストを書き出す（pptx-create の `qa.md` と同じ python-pptx の短いスクリプト）。
- **設計値を機械的に抽出する**（目分量で読み取らない）。pptx-review の `extract_style.py` に `--json-out deck/design-lock.json --md-out deck/design-lock.md` を渡す。タイトルの位置・サイズ・色、本文の左端とサイズの語彙、出典の位置、余白、書体、色、そして**レイアウト別**の複製元が出る。手順は `references/match-existing-design.md`。
- bundleに必ず含まれるpptx-reviewでlintを通し、元の状態の指摘を `deck/before/lint.json` に残す。元から壊れていた箇所と、自分が壊した箇所を区別するため。

### 2. 変更範囲（`deck/changes.md`）

対象ページ・図形・変更内容・維持するものを表にする。次に当たる場合は着手前に利用者に確認する。

- ページの削除・並べ替え
- 色・書体・レイアウトの変更
- 図表の数値の変更（意味が変わる）
- 「AIっぽさを消す」など判断を伴う一括修正（`references/cleanup-checklist.md` で対象を列挙して見せる）

ページを追加する、原型を変える、または意味領域を組み替える場合は、変更対象について pptx-create の `references/implementation-spec.md` と同じ `implementation-spec.json` / `.md` を編集前に作る。文言だけの差し替えでは `changes.md` で足りる。

編集前PPTXのハッシュを固定した契約を、**編集を始める前**に作る。座標・図形追加など意図した変更は `allow` にページ・図形・理由を記入する。別の原本へ契約を流用できない。

```bash
python3 <skills>/pptx-review/scripts/layout_guard.py deck/original.pptx \
  --init-contract deck/edit-contract.json
```

### 3. 手法の選択

| 変更 | 手法 |
|---|---|
| 単一段落の文言差替 | `scripts/safe_text_replace.py`。run書式と幾何が不変で、箱の使用率90%以下の場合だけ別名へ保存する |
| 複数段落の文言差替 | run単位で変更し、段落数・箇条書き・行間を維持する。変更直後に `layout_guard --contract` を通す |
| 図形の位置・大きさ・色 | python-pptx の shape 属性 |
| 図表の数値 | `chart.replace_data(chart_data)` |
| 表のセル | `cell.text_frame.paragraphs[0].runs[0].text` |
| 図表・表の**新規追加** | 同じデッキに既存の図表・表があれば複製して数値を差し替える（書式が揃う）。無ければ `add_chart` / `add_table` で作り、色・書体は `design-lock.json` の抽出値に合わせる。**画像として貼らない** |
| スライドの追加（テンプレのレイアウトから） | `prs.slides.add_slide(layout)` |
| 単純なスライドの複製 | `scripts/clone_slide.py`。画像・リンクのrelationshipを付け替える。図表・SmartArt・OLE・動画・アニメーションは拒否する |
| 複雑なスライドの複製・削除・並べ替え、テンプレ流し込み | `references/ooxml-editing.md`。拒否された部品を手作業で共有しない |
| 装飾の除去（飾り線・色帯・絵文字） | `references/cleanup-checklist.md` |

`.ppt`（旧形式）はこのスキルでは扱えない。利用者に PowerPoint で `.pptx` に保存し直してもらう。`.potx` は `.pptx` と同じ手順で扱い、拡張子を保つ。

### 4. 編集

**新しい要素は、同じレイアウトの既存要素から作る。** `design-lock.md` の「レイアウト別の設計値と複製元」を使う。全体多数派の複製元は互換用であり、編集対象と違うレイアウトへ流用しない。同じレイアウトに複製元が無ければ、図形を新設せず、近いページ全体を複製するか実装仕様書を作って再設計する。詳細は `references/match-existing-design.md`。

- スクリプト（`deck/edit.py`）で行い、手作業の XML 編集は最小限にする。同じ編集を再実行できる状態にしておく。
- 文言を差し替えるときは、元と同程度の長さにする。長くなるなら箱の大きさを見直すか、文を削る。縮小しない。
- テンプレ流し込みで枠が余ったら（4人分の枠に3人）、余った枠は画像・文字ごと削除する。文字だけ消して枠を残さない。
- 箇条書きは1項目1段落。段落をまとめて1つにしない。
- 和文の run には latin と ea の両方に書体を指定する（pptx-design の `typography-ja.md`）。
- 写真を差し替えるときは、置く前に正規化する（pptx-create の `materials.md`）。EXIF の回転と色空間はそのまま埋まるので、元デッキの写真と見え方が揃わなくなる。

### 5. 品質確認（`deck/qa/`）

- 再オープン検査: Python で `Presentation("deck/output.pptx")` を開く。例外が出れば壊れている。
- **編集前後のレイアウト比較**: `pptx-review/scripts/layout_guard.py deck/original.pptx deck/output.pptx --contract deck/edit-contract.json --strict --json-out deck/qa/layout-guard.json` を実行する。座標・寸法、回転・反転、グループ座標系、コネクタ接続、重ね順、placeholder、段落/run書式、自動調整、画像crop、表の行列寸法、関連画像・図表、theme/layoutを比較する。未許可の変化を0にする。原因と検査範囲はpptx-reviewの `references/layout-stability.md`。
- `--lock deck/design-lock.json --baseline deck/before/lint.json` を付けて lint を通し、**新しく増えた指摘**を 0 にする。元からある指摘は `inherited` として集計され、報告に書く。
- **統一性の指摘**（`TITLE_POSITION_DRIFT`、`TITLE_SIZE_DRIFT`、`MARGIN_DRIFT`、`BODY_SIZE_DRIFT`、`PALETTE_DRIFT`）が自分の触ったページに出ていたら、必ず直す。これが「修正したページだけデザインが違う」の直接の検出である。
- 描画の一覧（`render_preview.py --sheet`）で、触ったページが他と同じ骨格に見えるかを確かめる。1枚ずつ見ると気づかない。
- 触ったページに図表・表を足したなら、`Presentation` で開き直して `shape.has_chart` / `shape.has_table` が真であることを確かめる。lint の `FULL_PAGE_PICTURE` はページの85%以上を占める画像しか見ないので、ページの一部に貼った画像の図表は検出できない。
- 触ったページを描画して1枚ずつ見る。加えて全体を一覧し、他のページとの整合（タイトル位置、余白、フッター）を確認する。描画の手順は pptx-create の `references/qa.md` ゲート3にある。
- テキストを再度書き出し、変更前との差分が `deck/changes.md` の範囲に収まっていることを確認する。
- 実装仕様書を作った編集では、`qa_evidence.py init` で生成後の設計〜実装対応表とQA証跡を作る。形式的QAとデザイン的QAを分け、全ページの個別previewと一覧previewに根拠を記入して `qa_evidence.py check` を通す。
- 図表・SmartArt・画像を含む場合、`qa_evidence.py` がPowerPoint互換描画の確認を必須にする。手段が無ければ「未確認」として納品を止め、簡易描画だけで合格にしない。

### 6. 報告

- 保存先（別名）
- 変更一覧（ページ・図形・前後）
- 維持したデザインシステムと、やむを得ず逸脱した点
- 実行した検査、確認したページ数、検出件数
- 使用した書体と、描画で代替が起きたかどうか
- 元から存在した問題で今回触らなかったもの
- 再現条件（工程0で確認したライブラリの版）

## 絶対規則

- 元ファイルを上書きしない。
- 図表や数値の意味を変えない。変えるなら利用者の指示を引用する。
- **図表・表をネイティブに保つ。** 既存のネイティブな図表を画像に置き換えない。追加するときも `add_chart` / `add_table` で作る。画像にしてよいのは写真・ロゴ・PowerPoint に形の無い図（サンキー、ネットワーク図）だけ。
- テーマに無い色・書体を足さない。
- 新しい要素は複製から作る。空の図形に書式を手で設定しない。
- 構造変更（追加・削除・並べ替え）を先に、内容変更を後に。
- `copy.deepcopy(shape._element)` を別スライドへ使うのはrelationshipを持たないテキストボックスと基本図形だけ。画像・図表・SmartArt・リンクはスライドごと複製する。
- 描画画像を見ずに完了と言わない。
- `safe_text_replace.py` が拒否した文言を、検査を外して直接書き込まない。文章を短くするかレイアウトを明示的に再設計する。

## 出力

編集済みの `.pptx`（別名）と、変更一覧、未解決事項、形式的QAとデザイン的QAの証拠を返す。ページ追加・原型変更・領域再編では、スライド実装仕様書と設計〜実装対応表も返す。
