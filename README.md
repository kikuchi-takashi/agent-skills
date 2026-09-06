# Agent Skills Marketplace

Agent Skills 互換のスキルを、コレクション単位で整理・検証・配布するための小さなマーケットプレイス基盤です。

## 方針

- スキル本体は Agent Skills の `SKILL.md` 形式に準拠する
- リポジトリ内は `collections/<category>/<skill-name>/SKILL.md` で整理する
- エージェントへのインストール時は、各スキルをフラットなディレクトリへ配置する
- マーケットプレイスのインデックスはスキルから自動生成する
- 初期版は外部サービスを持たず、ローカルファイルと Git リポジトリで運用する

すべての配布対象は `collections/<category>/<skill-name>/SKILL.md` の2階層です。通常は各スキルを単独でコピーできます。`metadata.bundle` を共有するスキル群は一体の配布物で、メンバーを1つ指定しても全スキルをフラットに配置します。特定クライアント専用の設定ツリーは配布形式に含めません。

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

# bundleメンバーを指定するとbundle全体をインストール
skills install pptx-create --root collections --target .installed/skills

# SDD スキル一式をフラットなスキルディレクトリへインストール
skills install collection:sdd --root collections --target ~/.agents/skills
```

`install` は既存スキルディレクトリを上書きしません。コレクションとbundleの一括導入では全スキルを一時領域へコピーしてから切り替えます。出力先の衝突が1件でもあれば何も変更せず停止し、コピーまたは切り替えでエラーが起きた場合も旧状態へロールバックします。内容を確認して置き換える場合だけ `--force` を指定してください。

## Codex / Claude Code へのインストール（npx）

Node.js/npm が使える環境では、[Vercelの `skills` CLI](https://github.com/vercel-labs/skills)（`npx skills`）からGitHub上のスキルを直接インストールできます。現行の `skills` CLI は Node.js 22.20.0 以上が必要です。SDDコレクションの15スキルをユーザー領域へ入れる場合は、対象エージェントごとに次を実行します。

```bash
# Codex
npx skills add kikuchi-takashi/agent-skills/collections/sdd \
  --skill '*' --agent codex --global --yes

# Claude Code
npx skills add kikuchi-takashi/agent-skills/collections/sdd \
  --skill '*' --agent claude-code --global --yes
```

特定のスキルだけを入れる場合は `--skill '*'` を名前に置き換えます。

```bash
# 例: SDDのレビューだけをCodexへ
npx skills add kikuchi-takashi/agent-skills/collections/sdd \
  --skill sdd-review --agent codex --global --yes
```

プロジェクト内だけで使う場合は `--global` を外します。`--yes` を外すと、導入するスキルと対象エージェントを確認してから実行できます。CLIの既定ではエージェント側から共有コピーへのリンクを作成します。リンクではなく独立コピーにしたい場合は `--copy` を追加してください。配置先は、プロジェクトスコープではCodexが `.agents/skills/`、Claude Codeが `.claude/skills/`、グローバルスコープ（`--global`）ではCodexが `~/.codex/skills/`、Claude Codeが `~/.claude/skills/` です。

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
