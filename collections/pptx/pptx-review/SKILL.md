---
name: pptx-review
description: "PowerPoint（.pptx）を変更せずに監査し、はみ出し・キャンバス外・書体の混在・生成AIらしい装飾や文章・論理構成・デザインロックとの乖離を、機械検査（同梱の pptx_lint.py、標準ライブラリのみ）と描画画像の目視で判定して報告する。「このPPTをレビューして」「AIっぽくないか見て」「納品前にチェック」「デッキを監査」のとき、および pptx-create / pptx-edit の品質確認を別コンテキストで行うときに使う。修正はしない。修正は pptx-edit。"
license: MIT
compatibility: "Python 3.9+（lint は標準ライブラリのみ）。視覚確認に LibreOffice（soffice）と Poppler（pdftoppm）。"
metadata:
  version: "1.0.0"
  publisher: "agent-skills"
---

# pptx-review — 変更せずに監査し、証拠つきで報告する

## 役割

生成者とは別の目で、デッキを「描画された事実」として見る。生成した本人は自分の期待を見てしまうので、可能な限り生成とは別のコンテキスト（サブエージェント）でこのスキルを使う。

このスキルはファイルを変更しない。修正案は書くが、実行は pptx-edit か生成スクリプトの側で行う。

## 入力

- 対象の `.pptx`（必須）
- 密度モード: 講演型（`talk`）か資料型（`doc`）。不明なら `doc`
- あれば `design-lock.json`（書体・色・最小サイズ）と `outline.md`（意図した構成）
- 監査の観点の指定（例: 「AIっぽさだけ」「はみ出しだけ」）。無ければ全項目

## 手順

### 1. 機械検査

```bash
python3 scripts/pptx_lint.py deck.pptx --mode doc [--lock design-lock.json] --json-out qa/lint.json
```

- 標準出力に JSON、標準エラーに要約。`errors` があれば終了コード 1。`--strict` で warning も失敗扱い。
- 編集前のレポートがあれば `--baseline before.json` を付ける。元からあった指摘は `inherited` として除き、新しく増えた指摘だけで判定する。
- `--mode talk` は講演型（注記を含む下限 14pt、全角 250 字）、`--mode doc` は資料型（12pt、400 字）。
- 検査項目と重大度は `references/review-rubric.md`。
- lint は発見器であり、判定器ではない。`passed: true` でも視覚の確認は省略しない。逆に warning は文脈で意図的なものがあり得るので、1件ずつ理由を確認する。

### 2. 描画

```bash
soffice --headless --convert-to pdf --outdir qa deck.pptx
rm -f qa/slide-*.jpg
pdftoppm -jpeg -r 110 qa/deck.pdf qa/slide
```

macOS で `soffice` が無ければ `/Applications/LibreOffice.app/Contents/MacOS/soffice`。和文書体は代替描画になり得るので、ぎりぎりの収まりは「溢れる」と判定する。

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

### 5. 報告

```markdown
# 監査報告: <ファイル名>

- 判定: 合格 / 要修正（重大 N 件、重要 N 件、軽微 N 件）
- lint: errors N / warnings N（qa/lint.json）
- 描画: N 枚を確認（qa/slide-*.jpg）、書体の代替: あり/なし

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
- 「概ね良好」「問題ないと思われる」と書かない。件数と場所で書く。
- 数値・出典の真偽は判定できない。「出典の記載が無い」「数値に裏付けの表示が無い」までを指摘する。

## 出力

監査報告（Markdown）、`qa/lint.json`、描画画像の場所。
