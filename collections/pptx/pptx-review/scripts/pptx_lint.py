#!/usr/bin/env python3
"""PPTX の機械検査。標準ライブラリだけで動く。

検査内容:
  - キャンバス外の要素、余白の侵食、テキスト同士の重なり
  - 文字はみ出しの推定（文字幅の概算。断定ではなく目安）
  - 最小フォントサイズ、書体の混在、和文に ea 書体が無い run
  - 生成AIらしさの兆候: タイトル下の飾り線、上下の色帯、側面の縦帯、
    カード左縁の帯、絵文字、誇張語彙、トピックラベル型タイトル、
    同型レイアウトの連続、文字密度
  - デザインロック（許可された書体・色）との乖離
  - パッケージの整合（参照先の無い rels、Content_Types の欠落）
  - 仮置き文言、空のプレースホルダ、全面画像、整列のずれ、角処理の混在
  - --baseline で以前のレポートを渡すと、元からあった指摘を除いて判定する
  - 死んだ空白（本文領域の被覆率）、文字と塗り面・画像の部分的な衝突
  - design-lock.json の allow に登録した指摘は「意図的」として判定から除く
  - Pillow と書体ファイルがあれば実フォントで折り返しを測る（無ければ概算）

使い方:
  python3 pptx_lint.py deck.pptx [--mode talk|doc] [--lock design-lock.json]
                       [--json-out report.json] [--strict]

標準出力に JSON、標準エラーに要約を出す。errors があれば終了コード 1。
--strict では warnings も失敗扱い。
"""

import argparse
import json
import math
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
EMU = 914400.0

TOPIC_LABEL_TITLES = {
    "まとめ", "概要", "背景", "目的", "課題", "現状", "目次", "アジェンダ", "市場概況",
    "今後の展望", "展望", "ポイント", "要点", "はじめに", "おわりに", "結論", "提案",
    "次のステップ", "検討事項", "考察", "分析", "方針", "施策", "全体像", "サマリー",
    "agenda", "summary", "overview", "key takeaways", "conclusion", "introduction",
    "background", "results", "discussion", "next steps", "thank you",
    "ご清聴ありがとうございました",
}
TOPIC_LABEL_SUFFIXES = ("について", "のご紹介", "の全体像", "の概要", "の背景", "の課題", "の現状")

AI_VOCAB = [
    "シームレス", "革新的", "画期的", "飛躍的", "抜本的", "次世代", "ソリューション",
    "シナジー", "エンパワー", "レバレッジ", "ゲームチェンジャー", "パラダイム",
    "を実現", "を推進", "を加速", "を最大化", "の鍵", "が重要です", "が求められ",
    "に寄与", "を可能に", "包括的", "戦略的な", "効果的な", "多様な", "様々な",
    "の重要性", "の可能性", "のあり方", "高度化", "最適化", "効率化",
    "leverage", "unlock", "empower", "seamless", "cutting-edge", "game-changer",
    "robust", "delve", "landscape", "pivotal", "testament",
]

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF☀-➿⭐⭕✅❌✨⚠]"
)
CJK_RE = re.compile("[　-ヿ㐀-䶿一-鿿豈-﫿＀-￯]")
THEME_FONT_RE = re.compile(r"^\+m[jn]-")

try:  # 任意依存: あれば実フォントで測る
    from PIL import ImageFont as _ImageFont
except Exception:  # pragma: no cover
    _ImageFont = None

_FONT_DIRS = (
    "/usr/share/fonts", "/usr/local/share/fonts", "/System/Library/Fonts", "/Library/Fonts",
    "~/Library/Fonts", "~/.fonts", "~/.local/share/fonts", "C:/Windows/Fonts", "/mnt/data", ".",
)
_CJK_HINTS = {  # 名前の断片 → 優先度（和文専用を高く、和文を含む汎用 CJK を低く）
    "notosansjp": 3, "notoserifjp": 3, "ヒラギノ角ゴ": 3, "ヒラギノ": 3, "yugoth": 3, "meiryo": 3, "msgothic": 3,
    "ipag": 3, "ipaexg": 3, "ipam": 3, "biz-udp": 3, "bizudp": 3, "takao": 3, "vlgothic": 3,
    "notosanscjkjp": 3, "sourcehansansjp": 3, "notosanscjk": 2, "notoserifcjk": 2,
}
_LATIN_HINTS = ("dejavusans.ttf", "arial.ttf", "liberationsans-regular", "helvetica")


def find_fonts():
    """(和文対応の書体パス or None, 欧文の書体パス or None) を返す。"""
    import os
    cjk = latin = None
    best = 0
    for base in _FONT_DIRS:
        base = os.path.expanduser(base)
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for name in files:
                low = name.lower()
                if not low.endswith((".ttf", ".otf", ".ttc")):
                    continue
                path = os.path.join(root, name)
                score = max([v for k, v in _CJK_HINTS.items() if k in low] or [0])
                if score > best:
                    cjk, best = path, score
                if latin is None and any(h in low for h in _LATIN_HINTS):
                    latin = path
    if latin is None:
        try:
            import matplotlib
            cand = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf", "DejaVuSans.ttf")
            if os.path.exists(cand):
                latin = cand
        except Exception:
            pass
    return cjk, latin


class TextMeasurer(object):
    """実フォントがあれば glyph 幅、無ければ概算で文字幅（pt）を返す。"""

    def __init__(self, font_path=None):
        self.font_path = font_path
        self._cache = {}
        self.enabled = bool(font_path and _ImageFont)

    def _font(self, size):
        key = int(round(size * 4))
        if key not in self._cache:
            try:
                self._cache[key] = _ImageFont.truetype(self.font_path, max(int(round(size * 4)), 4))
            except Exception:
                self._cache[key] = None
                self.enabled = False
        return self._cache[key]

    def width(self, text, size):
        font = self._font(size) if self.enabled else None
        if font is None:
            return text_width_pt(text, size)
        try:
            return font.getlength(text) / 4.0
        except Exception:
            return text_width_pt(text, size)
FOOTER_PREFIXES = ("出典", "Source", "出所", "※", "注", "問い合わせ", "お問い合わせ", "連絡先", "ご連絡先",
                   "Contact", "©", "(c)", "Confidential", "機密", "社外秘", "参考")
PLACEHOLDER_RE = re.compile(
    r"lorem|ipsum|\btodo\b|\bxxx+\b|\btbd\b|ダミー|サンプルテキスト|テキストを入力|ここに.{0,8}(入力|記入|挿入)|"
    r"\[insert|\[挿入|click to (add|edit)|要確認",
    re.I,
)


def q(prefix, tag):
    return "{%s}%s" % (NS[prefix], tag)


def fullwidth_len(text):
    total = 0.0
    for ch in text:
        if ch in "\n\r":
            continue
        width = unicodedata.east_asian_width(ch)
        total += 1.0 if width in ("W", "F") else 0.5
    return total


def text_width_pt(text, size_pt):
    total = 0.0
    for ch in text:
        if ch == " ":
            total += size_pt * 0.3
        elif unicodedata.east_asian_width(ch) in ("W", "F"):
            total += size_pt * 1.0
        else:
            total += size_pt * 0.55
    return total


class Package(object):
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        self.names = set(self.zip.namelist())
        self._cache = {}

    def xml(self, name):
        if name not in self._cache:
            self._cache[name] = ET.fromstring(self.zip.read(name))
        return self._cache[name]

    def rels(self, part):
        folder, _, base = part.rpartition("/")
        rel_name = ("%s/_rels/%s.rels" % (folder, base)) if folder else ("_rels/%s.rels" % base)
        return self.rels_file(rel_name, folder)

    def rels_file(self, rel_name, folder):
        result = {}
        if rel_name not in self.names:
            return result
        root = self.xml(rel_name)
        for rel in root.findall(q("rel", "Relationship")):
            target = rel.get("Target")
            if rel.get("TargetMode") == "External":
                continue
            if target.startswith("/"):
                resolved = target.lstrip("/")
            else:
                resolved = normalize((folder + "/" if folder else "") + target)
            result[rel.get("Id")] = (rel.get("Type"), resolved)
        return result

    def related(self, part, type_suffix):
        for _, (rtype, target) in self.rels(part).items():
            if rtype.endswith(type_suffix):
                return target
        return None


