"""Read a current quotation workbook and return traceable GEO media candidates."""

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook

TIERS = ("市场价格", "超级代理", "核心代理", "高级代理", "普通代理", "普通会员")
SHEETS = {"network": "网络媒体报价", "self": "自媒体报价"}


def price(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).strip().replace(",", "").lstrip("¥￥"))
        return str(amount.quantize(Decimal("0.01"))) if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def restriction(note):
    text = str(note or "").strip()
    if not re.search(r"geo", text, re.I):
        return "候选"
    # shortcut: only explicit GEO refusals are excluded; other editorial limits need human confirmation.
    clauses = re.split(r"[，,。；;\n]", text)
    for clause in clauses:
        rejected = re.search(r"(?:不发|不接|拒发|不收|禁止|不做|暂停).{0,10}geo|geo.{0,10}(?:不发|不接|拒发|不收|禁止)", clause, re.I)
        if rejected and not re.search(r"对比|测评|评测|榜单|排名|除非|并非|不是|仅|只", clause):
            return "排除"
    return "需核实"


def search_media(path, tier, query="", region="", kind="all", limit=30):
    if tier not in TIERS:
        raise ValueError("报价档位无效：" + tier)
    if kind not in (*SHEETS, "all") or limit < 1 or limit > 500:
        raise ValueError("kind必须是network/self/all，limit须在1至500之间")
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("请提供.xlsx报价表")
    terms = [s.casefold() for s in query.split() if s]
    regions = [s.strip() for s in re.split(r"[,，\s]+", region) if s.strip()]
    candidates = []
    stats = {"scanned": 0, "matched": 0, "excluded_geo": 0, "needs_confirmation": 0}
    book = load_workbook(path, read_only=True, data_only=True)
    selected = list(SHEETS.values()) if kind == "all" else [SHEETS[kind]]
    try:
        for sheet_name in selected:
            if sheet_name not in book.sheetnames:
                raise ValueError("报价表缺少工作表：" + sheet_name)
            sheet = book[sheet_name]
            rows = sheet.iter_rows(values_only=True)
            header = [str(v or "").strip() for v in next(rows)]
            required = {"媒体名称", "软文街id", tier, "备注"}
            if not required.issubset(header):
                raise ValueError(sheet_name + "缺少字段：" + ",".join(sorted(required - set(header))))
            for row_number, values in enumerate(rows, 2):
                row = dict(zip(header, values))
                if not row.get("媒体名称"):
                    continue
                stats["scanned"] += 1
                searchable = " ".join(str(row.get(k) or "") for k in ("媒体名称", "媒体分类", "媒体类型", "综合门户", "渠道")).casefold()
                if terms and not all(term in searchable for term in terms):
                    continue
                actual_region = str(row.get("地区") or "").strip()
                if regions and actual_region and "全国" not in actual_region and not any(r in actual_region for r in regions):
                    continue
                stats["matched"] += 1
                state = restriction(row.get("备注"))
                if state == "排除":
                    stats["excluded_geo"] += 1
                    continue
                amount = price(row.get(tier))
                checks = []
                if state == "需核实":
                    checks.append("备注包含GEO限制或要求，需结合稿件核实")
                if not actual_region:
                    checks.append("地区缺失，需核实覆盖范围")
                if amount is None:
                    checks.append("报价缺失或非确定金额，需询价")
                if checks:
                    state = "需核实"
                    stats["needs_confirmation"] += 1
                candidates.append({
                    "media_id": str(row["软文街id"] or ""),
                    "media_name": str(row["媒体名称"]),
                    "media_type": "网络媒体" if sheet_name == SHEETS["network"] else "自媒体",
                    "category": str(row.get("媒体分类") or row.get("媒体类型") or ""),
                    "portal": str(row.get("综合门户") or ""),
                    "region": actual_region,
                    "channel": str(row.get("渠道") or ""),
                    "price_tier": tier,
                    "unit_price": amount,
                    "status": state,
                    "editorial_note": str(row.get("备注") or ""),
                    "checks": checks,
                    "source_file": path.name,
                    "source_sheet": sheet_name,
                    "source_row": row_number,
                })
    finally:
        book.close()
    candidates.sort(key=lambda item: (item["status"] == "需核实", item["unit_price"] is None, Decimal(item["unit_price"] or "0"), item["media_name"]))
    return {
        "source_file": path.name,
        "price_tier": tier,
        "query": query,
        "region": region,
        "stats": stats,
        "returned": min(len(candidates), limit),
        "truncated": len(candidates) > limit,
        "limitation": "仅为报价候选筛选，未验证实时可发、媒体身份、搜索收录或AI引用；候选不等于已选。",
        "candidates": candidates[:limit],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--tier", required=True, choices=TIERS)
    parser.add_argument("--query", default="", help="以空格分隔的主题词，全部匹配名称/分类/门户/渠道")
    parser.add_argument("--region", default="", help="多个区域用逗号分隔；地区未知的记录保留并提示")
    parser.add_argument("--kind", choices=("all", "network", "self"), default="all")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("输出文件已存在，请使用新路径：" + str(args.out))
        result = search_media(args.input, args.tier, args.query, args.region, args.kind, args.limit)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps({"output": str(args.out), "returned": result["returned"], "stats": result["stats"]}, ensure_ascii=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
