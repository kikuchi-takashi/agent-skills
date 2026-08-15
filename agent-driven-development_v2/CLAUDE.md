# agent-driven-development_v2 — 仕様駆動開発（SDD）スキルセット

「〜を作って」と言うだけで、仕様→計画→実装→検証をユーザー承認ゲート付きで進める
汎用ワークフロー。superpowers（プロセス規律）と spec-kit（フェーズ構造）を参考に構築。

## 使い方

- **新規開発**: 「TODO アプリを作って」→ `sdd` が自動発火し、フェーズを順に進める（各フェーズはユーザー承認制）
- **フルオート**: 「フルオートで〜を作って」と明示指定 → `auto` が承認を審査エージェントに代行させ、統合手前まで無人で完走（破壊的操作・仕様の根本的曖昧さ・ループ上限では停止）
- **再開**: 「続きから」「開発を再開して」→ `specs/*/state.md` から現在フェーズに復帰
- **小規模修正**: 1〜2ファイル（テスト込み）の修正は spec-lite によるバイパスルート（判定は sdd が行う）
- 各フェーズスキル（`specify` 等）は単体でも呼び出し可
- **受領レビュー対応**: 「PR コメントを反映して」「レビュー指摘に対応して」→ `receive-review` が指摘を検証・分類し、完了済み機能を再オープンして修正ルートへ
- **スキルセット自体の変更**: 「スキルを改善して」「新スキルを追加して」→ `maintain` が契約（state.md 書式・フェーズ列挙・description 規約）を守らせる
- **不具合報告からの改善**: 「〇〇スキルがうまく動かなかった」→ `troubleshoot` が証拠を確認し原因を切り分け、承認を得た上で専用ブランチに修正を積んで PR を作成する

## フェーズ

```
constitution → specify → clarify → plan → tasks → analyze → implement → review → verify
（原則策定）   （仕様）  （曖昧解消）（技術計画）（分解） （整合検証） （実装） （コードレビュー）（受入検証）
```

各フェーズの完了にはユーザー承認が必須（clarify のみ曖昧箇所ゼロなら自動通過）。
実装はサブエージェント駆動＋TDD、小タスクは本体で直接。

## 成果物とテンプレート

テンプレートは各フェーズスキルのディレクトリ内に同梱（スキルごと他プロジェクトへコピーすればそのまま使える）。

| 成果物 | 生成フェーズ | テンプレート |
|---|---|---|
| `docs/constitution.md` | constitution（初回のみ） | `.claude/skills/constitution/template.md` |
| `specs/YYYY-MM-DD-機能名/spec.md` | specify | `.claude/skills/specify/template.md` |
| `specs/YYYY-MM-DD-機能名/clarifications.md` | clarify | （spec の Q&A 記録。書式は clarify 参照） |
| `specs/YYYY-MM-DD-機能名/plan.md` | plan | `.claude/skills/plan/template.md` |
| `specs/YYYY-MM-DD-機能名/tasks.md` | tasks | `.claude/skills/tasks/template.md` |
| `specs/YYYY-MM-DD-機能名/analyze-report.md` | analyze | （書式は analyze 参照。state.md 復旧材料） |
| `specs/YYYY-MM-DD-機能名/review-report.md` | review（フィーチャーレビューのみ） | （書式は review 参照。state.md 復旧材料） |
| `specs/YYYY-MM-DD-機能名/spec-lite.md` | バイパス時のみ | `.claude/skills/sdd/spec-lite-template.md` |
| `specs/YYYY-MM-DD-機能名/state.md` | sdd が管理 | 書式は `.claude/skills/sdd/SKILL.md` が正 |

## 構成

```
.claude/skills/   sdd / auto（オーケストレーター）＋9フェーズスキル（テンプレート同梱）
                  ＋receive-review（受領レビュー対応）＋maintain（メンテ用）
                  ＋troubleshoot（不具合報告からの改善＋PR作成）
.claude/agents/   sdd-improver（評価・改善ループ専門エージェント。maintain / troubleshoot から派遣）
specs/            機能ごとの成果物（YYYY-MM-DD-機能名）
docs/             constitution.md（初回に生成）・maintain-log.md（却下記録: 新スキル却下／不具合却下。初回追記時に生成）
```
