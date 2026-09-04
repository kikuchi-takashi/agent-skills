# SDD Agent Skills Collection

仕様策定から計画、実装、レビュー、受け入れ検証までを、承認ゲート付きで進める Agent Skills 互換のスキル群です。特定のエージェント製品や設定ディレクトリには依存しません。

## インストール

マーケットプレイスのルートから、利用するエージェントのスキルディレクトリを `--target` に指定します。

```bash
skills install collection:sdd --root collections --target ~/.agents/skills
```

15個のスキルがフラットにコピーされます。個別に必要な場合は、たとえば `skills install sdd-specify ...` のようにスキル名を指定できます。既存の同名ディレクトリが1つでもあれば、`--force` なしでは何もコピーしません。

## 主な入口

- `sdd`: 通常の開発フローを9フェーズで進行する
- `sdd-auto`: ユーザーがフルオートを明示した場合だけ、承認判定を自動化する
- `sdd-receive-review`: 外部から受け取ったレビュー指摘を検証して修正経路へ戻す
- `sdd-maintain`: このSDDスキル群を契約に沿って変更する
- `sdd-troubleshoot`: SDDスキルの実運用上の不具合を診断する
- `sdd-improver`: SDDスキル群の批評、実戦トライアル、整合性監査を行う

フェーズスキルは `sdd-constitution` → `sdd-specify` → `sdd-clarify` → `sdd-plan` → `sdd-tasks` → `sdd-analyze` → `sdd-implement` → `sdd-review` → `sdd-verify` の順です。フェーズ名として state.md に記録するときは、接頭辞なしの `constitution`、`specify` などを使います。

## 成果物と同梱リソース

実行対象プロジェクトには `docs/constitution.md` と `specs/YYYY-MM-DD-機能名/` 以下の仕様・計画・状態・検証レポートを生成します。テンプレートや実装者プロンプトは、それを利用するスキルのディレクトリに同梱されています。

```text
sdd/spec-lite-template.md
sdd-constitution/template.md
sdd-specify/template.md
sdd-plan/template.md
sdd-tasks/template.md
sdd-implement/implementer-prompt.md
```

`docs/genesis/` と `docs/trials/` は設計経緯を残すリポジトリ内の保守記録であり、個別スキルの配布物には含まれません。過去のクライアント固有パスが記録に残っていても、現在の導入契約ではありません。

## 保守時の検証

このコレクションを変更したら、リポジトリルートの検証に加えて次を実行します。

```bash
collections/sdd/scripts/validate
```
