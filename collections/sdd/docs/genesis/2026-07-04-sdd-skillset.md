# SDD スキルセット（agent-driven-development_v2）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仕様駆動開発の9スキル（sdd オーケストレーター＋8フェーズ）を `agent-driven-development_v2/.claude/skills/` に新規作成する。

**Architecture:** オーケストレーター（sdd）が `specs/NNN-機能名/state.md` でフェーズ状態を永続化し、各フェーズを個別スキルとして Skill ツールで呼び出す。実装フェーズはサブエージェント駆動＋TDD。全スキル日本語本文。

**Tech Stack:** Claude Code スキル（SKILL.md ＋ YAML frontmatter）のみ。外部依存なし。

## Global Constraints

- ベースディレクトリ: `/Users/takashi-kikuchi/Desktop/Projects/claude/design/agent-driven-development_v2`（design リポジトリ内の新規ディレクトリ。以下、相対パスはここ基準）
- 設計書: `agent-driven-development/docs/superpowers/specs/2026-07-04-sdd-skillset-design.md` が正。矛盾したら設計書に従う
- スキル本文は日本語。frontmatter は `name:`（kebab-case）と `description:`（二重引用符付き1行、日本語トリガー例を含む）の2キーのみ
- 各 SKILL.md は 500 行以内
- 各フェーズスキルの description 末尾に必ず「通常は sdd オーケストレーター経由で呼ばれる。単体でも呼び出し可」を含める（二重発火防止）
- v1（`agent-driven-development/`）のファイルには一切触れない
- コミットは design リポジトリ（`/Users/takashi-kikuchi/Desktop/Projects/claude/design`）に対して行う

