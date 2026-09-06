#!/usr/bin/env python3
"""生成前のスライド実装仕様書を検査する。標準ライブラリのみ。"""

import argparse
import json
import pathlib
import re
import sys

REQUIRED = ("function", "regions", "content_bindings", "overflow", "design_intent")
OVERFLOW = {"place", "fit_text", "fixed-native", "not-applicable"}
PRIORITY = {"cover", "dense", "data", "standard"}
COVER_ROLES = {"cover", "表紙", "title", "タイトル"}
DATA_EXHIBITS = ("chart", "table", "picture", "graph", "図表", "グラフ", "表", "写真")


def engine_functions():
    path = pathlib.Path(__file__).resolve().parents[1] / "references" / "engine-notes.md"
    match = re.search(r"```python\n(.*?)```", path.read_text(encoding="utf-8"), re.S)
    return set(re.findall(r"^def (slide_[a-z0-9_]+)\(", match.group(1), re.M)) if match else set()


def check(spec, outline, preview_prefix=None):
    findings = []
    slides = spec.get("slides") if isinstance(spec, dict) else None
    pages = outline.get("pages") if isinstance(outline, dict) else None
    if not isinstance(slides, list) or not slides:
        return ["slides が空。全ページを1ページ1オブジェクトで書く"]
    if not isinstance(pages, list) or not pages:
        return ["outline の pages が空"]
    if len(slides) != len(pages):
        findings.append("ページ数が outline=%d / implementation-spec=%d" % (len(pages), len(slides)))
    known = engine_functions()
    outline_by_n = {p.get("n", i): p for i, p in enumerate(pages, 1)}
    seen = set()
    preview_roles = set()
    preview_pages = set()
    for i, slide in enumerate(slides, 1):
        n = slide.get("n", i)
        if n in seen:
            findings.append("ページ %s: n が重複" % n)
        seen.add(n)
        page = outline_by_n.get(n)
        if page is None:
            findings.append("ページ %s: outline に対応ページが無い" % n)
            continue
        title = str(slide.get("title", "")).strip()
        if title != str(page.get("title", "")).strip():
            findings.append("ページ %s: title が outline と一致しない" % n)
        archetype = str(slide.get("archetype", "")).strip()
        if archetype != str(page.get("archetype", "")).strip():
            findings.append("ページ %s: archetype が outline と一致しない" % n)
        impl = slide.get("implementation")
        if not isinstance(impl, dict):
            findings.append("ページ %s: implementation が無い" % n)
            continue
        for key in REQUIRED:
            if key not in impl or impl[key] in (None, "", [], {}):
                findings.append("ページ %s: implementation.%s が空" % (n, key))
        function = str(impl.get("function", "")).strip()
        if known and function and function not in known:
            findings.append("ページ %s: function %s は骨格に無い" % (n, function))
        if impl.get("overflow") not in OVERFLOW:
            findings.append("ページ %s: overflow は %s から選ぶ" % (n, "/".join(sorted(OVERFLOW))))
        regions = impl.get("regions")
        if not isinstance(regions, list) or any(not str(v).strip() for v in regions):
            findings.append("ページ %s: regions は空でない文字列の配列" % n)
        bindings = impl.get("content_bindings")
        if not isinstance(bindings, dict) or any(not str(k).strip() or not str(v).strip()
                                                 for k, v in bindings.items()):
            findings.append("ページ %s: content_bindings は領域→内容の対応表" % n)
        priority = slide.get("preview_priority", "standard")
        if priority not in PRIORITY:
            findings.append("ページ %s: preview_priority が不正" % n)
        preview_roles.add(priority)
        if priority != "standard":
            preview_pages.add(n)
    cover_pages = {p.get("n", i) for i, p in enumerate(pages, 1)
                   if str(p.get("role", "")).strip().lower() in COVER_ROLES}
    data_pages = {p.get("n", i) for i, p in enumerate(pages, 1)
                  if any(term in str(p.get("exhibit", "")).strip().lower()
                         for term in DATA_EXHIBITS)}
    required_preview = {"dense"} if len(pages) > 1 else set()
    if cover_pages:
        required_preview.add("cover")
    if data_pages:
        required_preview.add("data")
    missing = required_preview - preview_roles
    if missing:
        findings.append("事前previewの代表ページが不足: %s" % ", ".join(sorted(missing)))
    if len(pages) <= 3:
        if preview_pages != set(outline_by_n):
            findings.append("3ページ以下は全ページを事前preview対象にする")
    elif len(preview_pages) < 3:
        findings.append("4ページ以上は最低3ページを事前preview対象にする")
    if preview_prefix is not None:
        prefix = pathlib.Path(preview_prefix)
        review = spec.get("pre_preview_review", {})
        if review.get("status") != "pass" or len(str(review.get("sheet_evidence", "")).strip()) < 8:
            findings.append("事前previewの一覧表示レビューと根拠が未完了")
        slide_evidence = review.get("slides", {})
        evidence = []
        for n in sorted(preview_pages):
            image = pathlib.Path("%s-%02d.png" % (prefix, n))
            note = str(slide_evidence.get(str(n), slide_evidence.get(n, ""))).strip()
            if not image.exists():
                findings.append("事前preview画像が無い: %s" % image)
            if len(note) < 8:
                findings.append("ページ %s: 事前previewの個別所見が無い" % n)
            evidence.append(note)
        sheet = pathlib.Path(str(prefix) + "-sheet.png")
        if not sheet.exists():
            findings.append("事前previewの一覧画像が無い: %s" % sheet)
        if evidence and len(set(evidence)) != len(evidence):
            findings.append("事前previewの個別所見がページ固有でない")
    return findings


