# 修正後のレイアウト安定性

既存デッキの修正では、完成後だけを見るlintに加えて、編集前後の差分を検査する。見た目の崩れは一つの原因ではなく、次の層で起きる。

| 層 | 主な原因 | 機械検査 |
|---|---|---|
| 文字 | 文言増加、折返しなし、`spAutoFit` の箱伸長、`normAutofit` の縮小、行送り・余白・縦位置の変化 | `AUTOFIT_GROW`、`EDIT_AUTOFIT_REFLOW`、`EDIT_TEXT_REFLOW_RISK`、`TEXT_FRAME_CHANGED` |
| 書式 | `text_frame.text` / `shape.text` / `cell.text` による段落・run書式の消失、和文書体の欠落 | `TEXT_STYLE_CHANGED`、`NO_EA_FONT`、`SHAPE_TEXT_UNSTYLED` |
| 幾何 | 図形の位置・寸法、group変換、回転・反転、重ね順、コネクタ端点の変化 | `SHAPE_GEOMETRY_CHANGED`、`GROUP_TRANSFORM_CHANGED`、`SHAPE_TRANSFORM_CHANGED`、`Z_ORDER_CHANGED`、`CONNECTOR_ENDPOINT_CHANGED` |
| 継承 | placeholderの種類、slideLayout、slideMaster、themeの付け替え | `SHAPE_ROLE_CHANGED`、`SLIDE_LAYOUT_CHANGED`、`THEME_CHANGED` |
| 表・画像 | 表の列幅/行高、画像のcrop・回転・縦横比、DPI任せの再配置 | `TABLE_GEOMETRY_CHANGED`、`PICTURE_CROP_CHANGED`、`RELATED_PART_CHANGED`、通常lintと描画 |
| 図表 | 系列・カテゴリ増加による凡例/ラベル衝突、共有chart partの片側編集 | `SHARED_PART_CHANGED`、図表lint、PowerPoint互換描画 |
| パッケージ | `r:embed` 等だけを別スライドへコピー、欠落part、Content Typesの不整合 | `BROKEN_RELATIONSHIP_REFERENCE`、`BROKEN_RELATIONSHIP`、`CONTENT_TYPE_*` |
| 描画環境 | 代替書体、禁則、影・グラデーション、SmartArt、アニメーション、アプリ間差 | 簡易描画では未確認として報告し、図表・SmartArt・画像があればPowerPoint互換描画で確認 |

## 編集前に契約を作る

編集前PPTXのSHA-256を固定した契約を先に作る。編集後にallowを後付けすると、偶発的な変更まで「意図した」と説明できてしまうためである。

```bash
python3 scripts/layout_guard.py before.pptx --init-contract qa/edit-contract.json
```

意図した座標変更や追加・削除を `allow` にページ・図形・理由つきで追記する。契約を別の原本へ流用するとハッシュ不一致で停止する。

## 編集前後を比較する

```bash
python3 scripts/layout_guard.py before.pptx after.pptx \
  --contract qa/edit-contract.json --strict --json-out qa/layout-guard.json
```

図形はページ番号ではなく、スライド部品名と `cNvPr id` で追跡する。並べ替え後も同じ既存スライド・図形を比較できる。比較対象はキャンバス、theme、layout/master、位置と寸法、回転・反転、グループ座標系、コネクタ接続、重ね順、placeholder、text frame、段落/run書式、塗りと線、画像crop、表の行列寸法、関連する画像・図表部品である。文言が変わった箱は、編集後の収まりも再計算する。

意図した変更は理由つきで許可する。

```json
{
  "allow": [
    {
      "code": "SHAPE_GEOMETRY_CHANGED",
      "slide": 4,
      "shape": "本文 3",
      "reason": "利用者指定で図を広げ、本文幅を狭めた"
    }
  ]
}
```

この配列を `edit-contract.json` の `allow` に入れる。理由のない登録は設定エラーになる。追加・削除・移動をまとめて全許可せず、ページと図形まで絞る。`--allow` は旧ワークフローとの互換用で、新規編集では使わない。

## 比較だけでは確定できないもの

- 文字列が短くても、受け手に指定書体が無ければ文字幅は変わる。指定書体と代替可能性を報告する
- グラフの軸ラベル、凡例、データラベルは値とアプリで再配置される。系列やカテゴリを変えたらPowerPoint互換描画を見る
- SmartArt、数式、埋め込みオブジェクト、アニメーション、影、グラデーションは簡易描画で再現できない
- 意図した図形追加・削除の意味までは判定できない。変更表とallowを照合する

したがって合格条件は、契約付き `layout_guard --strict`、通常lint、全ページの簡易描画である。図表・SmartArt・画像があればPowerPoint互換描画も必須とし、手段が無い場合は「未確認」で止める。比較検査を通常lintの `--baseline` で代用しない。