def normalize(path):
    parts = []
    for piece in path.split("/"):
        if piece == "..":
            if parts:
                parts.pop()
        elif piece and piece != ".":
            parts.append(piece)
    return "/".join(parts)


def slide_order(pkg):
    pres = pkg.xml("ppt/presentation.xml")
    rels = pkg.rels("ppt/presentation.xml")
    slides = []
    id_list = pres.find(q("p", "sldIdLst"))
    if id_list is None:
        return slides
    for sld in id_list.findall(q("p", "sldId")):
        rid = sld.get(q("r", "id"))
        if rid in rels:
            slides.append(rels[rid][1])
    return slides


def canvas_size(pkg):
    pres = pkg.xml("ppt/presentation.xml")
    size = pres.find(q("p", "sldSz"))
    if size is None:
        return 13.333, 7.5
    return int(size.get("cx")) / EMU, int(size.get("cy")) / EMU


def theme_colors(pkg):
    """theme1.xml の配色（dk1, lt1, accent1 ...）→ HEX。"""
    colors = {}
    name = "ppt/theme/theme1.xml"
    if name not in pkg.names:
        return colors
    scheme = pkg.xml(name).find(".//" + q("a", "clrScheme"))
    if scheme is None:
        return colors
    for node in scheme:
        key = node.tag.split("}")[-1]
        srgb = node.find(q("a", "srgbClr"))
        sysc = node.find(q("a", "sysClr"))
        if srgb is not None:
            colors[key] = srgb.get("val", "000000").upper()
        elif sysc is not None:
            colors[key] = sysc.get("lastClr", "000000").upper()
    return colors


def theme_fonts(pkg):
    name = "ppt/theme/theme1.xml"
    if name not in pkg.names:
        return {}
    root = pkg.xml(name)
    result = {}
    for kind in ("majorFont", "minorFont"):
        node = root.find(".//" + q("a", kind))
        if node is None:
            continue
        latin = node.find(q("a", "latin"))
        ea = node.find(q("a", "ea"))
        result[kind] = {
            "latin": latin.get("typeface") if latin is not None else None,
            "ea": ea.get("typeface") if ea is not None else None,
        }
    return result


def read_xfrm(xfrm):
    if xfrm is None:
        return None
    off = xfrm.find(q("a", "off"))
    ext = xfrm.find(q("a", "ext"))
    if off is None or ext is None:
        return None
    return (
        int(off.get("x")) / EMU,
        int(off.get("y")) / EMU,
        int(ext.get("cx")) / EMU,
        int(ext.get("cy")) / EMU,
    )


def placeholder_key(sp):
    nv = sp.find(q("p", "nvSpPr"))
    if nv is None:
        nv = sp.find(q("p", "nvPicPr"))
    if nv is None:
        nv = sp.find(q("p", "nvGraphicFramePr"))
    if nv is None:
        return None
    ph = nv.find(q("p", "nvPr") + "/" + q("p", "ph"))
    if ph is None:
        return None
    return ph.get("type", "body"), ph.get("idx", "0")


def placeholder_positions(pkg, part):
    """レイアウトとマスターにある placeholder の位置を集める。"""
    positions = {}
    root = pkg.xml(part)
    tree = root.find(".//" + q("p", "spTree"))
    if tree is None:
        return positions
    for sp in tree:
        key = placeholder_key(sp)
        if key is None:
            continue
        xfrm = sp.find(q("p", "spPr") + "/" + q("a", "xfrm"))
        box = read_xfrm(xfrm)
        if box is not None:
            positions[key] = box
    return positions


def inherit_box(key, layout_pos, master_pos):
    if key is None:
        return None
    for table in (layout_pos, master_pos):
        if key in table:
            return table[key]
        for (ptype, pidx), box in table.items():
            if pidx == key[1] and key[1] != "0":
                return box
        for (ptype, pidx), box in table.items():
            if ptype == key[0]:
                return box
    return None


def shape_kind(el):
    tag = el.tag
    if tag == q("p", "pic"):
        return "picture"
    if tag == q("p", "cxnSp"):
        return "connector"
    if tag == q("p", "graphicFrame"):
        data = el.find(".//" + q("a", "graphicData"))
        uri = data.get("uri", "") if data is not None else ""
        if uri.endswith("/table"):
            return "table"
        if uri.endswith("/chart"):
            return "chart"
        return "graphic"
    if tag == q("p", "grpSp"):
        return "group"
    return "shape"


def geometry(el):
    prst = el.find(".//" + q("a", "prstGeom"))
    return prst.get("prst") if prst is not None else None


def has_fill(el):
    sp_pr = el.find(q("p", "spPr"))
    if sp_pr is not None:
        if sp_pr.find(q("a", "noFill")) is not None:
            return False
        if sp_pr.find(q("a", "solidFill")) is not None or sp_pr.find(q("a", "gradFill")) is not None:
            return True
    style = el.find(q("p", "style"))          # テーマ由来の塗り（既定の図形はこちら）
    if style is not None:
        ref = style.find(q("a", "fillRef"))
        if ref is not None and ref.get("idx", "0") != "0":
            return True
    return False


def body_insets(body_pr):
    default = {"l": 0.1, "r": 0.1, "t": 0.05, "b": 0.05}
    if body_pr is None:
        return default
    for side, attr in (("l", "lIns"), ("r", "rIns"), ("t", "tIns"), ("b", "bIns")):
        val = body_pr.get(attr)
        if val is not None:
            default[side] = int(val) / EMU
    return default


def paragraphs(tx_body):
    """段落ごとに (text, sizes, fonts, ea_missing_with_cjk, spacing) を返す。"""
    result = []
    if tx_body is None:
        return result
    for para in tx_body.findall(q("a", "p")):
        text_parts = []
        sizes = []
        fonts = set()
        runs = []
        ea_missing = False
        for run in para:
            if run.tag not in (q("a", "r"), q("a", "fld"), q("a", "br")):
                continue
            if run.tag == q("a", "br"):
                text_parts.append("\n")
                runs.append({"text": "\n", "size": None, "bold": False, "color": None})
                continue
            t = run.find(q("a", "t"))
            text = t.text if t is not None and t.text else ""
            text_parts.append(text)
            rpr = run.find(q("a", "rPr"))
            run_info = {"text": text, "size": None, "bold": False, "color": None}
            if rpr is not None:
                if rpr.get("sz"):
                    sizes.append(int(rpr.get("sz")) / 100.0)
                    run_info["size"] = int(rpr.get("sz")) / 100.0
                run_info["bold"] = rpr.get("b") == "1"
                run_info["color"] = color_of(rpr)
                latin = rpr.find(q("a", "latin"))
                ea = rpr.find(q("a", "ea"))
                if latin is not None and latin.get("typeface"):
                    fonts.add(latin.get("typeface"))
                if ea is not None and ea.get("typeface"):
                    fonts.add(ea.get("typeface"))
                if latin is not None and ea is None and CJK_RE.search(text):
                    ea_missing = True
            runs.append(run_info)
        end = para.find(q("a", "endParaRPr"))
        if not sizes and end is not None and end.get("sz"):
            sizes.append(int(end.get("sz")) / 100.0)
        ppr = para.find(q("a", "pPr"))
        line_spacing = 1.2
        before = after = 0.0
        algn, bullet, mar_l, indent, level = "l", None, 0.0, 0.0, 0
        if ppr is not None:
            algn = ppr.get("algn", "l")
            level = int(ppr.get("lvl", "0") or 0)
            mar_l = int(ppr.get("marL", "0") or 0) / EMU
            indent = int(ppr.get("indent", "0") or 0) / EMU
            bu = ppr.find(q("a", "buChar"))
            if bu is not None:
                bullet = bu.get("char", "•")
            elif ppr.find(q("a", "buAutoNum")) is not None:
                bullet = "#"
            ln = ppr.find(q("a", "lnSpc") + "/" + q("a", "spcPct"))
            if ln is not None and ln.get("val"):
                line_spacing = int(ln.get("val")) / 100000.0
            for tag, target in (("spcBef", "before"), ("spcAft", "after")):
                pts = ppr.find(q("a", tag) + "/" + q("a", "spcPts"))
                if pts is not None and pts.get("val"):
                    if target == "before":
                        before = int(pts.get("val")) / 100.0
                    else:
                        after = int(pts.get("val")) / 100.0
        result.append({
            "text": "".join(text_parts),
            "sizes": sizes,
            "fonts": fonts,
            "runs": runs,
            "ea_missing": ea_missing,
            "line_spacing": line_spacing,
            "before": before,
            "after": after,
            "algn": algn,
            "bullet": bullet,
            "mar_l": mar_l,
            "indent": indent,
            "level": level,
        })
    return result


