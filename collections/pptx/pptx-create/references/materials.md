# 素材の道具立て — 何を使い、無いときどうするか

写真・図・元資料をデッキに入れる前の処理を、**作業ごとに道具を1つ指名**して書く。「環境にあるライブラリを使ってよい」と書くと、実行のたびに違う道具が選ばれ、結果が揃わない。

**前提は2つ。**

1. **依存を増やせない環境がある。** 追加導入を試みない。`importlib` で有無を確かめ、無ければ縮退する道をここに書いてある。
2. **出力はネイティブに保つ。** ここでの加工は、素材をネイティブ要素（`add_picture` の写真、`add_chart` の図表、`add_shape` の図形）に載せるための前処理であって、ページを画像にするためのものではない。

## 1. 作業と道具

| 作業 | 道具 | 無いとき |
|---|---|---|
| 写真の回転・色空間・縮小の正規化 | **Pillow**（`PIL`） | 描画確認もできない環境なので、素材を整えた形で利用者にもらう |
| 参考画像から基準色を取る | **`pptx-design` の `generate_palette.py`**（内部で Pillow） | 主題から言葉で導く（`pptx-design` の `design-principles.md` 1節） |
| `.docx` / `.xlsx` / `.pptx` から文字を取る | **標準ライブラリ**（`zipfile` + `xml.etree`） | 常に使える。第三者ライブラリを探しに行かない |
| `.pdf` から文字を取る | 抽出ライブラリを probe する | **無いのが既定。** 利用者に必要な箇所をテキストで渡してもらう |
| SVG を置く | **置かない。** ネイティブ図形に組み直す | — |
| アイコン・ダイアグラム | **骨格の図形**（`box_text` / `connect` / `rect`） | — |
| 数表を Excel として添える | **XlsxWriter** | 表は `add_table` でデッキ内に入れる |

道具の有無は、使う直前にこれで確かめる。

```python
import importlib

def have(name):
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False
```

`have()` が False のときは、上の表の「無いとき」に従い、**何を諦めたかを納品報告に書く**。黙って別の道具を探しに行かない。

## 2. 写真の正規化（Pillow）

**置く前に必ず通す。** 通さないと、次の3つが起きる。

```python
from PIL import Image, ImageOps

def normalize_photo(src, dst, max_px=2400):
    """置く前の下ごしらえ。回転・色空間・画素数・DPI を揃える。"""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)      # 回転を実際の画素に焼く
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")            # CMYK・16bit・パレットを揃える
        im.thumbnail((max_px, max_px))        # 版面に対して過剰な画素を落とす
        im.save(dst, dpi=(96, 96))            # DPI を書かないと置かれる寸法が変わる
    return dst
```

- **EXIF の回転は python-pptx が見ない。** スマホ写真は横倒しのまま入る（実測: Orientation=6 の 600×400 が、回転されずに横長のまま置かれた）。`exif_transpose()` で画素そのものを回す。
- **CMYK JPEG も 16bit PNG も、python-pptx はエラーを出さずにバイト列をそのまま埋める。** 素材の色空間がそのまま受け手に渡るので、置く前に `RGB` に揃える。
- **DPI で置かれる寸法が変わる。** `add_picture` に寸法を渡さないと、素材の DPI メタデータから実寸が決まる。実測では同じ 600×400px が 72dpi で 8.33in、96dpi で 6.25in、300dpi で 2.00in になった。骨格の `picture()` は必ず幅と高さを渡すのでこの影響を受けない。**`add_picture` を直に呼ばない。**
- 画素数の上限は版面から決める。13.333in 幅のページに全面で置く写真でも、96dpi 換算で 1280px、印刷を考えても 2400px で足りる。元の 4000px をそのまま入れるとファイルだけが太る。

## 3. 参考画像から基準色を取る

**自分で書かない。** `pptx-design` の `generate_palette.py` が `palette-intent.json` の `reference_images` を読んで基準色を1つ選ぶ。手順は `pptx-design` の `palette-automation.md`。

同じ処理を手で書くと、スクリプトと結果がずれる。スクリプトは単純に多い色を取るのではなく、**ほぼ黒・ほぼ白・彩度の低い色を落としてから、色みの強さで重みづけして選ぶ**——最も面積の広い色は地であって主色ではないことが多いためである。

取れるのは基準色1つで、7色のパレットではない。派生とコントラスト調整もスクリプトの仕事である。

## 4. 元資料から文字を取る

`.docx` / `.xlsx` / `.pptx` は ZIP と XML なので、**第三者ライブラリは要らない。**

```python
import zipfile
from xml.etree import ElementTree as ET

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"    # pptx の本文
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"   # docx の本文

def ooxml_text(path, part_prefix, tag):
    """OOXML から文字だけを取り出す。**読むだけ。** 書き戻しには使わない。"""
    out = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(n for n in z.namelist() if n.startswith(part_prefix)):
            root = ET.fromstring(z.read(name))
            out.extend(t.text for t in root.iter(tag) if t.text)
    return out

# ooxml_text("src.pptx", "ppt/slides/slide", A)
# ooxml_text("src.docx", "word/document", W)
```

`ElementTree` を使ってよいのは**読み出しだけ**である。OOXML をこれで読み書きすると名前空間の接頭辞が書き換わり、ファイルが壊れる。編集は python-pptx か lxml で行う（`pptx-edit` の `ooxml-editing.md`）。

`.pdf` には標準ライブラリの道が無い。抽出ライブラリを `have()` で確かめ、無ければ**利用者に必要な箇所をテキストで渡してもらう**。画像化した PDF から文字を起こそうとしない。

## 5. SVG は置かず、図形に組み直す

`add_picture` に SVG を渡すと `UnidentifiedImageError` で落ちる。EMF も読めない。

**変換ライブラリを探しに行かない。** 変換できたとしても、結果は編集できない画像になり、「ネイティブを守る」に反する。SVG で渡された図は、**何を表しているかを読み取って骨格の図形で組み直す**——箱と文字は `box_text()`、つなぎは `connect()`、面は `rect()`。組み直せない複雑さなら、その図はそのページに要るのかを疑う。

例外は写真とロゴだけである。ロゴが SVG でしか無いなら、利用者に PNG を求める。

## 6. 置いたあとの確認

- 描画確認（`render_preview.py`）で、写真の向き・切り落とし位置・文字とのコントラストを見る。
- 写真の上に文字を置いたなら、薄い面（`scrim()`）が入っているかを描画画像で確かめる。
- 納品報告に、**加工した素材と、その加工内容**（回転の修正、縮小、色空間の変換）を書く。元素材と見え方が変わっているため。
