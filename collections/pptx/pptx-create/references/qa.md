# 品質確認 — 3つのゲートと、合格の示し方

合格は「lint の JSON に `passed: true` があり、全ページの描画画像を見て指摘が無い」ことで示す。どちらか一方では合格にしない。「問題ないはず」「概ね良好」は合格ではない。

pptx-review スキルが導入されていれば、別コンテキスト（サブエージェント）で監査させる。生成した本人は自分の期待を見てしまい、描画された事実を見落とす。無ければ本ファイルの手順で行う。

## ゲート1: 内容

テキストを全部書き出し、`outline.md` と突き合わせる。

```python
from pptx import Presentation
p = Presentation("deck/output.pptx")
for i, s in enumerate(p.slides, 1):
    print("=== slide", i)
    for sh in s.shapes:
        if sh.has_text_frame and sh.text_frame.text.strip():
            print(sh.text_frame.text)
    if s.has_notes_slide:
        print("[notes]", s.notes_slide.notes_text_frame.text[:200])
```

確認項目:

- 構成にあるページが全部あり、順序が同じ
- タイトルが主張の一文になっている（ゴーストデッキテストを再実行）
- 数値と出典が構成と一致し、捏造が無い。裏付けの無い数字に「要確認」が付いている
- 仮置き文言（「TODO」「ダミー」「Lorem」「xxx」「ここに」）が残っていない
- 誤字、敬体と常体の混在、全角英数字
- `anti-ai-checklist.md` の文章の兆候（語彙・文体）
- ノートに話す内容と出典がある

## ゲート2: ファイル

```python
# 再オープン
from pptx import Presentation
Presentation("deck/output.pptx")

# lint（pptx-review が導入されている場合。<skills> は導入先のパス。標準ライブラリのみで動く）
import subprocess, sys
subprocess.run([sys.executable, "<skills>/pptx-review/scripts/pptx_lint.py", "deck/output.pptx",
                "--mode", "doc", "--lock", "deck/design-lock.json", "--json-out", "deck/qa/lint.json"])
```

- `errors` は必ず 0 にする。`warnings` は1件ずつ理由を確認し、意図的なものは納品報告に書く。
- lint はパッケージの整合（参照先の無い rels、Content_Types の欠落、仮置き文言）も検査する。XML を直接触った後は必ず通す。
- 意図的に残す指摘（内容の数が3で3列にした、など）は `design-lock.json` の `allow` に理由つきで登録する。口頭で「意図的」と言うだけでは判定から外れない。
- lint が無い環境では、少なくとも再オープン検査と、後述の数値ガードレールを目視で確認する。

## ゲート3: 視覚

`engine-notes.md` の手順で全ページを `render_preview.py` で描画し、**1枚ずつ画像を開いて見る。** 縮小一覧だけで済ませない。デッキ全体の整合（ページをまたいだ位置・余白・リズム）は `--sheet` の一覧画像で見る。

描画は Pillow による簡易描画で、PowerPoint と同じではない。和文の書体が無い環境では和文が灰色バーになるが、位置・折り返し・重なり・余白の確認には足りる。赤枠が付いたページは、はみ出しが実測で出ている。

pptx-review が導入されていない場合の代替は、幾何の表である。各図形の位置・大きさ・文字数・サイズを書き出し、キャンバス外、重なり、箱に対する文字量を数値で確かめる。画像より見落としやすいので、pptx-review の導入を利用者に勧める。

```python
from pptx import Presentation
from pptx.util import Emu
p = Presentation("deck/output.pptx")
W, H = Emu(p.slide_width).inches, Emu(p.slide_height).inches
for i, s in enumerate(p.slides, 1):
    for sh in s.shapes:
        x, y, w, h = (Emu(v).inches for v in (sh.left, sh.top, sh.width, sh.height))
        text = sh.text_frame.text.strip()[:20] if sh.has_text_frame else ""
        flag = "OUT" if x < 0 or y < 0 or x + w > W or y + h > H else ""
        print("slide %d %-22s x=%.2f y=%.2f w=%.2f h=%.2f %s %s" % (i, sh.name, x, y, w, h, flag, text))
```