def markdown(spec):
    lines = ["# スライド実装仕様書", "",
             "| p. | タイトル | 原型 | 実装関数 | 領域 | 内容対応 | overflow | 設計意図 | 事前preview |",
             "|---:|---|---|---|---|---|---|---|---|"]
    for i, slide in enumerate(spec.get("slides", []), 1):
        impl = slide.get("implementation", {})
        bindings = "; ".join("%s → %s" % (k, v)
                             for k, v in impl.get("content_bindings", {}).items())
        values = [slide.get("n", i), slide.get("title", ""), slide.get("archetype", ""),
                  impl.get("function", ""), ", ".join(impl.get("regions", [])), bindings,
                  impl.get("overflow", ""), impl.get("design_intent", ""),
                  slide.get("preview_priority", "standard")]
        lines.append("| %s |" % " | ".join(str(v).replace("|", "\\|").replace("\n", " ")
                                               for v in values))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="スライド実装仕様書を生成前に検査する")
    parser.add_argument("spec", help="deck/implementation-spec.json")
    parser.add_argument("--outline", required=True, help="deck/outline.json")
    parser.add_argument("--md-out", help="検査済み仕様のMarkdown表示を書き出す")
    parser.add_argument("--preview-prefix", help="代表previewの個別・一覧画像と目視根拠も検査する")
    parser.add_argument("--force", action="store_true", help="既存のMarkdown表示を明示的に更新する")
    args = parser.parse_args(argv)
    try:
        spec = json.loads(pathlib.Path(args.spec).read_text(encoding="utf-8"))
        outline = json.loads(pathlib.Path(args.outline).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    findings = check(spec, outline, args.preview_prefix)
    print("--- check_implementation_spec: %d 件" % len(findings))
    for finding in findings:
        print("  " + finding, file=sys.stderr)
    if findings:
        return 1
    if args.md_out:
        out = pathlib.Path(args.md_out)
        if out.exists() and not args.force:
            print("ERROR: output exists: %s; use --force" % out, file=sys.stderr)
            return 2
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(markdown(spec), encoding="utf-8")
        except OSError as exc:
            print("ERROR: %s" % exc, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
