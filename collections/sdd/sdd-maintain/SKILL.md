---
name: sdd-maintain
description: "SDD スキルセット自体を、共有契約を壊さず追加・更新・整理する。日本語トリガー例:「SDDスキルを改善して」「新しいSDDスキルを追加して」「SDDのテンプレートを変更して」。実運用上の不具合報告は sdd-troubleshoot、評価だけなら sdd-improver を使う"
license: MIT
metadata:
  version: "2.0.0"
  publisher: "agent-skills"
---

# sdd-maintain — SDDスキルセットの保守

SDD スキル群は個別配布できるが、state.md とフェーズ遷移の契約を共有する。変更前に対象スキルだけでなく、次の契約表にある追随先を読む。

## 壊してはいけない契約（契約表）

| 契約 | 正 | 主な追随先 |
|---|---|---|
| state.md の列挙値・履歴・進捗 | `sdd/SKILL.md` | 全フェーズスキル、sdd-auto、sdd-receive-review |
| フェーズ順序と数（現在9） | `sdd` のフェーズ表 | sdd の description、README、sdd-auto、この表 |
| 承認・差し戻しの記録責務 | `sdd` の起動手順6 | sdd-verify、sdd-receive-review、sdd-auto |
| 小規模バイパス | `sdd` のバイパス節 | sdd-implement、sdd-review、sdd-verify、sdd-auto、sdd-receive-review |
| 実装者の報告値と書式 | `sdd-implement/implementer-prompt.md` | sdd-implement |
| review の2モードと判定値 | `sdd-review` | sdd-implement、sdd-verify、sdd-auto、sdd |
| テンプレート | 各利用スキル配下のファイル | 利用元 SKILL.md、README のリソース一覧 |
| 保守ログ | `docs/maintain-log.md` | sdd-maintain、sdd-troubleshoot |
| 配布境界 | コレクションの `AGENTS.md` | README、scripts/validate、マーケットプレイスの索引とテスト |

スキル識別子は `sdd` または `sdd-*`、state.md のフェーズ値は接頭辞なしとする。frontmatter は少なくともディレクトリと一致する `name`、何をいつ使うかを絞った `description`、`license: MIT` を持ち、配布版では `metadata.version` と `metadata.publisher` も記録する。本文とリソース参照は、そのスキル単体をコピーしても成立させる。

## 変更の種類別チェックリスト

### A. 既存スキルの修正

1. 契約表のどの行に触れるかを特定する。
2. 正と追随先を同じ変更で更新する。
3. 無関係な改善、権限拡張、クライアント固有 API への依存を混ぜない。

### B. フェーズの追加・削除

1. `sdd` のフェーズ表、description、state.md 列挙値を更新する。
2. `sdd-auto` の審査観点、隣接フェーズの受け渡し、README、この契約表を更新する。
3. `scripts/validate` の期待値を更新し、正例と近接する負例でトリガーを確認する。

### C. 独立スキルの追加

先に「そのスキルがないため起きた失敗」を1件示す。採用・却下のどちらでも `docs/maintain-log.md` に `[新スキル採用]` または `[新スキル却下]`、日付、対象、理由を1行記録する。非フェーズスキルは sdd から自動で呼ばれないことを description で明示する。

### D. テンプレートの変更

項目を追加・削除したら、生成側だけでなく sdd-analyze、sdd-auto、sdd-verify など検算側への影響を確認する。規則本文をテンプレートと SKILL.md に二重管理しない。

## 改善ループの回し方

`sdd-improver` にモード（批評・実戦・監査）と修正権限（報告のみ・反映まで）を渡し、1周ずつ実行する。独立した作業担当を利用できる場合は評価を委ねる。利用できない場合も現在のセッションで実行できるが、自己評価であることを結果に明記する。

- 批評: 参考実装や過去の摩擦ログと比較し、判断を誤らせる欠け・矛盾・水膨れを探す。
- 実戦: 一時ディレクトリへ必要なスキルをコピーし、小さな題材を実走して摩擦ログを残す。
- 監査: 契約表と全現物を双方向に照合し、古い参照、継ぎ接ぎ矛盾、配布不能な依存を探す。

## 変更後の必須検証（コミット前）

```bash
collections/sdd/scripts/validate
python -m agent_skills_marketplace validate --root collections
python -m agent_skills_marketplace index --root collections --output marketplace.json
```

description を変えた場合は、正例3件以上と他スキルが選ばれるべき負例を確認する。最後に旧名、削除したパス、クライアント固有設定への現行文書からの参照を検索する。
