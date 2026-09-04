# 試作デッキによる較正記録（2026-09-04）

pptx-create の `engine-notes.md` の骨格コードをそのまま使い、8枚（表紙・主張＋証拠（図表）・数字・比較・表・一文・手順・結論）を生成し、pptx-review の lint と LibreOffice 描画で確認した。以下は、その結果スキルに反映した変更。

| 観察 | 反映先 |
|---|---|
| タイトル帯 1.1in は 28pt 2行で窮屈 | グリッドをタイトル y 0.6〜2.0（高さ 1.4）、本文開始 2.2 に変更。箱の高さは (行数+0.5)×サイズ×1.4÷72 |
| 表紙タイトルの箱に1行分の余裕を足すと副題と重なる | `text_height()` の余裕を半行に |
| 84pt の数字は1行でも箱 1.7in 必要。説明を上端で揃えると段違いに見える | layout-catalog #7: 文脈は数字と下端を揃え、直下の説明は 0.3 空ける |
| 表の見出しが左揃えで数字列と合わない | layout-catalog #9: 見出しは列の本文と同じ揃え |
| 手順の番号だけ下がって見える | layout-catalog #10: 同じ高さの箱に anchor=MIDDLE |
| python-pptx の棒グラフで負の値が LibreOffice では上向きに描かれる（−1.9 が +1.9 に見える） | engine-notes: `bar_chart()` が `invertIfNegative val=0` を明示し、負値時は項目名を LOW に。lint に CHART_NEGATIVE_RENDER を追加 |
| 出典行・問い合わせ行が下限と余白の検査に引っかかる | lint: フッター系の接頭辞と 11pt 以下は余白検査から除外、下限 9pt |
| 推定器が最終段落の段落後間隔を数えて 1.05 と出る | lint: 最終段落の spcAft を数えない。POSSIBLE の閾値を 1.02 に |
| 34字のタイトルで2行目が1文字になる | storyline: 2行目が5文字未満なら言い換える。lint の title-max 既定を 36 に |

最終状態: `--strict` で 0 errors / 0 warnings。描画 8 枚を目視し、指摘なし。

再現手順は scratchpad 側の `run_trial.py`（恒久保存はしていない）。同種の較正を行うときは、`engine-notes.md` の python ブロックを抜き出して実行し、lint と描画で確認する。
