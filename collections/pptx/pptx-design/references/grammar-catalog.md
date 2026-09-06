# デッキの文法カタログ — 目的から選び、そのまま貼る

`design-lock.json` の `grammar` に何を書くかの引き出し。**目的で選ぶ**——分野や枚数ではない。

`storyline.md` の骨格（`pptx-create`）と対になっている。あちらは人が構成を書くための説明、こちらは機械が読む値。**片方だけ選ばない**。

| 目的 | 文法 | 読みの筋 | 向く場面 |
|---|---|---|---|
| 判断を仰ぐ | `answer-led` | 答え → 根拠 → 前提とリスク → 依頼 | 経営層、時間が短い、決裁 |
| 説得する | `situation-complication` | 状況 → 変化 → 打ち手 → 次 | 提案、方針転換、社内稟議 |
| 痛みから動かす | `pain-led` | 痛み → 損失 → 解決 → 証拠 → 依頼 | 営業、ピッチ、危機の共有 |
| 示して納得させる | `question-evidence` | 問い → 方法 → 結果 → 限界 → 含意 | 調査報告、学術、監査 |
| 経緯を伝える | `chronicle` | 起点 → 転機 → 現在 → 次 | 振り返り、事故報告、沿革 |
| 変化を見せる | `before-after` | 現状 → 変化後 → 橋渡し → 依頼 | 構想発表、刷新、体験の刷新 |
| 教えて動かす | `fact-meaning-action` | 事実 → 意味 → 行動（主題ごとに繰り返す） | 研修、社内共有、勉強会 |

**迷ったら `answer-led`。** 相手の時間を最も使わない。

## 使い方

選んだ文法の JSON を `design-lock.json` にそのまま貼る。`escalate` は**その文法では軽微で済まない指摘**で、`allow` の逆に重大度を1段上げる。

```json
"grammar": {
  "id": "answer-led",
  "arc": ["答え", "根拠", "前提とリスク", "依頼"],
  "escalate": ["CARD_ROW", "EQUAL_EMPHASIS"]
}
```

`arc` の段名は `outline.json` の `role` にそのまま使う。`check_outline.py` が「本文の最初の3枚に先頭の段が現れるか」を見る。**段名を勝手に言い換えない**——照合できなくなる。

---

## `answer-led` — 判断を仰ぐ

```json
"grammar": {"id": "answer-led", "arc": ["答え", "根拠", "前提とリスク", "依頼"],
            "escalate": ["CARD_ROW", "EQUAL_EMPHASIS"]}
```

- **原型の並び**: `statement` か `hero-number` → `claim-evidence` ×2〜3 → `comparison` か `table` → `closing`
- **やらないこと**: 答えを最後まで取っておかない。経緯から始めない
- **なぜその `escalate`**: 根拠の層をカードの羅列で埋めると、答えを支えるものが消える

## `situation-complication` — 説得する

```json
"grammar": {"id": "situation-complication", "arc": ["状況", "変化", "打ち手", "次"],
            "escalate": ["TITLE_TOPIC_LABEL", "FORM_FAMILY_MONOTONE"]}
```

- **原型の並び**: `claim-evidence` → `trend` か `before-after` → `comparison` → `steps` か `roadmap` → `closing`
- **やらないこと**: 状況を長く語らない（共有済みの前提は1〜2枚）。変化を書かずに打ち手へ飛ばない
- **なぜその `escalate`**: 話題ラベルのタイトルだと「変化」が主張として立たない。形が単調だと状況と変化の区別が消える

## `pain-led` — 痛みから動かす

```json
"grammar": {"id": "pain-led", "arc": ["痛み", "損失", "解決", "証拠", "依頼"],
            "escalate": ["AI_VOCAB", "CARD_ROW"]}
```

- **原型の並び**: `claim-evidence` → `hero-number`（損失額） → `before-after` → `table` か `trend` → `closing`
- **やらないこと**: 痛みを一般論で書かない（相手の数字で書く）。解決を先に出さない
- **なぜその `escalate`**: 誇張語彙で痛みを作ろうとすると、数字の説得力が消える。この文法はいちばん煽りに転びやすい

## `question-evidence` — 示して納得させる

```json
"grammar": {"id": "question-evidence", "arc": ["問い", "方法", "結果", "限界", "含意"],
            "escalate": ["CHART_AXIS_TRUNCATED", "CHART_BARS_UNSORTED", "DARK_PAGE_OVERUSE"]}
```

- **原型の並び**: `statement`（問い） → `steps` か `structure`（方法） → `trend` / `table` / `claim-evidence` → `comparison`（限界） → `closing`
- **やらないこと**: 限界の段を飛ばさない。結果を強調色で盛らない
- **なぜその `escalate`**: 軸を切り詰めた図は、この文法では誠実さの問題になる。濃い面の多用も演出に見える

## `chronicle` — 経緯を伝える

```json
"grammar": {"id": "chronicle", "arc": ["起点", "転機", "現在", "次"],
            "escalate": ["CHART_BARS_UNSORTED", "LAYOUT_MONOTONE"]}
```

- **原型の並び**: `claim-evidence` → `roadmap` か `trend` → `hero-number` → `closing`
- **やらないこと**: 時系列を値の順に並べ替えない。転機を書かずに出来事を列挙しない
- **なぜその `escalate`**: 時系列の並びが崩れると経緯が読めない。同じ形が続くと転機が埋もれる

## `before-after` — 変化を見せる

```json
"grammar": {"id": "before-after", "arc": ["現状", "変化後", "橋渡し", "依頼"],
            "escalate": ["EQUAL_EMPHASIS", "DEAD_WHITESPACE"]}
```

- **原型の並び**: `claim-evidence`（現状） → `before-after` → `photo-half` か `structure`（橋渡し） → `steps` → `closing`
- **やらないこと**: 現状と変化後を等分に置かない（主張を運ぶ側を広く）。橋渡しを飛ばさない
- **なぜその `escalate`**: 等分の左右は「どちらを見ればよいか」を言っていない。この文法の核心が消える

## `fact-meaning-action` — 教えて動かす

```json
"grammar": {"id": "fact-meaning-action", "arc": ["事実", "意味", "行動"],
            "escalate": ["TEXT_DENSE", "TITLE_TOPIC_LABEL"]}
```

- **原型の並び**: 主題ごとに `claim-evidence` → `statement` か `hero-number` → `steps` を繰り返す
- **やらないこと**: 事実を並べて意味を言わない。1つの主題で3段そろわないなら、その主題は入れない
- **なぜその `escalate`**: 教える資料は詰め込みに転びやすい。話題ラベルのタイトルは「意味」の段を空にする

---

## カタログを増やすとき

**目的が既存の7つと違うときだけ足す。** 分野が違うだけなら足さない——医療でも官公庁でも、判断を仰ぐなら `answer-led` である。

足すときは4つを埋める。**`escalate` には実在する指摘コードだけを書く**（`pptx-review` の `review-rubric.md` の一覧にあるもの）。整合監査がコードの実在を確かめる。

1. 読みの筋（`arc`）
2. 原型の並び
3. やらないこと（散文。機械で見られないもの）
4. `escalate`（機械で見られるもの）と、なぜそれなのか
