---
name: pdf-extract
description: PDFからテキスト、表、メタデータを抽出する。PDFの内容確認、検索可能なテキスト化、構造化データへの変換を行うときに使う。
license: MIT
compatibility: PDF処理ツールまたはPythonのPDFライブラリが実行環境に必要。
metadata:
  version: "0.1.0"
  publisher: "agent-skills"
---

# PDF Extract

## Workflow

1. 入力PDFのページ数、暗号化状態、読み取り可能性を確認する。
2. テキスト抽出を実行し、ページ番号を保持する。
3. 表が含まれる場合は、セル構造を確認してから構造化する。
4. 抽出結果の欠落や文字化けを確認し、必要なら別の抽出方法を試す。

## Rules

- ページ番号と抽出元を結果に残す。
- 抽出できなかった箇所を推測で補完しない。
- スキャンPDFではOCRが必要な可能性を明記する。

## Output

テキスト、表、メタデータを、利用者が再利用できる形式で返す。

