# PPTX Skill Set

PowerPoint（.pptx）を、生成AIらしさを出さず、デザインを安定させて作る・直す・監査するためのスキル群です。特定のエージェント製品には依存しません。

- `pptx-create`: 要件や原稿から新しいデッキを設計・生成する。構成 → デザインロック → 生成 → 品質確認
- `pptx-edit`: 既存デッキを、元のデザインシステムを壊さずに編集する。テンプレ流し込み、AIっぽい装飾の除去を含む
- `pptx-review`: デッキを変更せずに監査し、機械検査（`pptx_lint.py`）と簡易描画（`render_preview.py`）で判定する。生成者とは別のコンテキストで使う

## 設計方針

- **内容が先、装飾は後。** タイトルは主張の一文、1枚1主張、展示物は1つ
- **デザインは生成前にロックする。** パレット・書体・型スケール・グリッド・レイアウト名簿を固定し、全ページをそこから導出する。テンプレがあればテンプレがロック
- **生成AIらしさの兆候を名指しで避ける。** タイトル下の飾り線、上下の色帯、同型カード、絵文字、誇張語彙、話題ラベル型タイトルなど。視覚・文章（日本語）・構造の3層で点検する
- **合格は機械の出力と描画画像で示す。** 口頭の合格宣言を認めない
- **生成者と監査者を分ける。** 生成した本人は自分の期待を見てしまう

## インストール

```bash
skills install collection:pptx --root collections --target ~/.agents/skills
```

3つのスキルがフラットにコピーされます。`pptx-create` と `pptx-edit` は単体でも動きますが、`pptx-review` が同時に導入されていると、品質確認で `pptx_lint.py` と `render_preview.py` を使えます。

## 前提

- Python 3.9 以上
- `python-pptx`（生成・編集。lxml、Pillow、XlsxWriter に依存）
- Pillow（描画確認）
- `pptx_lint.py` は標準ライブラリのみで動く
- 外部ツール（LibreOffice など）、ネットワーク、追加インストールは不要。シェルが無い環境でも Python だけで手順が完結する
- 和文の書体ファイルがあれば描画確認で字形まで出る。無ければ和文は文字幅どおりの灰色バーで代替される

## 参考にしたもの

以下の公開スキル・リポジトリの考え方を参考に、文面は日本語で書き起こしました。文章やコードの転載はしていません。

- anthropics/skills（pptx）: エンジンの落とし穴、視覚QAの手順、装飾の禁止リスト
- EveryInc/hands-on-deck（designing-slides.md）: 主題からデザインを導く、既定のAI外観の拒否、引き算のパス
- addsumtech/slides_maker: AIらしさの兆候（視覚・文章）、リズム、独立した批評者
- crazyykhllc-bit/CyberPPT、likaku/Mck-ppt-design-skill、zairuilab/consulting-deck: スタイルロック、数値ガードレール、機械判定ゲート、経験ログ
- Gabberflast/academic-pptx-skill: アクションタイトル、ゴーストデッキテスト、1枚1展示
- LearnPrompt/humanize-ppt: 聴衆の状態遷移、話者視点の点検
