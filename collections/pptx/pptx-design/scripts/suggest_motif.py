#!/usr/bin/env python3
"""主題から署名の候補を出す。標準ライブラリだけで動く。

design-principles.md 5節は「署名は主題から作れ」と要求するが、引き出しが無いと
毎回ゼロから発明することになる。ここは**引き出しを開けるだけ**で、選ばない。

    python3 <skills>/pptx-design/scripts/suggest_motif.py "夜間物流の管制画面。遅延を早く見つけたい"
    python3 <skills>/pptx-design/scripts/suggest_motif.py --json "…"

終了コード: 0=候補あり / 1=一致が弱く候補を出さない / 2=実行できない

**候補は出発点であって既定値ではない。** 採用するには design-lock.md に
「この主題でこの形が意味を持つ理由」を1行書く。書けないなら採用しない。
一致が弱いときは何も出さない——無理に当てはめた署名は、別の主題にも移せて
しまい、それは署名ではない。
"""

import argparse
import json
import sys

EXIT_OK, EXIT_WEAK, EXIT_ERROR = 0, 1, 2
THRESHOLD = 3          # これ未満なら候補を出さない

# 語彙。**完成品ではなく素材**である。増やしてよいが、増やすときは
# mark（静かな標識）・geometry（幾何そのものの1枚）・avoid（効かない用途）を必ず埋める。
MOTIFS = {
    "帳簿": {
        "mark": "締め線（合計の上の一本）",
        "geometry": "行が揃い、最後に締まらない明細",
        "avoid": "金額や収支が主題に無いなら使わない。数字が並ぶだけの表に付けても意味が出ない",
        "keywords": ["収支", "予算", "精算", "原価", "費用", "利益", "会計", "決算", "資金",
                     "投資", "回収", "コスト", "売上"],
    },
    "計器": {
        "mark": "目盛（しきい値に印のある短い軸）",
        "geometry": "しきい値を跨ぐ帯。正常域と異常域が地の濃さで分かれる",
        "avoid": "監視や基準値が主題に無いなら使わない。ただの推移グラフに目盛を足しても飾りになる",
        "keywords": ["監視", "閾値", "しきい値", "異常", "稼働", "計測", "センサー", "アラート",
                     "管制", "運用", "SLA", "可用性", "遅延", "検知"],
    },
    "図面": {
        "mark": "寸法線（両端に印のある補助線）",
        "geometry": "寸法の入った断面。部品の関係が実寸で見える",
        "avoid": "物理的な対象が無いなら使わない。概念図に寸法線を引くと嘘になる",
        "keywords": ["製造", "設計", "公差", "部品", "工場", "組立", "図面", "仕様", "寸法",
                     "設備", "ライン", "歩留"],
    },
    "被覆": {
        "mark": "取得点と未取得点（塗りと白抜きの小さな四角）",
        "geometry": "格子の疎密。埋まっている所と空いている所が一目で分かる",
        "avoid": "網羅性が主題に無いなら使わない。単なる一覧に格子を敷いても情報が増えない",
        "keywords": ["網羅", "カバレッジ", "抜け漏れ", "対応状況", "進捗", "棚卸", "点検",
                     "監査", "適合", "チェック", "取得", "未実施"],
    },
    "経路": {
        "mark": "分岐の印（線が割れる所の小さな点）",
        "geometry": "分水嶺。どこで道が分かれ、どちらに何が流れたか",
        "avoid": "分岐や選択が主題に無いなら使わない。単純な手順に分岐を描くと複雑に見えるだけ",
        "keywords": ["分岐", "判定", "振り分け", "経路", "動線", "選択", "条件", "フロー",
                     "意思決定", "審査", "トリアージ"],
    },
    "地層": {
        "mark": "境界線（層の切り替わりの細い線）",
        "geometry": "積み上がった層の断面。下から順に何が乗ってきたか",
        "avoid": "積み重ねの歴史が主題に無いなら使わない。単なる内訳の積み上げ棒とは違う",
        "keywords": ["沿革", "経緯", "積み上げ", "段階", "履歴", "変遷", "累積", "負債",
                     "技術負債", "移行", "世代"],
    },
}


def score(text, motif):
    """主題の文に対する当てはまりの強さ。部分一致の加点だけで決める。"""
    lowered = text.lower()
    hits = [k for k in motif["keywords"] if k.lower() in lowered]
    return len(hits) * 2 + (1 if len(hits) >= 2 else 0), hits


def suggest(text, limit=3):
    ranked = []
    for name, motif in MOTIFS.items():
        value, hits = score(text, motif)
        if value:
            ranked.append({"name": name, "score": value, "matched": hits,
                           "mark": motif["mark"], "geometry": motif["geometry"],
                           "avoid": motif["avoid"]})
    ranked.sort(key=lambda r: (-r["score"], r["name"]))
    return [r for r in ranked if r["score"] >= THRESHOLD][:limit]


def main(argv=None):
    ap = argparse.ArgumentParser(description="主題から署名の候補を出す（選びはしない）")
    ap.add_argument("subject", help="主題・palette_basis・ブリーフの要点をそのまま渡す")
    ap.add_argument("--json", action="store_true", help="JSON で出す")
    ap.add_argument("--limit", type=int, default=3, help="出す候補の数（既定 3）")
    args = ap.parse_args(argv)

    if not args.subject.strip():
        print("ERROR: 主題が空", file=sys.stderr)
        return EXIT_ERROR

    found = suggest(args.subject, args.limit)
    if args.json:
        print(json.dumps({"subject": args.subject, "candidates": found},
                         ensure_ascii=False, indent=2))
    elif not found:
        print("候補なし。主題に当てはまる語彙が無いので、**主題から自分で作る**。")
        print("design-principles.md 1節の3行（主題は何か／その世界の素材は／紙で使えるのは）に戻る。")
    else:
        print("候補 %d 件（**出発点であって既定値ではない**）:" % len(found))
        for r in found:
            print("\n■ %s（当たった語: %s）" % (r["name"], "、".join(r["matched"])))
            print("  静かな標識: %s" % r["mark"])
            print("  幾何そのものの1枚: %s" % r["geometry"])
            print("  使わない場合: %s" % r["avoid"])
        print("\n採用するには design-lock.md に「この主題でこの形が意味を持つ理由」を1行書く。")
        print("書けないなら採用しない。書けない署名は、別の主題にも移せる装飾である。")
    return EXIT_OK if found else EXIT_WEAK


if __name__ == "__main__":
    sys.exit(main())
