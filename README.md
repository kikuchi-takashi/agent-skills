# Agent Skills Marketplace

Agent Skills 互換のスキルを、コレクション単位で整理・検証・配布するための小さなマーケットプレイス基盤です。

## 方針

- スキル本体は Agent Skills の `SKILL.md` 形式に準拠する
- リポジトリ内は `collections/<category>/<skill-name>/SKILL.md` で整理する
- エージェントへのインストール時は、各スキルをフラットなディレクトリへ配置する
- マーケットプレイスのインデックスはスキルから自動生成する
- 初期版は外部サービスを持たず、ローカルファイルと Git リポジトリで運用する

## セットアップ

Python 3.9 以上で実行できます。依存ライブラリはありません。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## CLI

```bash
# スキルを再帰的に検出
skills discover --root collections

# スキルを検証
skills validate --root collections

# マーケットプレイスのインデックスを生成
skills index --root collections --output marketplace.json

# 個別スキルをインストール
skills install pdf-extract --root collections --target .installed/skills

# コレクション内のスキルをまとめてインストール
skills install collection:pdf --root collections --target .installed/skills
```

`install` は既存ディレクトリを上書きしません。意図的に上書きする場合だけ `--force` を指定してください。

## スキルの追加

```text
collections/
└── my-category/
    └── my-skill/
        └── SKILL.md
```

`SKILL.md` の最低限の形式は次のとおりです。

```markdown
---
name: my-skill
description: 何を行うスキルか、いつ使うかを説明する
---

# My Skill

スキルの指示本文。
```

詳細な設計は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) を参照してください。
