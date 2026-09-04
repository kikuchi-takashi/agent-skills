---
name: pdf-edit
description: PDFの結合、分割、ページ並べ替え、回転、削除を行う。複数PDFの整理や納品用PDFの作成に使う。
license: MIT
compatibility: PDF編集ツールまたはPythonのPDFライブラリが実行環境に必要。
metadata:
  version: "0.1.0"
  publisher: "agent-skills"
---

# PDF Edit

## Workflow

1. 入力ファイルと希望するページ操作を確認する。
2. 元ファイルを変更せず、作業用の出力先を用意する。
3. ページ順、回転、結合、分割を指定どおりに適用する。
4. 出力PDFが開けることとページ数を検証する。

## Rules

- 元のPDFを上書きしない。
- ページ範囲は1始まりとして明示する。
- パスワード保護や電子署名への影響を報告する。

## Output

編集後のPDFと、適用したページ操作の簡潔な記録を返す。