def color_of(container):
    """solidFill の色を ('srgb', 'RRGGBB') か ('scheme', 'accent1') で返す。無ければ None。"""
    fill = container.find(q("a", "solidFill"))
    if fill is None:
        return None
    srgb = fill.find(q("a", "srgbClr"))
    if srgb is not None:
        return ("srgb", srgb.get("val", "000000").upper())
    scheme = fill.find(q("a", "schemeClr"))
    if scheme is not None:
        mods = {}
        for child in scheme:
            tag = child.tag.split("}")[-1]
            if tag in ("lumMod", "lumOff", "tint", "shade", "alpha"):
                mods[tag] = int(child.get("val", "100000")) / 100000.0
        return ("scheme", scheme.get("val", "tx1"), mods)
    return None


def collect_shapes(pkg, part, layout_pos, master_pos):
    root = pkg.xml(part)
    tree = root.find(".//" + q("p", "spTree"))
    shapes = []
    if tree is None:
        return shapes

    def walk(container, transform):
        for el in container:
            kind = shape_kind(el)
            if kind == "group":
                xfrm = el.find(q("p", "grpSpPr") + "/" + q("a", "xfrm"))
                box = read_xfrm(xfrm)
                child = None
                if xfrm is not None:
                    ch_off = xfrm.find(q("a", "chOff"))
                    ch_ext = xfrm.find(q("a", "chExt"))
                    if ch_off is not None and ch_ext is not None:
                        child = (
                            int(ch_off.get("x")) / EMU,
                            int(ch_off.get("y")) / EMU,
                            int(ch_ext.get("cx")) / EMU,
                            int(ch_ext.get("cy")) / EMU,
                        )
                inner = transform
                if box is not None and child is not None and child[2] > 0 and child[3] > 0:
                    box_abs = apply_transform(box, transform)
                    sx = box_abs[2] / child[2]
                    sy = box_abs[3] / child[3]
                    inner = (box_abs[0], box_abs[1], child[0], child[1], sx, sy)
                walk(el, inner)
                continue
            if el.tag not in (q("p", "sp"), q("p", "pic"), q("p", "cxnSp"), q("p", "graphicFrame")):
                continue
            if kind == "graphic" or kind in ("table", "chart"):
                box = read_xfrm(el.find(q("p", "xfrm")))
            else:
                box = read_xfrm(el.find(q("p", "spPr") + "/" + q("a", "xfrm")))
            key = placeholder_key(el)
            inherited = False
            if box is None:
                box = inherit_box(key, layout_pos, master_pos)
                inherited = box is not None
            if box is not None:
                box = apply_transform(box, transform)
            name_el = el.find(".//" + q("p", "cNvPr"))
            tx_body = el.find(q("p", "txBody"))
            paras = paragraphs(tx_body)
            text = "\n".join(p["text"] for p in paras).strip()
            cnv_sp = el.find(q("p", "nvSpPr") + "/" + q("p", "cNvSpPr"))
            shapes.append({
                "el": el,
                "kind": kind,
                "is_textbox": cnv_sp is not None and cnv_sp.get("txBox") == "1",
                "name": name_el.get("name") if name_el is not None else "",
                "id": name_el.get("id") if name_el is not None else "",
                "box": box,
                "inherited": inherited,
                "placeholder": key,
                "geom": geometry(el),
                "filled": has_fill(el),
                "paragraphs": paras,
                "text": text,
                "body_pr": tx_body.find(q("a", "bodyPr")) if tx_body is not None else None,
            })

    walk(tree, None)
    return shapes


def apply_transform(box, transform):
    if transform is None:
        return box
    ox, oy, cx, cy, sx, sy = transform
    x, y, w, h = box
    return (ox + (x - cx) * sx, oy + (y - cy) * sy, w * sx, h * sy)


def slide_colors(pkg, part):
    root = pkg.xml(part)
    colors = Counter()
    for node in root.iter(q("a", "srgbClr")):
        colors[node.get("val", "").upper()] += 1
    return colors


def slide_text_colors(shapes):
    """文字に使われている色だけを集める。面や線の色は設計判断なので分けて扱う。"""
    colors = set()
    for shape in shapes:
        for para in shape["paragraphs"]:
            for run in para["runs"]:
                if run["text"].strip() and run["color"] and run["color"][0] == "srgb":
                    colors.add(run["color"][1])
    return colors


def notes_present(pkg, part):
    target = pkg.related(part, "/notesSlide")
    if not target:
        return False
    root = pkg.xml(target)
    text = "".join(t.text or "" for t in root.iter(q("a", "t")))
    return bool(text.strip())


def is_title(shape):
    if shape["placeholder"] and shape["placeholder"][0] in ("title", "ctrTitle"):
        return True
    return False


MEASURER = TextMeasurer(None)


def estimate_overflow(shape):
    """(ratio, confidence) を返す。ratio は必要高さ / 箱の高さ。"""
    box = shape["box"]
    if box is None or not shape["text"]:
        return None
    body_pr = shape["body_pr"]
    if body_pr is not None and body_pr.find(q("a", "spAutoFit")) is not None:
        return None
    autofit = body_pr.find(q("a", "normAutofit")) if body_pr is not None else None
    wrap_none = body_pr is not None and body_pr.get("wrap") == "none"
    insets = body_insets(body_pr)
    inner_w = max(box[2] - insets["l"] - insets["r"], 0.1) * 72.0
    inner_h = max(box[3] - insets["t"] - insets["b"], 0.05) * 72.0
    needed = 0.0
    known = True
    last = len(shape["paragraphs"]) - 1
    for idx, para in enumerate(shape["paragraphs"]):
        if not para["sizes"]:
            known = False
            size = 18.0
        else:
            size = max(para["sizes"])
        text = para["text"]
        if wrap_none:
            lines = max(1, text.count("\n") + 1)
        else:
            lines = 0
            for segment in text.split("\n"):
                width = MEASURER.width(segment, size)
                lines += max(1, int(math.ceil(width / inner_w))) if segment else 1
        needed += lines * size * max(para["line_spacing"], 1.0) + para["before"] + (para["after"] if idx < last else 0.0)
    if needed <= 0:
        return None
    confidence = ("measured" if MEASURER.enabled else "estimate") if known else "size-inherited"
    if autofit is not None:
        confidence = "autofit"
    return needed / inner_h, confidence


