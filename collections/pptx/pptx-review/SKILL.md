---
name: pptx-review
description: "PowerPoint（.pptx）を変更せずに監査し、はみ出し・キャンバス外・書体の混在・ページ間のデザインの不統一・生成AIらしい装飾や文章・論理構成・デザインロックとの乖離を、機械検査（同梱の pptx_lint.py、標準ライブラリのみ）と描画画像の目視で判定して報告する。「このPPTをレビューして」「AIっぽくないか見て」「納品前にチェック」「デッキを監査」のとき、および pptx-create / pptx-edit の品質確認を別コンテキストで行うときに使う。pptx-design が書いた design-lock.json を渡すと、それを基準に乖離を判定する。修正はしない。修正は pptx-edit、デザイン方針の作り直しは pptx-design。"
license: MIT
compatibility: "Python 3.9+。lint と設計値抽出は標準ライブラリのみ、簡易描画は Pillow。和文の書体ファイルがあれば字形まで描く。ハーネスが PowerPoint 互換の描画を提供する場合は最終確認に併用する。"
metadata:
  version: "1.7.0"
  publisher: "agent-skills"
  bundle: pptx-suite
---

# pptx-review — 変更せずに監査し、証拠つきで報告する

`pptx-design`、`pptx-create`、`pptx-edit`、`pptx-review` は `pptx-suite` として一体配布する。このスキルの `scripts/` は、4スキル共通の抽出・lint・描画基盤と、その回帰検査を持つ。監査の基準になる `design-lock.json` は `pptx-design` の成果物である。4スキルの一部だけを配布・導入しない。

## 役割

生成者とは別の目で、デッキを「描画された事実」として見る。生成した本人は自分の期待を見てしまうので、可能な限り生成とは別のコンテキスト（サブエージェント）でこのスキルを使う。

このスキルはファイルを変更しない。修正案は書くが、実行は pptx-edit か生成スクリプトの側で行う。

## 入力

- 対象の `.pptx`（必須）
- 密度モード: 講演型（`talk`）か資料型（`doc`）。不明なら `doc`
- あれば `design-lock.json`（書体・役割付きpalette・追加許可色・最小サイズ）、`outline.md`（意図した構成）、`implementation-spec.json`（ページの実装契約）
- 監査の観点の指定（例: 「AIっぽさだけ」「はみ出しだけ」）。無ければ全項目
- 編集監査では、編集前の `.pptx` と、意図したレイアウト変更を理由つきで列挙したallow JSON

## 手順

### 0. 設計値の抽出（既存デッキの監査、または編集の前）

```python
import os, subprocess, sys
os.makedirs("qa", exist_ok=True)
subprocess.run([sys.executable, "scripts/extract_style.py", "deck.pptx",
                "--json-out", "qa/design-lock.json", "--md-out", "qa/design-lock.md"], check=True)
```

タイトルの位置・サイズ・色、本文の左端とサイズ、出典の位置、余白、書体、色、複製元を実測して書き出す。ロックが与えられていない監査では、これを「そのデッキ自身の正」として使い、次の機械検査に `--lock qa/design-lock.json` で渡す。

### 1. 機械検査

```python
import subprocess, sys
result = subprocess.run([sys.executable, "scripts/pptx_lint.py", "deck.pptx", "--mode", "doc",
                         "--lock", "design-lock.json", "--json-out", "qa/lint.json"])
if result.returncode >= 2:
    raise RuntimeError("pptx_lint.py が異常終了した")
```

- 標準出力に JSON、標準エラーに要約。`errors` があれば終了コード 1。`--strict` で warning も失敗扱い。
- 編集前のレポートがあれば `--baseline before.json` を付ける。元からあった指摘は `inherited` として除き、新しく増えた指摘だけで判定する。
- `--mode talk` は講演型（注記を含む下限 14pt、全角 250 字）、`--mode doc` は資料型（12pt、400 字）。
- Pillow と和文の書体があれば折り返しを実測し（要約に `measured with ...`）、無ければ概算（`estimated`）。書体は `--font` で指定できる。
- `design-lock.json` の `allow` に登録された指摘は「意図的」として判定から外れる。登録の理由が妥当かは目視で確認する。
- 検査項目と重大度は `references/review-rubric.md`。
- 4枚以上のデッキでは、ページ間の統一性（タイトルの位置と大きさ、本文の左端、本文サイズ、色）を多数派と比べ、外れたページに `*_DRIFT` を出す。`--no-consistency` で切れる。
- lint は発見器であり、判定器ではない。`passed: true` でも視覚の確認は省略しない。逆に warning は文脈で意図的なものがあり得るので、1件ずつ理由を確認する。

