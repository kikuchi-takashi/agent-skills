---
name: pptx-edit
description: "既存のPowerPoint（.pptx/.potx）を、元のデザインに揃えたまま編集する。設計値を機械的に抽出し、既存要素を複製して作ることで、修正したページだけ浮くことを防ぐ。文言の差替、スライドの追加・削除・並べ替え、テンプレへの流し込み、図表データの更新、生成AIっぽい装飾の除去、体裁の修正に使う。「このPPTを直して」「スライド3を修正」「テンプレに流し込んで」「AIっぽさを消して」など、既存ファイルがあるときに使う。新規作成は pptx-create、監査だけなら pptx-review。"
license: MIT
compatibility: "Python 3.9+ と python-pptx（lxml、Pillow）。構造変更は zipfile と XML 編集。設計値の抽出・検査・描画は pptx-review 同梱のスクリプト。ハーネスが PowerPoint 互換の描画を提供する場合は最終確認に使う。"
metadata:
  version: "1.1.0"
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

### 0. 能力の確認（着手時に1回）

pptx-create の工程0と同じ表で経路を決める。`python-pptx` が無ければ編集できないので、その時点で利用者に伝える。確認した版は報告に残す。

### 1. 把握（`deck/before/`）

- 全ページを描画し（pptx-review の `render_preview.py --sheet`）、一覧を見る。
- テキストを書き出す（pptx-create の `qa.md` と同じ python-pptx の短いスクリプト）。
- **設計値を機械的に抽出する**（目分量で読み取らない）。pptx-review の `extract_style.py` に `--json-out deck/design-lock.json --md-out deck/design-lock.md` を渡す。タイトルの位置・サイズ・色、本文の左端とサイズの語彙、出典の位置、余白、書体、色、そして役割ごとの複製元が出る。手順は `references/match-existing-design.md`。
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

`.ppt`（旧形式）はこのスキルでは扱えない。利用者に PowerPoint で `.pptx` に保存し直してもらう。`.potx` は `.pptx` と同じ手順で扱い、拡張子を保つ。

### 4. 編集

**新しい要素は既存要素の複製から作る。** `design-lock.md` の複製元を `copy.deepcopy` で写し、位置と文言だけ変える。ゼロから `add_textbox` すると PowerPoint の既定書式（Calibri 18pt 黒、行間 1.0）になり、そのページだけ浮く。ページを足すときも、同じ役割の既存ページを複製してから中身を差し替える。詳細は `references/match-existing-design.md`。

- スクリプト（`deck/edit.py`）で行い、手作業の XML 編集は最小限にする。同じ編集を再実行できる状態にしておく。
- 文言を差し替えるときは、元と同程度の長さにする。長くなるなら箱の大きさを見直すか、文を削る。縮小しない。
- テンプレ流し込みで枠が余ったら（4人分の枠に3人）、余った枠は画像・文字ごと削除する。文字だけ消して枠を残さない。
- 箇条書きは1項目1段落。段落をまとめて1つにしない。
- 和文の run には latin と ea の両方に書体を指定する（pptx-create の `typography-ja.md`）。

### 5. 品質確認（`deck/qa/`）

- 再オープン検査: Python で `Presentation("deck/output.pptx")` を開く。例外が出れば壊れている。
- pptx-review があれば `--lock deck/design-lock.json --baseline deck/before/lint.json` を付けて lint を通し、**新しく増えた指摘**を 0 にする。元からある指摘は `inherited` として集計され、報告に書く。
- **統一性の指摘**（`TITLE_POSITION_DRIFT`、`TITLE_SIZE_DRIFT`、`MARGIN_DRIFT`、`BODY_SIZE_DRIFT`、`PALETTE_DRIFT`）が自分の触ったページに出ていたら、必ず直す。これが「修正したページだけデザインが違う」の直接の検出である。
- 描画の一覧（`render_preview.py --sheet`）で、触ったページが他と同じ骨格に見えるかを確かめる。1枚ずつ見ると気づかない。
- 触ったページを描画して1枚ずつ見る。加えて全体を一覧し、他のページとの整合（タイトル位置、余白、フッター）を確認する。高忠実度の描画が使えるときの追加確認は pptx-create の `references/qa.md` ゲート3にある。
- テキストを再度書き出し、変更前との差分が `deck/changes.md` の範囲に収まっていることを確認する。

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
- テーマに無い色・書体を足さない。
- 新しい要素は複製から作る。空の図形に書式を手で設定しない。
- 構造変更（追加・削除・並べ替え）を先に、内容変更を後に。
- 描画画像を見ずに完了と言わない。

## 出力

編集済みの `.pptx`（別名）と、変更一覧、未解決事項、品質確認の証拠を返す。