def lint_slide(index, shapes, canvas, args, lock, deck_state, has_notes):
    cw, ch = canvas
    findings = []
    text_shapes = [s for s in shapes if s["text"] and s["box"] is not None]
    title_shape = next((s for s in shapes if is_title(s)), None)
    if title_shape is None and text_shapes:
        band = [s for s in text_shapes if s["box"][1] < ch * 0.30]
        if band:
            title_shape = max(band, key=lambda s: max((max(p["sizes"]) for p in s["paragraphs"] if p["sizes"]), default=0))
    title_text = title_shape["text"].strip() if title_shape else ""

    def add(code, severity, message, shape=None):
        entry = {"code": code, "severity": severity, "message": message}
        if shape is not None:
            entry["shape"] = shape["name"] or shape["id"]
            if shape["box"]:
                entry["box_in"] = [round(v, 2) for v in shape["box"]]
        findings.append(entry)

    # キャンバスと余白
    for s in shapes:
        box = s["box"]
        if box is None:
            continue
        x, y, w, h = box
        if x < -0.02 or y < -0.02 or x + w > cw + 0.02 or y + h > ch + 0.02:
            add("OUT_OF_CANVAS", "error", "要素がスライドの外に出ている", s)
        elif s["text"] and (x < args.margin or y < args.margin or cw - (x + w) < args.margin or ch - (y + h) < args.margin):
            biggest = max((max(p["sizes"]) for p in s["paragraphs"] if p["sizes"]), default=0)
            footer_like = biggest and biggest <= 11 or s["text"].strip().startswith(FOOTER_PREFIXES)
            if not footer_like:
                add("MARGIN_TIGHT", "info", "テキスト要素が余白 %.2fin の内側に入り込んでいる" % args.margin, s)

    # はみ出し推定
    for s in text_shapes:
        result = estimate_overflow(s)
        if result is None:
            continue
        ratio, confidence = result
        if confidence == "autofit":
            if ratio >= 1.0:
                add("AUTOFIT_SHRINK", "info",
                    "PowerPoint の自動縮小で収める設定（比 %.2f）。縮小後のサイズが下限を割らないか確認" % ratio, s)
            continue
        if ratio >= 1.15:
            add("TEXT_OVERFLOW_LIKELY", "error" if confidence in ("estimate", "measured") else "warning",
                "文字が箱に収まらない見込み（必要高さ/箱高さ=%.2f、%s）。描画画像で確認" % (ratio, confidence), s)
        elif ratio >= 1.02:
            add("TEXT_OVERFLOW_POSSIBLE", "warning",
                "文字が箱にぎりぎり（比 %.2f、%s）。描画画像で確認" % (ratio, confidence), s)

    # テキスト同士の重なり
    for i, a in enumerate(text_shapes):
        for b in text_shapes[i + 1:]:
            inter = overlap_area(a["box"], b["box"])
            smaller = min(a["box"][2] * a["box"][3], b["box"][2] * b["box"][3])
            if smaller > 0 and inter / smaller > 0.05:
                add("TEXT_OVERLAP", "warning", "テキスト要素同士が重なっている: %s / %s" % (a["name"] or a["id"], b["name"] or b["id"]))

    # フォントサイズと書体
    min_font = lock.get("min_font_pt", args.min_font)
    for s in text_shapes:
        scale = 1.0
        if s["body_pr"] is not None:
            autofit = s["body_pr"].find(q("a", "normAutofit"))
            if autofit is not None and autofit.get("fontScale"):
                scale = int(autofit.get("fontScale")) / 100000.0
        for para in s["paragraphs"]:
            if not para["sizes"] or not para["text"].strip():
                continue
            smallest = min(para["sizes"]) * scale
            text = para["text"].strip()
            # フッター帯にある小さな文字は、出典・章表示・ページ番号などの細部として扱う
            in_footer = s["box"] is not None and s["box"][1] >= ch - 0.9
            is_source = (text.startswith(FOOTER_PREFIXES)
                         or text.replace("/", "").replace(" ", "").isdigit()
                         or (in_footer and smallest <= 11.5))
            floor = 9.0 if is_source else min_font
            if smallest < floor:
                add("FONT_TOO_SMALL", "error", "%.1fpt は下限 %.0fpt 未満: 「%s」" % (smallest, floor, text[:30]), s)
                break
        if any(p["ea_missing"] for p in s["paragraphs"]):
            add("NO_EA_FONT", "info", "和文を含む run に latin 書体だけが指定され ea 書体が無い（受け手の環境で代替書体になる）", s)
    fonts = set()
    for s in shapes:
        for para in s["paragraphs"]:
            fonts.update(f for f in para["fonts"] if not THEME_FONT_RE.match(f))
    deck_state["fonts"].update(fonts)
    if lock.get("fonts"):
        bad = sorted(f for f in fonts if f not in lock["fonts"])
        if bad:
            add("DESIGN_LOCK_FONT", "warning", "デザインロックに無い書体: %s" % ", ".join(bad))

    # 生成AIらしさ: 飾り線・色帯・縦帯・カード縁の帯
    title_box = title_shape["box"] if title_shape and title_shape["box"] else None
    rects = [s for s in shapes if s["box"] is not None and s["kind"] in ("shape", "connector") and not s["text"]]
    for s in rects:
        x, y, w, h = s["box"]
        thin_h = h <= 0.06 and w >= 0.8
        thin_v = w <= 0.06 and h >= 0.8
        if thin_h and title_box is not None:
            tx, ty, tw, th = title_box
            if ty + th - 0.15 <= y <= ty + th + 0.6 and w <= cw * 0.7:
                add("ACCENT_LINE_UNDER_TITLE", "warning", "タイトル直下の飾り線（生成AIらしさの典型）。余白か面で区切る", s)
                continue
        if s["filled"] and w >= cw * 0.95 and 0.03 <= h <= 1.5 and (y <= 0.15 or y + h >= ch - 0.15):
            add("COLOR_BAND", "warning", "スライド上端または下端に接した全幅の帯。装飾なら削除する", s)
            continue
        if s["filled"] and h >= ch * 0.95 and 0.1 <= w <= 1.2 and (x <= 0.2 or x + w >= cw - 0.2):
            add("SIDE_STRIPE", "warning", "側面の縦帯。装飾なら削除する", s)
            continue
        if thin_v or (s["filled"] and w <= 0.12 and h >= 0.5):
            for card in shapes:
                if card is s or card["box"] is None or card["kind"] != "shape":
                    continue
                cx_, cy_, cw_, ch_ = card["box"]
                if cw_ > 1.0 and abs(cx_ - x) <= 0.06 and cy_ - 0.05 <= y and y + h <= cy_ + ch_ + 0.05:
                    add("CARD_EDGE_STRIPE", "warning", "カード左縁のアクセント帯（生成AIらしさの典型）。背景の淡い面で区別する", s)
                    break
        if thin_h and w >= cw * 0.9 and not (title_box and y < title_box[1]):
            add("FULL_WIDTH_RULE", "info", "全幅の罫線。フッター罫線なら1本まで", s)

    # 同型カードの横並び
    cards = [s for s in shapes if s["box"] is not None and s["kind"] == "shape" and s["filled"] and s["box"][2] >= 1.5 and s["box"][3] >= 1.0]
    rows = Counter((round(s["box"][1], 1), round(s["box"][2], 1), round(s["box"][3], 1)) for s in cards)
    for (y, w, h), count in rows.items():
        if count >= 3:
            add("CARD_ROW", "info", "同じ大きさの塗り面が %d 枚横並び（y=%.1f）。内容の数がそのまま %d なら可。装飾なら形式を変える" % (count, y, count))

    # 仮置き文言と空のプレースホルダ
    all_text = "\n".join(s["text"] for s in shapes if s["text"])
    hit = PLACEHOLDER_RE.search(all_text)
    if hit:
        add("PLACEHOLDER_TEXT", "error", "仮置き文言が残っている: 「%s」" % hit.group(0))
    for s in shapes:
        if s["placeholder"] and s["kind"] == "shape" and not s["text"]:
            add("EMPTY_PLACEHOLDER", "info", "空のプレースホルダ（編集画面で入力促進文が見える）。使わないなら削除", s)

    # 全面画像
    for s in shapes:
        if s["kind"] == "picture" and s["box"] is not None:
            if s["box"][2] * s["box"][3] >= cw * ch * 0.85:
                # 画像の上にネイティブの文字が載っていれば、裁ち落としの設計であって
                # 「ページごと画像化した」ではない
                over = sum(1 for t in text_shapes if overlap_area(t["box"], s["box"]) > t["box"][2] * t["box"][3] * 0.5)
                if not over:
                    add("FULL_PAGE_PICTURE", "warning",
                        "ページの85%以上を1枚の画像が占め、その上にネイティブの文字が無い。ページごと画像化していないか確認する", s)

    # 整列のずれ（共有されている端から 0.03〜0.15in 外れた端）
    boxed = [s for s in shapes if s["box"] is not None and not (s["box"][2] >= cw * 0.95 and s["box"][3] >= ch * 0.95)]
    for axis, label in ((0, "左端"), (1, "上端")):
        values = [s["box"][axis] for s in boxed]
        for s in boxed:
            v = s["box"][axis]
            others = [o for o in values if abs(o - v) > 0.001]
            for g in set(round(o, 2) for o in others):
                shared = sum(1 for o in others if abs(o - g) <= 0.01)
                if shared >= 2 and 0.03 <= abs(v - g) <= 0.15:
                    add("MISALIGNED", "info", "%sが他の %d 要素の揃え線 %.2fin から %.2fin ずれている" % (label, shared, g, abs(v - g)), s)
                    break

    # 死んだ空白（本文領域の被覆率。表紙・章扉のような要素の少ないページは除く）
    body_shapes = [s for s in boxed if s["box"][1] + s["box"][3] > 1.6 and s["box"][1] < ch - 0.8]
    if len(body_shapes) >= 3 and title_shape is not None:
        top, bottom, left, right = 2.0, ch - 0.9, args.margin, cw - args.margin
        grid = 20
        cell_w, cell_h = (right - left) / grid, (bottom - top) / grid
        covered = 0
        for gy in range(grid):
            for gx in range(grid):
                cx0, cy0 = left + gx * cell_w, top + gy * cell_h
                cx1, cy1 = cx0 + cell_w, cy0 + cell_h
                for s2 in body_shapes:
                    x, y, w, h = s2["box"]
                    if x < cx1 and x + w > cx0 and y < cy1 and y + h > cy0:
                        covered += 1
                        break
        empty = 1.0 - covered / float(grid * grid)
        if empty > 0.55:
            add("DEAD_WHITESPACE", "info", "本文領域の %d%% が空いている。下や右に偏った空白なら、要素を大きくするか分割を見直す" % int(empty * 100))

    # 文字と塗り面・画像・図表の部分的な衝突（容器に収まっているものは除く）
    fills = [s for s in boxed if s["box"] is not None and ((s["kind"] == "shape" and s["filled"] and not s["text"]) or s["kind"] in ("picture", "chart", "table"))]
    for t in text_shapes:
        tx, ty, tw, th = t["box"]
        t_area = tw * th
        for f in fills:
            inter = overlap_area(t["box"], f["box"])
            if t_area <= 0 or inter <= 0:
                continue
            if inter / t_area > 0.05 and inter / t_area < 0.9:
                add("TEXT_SHAPE_COLLISION", "warning", "テキスト「%s」が %s（%s）と部分的に重なっている" % (t["text"][:20], f["name"] or f["id"], f["kind"]), t)
                break

    # 図形の中の文字: 書体とサイズが未指定だと、受け手の環境の既定になって崩れる
    for s in shapes:
        if s["kind"] != "shape" or not s["text"]:
            continue
        has_size = any(p["sizes"] for p in s["paragraphs"])
        has_font = any(f for p in s["paragraphs"] for f in p["fonts"] if not THEME_FONT_RE.match(f))
        if not has_size or not has_font:
            missing = " と ".join(x for x, ok in (("サイズ", has_size), ("書体", has_font)) if not ok)
            where = "テキストボックス" if s.get("is_textbox") else "図形"
            add("SHAPE_TEXT_UNSTYLED", "warning",
                "%sの中の文字に%sの指定が無い。受け手の環境の既定になって崩れる" % (where, missing), s)
        if s.get("is_textbox"):
            continue                              # 枠の無いテキストボックスは上寄せが普通
        anchor = s["body_pr"].get("anchor", "t") if s["body_pr"] is not None else "t"
        biggest = max((max(p["sizes"]) for p in s["paragraphs"] if p["sizes"]), default=0)
        if anchor == "t" and biggest and s["box"][3] > biggest * 1.4 / 72.0 * 2.2:
            add("SHAPE_TEXT_TOP_ANCHORED", "info",
                "図形の中の文字が上に貼り付いている。枠の高さに余りがあるなら上下中央に置く", s)

    # コネクタ: 端点が図形の辺に接しているか、斜めに空間を横切っていないか
    connect_targets = [s for s in shapes if s["box"] is not None and s["kind"] in ("shape", "picture", "table", "chart")
                       and not (s["box"][2] >= cw * 0.95 and s["box"][3] >= ch * 0.95)]
    for s in shapes:
        if s["kind"] != "connector" or s["box"] is None:
            continue
        x, y, w, h = s["box"]
        xfrm = s["el"].find(".//" + q("a", "xfrm"))
        flip_h = xfrm is not None and xfrm.get("flipH") == "1"
        flip_v = xfrm is not None and xfrm.get("flipV") == "1"
        p0 = (x + w if flip_h else x, y + h if flip_v else y)
        p1 = (x if flip_h else x + w, y if flip_v else y + h)
        loose = []
        for point in (p0, p1):
            near = any(tx - 0.12 <= point[0] <= tx + tw + 0.12 and ty - 0.12 <= point[1] <= ty + th + 0.12
                       for tx, ty, tw, th in (t["box"] for t in connect_targets))
            if not near:
                loose.append(point)
        if loose:
            add("CONNECTOR_DETACHED", "warning",
                "線の端点が図形に接していない（%s）。図形の辺から引く" %
                ", ".join("x=%.2f y=%.2f" % pt for pt in loose), s)
        elif (s["geom"] or "").startswith("line") or s["geom"] == "straightConnector1":
            if abs(w) > 0.25 and abs(h) > 0.25:
                add("CONNECTOR_DIAGONAL", "warning",
                    "斜めの直線で図形を結んでいる。段がずれているなら直角に折る", s)

    # 角処理の混在
    big_fills = [s for s in boxed if s["kind"] == "shape" and s["filled"] and s["box"][2] >= 1.0 and s["box"][3] >= 0.8]
    geoms = set(s["geom"] for s in big_fills if s["geom"] in ("rect", "roundRect"))
    if len(geoms) == 2:
        add("CORNER_MIX", "info", "角丸と直角の塗り面が同じページに混在。角処理を1つに統一")

    # 文章の兆候
    if EMOJI_RE.search(all_text):
        add("EMOJI", "warning", "絵文字・記号装飾がある: %s" % "".join(sorted(set(EMOJI_RE.findall(all_text))))[:20])
    hits = [term for term in AI_VOCAB if term in all_text]
    if hits:
        add("AI_VOCAB", "warning", "誇張・抽象語彙: %s。具体的な事実や数値に置き換える" % ", ".join(hits[:8]))
    if title_text and title_shape and title_shape["box"]:
        # 折り返した最終行が極端に短いと、1文字だけ落ちた見出しになる
        body_pr = title_shape["body_pr"]
        if not (body_pr is not None and body_pr.get("wrap") == "none"):
            insets = body_insets(body_pr)
            inner_w = max(title_shape["box"][2] - insets["l"] - insets["r"], 0.1) * 72.0
            size = max((max(p["sizes"]) for p in title_shape["paragraphs"] if p["sizes"]), default=0)
            if size:
                for para in title_shape["paragraphs"]:
                    text = para["text"].strip()
                    if not text or MEASURER.width(text, size) <= inner_w:
                        continue
                    line, last = "", ""
                    for char in text:                       # ch はキャンバス高さなので使わない
                        if MEASURER.width(line + char, size) > inner_w and line:
                            last, line = line, char
                        else:
                            line += char
                    tail = fullwidth_len(line)
                    if last and tail < 3:
                        add("TITLE_ORPHAN_LINE", "warning",
                            "タイトルの最終行が全角%.0f文字分しかない（「%s」）。言い換えて行を整える" % (tail, line[:8]), title_shape)
                    break

    if title_text:
        lowered = title_text.strip().lower().rstrip("。.")
        if lowered in TOPIC_LABEL_TITLES or lowered.endswith(TOPIC_LABEL_SUFFIXES):
            add("TITLE_TOPIC_LABEL", "warning", "タイトルが話題ラベル: 「%s」。主張を一文で書く（表紙・目次・章扉なら無視可）" % title_text[:40])
        if fullwidth_len(title_text) > args.title_max:
            add("TITLE_TOO_LONG", "warning", "タイトルが全角 %.0f 文字相当（上限 %d）" % (fullwidth_len(title_text), args.title_max))
    density = fullwidth_len(all_text)
    if density > args.max_chars:
        add("TEXT_DENSE", "warning", "本文が全角 %.0f 文字相当（目安 %d）。分割するか削る" % (density, args.max_chars))

    # レイアウト署名
    signature = tuple(sorted(
        (s["kind"], round(s["box"][0] * 2) / 2, round(s["box"][1] * 2) / 2, round(s["box"][2] * 2) / 2, round(s["box"][3] * 2) / 2)
        for s in shapes if s["box"] is not None
    ))
    deck_state["signatures"].append(signature)
    for s2 in shapes:
        if s2["text"] or s2["box"] is None or s2["kind"] not in ("shape", "connector"):
            continue
        x, y, w, h = s2["box"]
        thin = h <= 0.1 or w <= 0.1
        in_content = 0.15 < y < ch - 1.0          # 端の帯とフッター罫線は対象外
        if thin and in_content and (w >= 0.8 or h >= 0.8):
            deck_state["decorations"].append((index, round(y, 1), round(x, 1), round(w, 1), round(h, 2)))
    containers = [s for s in shapes if s["box"] is not None and s["kind"] in ("shape", "picture", "table", "chart")
                  and (s["filled"] or s["kind"] != "shape") and s["box"][2] * s["box"][3] < cw * ch * 0.8]

    def inside_container(shape):
        box = shape["box"]
        return any(c is not shape and overlap_area(box, c["box"]) > box[2] * box[3] * 0.8
                   and c["box"][2] * c["box"][3] > box[2] * box[3] * 1.05 for c in containers)

    content_left = [s["box"][0] for s in shapes
                    if s["box"] is not None and s is not title_shape
                    and s["box"][1] > 1.0 and s["box"][1] < ch - 0.9
                    and not (s["box"][2] >= cw * 0.95 and s["box"][3] >= ch * 0.95)
                    and not (s["text"] and s["text"].strip().startswith(FOOTER_PREFIXES))
                    and not inside_container(s)]
    body_runs = Counter()
    for s in text_shapes:
        if s is title_shape or s["text"].strip().startswith(FOOTER_PREFIXES):
            continue
        for para in s["paragraphs"]:
            if para["text"].strip() and para["sizes"]:
                body_runs[round(max(para["sizes"]))] += len(para["text"].strip())
    full_bleed = any(s["box"] is not None and s["filled"] and s["box"][2] >= cw * 0.95 and s["box"][3] >= ch * 0.95
                     for s in shapes if s["kind"] == "shape")
    deck_state["records"].append({
        "index": index,
        "title_box": tuple(round(v, 2) for v in title_box) if title_box else None,
        "title_size": max((max(p["sizes"]) for p in title_shape["paragraphs"] if p["sizes"]), default=None) if title_shape else None,
        "left_x": round(min(content_left), 2) if content_left else None,
        "body_size": body_runs.most_common(1)[0][0] if body_runs else None,
        "family": form_family(shapes, text_shapes, title_shape, cw, ch),
        # 表紙かどうかは、全ページのタイトルサイズが出そろってから決める（consistency_findings）。
        "full_bleed": full_bleed,
    })
    run = deck_state["signatures"][-3:]
    if len(run) == 3 and run[0] == run[1] == run[2] and len(signature) >= 2:
        add("LAYOUT_REPEATED", "warning", "同じレイアウトが3枚連続。主役（図・数字・表・文）を変える")

    return {
        "index": index,
        "title": title_text[:80],
        "shapes": len(shapes),
        "chars_fullwidth": round(density, 1),
        "has_notes": has_notes,
        "findings": findings,
    }