見る順番（頻度の高い順）:

1. **文字のはみ出し・切れ。** 赤枠のページと、箱の端に触れている文字。簡易描画なので、ぎりぎりは溢れると判断する
2. 要素の重なり（文字に線が乗る、図形が文字を隠す）
3. 出典・フッターが本文と衝突していないか
4. 要素間の間隔が 0.3in 未満、余白が 0.6in 未満
5. 片側に空白が偏る、下 1/3 が空いている
6. 列や箱の端がそろっていない（0.05in のずれも並べると見える）
7. コントラスト不足（淡い地に淡い文字、暗い地に暗いアイコン）
8. `anti-ai-checklist.md` の視覚の兆候
9. 同じレイアウトの3枚連続、同じ形式ファミリーが本文の半分超（lint の `FORM_FAMILY_MONOTONE` と内訳）
10. ページをまたいで、タイトル位置・余白・フッターの高さが一定か（静かな層）
11. **主役がいるか。** 目を細めて（画像を縮小して）見たとき、3〜4段の階層が区別できるか。全部が均一なら主役を大きくする
12. **リズムがあるか。** 密なページの後に余白のページがあるか。濃い面が3回まで置かれているか。主役（図・文・数字・表）が回っているか
13. **消せる要素はないか。** 各ページで最も要らないものを1つ探す（`design-principles.md` 8節）

複数ページを見るときは、1ページ分の画像と lint 結果だけを渡したサブエージェントに判定させ、判定（合格／指摘と修正案）だけを受け取る。自分のコンテキストに画像を溜めない。

## 数値ガードレール

| 項目 | 値 |
|---|---|
| 余白 | 上下左右 0.6in（本文が入り込まない） |
| 要素間の最小間隔 | 0.3in |
| 本文の最小サイズ | 講演型 18pt、資料型 14pt |
| 出典の最小サイズ | 10pt |
| タイトル | 2行まで、全角30字以内 |
| 1枚の文字量 | 講演型 全角120字、資料型 全角250字 |
| 書体 | 和文1種＋欧文1種まで |
| 強調色 | 1ページ1か所 |
| 同一レイアウトの連続 | 2枚まで |
| 同一形式ファミリー | 本文の50%まで |
| 濃い面のページ | 3回まで |
| 表 | 6行×5列まで |
| 図表の系列 | 3本まで |
| コントラスト | 本文 4.5:1、大きな文字 3:1 |

## リポジトリ保守者向けの検査

このコレクション自体を変更したときは、次を走らせる（配布物ではない）。

```bash
python3 collections/pptx/scripts/eval-checks.py           # 検査の精度（出るべき/出てはいけない）
python3 collections/pptx/scripts/audit-consistency.py     # 文書と実装の整合
```

## 修正のループ

1. 指摘をページ番号・要素名・症状・修正案の表にする（`deck/qa/findings.md`）
2. `build.py` を直す。生成物の XML を直接直さない
3. 再生成し、変更したページだけ再描画して確認
4. 新しい指摘が出なくなるまで繰り返す
5. 3周して収束しなければ止め、残った指摘を利用者に報告して判断を仰ぐ

修正がパターン級（このデッキ固有ではなく、次のデッキでも起きる）なら `deck/qa/experience-log.md` に「問題・原因・修正・予防」を1項目ずつ残す。スキル本体は書き換えない。

## 納品報告に書くこと

- lint の要約（errors / warnings と、残した warning の理由）
- 描画画像の場所と、確認した枚数
- 書体の指定と代替描画の有無
- 置いた仮定と「要確認」の数値
- 未解決の指摘と、利用者に判断してほしいこと
