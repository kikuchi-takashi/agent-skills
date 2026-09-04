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

### 3. Client installation

エージェントごとにスキャン方法が異なるため、インストール先ではスキルをフラットにします。

```text
~/.codex/skills/
├── pdf-extract/
└── pdf-edit/
```

シンボリックリンクではなくコピーすることで、クライアントや OS に依存しにくくします。

## Index generation

`skills index` は `collections/**/SKILL.md` を再帰的に検出し、カテゴリーとスキルのメタデータから `marketplace.json` を生成します。インデックスは編集元ではなく生成物として扱います。

個別のスキルは `name` で識別し、公開者を含むマーケットプレイス上の ID は将来 `publisher/name` の形式へ拡張できます。

## Versioning

初期版では `SKILL.md` の `metadata.version` を表示用のバージョンとして扱います。再現性が必要になった段階で Git tag、アーカイブの SHA-256、stable/beta チャンネルをインデックスに追加します。

## Security boundary

スキルには命令文だけでなくコードや外部リソースも含められます。将来的な公開フローでは、検証、公開者情報、ライセンス、チェックサム、信頼レベルを追加します。インストール時のコード実行は行わず、スキルのコピーだけを担当します。

