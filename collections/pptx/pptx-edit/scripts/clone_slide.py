#!/usr/bin/env python3
"""単純なスライドを、relationshipを検査・付け替えして安全に複製する。"""

import argparse
import copy
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
REVIEW_SCRIPTS = HERE.parents[2] / "pptx-review" / "scripts"
sys.path.insert(0, str(REVIEW_SCRIPTS))

import pptx_lint as L  # noqa: E402

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ALLOWED_RELATIONSHIPS = ("/image", "/hyperlink")
FORBIDDEN_SLIDE_TAGS = ("timing", "transition", "controls")


def referenced_relationships(element):
    found = set()
    for node in element.iter():
        for attr, value in node.attrib.items():
            if attr.startswith("{%s}" % R_NS) and value:
                found.add(value)
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="画像とリンクを含む単純スライドを安全に複製する。図表・SmartArt・OLE等は拒否")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--slide", required=True, type=int, help="複製元。1始まり")
    args = parser.parse_args(argv)
    temp_path = None
    try:
        src, dst = pathlib.Path(args.input), pathlib.Path(args.output)
        if src.resolve() == dst.resolve():
            raise ValueError("input と output は別名にする")
        if dst.exists():
            raise ValueError("output exists: %s" % dst)

        from pptx import Presentation
        prs = Presentation(str(src))
        if args.slide < 1 or args.slide > len(prs.slides):
            raise ValueError("slide が範囲外")
        source = prs.slides[args.slide - 1]
        source_root = source._element
        for local in FORBIDDEN_SLIDE_TAGS:
            if source_root.find("{%s}%s" % (source_root.nsmap["p"], local)) is not None:
                raise RuntimeError("%s を持つスライドは安全経路の対象外" % local)

        source_tree = source.shapes._spTree
        refs = referenced_relationships(source_tree)
        rels = {}
        for rid in refs:
            rel = source.part.rels.get(rid)
            if rel is None:
                raise RuntimeError("参照先の無いrelationship: %s" % rid)
            if not any(rel.reltype.endswith(suffix) for suffix in ALLOWED_RELATIONSHIPS):
                raise RuntimeError("共有・複合部品 %s は自動複製しない" % rel.reltype.rsplit("/", 1)[-1])
            rels[rid] = rel

        dest = prs.slides.add_slide(source.slide_layout)
        dest_tree = dest.shapes._spTree
        for element in list(dest_tree)[2:]:
            dest_tree.remove(element)
        for element in list(source_tree)[2:]:
            clone = copy.deepcopy(element)
            for node in clone.iter():
                for attr, value in list(node.attrib.items()):
                    if not attr.startswith("{%s}" % R_NS) or value not in rels:
                        continue
                    rel = rels[value]
                    target = rel.target_ref if rel.is_external else rel._target
                    node.set(attr, dest.part.relate_to(target, rel.reltype, rel.is_external))
            dest_tree.append(clone)

        source_c_sld = source_root.cSld
        dest_c_sld = dest._element.cSld
        source_bg = source_c_sld.find("{%s}bg" % source_root.nsmap["p"])
        dest_bg = dest_c_sld.find("{%s}bg" % source_root.nsmap["p"])
        if dest_bg is not None:
            dest_c_sld.remove(dest_bg)
        if source_bg is not None:
            dest_c_sld.insert(0, copy.deepcopy(source_bg))
        for attr in ("showMasterSp", "showMasterPhAnim", "show"):
            if source_root.get(attr) is not None:
                dest._element.set(attr, source_root.get(attr))

        new_id = prs.slides._sldIdLst[-1]
        prs.slides._sldIdLst.remove(new_id)
        prs.slides._sldIdLst.insert(args.slide, new_id)

        dst.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(prefix="pptx-clone-", suffix=".pptx",
                                             dir=str(dst.parent), delete=False)
        temp_path = handle.name
        handle.close()
        prs.save(temp_path)
        check_pkg = L.Package(temp_path)
        broken = [f for f in L.package_findings(check_pkg, L.slide_order(check_pkg))
                  if f["severity"] == "error"]
        if broken:
            raise RuntimeError("複製後のパッケージ検査に失敗: %s" %
                               ", ".join(sorted(set(f["code"] for f in broken))))
        os.replace(temp_path, dst)
        temp_path = None
        print("複製完了: p.%d -> p.%d (%s)" % (args.slide, args.slide + 1, dst))
        return 0
    except RuntimeError as exc:
        print("REJECTED: %s" % exc, file=sys.stderr)
        return 1
    except (OSError, ValueError, IndexError, KeyError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    sys.exit(main())
