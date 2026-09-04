# Agent Skills Marketplace

Agent Skills 互換のスキルを、コレクション単位で整理・検証・配布するための小さなマーケットプレイス基盤です。

## 方針

- スキル本体は Agent Skills の `SKILL.md` 形式に準拠する
- リポジトリ内は `collections/<category>/<skill-name>/SKILL.md` で整理する
- エージェントへのインストール時は、各スキルをフラットなディレクトリへ配置する
- マーケットプレイスのインデックスはスキルから自動生成する
- 初期版は外部サービスを持たず、ローカルファイルと Git リポジトリで運用する

すべての配布対象は `collections/<category>/<skill-name>/SKILL.md` の2階層です。各スキルは単独でコピーでき、コレクション一括インストールでも同じスキル群をフラットに配置します。特定クライアント専用の設定ツリーは配布形式に含めません。

## セットアップ

Python 3.9 以上で実行できます。依存ライブラリはありません。

```bash
python3 -m venv .venv
source .venv/bin/activate
export PYTHONPATH="$PWD/src"
```

これで `python -m agent_skills_marketplace ...` とテストを追加依存なしで実行できます。`skills` コマンド名を使う場合は、PEP 660 対応の packaging tools がある環境で `python -m pip install -e .` を実行してください。

## CLI

```bash
# 配布対象スキルを検出
skills discover --root collections

# スキルを検証
skills validate --root collections

# マーケットプレイスのインデックスを生成
skills index --root collections --output marketplace.json

# 生成済みインデックスが最新か、書き換えずに確認
skills index --root collections --output marketplace.json --check

# 個別スキルをインストール
skills install pdf-extract --root collections --target .installed/skills

# コレクション内のスキルをまとめてインストール
skills install collection:pdf --root collections --target .installed/skills

# SDD スキル一式をフラットなスキルディレクトリへインストール
skills install collection:sdd --root collections --target ~/.agents/skills
```

`install` は既存スキルディレクトリを上書きしません。コレクション一括導入でも全出力先を先に検査し、衝突が1件でもあれば何もコピーせず停止します。内容を確認して置き換える場合だけ `--force` を指定してください。

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
コントリビューションと必須検証は [CONTRIBUTING.md](CONTRIBUTING.md) および [AGENTS.md](AGENTS.md) を参照してください。
