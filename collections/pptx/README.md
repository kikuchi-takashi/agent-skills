# PPTX Skill Set

PowerPoint（`.pptx`）の設計、生成、編集、監査を一貫した品質基準で行う Agent Skills bundleです。`pptx-create`、`pptx-edit`、`pptx-review` の3スキルを `pptx-suite` として一体配布し、内容設計、デザインロック、編集可能な成果物、機械検査、描画確認を組み合わせます。

## スキルを選ぶ

| スキル | 用途 | 主な成果物 |
|---|---|---|
| `pptx-create` | 要件、原稿、資料から新しいデッキを設計・生成する | `.pptx`、ブリーフ、構成、デザインロック、QA結果 |
| `pptx-edit` | 既存デッキの内容やページを、元のデザインシステムに合わせて編集する | 編集済み `.pptx`、変更内容、QA結果 |
| `pptx-review` | デッキを変更せず、構造、レイアウト、文章、デザインの整合を監査する | 監査報告、lint結果、描画画像 |

新規作成は `pptx-create`、既存ファイルの変更は `pptx-edit`、評価だけなら `pptx-review` を使います。作成・編集後の品質確認では `pptx-review` を別コンテキストで実行すると、生成時の思い込みから独立した判定になります。

## 共通ワークフロー

1. 聴衆、目的、利用場面、言語、枚数、ブランド制約、素材をブリーフにまとめる。
2. 各ページの主張、役割、証拠、展示物を構成として定義する。
3. パレット、書体、型スケール、グリッド、レイアウト原型をデザインロックに記録する。
4. デザインロックから編集可能な `.pptx` を生成または編集する。
5. lintと描画画像を照合し、指摘箇所を修正する。
6. 成果物、仮定、要確認事項、検証結果をまとめて納品する。

設計では次の基準を共有します。

- タイトルをページの主張として書き、1枚に1つの論点と中心展示物を置く。
- 展示物は候補を2つ以上出し、決め手で選ぶ。最初に当てはまった形をそのまま採らない。
- 横並びと面（カード）は既定にしない。主役を1つ決め、面を敷くのは項目が並列・無順序・等重みのときだけにする。
- 色、書体、余白、タイトル位置を静かな共通層として揃え、レイアウト、主役、密度にリズムをつける。
- シグネチャは主題の素材から作り、静かな標識・幾何そのものの1枚・初出の凡例の3層で示す。
- 既存デッキでは、実測した設計値と同じ役割の既存要素を編集の基準にする。
- 装飾には情報上の役割を持たせ、主張と証拠の視線誘導を優先する。
- 品質判定には、機械検査の結果、描画画像、確認範囲を添える。

## インストール

リポジトリのCLIからコレクションをまとめて導入します。

```bash
skills install collection:pptx --root collections --target ~/.agents/skills
```

3つのスキルはインストール先へフラットにコピーされますが、配布単位は常に `pptx-suite` 全体です。このリポジトリのCLIでは、`pptx-create`、`pptx-edit`、`pptx-review` のどれか1つを指定しても3つすべてを原子的に導入します。外部の `npx skills` を使う場合は、コレクションパスに対して `--skill '*'` を指定し、一部だけを導入しないでください。

```bash
npx skills add kikuchi-takashi/agent-skills/collections/pptx \
  --skill '*' --agent codex --global --yes
```

`pptx-review` にはbundle共通の次の補助ツールが含まれます。

- `extract_style.py`: 既存デッキからデザインロックを抽出する
- `pptx_lint.py`: OOXMLを解析し、構造・配置・文字・デザインの問題を報告する
- `render_preview.py`: スライドとコンタクトシートを簡易描画する

## 実行環境と能力選択

Python 3.9以上を基準とし、着手時に利用できるライブラリを確認して実行経路を決めます。

```python
import importlib

modules = ["pptx", "lxml", "PIL", "xlsxwriter"]
for name in modules:
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "available")
        print(f"{name:12} {version}")
    except ImportError:
        print(f"{name:12} unavailable")
```

