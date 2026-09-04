---
name: pptx-create
description: 要件や原稿からPowerPointプレゼンテーションを設計・作成する。スライド構成、レイアウト、発表者ノートが必要なときに使う。
license: MIT
compatibility: PowerPoint互換の生成・検証ツールが実行環境に必要。
metadata:
  version: "0.1.0"
  publisher: "agent-skills"
---

# PPTX Create

## Workflow

1. 対象 audience、目的、発表時間、必要な出力形式を確認する。
2. メッセージを整理し、スライドごとの役割を決める。
3. タイトル、本文、図表の視線誘導が一貫するレイアウトを選ぶ。
4. プレゼンテーションを生成し、全スライドをレンダリングして確認する。
5. 内容の重複、文字のはみ出し、読みにくい配色を修正する。

## Rules

- 1枚のスライドに複数の主張を詰め込みすぎない。
- 数値や引用元を明記する。
- 生成後は必ず視覚的な検証を行う。

## Output

編集可能なPPTXファイルと、スライド構成の概要を返す。