**各タスク共通の検証コマンド**（`<dir>` をスキル名に置換）:

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design/agent-driven-development_v2 && \
head -1 .claude/skills/<dir>/SKILL.md | grep -qx -- '---' && \
grep -q '^name: <dir>$' .claude/skills/<dir>/SKILL.md && \
grep -q '^description: "' .claude/skills/<dir>/SKILL.md && \
awk '/^---$/{c++} END{exit c<2}' .claude/skills/<dir>/SKILL.md && echo OK
```

Expected: `OK`

---

### Task 1: 骨格＋sdd オーケストレーター

**Files:**
- Create: `.claude/skills/sdd/SKILL.md`
- Create: `specs/.gitkeep`（空ファイル）

**Interfaces:**
- Produces: state.md フォーマット（全後続スキルが読み書きする）、フェーズ遷移順序 `constitution→specify→clarify→plan→tasks→analyze→implement→verify`、バイパス基準。後続タスクのスキルはこの SKILL.md の「state.md フォーマット」節と同一の書式を前提とする

- [ ] **Step 1: ディレクトリと SKILL.md を作成**

`.claude/skills/sdd/SKILL.md` を以下の内容で作成:

````markdown
---
name: sdd
description: "仕様駆動開発のオーケストレーター。新しい機能・アプリ・スクリプトの開発依頼すべてで最初に使う。仕様→明確化→計画→タスク分解→整合性検証→実装→検証の8フェーズをゲート付きで進行管理する。日本語トリガー例:「〜を作って」「機能を追加して」「〜を実装したい」「開発を再開して」「続きから」"
---

# sdd — 仕様駆動開発オーケストレーター

開発依頼を受けたら、コードを1行も書く前にこのワークフローで仕様から始める。

<HARD-GATE>
承認記録のないフェーズを飛ばして先のフェーズスキルを呼ぶことを禁止する。
フェーズ成果物を作ったら必ず要約を提示し、ユーザー承認を得てから state.md に記録して次へ進む。
</HARD-GATE>

## 起動時の手順（必ずこの順）

1. **再開チェック**: `specs/*/state.md` を走査する。「現在フェーズ」が「完了」以外の機能があれば一覧を提示し、再開するか新規かをユーザーに確認する。再開なら該当フェーズのスキルを呼ぶ。
2. **constitution チェック**: `docs/constitution.md` がなければ、先に sdd-constitution スキルを呼ぶ。
3. **ルート判定**: 下記のバイパス基準で フル / バイパス を判定し、ユーザーに判定結果と理由を伝える。
4. **採番**: `specs/` 直下の既存 NNN の最大値+1 で `specs/NNN-機能名/`（機能名は kebab-case）を作成し、state.md を初期化する。
5. **フェーズ実行**: 現在フェーズに対応するスキルを Skill ツールで呼ぶ。フェーズ完了→承認→state.md 更新→次フェーズ、を繰り返す。

## フェーズ順序と対応スキル

| # | フェーズ | スキル | 承認 |
|---|---------|--------|------|
| 1 | constitution | sdd-constitution | 必須（プロジェクト初回のみ） |
| 2 | specify | sdd-specify | 必須 |
| 3 | clarify | sdd-clarify | 曖昧箇所ゼロなら自動通過可（通過も state.md に記録） |
| 4 | plan | sdd-plan | 必須 |
| 5 | tasks | sdd-tasks | 必須 |
| 6 | analyze | sdd-analyze | 必須（重大問題ゼロの報告に対する確認） |
| 7 | implement | sdd-implement | タスクごとに検証、フェーズ完了時に承認 |
| 8 | verify | sdd-verify | 必須（証拠付き完了報告） |

## 小規模バイパス基準（すべて満たす場合のみ）

- 変更が1〜2ファイルに収まる見込み
- 既存 spec.md の受け入れ基準に影響しない
- 新しい依存関係・データモデル変更を伴わない

該当する場合: specify/plan/tasks を `spec-lite.md`（①変更内容 ②受け入れ基準 ③検証コマンド の3節）1枚にまとめ、ユーザー承認後 implement → verify へ直行する。バイパス採用と理由を state.md に記録する。

## state.md フォーマット（全フェーズスキル共通の正）

```markdown
# NNN-機能名 進行状態
- 機能名: <日本語名>
- ルート: フル | バイパス（理由: 〜）
- 現在フェーズ: constitution | specify | clarify | plan | tasks | analyze | implement | verify | 完了
## 承認履歴
- YYYY-MM-DD HH:MM <フェーズ名> 承認（ユーザー）
## フェーズ内進捗（implement 中のみ）
- [ ] T1: <タスク名>（subagent | 直接）
## 差し戻し履歴
- YYYY-MM-DD HH:MM <戻したフェーズ> 理由: 〜
```

## 差し戻し

どのフェーズからでも前フェーズへ戻せる。戻す際は理由を差し戻し履歴に記録し、下流成果物（例: spec 変更時の plan/tasks）の更新要否をユーザーに明示する。

## state.md が壊れている・矛盾している場合

成果物ファイルの存在（spec.md / plan.md / tasks.md）から状態を推定し、推定結果をユーザーに確認してから state.md を書き直す。黙って上書きしない。
````

- [ ] **Step 2: specs ディレクトリを作成**

```bash
mkdir -p /Users/takashi-kikuchi/Desktop/Projects/claude/design/agent-driven-development_v2/specs && \
touch /Users/takashi-kikuchi/Desktop/Projects/claude/design/agent-driven-development_v2/specs/.gitkeep
```

- [ ] **Step 3: 検証**

共通検証コマンド（`<dir>` = `sdd`）を実行。Expected: `OK`

- [ ] **Step 4: コミット**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2 && \
git commit -m "feat(sdd): オーケストレーター sdd スキルと骨格を追加"
```

---

### Task 2: sdd-constitution

**Files:**
- Create: `.claude/skills/sdd-constitution/SKILL.md`

**Interfaces:**
- Produces: `docs/constitution.md`（節構成: 技術スタック方針／品質基準／禁止事項／レビュー方針）。sdd-plan・sdd-analyze・sdd-implement がこの節構成を参照する

- [ ] **Step 1: SKILL.md を作成**

````markdown
---
name: sdd-constitution
description: "プロジェクトの開発原則（技術スタック方針・品質基準・禁止事項・レビュー方針）を対話で確定し docs/constitution.md に書く。プロジェクト初回のみ。日本語トリガー例:「プロジェクト原則を決めて」「開発ルールを作って」。通常は sdd オーケストレーター経由で呼ばれる。単体でも呼び出し可"
---

# sdd-constitution — プロジェクト原則の策定

以後の plan / analyze / implement すべてが参照する「憲法」を作る。

## 手順

1. **既存情報を先に読む**: CLAUDE.md・README・リンター設定・既存コードの規約を確認し、矛盾しない案を作る。既存プロジェクトの慣習は原則より優先。
2. **1問ずつ確認**: 以下4節について、提案→ユーザー確認の順で1節ずつ確定する（選択式優先）。
   - 技術スタック方針（言語・フレームワーク・依存追加の基準）
   - 品質基準（テスト必須度、カバレッジ観、型チェック）
   - 禁止事項（例: 秘密情報のハードコード、テストなしのマージ）
   - レビュー方針（フェーズ承認は誰が・タスク完了の確認方法）
3. **書き出し**: `docs/constitution.md` に上記4節の見出しで書く。各項目は1行の宣言文＋必要なら理由1行。10〜30行に収める。
4. **承認**: 全文を提示して承認を得る。sdd 経由の場合、承認を state.md に記録するのは sdd の責務。

## 原則

- 憲法は「守れる最小セット」にする。理想の羅列は形骸化する（YAGNI）
- 既に決まっていることを聞き直さない
````

- [ ] **Step 2: 検証**

共通検証コマンド（`<dir>` = `sdd-constitution`）。Expected: `OK`

- [ ] **Step 3: コミット**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2/.claude/skills/sdd-constitution && \
git commit -m "feat(sdd): sdd-constitution スキルを追加"
```

---

### Task 3: sdd-specify

**Files:**
- Create: `.claude/skills/sdd-specify/SKILL.md`

**Interfaces:**
- Produces: `specs/NNN-機能名/spec.md`（節構成: ユーザーストーリー／受け入れ基準（Given/When/Then）／スコープ外）。`[要確認: 〜]` マーカーは sdd-clarify の入力

- [ ] **Step 1: SKILL.md を作成**

````markdown
---
name: sdd-specify
description: "機能の仕様書（ユーザーストーリー＋Given/When/Then 受け入れ基準）を書く。WHAT/WHY のみを扱い、技術選定や実装方法（HOW）は書かない。日本語トリガー例:「仕様書を書いて」「要件をまとめて」。通常は sdd オーケストレーター経由で呼ばれる。単体でも呼び出し可"
---

# sdd-specify — 仕様書の作成

## HOW 禁止ルール

仕様書に次を書いたら失敗: フレームワーク名・ライブラリ名・DB 種別・API 設計・ファイル構成・クラス名。
「ユーザーがログインできる」は仕様。「JWT でセッション管理する」は仕様ではない（plan の仕事）。

## 出力フォーマット（specs/NNN-機能名/spec.md）

```markdown
# <機能名> 仕様書
## ユーザーストーリー
- <役割>として、<したいこと>。なぜなら<価値>だから。
## 受け入れ基準
### AC-1: <名前>
- Given: <前提>
- When: <操作>
- Then: <期待結果>
## スコープ外
- <今回やらないこと>
```

## 手順

1. 依頼内容からユーザーストーリーを起こす（1機能につき1〜5個）
2. 各ストーリーに受け入れ基準を AC-番号付きで書く。**検証可能な表現のみ**（「使いやすい」は不可、「3クリック以内で〜」は可）
3. 判断できない点は本文に `[要確認: 〜]` マーカーを埋め込む。推測で埋めない
4. スコープ外を明記する（YAGNI の防波堤）
5. 全文を提示して承認を得る。`[要確認]` が残っていれば「次は clarify」と伝える
````

- [ ] **Step 2: 検証**

共通検証コマンド（`<dir>` = `sdd-specify`）。Expected: `OK`

- [ ] **Step 3: コミット**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2/.claude/skills/sdd-specify && \
git commit -m "feat(sdd): sdd-specify スキルを追加"
```

---

### Task 4: sdd-clarify

**Files:**
- Create: `.claude/skills/sdd-clarify/SKILL.md`

**Interfaces:**
- Consumes: spec.md の `[要確認: 〜]` マーカー（Task 3 で定義）
- Produces: `specs/NNN-機能名/clarifications.md`、更新済み spec.md（マーカーゼロ）

- [ ] **Step 1: SKILL.md を作成**

````markdown
---
name: sdd-clarify
description: "仕様書の曖昧箇所を1問ずつの質問で解消し、Q&A を記録して spec.md に反映する。日本語トリガー例:「仕様の曖昧なところを詰めて」「要確認を潰して」。通常は sdd オーケストレーター経由で呼ばれる。単体でも呼び出し可"
---

# sdd-clarify — 曖昧箇所の解消

## 手順

1. spec.md の `[要確認]` マーカーを集める。加えて、受け入れ基準を読み「2通りに解釈できる箇所」を自分でも探す
2. **1メッセージ1問・選択式優先**で質問する。上限5問。5問を超える曖昧さがある場合は影響の大きい順に5問とし、残りは spec の分割をユーザーに提案する
3. 各回答を `clarifications.md` に追記する:

```markdown
## Q1: <質問>
- 回答: <ユーザーの回答>
- 反映先: spec.md <該当節>
```

4. 回答を spec.md 本文へ反映し、対応する `[要確認]` を消す
5. マーカーがゼロになったら、変更差分の要約を提示する

## 自動通過

呼ばれた時点でマーカーがゼロかつ自力検出の曖昧箇所もない場合は、質問せず「曖昧箇所ゼロ」を報告して終了してよい（sdd はこれを state.md に記録する）。
````

- [ ] **Step 2: 検証**

共通検証コマンド（`<dir>` = `sdd-clarify`）。Expected: `OK`

- [ ] **Step 3: コミット**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2/.claude/skills/sdd-clarify && \
git commit -m "feat(sdd): sdd-clarify スキルを追加"
```

---

### Task 5: sdd-plan

**Files:**
- Create: `.claude/skills/sdd-plan/SKILL.md`

**Interfaces:**
- Consumes: 承認済み spec.md（Task 3）、docs/constitution.md（Task 2 の節構成）
- Produces: `specs/NNN-機能名/plan.md`（節構成: 技術選定／コンポーネント分割／データモデル／エラー処理方針／テスト戦略／constitution 準拠チェック）

- [ ] **Step 1: SKILL.md を作成**

````markdown
---
name: sdd-plan
description: "承認済み仕様書から技術計画（技術選定・コンポーネント分割・データモデル・エラー処理・テスト戦略）を作る。constitution 準拠チェック必須。日本語トリガー例:「技術計画を立てて」「アーキテクチャを設計して」。通常は sdd オーケストレーター経由で呼ばれる。単体でも呼び出し可"
---

# sdd-plan — 技術計画

## 前提チェック

spec.md が承認済み（state.md の承認履歴に記録あり）でなければ、sdd に差し戻す。`[要確認]` が残っていたら clarify に差し戻す。

## 出力フォーマット（specs/NNN-機能名/plan.md）

```markdown
# <機能名> 技術計画
## 技術選定
- <選定>: <理由1行>（代替案: <検討して外した案>）
## コンポーネント分割
- <ユニット名>: 責務1行／公開インターフェース／依存先
## データモデル
## エラー処理方針
## テスト戦略
- 受け入れ基準 AC-n をどのレベル（unit/integration/e2e）で検証するか
## constitution 準拠チェック
- <constitution の各項目>: 準拠 | 逸脱（理由と代替案）
```

## 原則

- 各コンポーネントは「何をするか・どう使うか・何に依存するか」に1行ずつで答えられる粒度にする
- 既存コードベースでは既存パターンに従う。無関係なリファクタを計画に入れない
- constitution 準拠チェックは全項目を列挙する。逸脱を黙認しない
- 全文提示→承認
````

- [ ] **Step 2: 検証**

共通検証コマンド（`<dir>` = `sdd-plan`）。Expected: `OK`

- [ ] **Step 3: コミット**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2/.claude/skills/sdd-plan && \
git commit -m "feat(sdd): sdd-plan スキルを追加"
```

---

### Task 6: sdd-tasks

**Files:**
- Create: `.claude/skills/sdd-tasks/SKILL.md`

**Interfaces:**
- Consumes: 承認済み plan.md（Task 5 の節構成）
- Produces: `specs/NNN-機能名/tasks.md`（タスクごとに ①変更対象ファイル ②完了条件 ③検証コマンド ④依存タスク、`[P]` マーク）。sdd-implement はこの4項目を前提とする

- [ ] **Step 1: SKILL.md を作成**

````markdown
---
name: sdd-tasks
description: "技術計画を実装タスク列に分解する。各タスクに変更対象ファイル・完了条件・検証コマンド・依存関係を必須で付け、並列可能タスクに [P] を付ける。日本語トリガー例:「タスクに分解して」「実装タスクを作って」。通常は sdd オーケストレーター経由で呼ばれる。単体でも呼び出し可"
---

# sdd-tasks — タスク分解

## 出力フォーマット（specs/NNN-機能名/tasks.md）

```markdown
# <機能名> タスク一覧
## T1: <タスク名> [P]
- 変更対象: <正確なファイルパス（作成/変更の別）>
- 完了条件: <検証可能な1〜3行。対応する受け入れ基準 AC-n を明記>
- 検証コマンド: `<そのまま実行できるコマンド>` → 期待: <出力>
- 依存: なし | T<n>
```

## 規則

- **4項目すべて必須**。検証コマンドは実行可能なものに限る（「動作を確認する」は不可）
- 粒度: サブエージェントが1回の派遣で完了できる大きさ（目安: 関連ファイル5個以内）。超えるなら分割
- 依存のないタスク同士に `[P]`（並列可能）を付ける。ただし同一ファイルを触るタスク同士には付けない
- テストを先に書く前提でタスクを書く（完了条件に「テストがパスする」を含める）
- すべての受け入れ基準 AC-n がいずれかのタスクの完了条件に現れること（漏れは analyze で検出されるが、ここで防ぐ）
- 全文提示→承認
````

- [ ] **Step 2: 検証**

共通検証コマンド（`<dir>` = `sdd-tasks`）。Expected: `OK`

- [ ] **Step 3: コミット**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2/.claude/skills/sdd-tasks && \
git commit -m "feat(sdd): sdd-tasks スキルを追加"
```

---

### Task 7: sdd-analyze

**Files:**
- Create: `.claude/skills/sdd-analyze/SKILL.md`

**Interfaces:**
- Consumes: spec.md / plan.md / tasks.md / constitution.md（Task 2,3,5,6 の節構成）
- Produces: 整合性レポート（会話上の報告のみ。ファイルは書き換えない）

- [ ] **Step 1: SKILL.md を作成**

````markdown
---
name: sdd-analyze
description: "実装前に spec・plan・tasks の整合性を検証する読み取り専用チェック。受け入れ基準のカバレッジ表・矛盾・constitution 違反・検証コマンドの実行可能性を報告する。日本語トリガー例:「整合性をチェックして」「実装前チェックして」。通常は sdd オーケストレーター経由で呼ばれる。単体でも呼び出し可"
---

# sdd-analyze — 整合性検証（read-only）

<HARD-GATE>
このスキルは成果物を書き換えない。報告のみ。修正は該当フェーズへの差し戻しで行う。
</HARD-GATE>

## 検証項目（すべて実施）

1. **カバレッジ表**: 全 AC-n × タスクの対応表を作る。どのタスクにも現れない AC は「漏れ」
2. **spec↔plan 矛盾**: plan のコンポーネント・データモデルが spec の受け入れ基準と食い違っていないか
3. **constitution 違反**: plan・tasks が constitution の各項目に反していないか（plan の準拠チェック節の検算）
4. **検証コマンドの実行可能性**: tasks.md の各検証コマンドが現環境で実行できる形式か（ツールの存在・パスの妥当性）

## 報告フォーマット

```markdown
## 整合性レポート
### カバレッジ表
| AC | タスク | 状態 |
### 問題（重大度順）
- [重大|軽微] <内容> → 差し戻し先: <フェーズ>
### 判定: 実装に進んでよい | 差し戻しを推奨
```

重大問題ゼロでも必ずレポート全文を提示し、ユーザーの確認を得てから implement へ進める（承認記録は sdd の責務）。
````

- [ ] **Step 2: 検証**

共通検証コマンド（`<dir>` = `sdd-analyze`）。Expected: `OK`

- [ ] **Step 3: コミット**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2/.claude/skills/sdd-analyze && \
git commit -m "feat(sdd): sdd-analyze スキルを追加"
```

---

### Task 8: sdd-implement＋implementer-prompt

**Files:**
- Create: `.claude/skills/sdd-implement/SKILL.md`
- Create: `.claude/skills/sdd-implement/implementer-prompt.md`

**Interfaces:**
- Consumes: 承認済み tasks.md の4項目（Task 6）、state.md のフェーズ内進捗欄（Task 1）
- Produces: 実装済みコード＋更新された state.md チェックボックス

- [ ] **Step 1: SKILL.md を作成**

````markdown
---
name: sdd-implement
description: "承認済みタスク一覧をサブエージェント駆動＋TDD で実装する。小タスク（1〜2ファイル）は本体で直接実装。タスクごとに検証コマンドで確認し state.md を更新する。日本語トリガー例:「実装して」「タスクを実行して」。通常は sdd オーケストレーター経由で呼ばれる。単体でも呼び出し可"
---

# sdd-implement — 実装フェーズ

## 前提チェック

tasks.md が承認済みでなければ sdd に差し戻す。

## タスクごとの実行方式（自動選択）

- 変更対象が **1〜2ファイル** → 本体セッションで直接実装（TDD で）
- **3ファイル以上** → サブエージェント派遣
- 選択結果（subagent | 直接）を state.md のフェーズ内進捗欄に記録する

## サブエージェント派遣の規則

- 渡すもの: `implementer-prompt.md` の雛形＋該当タスク定義（tasks.md の当該節のみ）＋spec.md の関連 AC ＋constitution.md
- **渡さないもの**: plan 全文・他タスク・会話履歴（コンテキスト隔離。タスク定義で完結させる）
- `[P]` タスクは同時派遣可。ただし同一ファイルを触るタスクの同時派遣は禁止
- タスク完了報告を受けたら、**本体が検証コマンドを自分で実行**して確認し、state.md のチェックボックスを更新する。サブエージェントの「できました」を鵜呑みにしない
- 同じタスクで2回失敗したら本体で引き取り、原因を特定してからタスク定義を修正する

## 仕様矛盾を発見したら

実装を止めて報告する。spec.md の修正（ユーザー承認必要）→ 差し戻し履歴に記録 → 影響タスクを更新してから再開。黙って仕様と違うものを作らない。

## フェーズ完了

全タスクのチェックボックスが埋まったら、実行方式の内訳と検証結果の一覧を提示して承認を得る。
````

- [ ] **Step 2: implementer-prompt.md を作成**

````markdown
# 実装サブエージェント指示書（雛形）

あなたは1つのタスクだけを実装する。タスク定義に書かれていないことはやらない。

## 必ず TDD で進める

1. **RED**: タスクの完了条件に対応する失敗するテストを先に書き、実行して失敗を確認する
2. **GREEN**: テストを通す最小の実装を書く。実行してパスを確認する
3. **リファクタ**: テストを緑に保ったまま整理する

テストなしで実装コードを書き始めたら失敗。テストの後追い作成も失敗。

## 制約

- 変更してよいのはタスク定義の「変更対象」に列挙されたファイルのみ
- constitution.md の全項目に従う
- 仕様（添付の受け入れ基準）と矛盾する要求に気づいたら、実装せず矛盾内容を報告して終了する

## 完了報告フォーマット

- 変更ファイル一覧
- 実行した検証コマンドとその出力（そのまま貼る）
- 判断に迷った点（あれば）

## タスク定義

（派遣時にここへ tasks.md の該当節・spec.md の関連 AC・constitution.md を貼り付ける）
````

- [ ] **Step 3: 検証**

共通検証コマンド（`<dir>` = `sdd-implement`）に加えて:

```bash
test -f /Users/takashi-kikuchi/Desktop/Projects/claude/design/agent-driven-development_v2/.claude/skills/sdd-implement/implementer-prompt.md && echo OK
```

Expected: `OK` ×2

- [ ] **Step 4: コミット**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2/.claude/skills/sdd-implement && \
git commit -m "feat(sdd): sdd-implement スキルと実装者プロンプトを追加"
```

---

### Task 9: sdd-verify

**Files:**
- Create: `.claude/skills/sdd-verify/SKILL.md`

**Interfaces:**
- Consumes: spec.md の AC-n（Task 3）、state.md（Task 1）
- Produces: 証拠付き検証レポート、state.md の「完了」更新

- [ ] **Step 1: SKILL.md を作成**

````markdown
---
name: sdd-verify
description: "実装完了後、仕様書の全受け入れ基準を実際に実行して検証し、証拠（コマンドと出力）付きで完了報告する。証拠なしに完了と言うことを禁止。日本語トリガー例:「検証して」「完了確認して」「受け入れテストして」。通常は sdd オーケストレーター経由で呼ばれる。単体でも呼び出し可"
---

# sdd-verify — 受け入れ検証と完了

<HARD-GATE>
証拠（実際に実行したコマンドとその出力）なしに「完了」「動きます」と報告することを禁止する。
</HARD-GATE>

## 手順

1. spec.md（バイパス時は spec-lite.md）の受け入れ基準を1件ずつ、**Then を実証するコマンドや操作を実際に実行**して確認する
2. 結果を検証レポートとして記録する:

```markdown
## 検証レポート
### AC-1: <名前> — PASS | FAIL
- 実行: `<コマンド>`
- 出力: <そのまま貼る>
```

3. FAIL があれば implement へ差し戻す（差し戻し履歴に記録）。全件 PASS まで完了と言わない
4. 全件 PASS: state.md の現在フェーズを「完了」にし、レポート全文を提示する
5. 統合方法の選択肢を提示する: ①コミットして終了 ②PR 作成 ③そのまま（ユーザーが選ぶ。勝手にコミットしない）
````

- [ ] **Step 2: 検証**

共通検証コマンド（`<dir>` = `sdd-verify`）。Expected: `OK`

- [ ] **Step 3: コミット**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2/.claude/skills/sdd-verify && \
git commit -m "feat(sdd): sdd-verify スキルを追加"
```

---

### Task 10: 発火テスト

**Files:**
- Test: なし（サブエージェントによる実測）

**Interfaces:**
- Consumes: 全9スキル（Task 1〜9）

- [ ] **Step 1: 全スキルの frontmatter 一括検証**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design/agent-driven-development_v2 && \
for d in sdd sdd-constitution sdd-specify sdd-clarify sdd-plan sdd-tasks sdd-analyze sdd-implement sdd-verify; do \
  grep -q "^name: $d$" .claude/skills/$d/SKILL.md || echo "NG: $d"; \
done; echo DONE
```

Expected: `DONE` のみ（`NG:` 行なし）

- [ ] **Step 2: 発火シミュレーション**

サブエージェント（general-purpose）を2体派遣し、それぞれに次を依頼:
1. 「`agent-driven-development_v2` で作業する Claude Code セッションに『TODO アプリを作って』と言われた場合、`.claude/skills/` のどのスキルの description に最も合致するか。スキル名だけ答えよ」→ 期待: `sdd`
2. 同様に「『仕様の曖昧なところを詰めて』」→ 期待: `sdd-clarify`

Expected: 両方期待どおり。外れた場合は該当 description を修正して再テスト

- [ ] **Step 3: コミット（description 修正があった場合のみ）**

```bash
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add agent-driven-development_v2 && \
git commit -m "fix(sdd): 発火テスト結果に基づき description を調整"
```

---

### Task 11: 通しドライラン（再開・バイパス含む）

**Files:**
- Test: `specs/001-cli-calculator/`（ドライランの副産物。確認後に削除）

**Interfaces:**
- Consumes: 全9スキル

- [ ] **Step 1: 通しドライラン**

サブエージェントに「`agent-driven-development_v2` をカレントとして、sdd スキルの手順書どおりに『四則演算 CLI 電卓』の開発を specify〜tasks まで進めよ。ユーザー承認は『承認』と自己応答してよい（ドライランのため）。各フェーズで state.md を更新すること」と依頼。

確認項目:
- `specs/001-cli-calculator/` に state.md / spec.md / plan.md / tasks.md が生成される
- state.md の承認履歴にフェーズごとの記録がある
- spec.md に HOW（技術名）が混入していない

- [ ] **Step 2: 再開テスト**

別のサブエージェントに「`specs/001-cli-calculator/state.md` を読み、sdd スキルの再開手順に従って現在フェーズと次アクションを報告せよ」と依頼。
Expected: 「現在フェーズ: tasks（承認済みなら analyze）」を正しく特定

- [ ] **Step 3: バイパステスト**

サブエージェントに「sdd スキルの手順書に従い『README の誤字を1箇所直したい』という依頼のルート判定をせよ」と依頼。
Expected: バイパス判定（spec-lite ルート）

- [ ] **Step 4: ドライラン産物の削除と最終コミット**

```bash
rm -rf /Users/takashi-kikuchi/Desktop/Projects/claude/design/agent-driven-development_v2/specs/001-cli-calculator && \
cd /Users/takashi-kikuchi/Desktop/Projects/claude/design && \
git add -A agent-driven-development_v2 && \
git commit -m "test(sdd): 通しドライラン完了、産物を削除"
```

---

## Self-Review 結果

- **Spec coverage**: 設計書の9スキル＋state.md 書式＋ゲート＋バイパス＋テスト計画4項目（発火/通し/再開/バイパス）すべてにタスクあり。SessionStart フックは設計書でスコープ外
- **Placeholder scan**: 全 SKILL.md 本文を完全記載。TBD/TODO なし
- **整合性**: state.md 書式は Task 1 で単一定義し他タスクは参照のみ。フェーズ名・スキル名・成果物パスは全タスクで一致