def overlap_area(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def chart_findings(pkg, part):
    """スライドが参照する図表の、描画確認を裏切る設定を探す。"""
    findings = []
    ns_c = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    for _, (rtype, target) in pkg.rels(part).items():
        if not rtype.endswith("/chart") or target not in pkg.names:
            continue
        root = pkg.xml(target)
        for bar in root.iter("{%s}barChart" % ns_c):
            for ser in bar.findall("{%s}ser" % ns_c):
                values = []
                for v in ser.iter("{%s}v" % ns_c):
                    try:
                        values.append(float(v.text))
                    except (TypeError, ValueError):
                        pass
                if any(v < 0 for v in values) and ser.find("{%s}invertIfNegative" % ns_c) is None:
                    findings.append({"code": "CHART_NEGATIVE_RENDER", "severity": "warning",
                                     "message": "%s の棒グラフに負の値があるが invertIfNegative が無い。PowerPoint 以外のビューアで負の棒が上向きに見える。系列に val=0 を明示する" % target.rsplit("/", 1)[-1]})
                    break
    return findings


def form_family(shapes, text_shapes, title_shape, cw, ch):
    """ページの主役で分類する。デッキが同じ形ばかりになっていないかを見るため。"""
    kinds = set(s["kind"] for s in shapes)
    if "chart" in kinds:
        return "図表"
    if "table" in kinds:
        return "表"
    for s in shapes:
        if s["kind"] == "picture" and s["box"] and s["box"][2] * s["box"][3] > cw * ch * 0.2:
            return "画像"
    for s in text_shapes:
        if s is title_shape:
            continue
        if any(sz >= 48 for p in s["paragraphs"] for sz in p["sizes"]):
            return "大きな数字"
    bullets = sum(1 for s in text_shapes for p in s["paragraphs"] if p["bullet"])
    cards = [s for s in shapes if s["kind"] == "shape" and s["filled"] and s["box"]
             and s["box"][2] >= 1.5 and s["box"][3] >= 1.0
             and not (s["box"][2] >= cw * 0.95 and s["box"][3] >= ch * 0.95)]
    if len(cards) >= 2:
        return "カード・面"
    if bullets >= 3:
        return "箇条書き"
    body = [s for s in text_shapes if s is not title_shape]
    if len(body) >= 2:
        xs = sorted(round(s["box"][0], 1) for s in body)
        if xs[-1] - xs[0] > cw * 0.25:
            return "多段"
    return "文章"


def color_distance(a, b):
    try:
        return sum(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) for i in (0, 2, 4))
    except ValueError:
        return 999


