# Architecture

## Three layers

### 1. Portable skill package

各スキルは独立したディレクトリで、`SKILL.md` を必須エントリポイントとします。`scripts/`、`references/`、`assets/` は必要な場合だけ同じスキルディレクトリに置きます。

```text
pdf-extract/
├── SKILL.md
├── scripts/
└── references/
```

このレイヤーでは、Agent Skills 標準にない必須ファイルを追加しません。
配布時に参照先が欠けないよう、スキルディレクトリ外への依存とシンボリックリンクは禁止します。

### 2. Repository grouping

マーケットプレイスのソースリポジトリでは、カテゴリーをディレクトリで表現します。

```text
collections/
├── pdf/
│   ├── pdf-extract/
│   └── pdf-edit/
└── pptx/
    ├── pptx-create/
    └── pptx-edit/
```

この階層はリポジトリと CLI が解釈するグルーピングであり、Agent Skills 標準そのものの拡張ではありません。
コレクション名とスキル名は lowercase kebab-case とし、スキル名はリポジトリ全体で一意にします。CLI はこの2階層より深い `SKILL.md` を不正として扱います。

### 3. Client installation

エージェントごとにスキャン方法が異なるため、インストール先ではスキルをフラットにします。

```text
~/.codex/skills/
├── pdf-extract/
└── pdf-edit/
```

シンボリックリンクではなくコピーすることで、クライアントや OS に依存しにくくします。
インストール先はコレクションルート外でなければならず、ソースと重なる配置を拒否します。コレクション一括インストールでは、`--force` なしの場合は全出力先を事前確認してからコピーを始めるため、途中までだけインストールされた状態を避けます。

コレクション一括インストールでも全出力先をコピー前に検査します。`--force` なしでは、どれか1つでも既存スキルと衝突すれば何も書き込みません。

## Index generation

`skills index` は通常配置のスキルを検出し、`marketplace.json` schema 0.1 を生成します。インデックスは編集元ではなく生成物として扱い、`--check` で生成内容との一致を変更なしに確認できます。

`collections/sdd/` も例外ではなく、`sdd` と `sdd-*` の独立したスキルとして索引化します。一般名との衝突を避けるためフェーズスキルを名前空間化し、テンプレートは利用するスキル自身のディレクトリに同梱します。

個別のスキルは `name` で識別し、公開者を含むマーケットプレイス上の ID は将来 `publisher/name` の形式へ拡張できます。

## Versioning

初期版では `SKILL.md` の `metadata.version` を表示用のバージョンとして扱います。再現性が必要になった段階で Git tag、アーカイブの SHA-256、stable/beta チャンネルをインデックスに追加します。

## Security boundary

スキルには命令文だけでなくコードや外部リソースも含められます。検証ではポータブルパッケージ内のシンボリックリンクを拒否し、インストール時のコード実行は行わずコピーだけを担当します。スクリプトや外部素材は実行前レビューとライセンス由来確認が必要です。将来的な公開フローでは、公開者情報、チェックサム、信頼レベルを追加します。

## Repository maintenance

リポジトリ専用の管理スキルは `.agents/skills/` に置き、一般配布用の `collections/` と分離します。管理規約の正本はルート `AGENTS.md`、コントリビューター向け導線は `CONTRIBUTING.md` です。`marketplace.json` は CLI 以外で変更しません。
