# 高度デザインのpalette自動生成

高度デザインでは、エージェントが7色を直接選ばない。主題と色の意味を `palette-intent.json` に書き、`scripts/generate_palette.py` に派生色、コントラスト調整、候補比較を任せる。外部APIやネットワークは使わない。

## 使う条件

利用者が高度・印象的・ブランド性のあるデザインを求めた場合、または社外発表、イベント登壇、重要提案で視覚的な差別化が必要な場合に使う。既存テンプレや既存デッキがある場合は自動生成せず、`extract_style.py` で既存色を抽出する。

## 意図を書く

```json
{
  "basis": "夜間物流の管制画面。主色は運行中、強調色は遅延を示す",
  "tone": "technical, restrained, high-contrast",
  "surface": "dark",
  "accent_meaning": "遅延または要対応",
  "anchor_color": "176B55",
  "brand_colors": [],
  "reference_images": [],
  "fonts": ["Yu Gothic"],
  "min_font_pt": 12
}
```

基準色は次の優先順位で1つだけ選ばれる。

1. `brand_colors` の先頭
2. `anchor_color`
3. `reference_images` から抽出した有彩色

ブランド色は主色として保持し、2色あれば2色目も強調色として保持する。ただし背景とのコントラストが不足する場合だけ明度を調整する。`anchor_color` や参考画像を使う場合は、3候補で主色の明度・彩度、中間色の色味、強調色との関係を変える。いずれも無い場合、文字列だけから恣意的な色を作らず終了コード2で停止する。主題を読んで基準色を決めるのはエージェント、明度・彩度・派生色を計算するのはスクリプトの役割である。

参考画像のパスはintentファイルからの相対パスか絶対パスで書く。画像抽出にはPillowを使う。ロゴ、製品、現場写真など、色の根拠として利用者が渡した画像だけを対象にし、画像を勝手に取得しない。

## 3候補を生成して比較する

```bash
python3 <skills>/pptx-design/scripts/generate_palette.py deck/palette-intent.json \
  --candidates-out deck/qa/palette-candidates.json \
  --preview-pptx deck/qa/palette-candidates.pptx \
  --select auto \
  --lock-out deck/design-lock.json
```

3候補は補色、分裂補色、類似色の関係で作る。各候補には本文、補助文字、主色、強調色のコントラスト、主色・強調色間の通常色差、1型・2型色覚を近似したときの最小色差、4本の図表系列色が入る。色覚差は簡易シミュレーションであり医学的な判定ではない。`auto` は検査スコアが最も高い候補を選び、同点なら `basis` から決定的に選ぶ。同じintentなら同じ結果になる。

`palette-candidates.pptx` は候補ごとに表紙と本文を1枚ずつ持つ。pptx-review の `render_preview.py` で描画し、次を確認する。

- 主題の印象と基準色が合う
- 強調色が `accent_meaning` または `basis` に書いた意味として読める
- 表紙だけでなく白地・暗地の本文でも成立する
- どの候補でも本文、主色、強調色の視覚階層が保たれている

自動選択を使っても描画確認は省略しない。利用者が候補を指定した場合は `--select 1` のように固定して再実行する。

## 出力と安全

`design-lock.json` には `palette_basis`、7役の `palette`、`chart_series`、生成方式、基準色、検査値が残る。生成骨格はこのpaletteと系列色を直接使う。

既存ファイルは既定で上書きしない。内容を確認して置き換える権限がある場合だけ `--force` を使う。候補JSON、比較PPTX、design-lockは原則として未使用の出力先へ生成する。