def consistency_findings(report_slides, deck_state):
    """ページ間の統一性。多数派から外れたページに指摘を付ける（4枚以上のとき）。"""
    records = deck_state["records"]
    # 表紙・章扉の判定: 全面塗り、上部帯にタイトルが無い、またはタイトルが本文ページの多数派より
    # 目立って大きいページ。1枚目かどうかでは決めない（本文から始まるデッキがあるため）。
    titled = [r for r in records if not r["full_bleed"] and r["title_box"] and r["title_size"]]
    majority_title = Counter(r["title_size"] for r in titled).most_common(1)[0][0] if titled else None
    for r in records:
        r["is_cover"] = bool(r["full_bleed"] or not r["title_box"] or
                             (majority_title and r["title_size"] and r["title_size"] >= majority_title * 1.25))
    body = [r for r in records if not r["is_cover"]]
    if len(body) < 4:
        return
    by_index = {s["index"]: s for s in report_slides}

    def add(index, code, message, severity="warning"):
        by_index[index]["findings"].append({"code": code, "severity": severity, "message": message})

    # タイトルの位置と大きさ
    def has_majority(n):
        """過半数かつ3枚以上のときだけ「多数派」と認める。3対3で割れたら咎めない。"""
        return n >= 3 and n * 2 > len(body)

    boxes = Counter((r["title_box"][0], r["title_box"][1], r["title_box"][2]) for r in body if r["title_box"])
    if boxes:
        (mx, my, mw), n = boxes.most_common(1)[0]
        if has_majority(n):
            for r in body:
                if r["title_box"] and (abs(r["title_box"][0] - mx) > 0.1 or abs(r["title_box"][1] - my) > 0.1 or abs(r["title_box"][2] - mw) > 0.2):
                    add(r["index"], "TITLE_POSITION_DRIFT",
                        "タイトルの位置・幅 (x=%.2f, y=%.2f, w=%.2f) が多数派 (x=%.2f, y=%.2f, w=%.2f) と違う" % (r["title_box"][0], r["title_box"][1], r["title_box"][2], mx, my, mw))
    sizes = Counter(r["title_size"] for r in body if r["title_size"])
    if sizes:
        ms, n = sizes.most_common(1)[0]
        if has_majority(n):
            for r in body:
                if r["title_size"] and abs(r["title_size"] - ms) > 0.5:   # 1pt の差も型スケール外れとして扱う
                    add(r["index"], "TITLE_SIZE_DRIFT", "タイトルが %.0fpt。多数派は %.0fpt" % (r["title_size"], ms))
    # 本文の左端
    lefts = Counter(r["left_x"] for r in body if r["left_x"] is not None)
    if lefts:
        ml, n = lefts.most_common(1)[0]
        if has_majority(n):
            for r in body:
                if r["left_x"] is not None and abs(r["left_x"] - ml) > 0.15:
                    add(r["index"], "MARGIN_DRIFT", "本文の左端が x=%.2f。多数派は x=%.2f" % (r["left_x"], ml))
    # 本文サイズ: 型スケールに無く、かつ既存サイズに「惜しい」ものだけを咎める。
    # 明確に違うサイズ（密度を変える設計判断）は残す。
    scale = sorted(sz for sz, n in Counter(r["body_size"] for r in body if r["body_size"]).items() if n >= 2)
    if scale:
        for r in body:
            sz = r["body_size"]
            if not sz or sz in scale:
                continue
            close = [v for v in scale if 0 < abs(v - sz) <= 3]
            if close:
                add(r["index"], "BODY_SIZE_DRIFT",
                    "本文が %dpt。型スケールの %dpt に寄せる" % (sz, min(close, key=lambda v: abs(v - sz))))

    # 装飾の反復: 本文領域の同じ位置に繰り返される飾り（罫線・帯）は、内容を運ばない定型
    body_indexes_all = set(r["index"] for r in body)
    deco = Counter(d[1:] for d in deck_state.get("decorations", []) if d[0] in body_indexes_all)
    if deco and len(body) >= 4:
        (dy, dx, dw, dh), n = deco.most_common(1)[0]
        if n * 2 > len(body):
            for index in sorted(d[0] for d in deck_state["decorations"] if d[1:] == (dy, dx, dw, dh)):
                add(index, "DECORATION_REPEATED",
                    "本文領域の同じ位置（y=%.1f, 幅%.1f）に飾りが %d/%d ページで繰り返されている。内容を運ばないなら消す" % (dy, dw, n, len(body)))

    # 形式ファミリーの偏り: 同じ主役ばかりのデッキを咎める（乖離の裏返し）
    families = Counter(r["family"] for r in body if r["family"])
    if families and len(body) >= 5:
        top, n = families.most_common(1)[0]
        tally = " / ".join("%s %d" % kv for kv in families.most_common())
        deck_state["variety"] = {"tally": tally, "dominant": top, "share": round(n / float(len(body)), 2)}
    # 色の語彙（2ページ以上で使われる色）
    # 文字色: 既存の文字色に「近いが違う」色だけを指摘する。面や線の淡い色差は設計判断として扱わない
    body_indexes = set(r["index"] for r in body)
    color_pages = Counter(c for cs in deck_state["slide_colors"] for c in cs)
    palette = [c for c, n in color_pages.items() if n >= 2 and len(c) == 6]
    if palette:
        for i, cs in enumerate(deck_state["slide_colors"], start=1):
            if i not in body_indexes:
                continue
            near = []
            for c in sorted(cs):
                if not c or len(c) != 6 or c in palette:
                    continue
                closest = min(palette, key=lambda p: color_distance(c, p))
                if color_distance(c, closest) <= 40:
                    near.append((c, closest))
            if near:
                add(i, "PALETTE_DRIFT",
                    "文字色 %s が既存の %s に近いが違う。同じ色にそろえる" % (", ".join(a for a, _ in near), ", ".join(b for _, b in near)))