| 能力 | 実行要件 | 担当 |
|---|---|---|
| PPTXの構造監査と設計値抽出 | Python標準ライブラリ | `pptx_lint.py`、`extract_style.py` |
| PPTXの生成・編集 | `python-pptx`、`lxml`、`Pillow`、`XlsxWriter` | `pptx-create`、`pptx-edit` |
| 簡易描画とコンタクトシート | `Pillow` | `render_preview.py` |
| データ集計、画像加工、素材抽出 | 実行環境に備わる関連ライブラリ | 入力資料とスライド表現に応じて選択 |

和文書体が利用できる場合、簡易描画は実際の字形と文字幅を使います。書体ファイルを `render_preview.py --font path.ttf` で指定することもできます。代替描画になった文字や図形は、納品時に確認範囲として記録します。

## 品質確認

品質確認は、利用できる能力に応じて次の証拠を積み上げます。

1. `pptx_lint.py` で全ページの構造、配置、文字、パッケージ整合を検査する。
2. `render_preview.py` で全ページ画像とコンタクトシートを生成し、個別ページとデッキ全体を確認する。
3. ハーネス自身がPPTXを画像にする手段を持つ場合だけ、最終成果物を見比べて表示差を確認する。

納品報告には、実行した検査、確認したページ数、使用した書体、検出件数、残存する要確認事項を記載します。これにより、ハーネスごとの能力差があっても確認済みの範囲を追跡できます。

## 検証済みの互換基準

Python 3.9、python-pptx 0.6.21、Pillow 8.3.2を互換基準とし、骨格の20原型、3本の監査ツール、46件の評価ケースで動作を確認しています。実行時に取得したライブラリの版は、再現条件としてQA結果に残します。

## 用途別に束ねる例

`instruction.md` は、このコレクションを特定の用途（営業資料）向けに束ねる例です。配布スキルではありません。用途に固有のもの（要件の聞き方、ストーリーラインの型、その分野の禁止事項、デザインロックの出発点）だけを書き、設計原則・レイアウト原型・生成の骨格・検査・納品報告はスキル側に委ねる構成にしています。自分の用途に写して直す出発点として使えます。

## コレクションの保守

`collections/pptx/scripts/` はコレクション全体の保守用検査です。各スキルの配布パッケージには含まれません。

- `eval-checks.py`: 46件のケースでlintの検出・非検出と運用上の回帰を確認する
- `audit-consistency.py`: 文書、骨格コード、監査ツールの数値・名称・オプションを照合する

変更後はリポジトリルートで実行します。

```bash
python3 collections/pptx/scripts/eval-checks.py
python3 collections/pptx/scripts/audit-consistency.py
python3 -m agent_skills_marketplace validate --root collections
python3 -m agent_skills_marketplace index --root collections --output marketplace.json
python3 -m agent_skills_marketplace index --root collections --output marketplace.json --check
```

## 参考資料と由来

2026-09-06時点で、次の公開資料を比較調査しました。参照したのは役割分離、品質ゲート、編集可能性、ストーリー構成などの一般的な設計観点です。このbundleの文章とコードは独自実装で、第三者のコード、プロンプト、画像、テンプレート、書体は同梱していません。

| 参照先 | 確認したライセンス | このbundleでの扱い |
|---|---|---|
| [anthropics/skills — pptx](https://github.com/anthropics/skills/tree/main/skills/pptx) | [独自ライセンス・複製および派生物の制限あり](https://github.com/anthropics/skills/blob/main/skills/pptx/LICENSE.txt) | 動作範囲の比較だけに使用。文章・コード・資産は複製していない |
| [EveryInc/hands-on-deck](https://github.com/EveryInc/hands-on-deck) | MIT | 検査と編集を分離する考え方を比較。コードは使用していない |
| [addsumtech/slides_maker](https://github.com/addsumtech/slides_maker) | MIT | ネイティブ編集可能性と独立レビューの観点を比較。コードは使用していない |
| [Gabberflast/academic-pptx-skill](https://github.com/Gabberflast/academic-pptx-skill) | Proprietary | 学術デッキの役割分離を比較。文章・コードは使用していない |
| [LearnPrompt/humanize-ppt](https://github.com/LearnPrompt/humanize-ppt) | MIT | 聴衆とストーリー構成の観点を比較。コードは使用していない |
