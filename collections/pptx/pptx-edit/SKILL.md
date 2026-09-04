---
name: pptx-edit
description: 既存のPowerPointを編集し、レイアウト、文章、図表、ノートを整える。スライドの修正や品質確認に使う。
license: MIT
compatibility: PowerPoint互換の編集・レンダリングツールが実行環境に必要。
metadata:
  version: "0.1.0"
  publisher: "agent-skills"
---

# PPTX Edit

## Workflow

1. 既存スライドの構成、テーマ、レイアウトを把握する。
2. 変更対象と維持すべき要素を分ける。
3. テキスト、図表、画像、ノートを編集する。
4. 全スライドをレンダリングし、重なりやはみ出しを確認する。
5. 変更内容と未解決の問題を報告する。

## Rules

- 既存デザインを変更する場合は、変更範囲を明示する。
- グラフや数値の意味を変えない。
- 元ファイルを上書きせず、別名で保存する。

## Output

編集済みのPPTXファイルと、変更点の一覧を返す。