def package_findings(pkg, slides):
    findings = []
    for name in sorted(pkg.names):
        if not name.endswith(".rels"):
            continue
        folder = name.split("/_rels/")[0] if "/_rels/" in name else ""
        owner = name.replace("/_rels/", "/").replace("_rels/", "")[:-5]
        for rid, (rtype, target) in pkg.rels_file(name, folder).items():
            if target not in pkg.names:
                findings.append({"code": "BROKEN_RELATIONSHIP", "severity": "error",
                                 "message": "%s の %s が指す %s が存在しない（開けないか修復ダイアログが出る）" % (owner, rid, target)})
    try:
        types = pkg.zip.read("[Content_Types].xml").decode("utf-8", "ignore")
    except KeyError:
        findings.append({"code": "CONTENT_TYPES_MISSING", "severity": "error", "message": "[Content_Types].xml が無い"})
        return findings
    for part in slides:
        if 'PartName="/%s"' % part not in types:
            findings.append({"code": "CONTENT_TYPE_MISSING", "severity": "error",
                             "message": "%s が [Content_Types].xml に登録されていない" % part})
    return findings


def load_baseline(path):
    if not path:
        return set()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    keys = set()
    for s in data.get("slides", []):
        for f in s.get("findings", []):
            keys.add((s.get("title", "")[:40], f.get("code"), f.get("shape", "")))
    for f in data.get("deck_findings", []):
        keys.add(("", f.get("code"), ""))
    return keys