編集前のPPTXがある場合は、lintのbaselineとは別にレイアウト比較を行う。baselineは既存指摘を除外する機能で、図形が動いた・書式構造が変わったこと自体は比較しない。

```python
subprocess.run([sys.executable, "scripts/layout_guard.py", "before.pptx", "after.pptx",
                "--strict", "--json-out", "qa/layout-guard.json"])
```

意図した座標変更、図形追加・削除などがある場合だけ、`--allow layout-allow.json` でコード・ページ・図形・理由を登録する。理由のないallowは無効。`EDIT_AUTOFIT_REFLOW`、theme/layout変更、共有された図表部品の変更は、見た目がその場で正常でも別環境や別ページを壊すため解消する。原因とコードの対応、簡易描画で確定できない範囲は `references/layout-stability.md` を読む。

### 2. 描画

```python
import subprocess, sys
subprocess.run([sys.executable, "scripts/render_preview.py", "deck.pptx",
                "--out", "qa/preview", "--sheet"], check=True)
# 枚数が多ければ --slides 1-6 のように分ける。書体ファイルがあれば --font path.ttf
```

`scripts/render_preview.py` は Pillow だけで描く簡易描画で、位置・折り返し・重なり・余白・色の配分を見るためのもの。PowerPoint と同じではない。

描画確認は Pillow による簡易描画で行い、外部の変換ツールには依存しない。**ハーネス自身が PowerPoint を画像にする手段を持つ場合だけ**、簡易描画で位置と構造を確認したあとにもう一度見比べ、字形・影・図表の見え方を見る。無ければ簡易描画までを確認範囲として報告する。

- はみ出した箱は赤枠で示され、標準出力にページと図形名が出る。
- 和文の書体が無い環境では和文が文字幅どおりの灰色バーになる。レイアウトの確認には足りるが、字形・禁則・記号の欠けは判定できない。報告に「和文は幅のみ確認」と書く。
- 図表は値と色を簡略に描く。影・グラデーション・効果は描かない。
- ぎりぎりの収まりは「溢れる」と判定する。

### 3. ページごとの目視

**1枚ずつ画像を開いて見る。** 縮小一覧で済ませない。`references/review-rubric.md` の順（はみ出し → 重なり → 余白 → 整列 → コントラスト → 兆候 → 文章 → 論理）で見る。

ページ数が多いときは、1ページ分の画像と、その lint 結果だけを渡したサブエージェントに判定させ、判定だけを受け取る。画像を自分のコンテキストに溜めない。

### 4. デッキ全体の目視

縮小一覧で、ページをまたいだ整合を見る。

- タイトルの位置・大きさ、余白、フッターの高さが一定か
- 同じレイアウトの連続、同じ塊の形式の比率
- 濃い面のページの回数と間隔
- 強調色が特定のページに偏っていないか、逆に毎ページ同じ場所に出ていないか
- タイトルだけを順に読み、論旨が通るか（ゴーストデッキテスト）
- `outline.md` があれば、意図した構成との差

### 4a. 目視は定型で依頼する

生成・編集を行った文脈から視覚QAを依頼するときは、`references/visual-qa-prompt.md` の定型をそのまま使う。**即興のプロンプトは検収の姿勢になり、「特に問題ありません」で止まる。** 直近に見つかった不具合（描画の意図しない灰色枠、写真のEXIF横倒し、行送りの倍率指定）は、いずれも lint の41コードのどれにも該当せず、人が画像を開いて気づいたものである。

### 4b. 設計の判定（lint では出ない）

lint と描画がすべて通っても、**署名が無く形式を選んでいないデッキ**は「無難だが誰が作っても同じ」に見える。ここまでの検査はすべて欠陥を取り除くもので、欠陥の除去は品質を足さない。縮小一覧を見ながら次の3つを判定し、該当したら指摘として書く。判定の根拠は `pptx-design` の `design-principles.md`（署名は5節、形式の選択は7節、主役は2節）にある。

