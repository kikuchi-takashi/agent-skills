---
name: pptx-edit
description: "既存のPowerPoint（.pptx/.potx）を、元のデザインシステム（テーマ色・書体・レイアウト）を壊さずに編集する。文言の差替、スライドの追加・削除・並べ替え、テンプレへの流し込み、図表データの更新、生成AIっぽい装飾の除去、体裁の修正に使う。「このPPTを直して」「スライド3を修正」「テンプレに流し込んで」「AIっぽさを消して」など、既存ファイルがあるときに使う。新規作成は pptx-create、監査だけなら pptx-review。"
license: MIT
compatibility: "Python 3.9+ と python-pptx。構造変更には zip/unzip と XML 編集。視覚確認に LibreOffice（soffice）と Poppler（pdftoppm）。"
metadata:
  version: "1.0.0"
  publisher: "agent-skills"
---

# pptx-edit — 既存デッキを、そのデザインのまま直す

## 原則

1. **元ファイルを上書きしない。** 別名で保存し、元は残す。
2. **既存のデザインシステムがロックである。** テーマの色・書体・レイアウトの外に出ない。新しい色や書体を足すなら利用者に確認する。
3. **変える範囲を先に決め、書く。** 「ついでに」直さない。
4. **構造の変更は内容の変更より先に行う。** 追加・削除・並べ替えを済ませてから文言を触る。
5. **合格は描画画像と lint で示す。** 触ったページは必ず描画して見る。

## 工程

### 1. 把握（`deck/before/`）

- 全ページを描画し（`soffice --headless --convert-to pdf` → `pdftoppm`）、一覧を見る。
- テキストを書き出す（pptx-create の `qa.md` と同じ python-pptx の短いスクリプト）。
- デザインシステムを抽出して `deck/design-lock.md` に書く: `ppt/theme/theme1.xml` の配色と書体、使われているレイアウト名、本文とタイトルの実サイズ（スライド上の実値。テーマと違うことがある）。
- pptx-review スキルが導入されていれば lint を通し、元の状態の指摘を `deck/before/lint.json` に残す。元から壊れていた箇所と、自分が壊した箇所を区別するため。

### 2. 変更範囲（`deck/changes.md`）

対象ページ・図形・変更内容・維持するものを表にする。次に当たる場合は着手前に利用者に確認する。

- ページの削除・並べ替え
- 色・書体・レイアウトの変更
- 図表の数値の変更（意味が変わる）
- 「AIっぽさを消す」など判断を伴う一括修正（`references/cleanup-checklist.md` で対象を列挙して見せる）

### 3. 手法の選択

| 変更 | 手法 |
|---|---|
| 文言の差替（書式維持） | python-pptx で run 単位に `run.text` を書き換える。`text_frame.text =` は書式を消すので使わない |
| 図形の位置・大きさ・色 | python-pptx の shape 属性 |
| 図表の数値 | `chart.replace_data(chart_data)` |
| 表のセル | `cell.text_frame.paragraphs[0].runs[0].text` |
| スライドの追加（テンプレのレイアウトから） | `prs.slides.add_slide(layout)` |
| スライドの複製・削除・並べ替え、テンプレ流し込み | python-pptx では複製ができない。`references/ooxml-editing.md` の手順で XML を直接扱う |
| 装飾の除去（飾り線・色帯・絵文字） | `references/cleanup-checklist.md` |

`.ppt`（旧形式）は先に `soffice --headless --convert-to pptx` で変換する。`.potx` は `.pptx` と同じ手順で扱い、拡張子を保つ。

### 4. 編集

- スクリプト（`deck/edit.py`）で行い、手作業の XML 編集は最小限にする。同じ編集を再実行できる状態にしておく。
- 文言を差し替えるときは、元と同程度の長さにする。長くなるなら箱の大きさを見直すか、文を削る。縮小しない。
- テンプレ流し込みで枠が余ったら（4人分の枠に3人）、余った枠は画像・文字ごと削除する。文字だけ消して枠を残さない。
- 箇条書きは1項目1段落。段落をまとめて1つにしない。
- 和文の run には latin と ea の両方に書体を指定する（pptx-create の `typography-ja.md`）。

### 5. 品質確認（`deck/qa/`）

- 再オープン検査: `python3 -c "from pptx import Presentation; Presentation('deck/output.pptx')"`
- pptx-review があれば `--baseline deck/before/lint.json` を付けて lint を通し、**新しく増えた指摘**を 0 にする。元からある指摘は `inherited` として集計され、報告に書く。
- 触ったページを描画して1枚ずつ見る。加えて全体を一覧し、他のページとの整合（タイトル位置、余白、フッター）を確認する。
- テキストを再度書き出し、変更前との差分が `deck/changes.md` の範囲に収まっていることを確認する。

### 6. 報告

- 保存先（別名）
- 変更一覧（ページ・図形・前後）
- 維持したデザインシステムと、やむを得ず逸脱した点
- 元から存在した問題で今回触らなかったもの
- 書体の代替描画の有無

## 絶対規則

- 元ファイルを上書きしない。
- 図表や数値の意味を変えない。変えるなら利用者の指示を引用する。
- テーマに無い色・書体を足さない。
- 構造変更（追加・削除・並べ替え）を先に、内容変更を後に。
- 描画画像を見ずに完了と言わない。

## 出力

編集済みの `.pptx`（別名）と、変更一覧、未解決事項、品質確認の証拠を返す。