def load_lock(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    lock = {}
    if isinstance(data.get("fonts"), list):
        lock["fonts"] = set(data["fonts"])
    if isinstance(data.get("colors"), list):
        lock["colors"] = set(c.upper().lstrip("#") for c in data["colors"])
    if isinstance(data.get("min_font_pt"), (int, float)):
        lock["min_font_pt"] = float(data["min_font_pt"])
    if isinstance(data.get("allow"), list):
        lock["allow"] = [a for a in data["allow"] if isinstance(a, dict) and a.get("code")]
    return lock


def apply_allow(report_slides, deck_findings, allow):
    """登録済みの指摘に allowed=true と理由を付ける。slide 省略は全ページ。"""
    count = 0
    for entry in allow:
        code, slide, reason = entry.get("code"), entry.get("slide"), entry.get("reason", "")
        targets = report_slides if slide is None else [s for s in report_slides if s["index"] == slide]
        for s in targets:
            for f in s["findings"]:
                if f["code"] == code and not f.get("allowed"):
                    f["allowed"], f["reason"] = True, reason
                    count += 1
        if slide is None:
            for f in deck_findings:
                if f["code"] == code and not f.get("allowed"):
                    f["allowed"], f["reason"] = True, reason
                    count += 1
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description="PPTX の機械検査（標準ライブラリのみ）")
    parser.add_argument("pptx")
    parser.add_argument("--mode", choices=("talk", "doc"), default="doc",
                        help="talk=講演型（注記を含む下限14pt、全角250字）、doc=資料型（下限12pt、全角400字）")
    parser.add_argument("--lock", help="design-lock.json（fonts / colors / min_font_pt）")
    parser.add_argument("--min-font", type=float, help="出典以外の全文字の最小サイズ pt（mode の既定を上書き。本文の下限は目視で確認）")
    parser.add_argument("--max-chars", type=int, help="1枚あたりの全角換算文字数の上限")
    parser.add_argument("--title-max", type=int, default=36, help="タイトルの全角換算文字数の上限（storyline.md の予算 30 字に少し余裕）")
    parser.add_argument("--margin", type=float, default=0.4, help="テキストが侵食してはいけない余白 in")
    parser.add_argument("--json-out", help="JSON レポートの書き出し先")
    parser.add_argument("--baseline", help="編集前のレポート JSON。そこにある指摘は inherited として判定から除く")
    parser.add_argument("--font", help="折り返し計測に使う書体ファイル（.ttf/.otf）。省略時は和文対応の書体を探す")
    parser.add_argument("--no-consistency", action="store_true", help="ページ間の統一性検査（タイトル位置・左端・サイズ・色の乖離）を行わない")
    parser.add_argument("--strict", action="store_true", help="warning も失敗扱い")
    args = parser.parse_args(argv)

    if args.min_font is None:
        args.min_font = 14.0 if args.mode == "talk" else 12.0
    if args.max_chars is None:
        args.max_chars = 250 if args.mode == "talk" else 400

    try:
        pkg = Package(args.pptx)
    except (zipfile.BadZipFile, OSError) as exc:
        print("ERROR: %s を開けない: %s" % (args.pptx, exc), file=sys.stderr)
        return 2
    if "ppt/presentation.xml" not in pkg.names:
        print("ERROR: presentation.xml が無い。PPTX ではない", file=sys.stderr)
        return 2

    lock = load_lock(args.lock)
    baseline = load_baseline(args.baseline)
    if not slide_order(pkg):
        print("ERROR: スライドが1枚も無い", file=sys.stderr)
        return 2
    font_path = args.font
    if font_path is None and _ImageFont is not None:
        font_path = find_fonts()[0]
    MEASURER.__init__(font_path if (_ImageFont and font_path) else None)
    canvas = canvas_size(pkg)
    slides = slide_order(pkg)
    deck_state = {"fonts": set(), "signatures": [], "colors": Counter(), "records": [], "slide_colors": [],
                  "variety": None, "decorations": []}
    report_slides = []
    deck_findings = package_findings(pkg, slides)
    for index, part in enumerate(slides, start=1):
        if part not in pkg.names:
            report_slides.append({"index": index, "title": "", "shapes": 0, "chars_fullwidth": 0, "has_notes": False,
                                  "findings": [{"code": "SLIDE_PART_MISSING", "severity": "error",
                                                "message": "%s が ZIP 内に無い" % part}]})
            continue
        layout = pkg.related(part, "/slideLayout")
        if layout and layout not in pkg.names:
            layout = None
        master = pkg.related(layout, "/slideMaster") if layout else None
        if master and master not in pkg.names:
            master = None
        layout_pos = placeholder_positions(pkg, layout) if layout else {}
        master_pos = placeholder_positions(pkg, master) if master else {}
        shapes = collect_shapes(pkg, part, layout_pos, master_pos)
        colors_here = slide_colors(pkg, part)
        deck_state["colors"].update(colors_here)
        deck_state["slide_colors"].append(slide_text_colors(shapes))
        slide_report = lint_slide(index, shapes, canvas, args, lock, deck_state, notes_present(pkg, part))
        slide_report["findings"].extend(chart_findings(pkg, part))
        report_slides.append(slide_report)

    if not args.no_consistency:
        consistency_findings(report_slides, deck_state)
    fonts = sorted(deck_state["fonts"])
    variety = deck_state.get("variety")
    if variety and variety["share"] > 0.5:
        deck_findings.append({"code": "FORM_FAMILY_MONOTONE", "severity": "warning",
                              "message": "本文の %d%% が「%s」。主役を回す（内訳: %s）" % (
                                  int(variety["share"] * 100), variety["dominant"], variety["tally"])})
    if len(fonts) > 3:
        deck_findings.append({"code": "MIXED_FONTS", "severity": "warning",
                              "message": "書体が %d 種類: %s。和文1種＋欧文1種までに絞る" % (len(fonts), ", ".join(fonts))})
    if lock.get("colors"):
        bad = sorted(c for c in deck_state["colors"] if c and c not in lock["colors"])
        if bad:
            deck_findings.append({"code": "DESIGN_LOCK_COLOR", "severity": "warning",
                                  "message": "デザインロックに無い色: %s" % ", ".join(bad[:12])})
    signatures = [s for s in deck_state["signatures"] if len(s) >= 2]
    if len(signatures) >= 6:
        common, count = Counter(signatures).most_common(1)[0]
        if count / float(len(signatures)) > 0.5:
            deck_findings.append({"code": "LAYOUT_MONOTONE", "severity": "warning",
                                  "message": "同一レイアウトが本文スライドの %d%% を占める。形式を回す" % int(100 * count / len(signatures))})
    notes_count = sum(1 for s in report_slides if s["has_notes"])

    inherited = 0
    if baseline:
        for s in report_slides:
            for f in s["findings"]:
                if (s["title"][:40], f["code"], f.get("shape", "")) in baseline:
                    f["baseline"] = True
                    inherited += 1
        for f in deck_findings:
            if ("", f["code"], "") in baseline:
                f["baseline"] = True
                inherited += 1

    allowed = apply_allow(report_slides, deck_findings, lock.get("allow", []))

    def skip(f):
        return f.get("baseline") or f.get("allowed")

    def count(severity):
        n = sum(1 for s in report_slides for f in s["findings"] if f["severity"] == severity and not skip(f))
        return n + sum(1 for f in deck_findings if f["severity"] == severity and not skip(f))

    errors, warnings = count("error"), count("warning")
    passed = errors == 0 and (not args.strict or warnings == 0)

    report = {
        "file": args.pptx,
        "mode": args.mode,
        "canvas_in": [round(canvas[0], 3), round(canvas[1], 3)],
        "slide_count": len(slides),
        "theme_fonts": theme_fonts(pkg),
        "fonts_used": fonts,
        "colors_used": [c for c, _ in deck_state["colors"].most_common(16)],
        "notes_present": "%d/%d" % (notes_count, len(slides)),
        "form_families": (deck_state.get("variety") or {}).get("tally"),
        "deck_findings": deck_findings,
        "slides": report_slides,
        "summary": {"errors": errors, "warnings": warnings, "strict": args.strict,
                    "inherited_from_baseline": inherited, "allowed_by_lock": allowed},
        "measurement": {"font": MEASURER.font_path if MEASURER.enabled else None,
                        "mode": "measured" if MEASURER.enabled else "estimate"},
        "passed": passed,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(output + "\n")
    print(output)

    print("--- pptx_lint: %d slides, %d errors, %d warnings, passed=%s%s%s (text: %s)" % (
        len(slides), errors, warnings, passed,
        (", %d inherited from baseline" % inherited) if baseline else "",
        (", %d allowed by lock" % allowed) if allowed else "",
        "measured with " + os.path.basename(MEASURER.font_path) if MEASURER.enabled else "estimated"), file=sys.stderr)
    for s in report_slides:
        for f in s["findings"]:
            if f["severity"] in ("error", "warning") and not skip(f):
                print("  slide %d [%s] %s: %s" % (s["index"], f["severity"], f["code"], f["message"]), file=sys.stderr)
    for f in deck_findings:
        if not skip(f):
            print("  deck [%s] %s: %s" % (f["severity"], f["code"], f["message"]), file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