| 見るもの | 該当するとき | 指摘の書き方 |
|---|---|---|
| **署名** | このデッキを思い出す手がかりが無い。または、あるが色帯・飾り線・アイコン入りの丸・角丸カードの反復のような、どのデッキにも付く既製の見た目 | 主題のどの素材から署名を作れるかを1つ提案する。全ページの静かな標識・幾何そのものの1枚・初出の凡例の3層で示す |
| **形式の選択** | 内容が違うのに同じ形が繰り返されている（`FORM_FAMILY_MONOTONE`・`LAYOUT_MONOTONE` は手がかり。出ていなくても該当しうる） | そのページの内容が取りうる別の形式を1つ挙げ、どちらが強いかの決め手を書く |
| **主役** | 横並びの N 個が等分・同色・同サイズで、どれが主役か言えない（`EQUAL_EMPHASIS`・`CARD_ROW` は手がかり） | 主役にすべき1つを指名する。指名できないなら、横並びではなく表か箇条書きにするよう書く |

**この3つで「手組みに見えるから」を理由に減点しない。** 主題から作られた不揃いな図こそが、そのデッキをテンプレートでないものにしている。咎めるのは、意図が読み取れない不揃いだけである。

### 4c. 証跡の作成と検査

`implementation-spec.json` がある作成・編集ワークフローでは、描画後に `scripts/qa_evidence.py init` を実行する。実物から**設計〜実装対応表**と未記入のQA証跡を作り、形式的QA、デザイン的QA、一覧目視、各ページの実装一致・個別目視を別々に記入する。

```python
subprocess.run([sys.executable, "scripts/qa_evidence.py", "init", "deck.pptx",
                "--spec", "implementation-spec.json", "--preview-prefix", "qa/preview",
                "--json-out", "qa/qa-evidence.json",
                "--map-out", "qa/design-implementation-map.md"], check=True)
# 根拠を記入した後
subprocess.run([sys.executable, "scripts/qa_evidence.py", "check",
                "qa/qa-evidence.json"], check=True)
```

`check` は個別previewが全ページ分かつ固有であること、一覧previewがあること、各判定に根拠があることを確かめる。PPTXと画像のSHA-256も照合し、証跡作成後に差し替わっていれば再確認を求める。画像の存在を目視の代用にはしない。仕様書がない外部デッキの単独監査では、実装一致と対応表を「対象外」と報告し、形式的QAとデザイン的QAの分離、個別・一覧の目視証跡は維持する。

### 5. 報告

```markdown
# 監査報告: <ファイル名>

- 形式的QA: 合格 / 要修正 / 未確認（根拠: ...）
- デザイン的QA: 合格 / 要修正 / 未確認（根拠: ...）
- 総合判定: 合格 / 要修正（重大 N 件、重要 N 件、軽微 N 件）
- 設計の判定: 署名 あり/無し・既製、形式の選択 あり/繰り返し、主役 あり/不在
- 実行した検査: lint（errors N / warnings N、qa/lint.json）、簡易描画 N 枚、ハーネス側の描画 あり/なし
- 使用した書体と、描画で代替が起きたかどうか
- 再現条件: 使用したライブラリの版

## 指摘
| # | ページ | 図形 | 重大度 | 症状 | 修正案 |
|---|---|---|---|---|---|

## デッキ全体
- 構成: ...
- 整合: ...
- 生成AIらしさ: ...

## 意図的と判断して残した warning
| コード | ページ | 理由 |
```

重大度の定義は `references/review-rubric.md`。**重大が1件でもあれば「合格」と書かない。** lint の JSON と描画画像を見ていない項目については「未確認」と書き、確認したふりをしない。

## 絶対規則

- ファイルを変更しない。
- lint の JSON と全ページの描画画像なしに判定を出さない。
- 描画に使えなかったもの（書体が無い、画像形式が読めない）は「未確認」として書く。
- 「概ね良好」「問題ないと思われる」と書かない。件数と場所で書く。
- 数値・出典の真偽は判定できない。「出典の記載が無い」「数値に裏付けの表示が無い」までを指摘する。

## 出力

監査報告（Markdown）、`qa/lint.json`、全ページの個別描画画像、一覧画像。作成・編集ワークフローでは `qa/qa-evidence.json` と設計〜実装対応表も返す。

## bundle保守

- `scripts/eval-checks.py`: lint・編集前後比較・実装仕様・QA証跡の回帰検査
- `scripts/audit-consistency.py`: 兄弟スキルを含む文書・骨格・スクリプトの整合監査
- `scripts/visual-baseline.py`: `scripts/baseline/shapes.png` を使う描画像の回帰検査

生成骨格そのものの比較測定は、兄弟スキル `pptx-create/scripts/measure-skeleton.py` に置く。
