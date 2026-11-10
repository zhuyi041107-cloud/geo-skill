"""Read a current quotation workbook and return traceable GEO media candidates."""

import argparse
import csv
import gzip
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook

TIERS = ("市场价格", "超级代理", "核心代理", "高级代理", "普通代理", "普通会员")
SHEETS = {"network": "网络媒体报价", "self": "自媒体报价"}
CATALOG = Path(__file__).resolve().parents[1] / "references/media-catalog.csv.gz"
CATALOG_FIELDS = ("media_id", "media_name", "media_type", "category", "region", "portal", "entry_type", "editorial_note", "market_price", "quotation_date", "source_file", "source_sheet", "source_row")


def public_text(value):
    """Keep editorial limits while removing contact details from free text."""
    text = str(value or "")
    text = re.sub(r"https?://\S+|www\.\S+", "[链接已脱敏]", text, flags=re.I)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已脱敏]", text)
    text = re.sub(r"(?:联系人|对接人|商务联系人|联系编辑|客服姓名)\s*[:：]\s*[\u4e00-\u9fffA-Za-z·]{1,12}", "[联系人已脱敏]", text)
    text = re.sub(r"(?:找|联系|对接|咨询)\s*[\u4e00-\u9fff]{1,4}(?:先生|女士|经理|老师|小姐|总)\b", "[联系人已脱敏]", text)
    text = re.sub(r"(?:微[\s.*_-]*信|微[\s.*_-]*号|weixin|wechat|v[\s.*_-]*x|v信|薇信|威信|扣扣|q[\s.*_-]*q|qq号|手机号|手机|联系电话|电话|电联|邮箱)\s*[:：=、,，+-]?\s*[A-Za-z0-9][A-Za-z0-9_@.\-]{4,}", "[联系方式已脱敏]", text, flags=re.I)
    text = re.sub(r"(?:加|添加|联系)\s*(?:V|微(?:信)?|Q)\s*[:：+-]?\s*[A-Za-z0-9][A-Za-z0-9_\-]{3,}", "[联系方式已脱敏]", text, flags=re.I)
    text = re.sub(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9](?:[-\s]?\d){9}(?!\d)|(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)", "[电话已脱敏]", text)
    text = re.sub(r"(?<!\d)\d{12,}(?!\d)", "[长数字已脱敏]", text)
    text = re.sub(r"(?:代理价|成本价|底价|结算价|内部价|同行价|采购价|佣金|返点)[^，,。；;\n]*", "[非公开报价已移除]", text)
    return text.strip()


def build_catalog(source, destination, quotation_date):
    counts = {}
    book = load_workbook(source, read_only=True, data_only=True)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(destination, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CATALOG_FIELDS)
        writer.writeheader()
        for kind, name in SHEETS.items():
            rows = book[name].iter_rows(values_only=True)
            headers = list(next(rows))
            counts[name] = 0
            for line, values in enumerate(rows, 2):
                row = dict(zip(headers, values))
                if not row.get("媒体名称"):
                    continue
                media_name = re.sub(r"[A-Za-z0-9_][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[邮箱已脱敏]", str(row["媒体名称"]).strip())
                item = {"media_id": str(row["软文街id"]), "media_name": media_name,
                        "media_type": "网络媒体" if kind == "network" else "自媒体", "category": public_text(row.get("媒体分类")),
                        "region": public_text(row.get("地区")), "portal": public_text(row.get("综合门户")),
                        "entry_type": public_text(row.get("入口类型")), "editorial_note": public_text(row.get("备注")),
                        "market_price": price(row.get("市场价格")), "quotation_date": quotation_date,
                        "source_file": Path(source).name, "source_sheet": name, "source_row": line}
                writer.writerow(item)
                counts[name] += 1
    book.close()
    return {"records": sum(counts.values()), "sheets": counts, "bytes": destination.stat().st_size, "fields": list(CATALOG_FIELDS)}


def catalog_rows(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            yield row["source_sheet"], int(row["source_row"]), {
                "软文街id": row["media_id"], "媒体名称": row["media_name"], "媒体分类": row["category"],
                "地区": row["region"], "综合门户": row["portal"], "入口类型": row["entry_type"], "备注": row["editorial_note"],
                "市场价格": row["market_price"], "报价日期": row["quotation_date"], "原报价文件": row["source_file"]}


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


def search_media(path=None, tier="市场价格", query="", region="", kind="all", limit=30, min_price=None, max_price=None):
    if tier not in TIERS:
        raise ValueError("报价档位无效：" + tier)
    if kind not in (*SHEETS, "all") or limit < 1 or limit > 500:
        raise ValueError("kind必须是network/self/all，limit须在1至500之间")
    bounds = [price(v) if v is not None else None for v in (min_price, max_price)]
    if any(raw is not None and parsed is None for raw, parsed in zip((min_price, max_price), bounds)):
        raise ValueError("价格区间必须为非负确定金额")
    lower, upper = [Decimal(v) if v is not None else None for v in bounds]
    if lower is not None and upper is not None and lower > upper:
        raise ValueError("最低价格不能高于最高价格")
    path = Path(path) if path else CATALOG
    builtin = path.name.endswith(".csv.gz")
    if builtin and tier != "市场价格":
        raise ValueError("内置目录仅含市场参考价，代理价格档仅适用于外部原报价.xlsx")
    if not builtin and path.suffix.lower() != ".xlsx":
        raise ValueError("请提供.xlsx报价表或内置.csv.gz目录")
    terms = [s.casefold() for s in query.split() if s]
    regions = [s.strip() for s in re.split(r"[,，\s]+", region) if s.strip()]
    candidates = []
    stats = {"scanned": 0, "matched": 0, "excluded_geo": 0, "needs_confirmation": 0}
    selected = list(SHEETS.values()) if kind == "all" else [SHEETS[kind]]
    book = None
    if builtin:
        rows_to_search = catalog_rows(path)
    else:
        book = load_workbook(path, read_only=True, data_only=True)
        rows_to_search = []
        for sheet_name in selected:
            if sheet_name not in book.sheetnames:
                book.close()
                raise ValueError("报价表缺少工作表：" + sheet_name)
            rows = book[sheet_name].iter_rows(values_only=True)
            header = [str(v or "").strip() for v in next(rows)]
            required = {"媒体名称", "软文街id", tier, "备注"}
            if not required.issubset(header):
                book.close()
                raise ValueError(sheet_name + "缺少字段：" + ",".join(sorted(required - set(header))))
            rows_to_search.extend((sheet_name, i, dict(zip(header, values))) for i, values in enumerate(rows, 2))
    try:
        for sheet_name, row_number, row in rows_to_search:
                if sheet_name not in selected:
                    continue
                if not row.get("媒体名称"):
                    continue
                stats["scanned"] += 1
                searchable = " ".join(str(row.get(k) or "") for k in ("媒体名称", "媒体分类", "媒体类型", "综合门户", "渠道类型", "渠道名称", "备注")).casefold()
                if terms and not all(term in searchable for term in terms):
                    continue
                actual_region = str(row.get("地区") or "").strip()
                if regions and actual_region and "全国" not in actual_region and not any(r in actual_region for r in regions):
                    continue
                amount = price(row.get(tier))
                if (lower is not None and (amount is None or Decimal(amount) < lower)) or (upper is not None and (amount is None or Decimal(amount) > upper)):
                    continue
                stats["matched"] += 1
                state = restriction(row.get("备注"))
                if state == "排除":
                    stats["excluded_geo"] += 1
                    continue
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
                    "channel_type": str(row.get("渠道类型") or ""), "channel_name": str(row.get("渠道名称") or ""),
                    "channel": " / ".join(str(row.get(k) or "") for k in ("渠道类型", "渠道名称")).strip(" /"),
                    "price_tier": tier,
                    "unit_price": amount if tier != "市场价格" else None,
                    "market_reference_price": amount if tier == "市场价格" else None,
                    "market_price": amount if tier == "市场价格" else None,
                    "price_basis": "市场参考价，非采购成本" if tier == "市场价格" else "外部报价档位",
                    "quotation_date": str(row.get("报价日期") or ""),
                    "entry_type": str(row.get("入口类型") or ""),
                    "status": state,
                    "editorial_note": str(row.get("备注") or ""),
                    "checks": checks,
                    "source_file": str(row.get("原报价文件") or path.name),
                    "source_sheet": sheet_name,
                    "source_row": row_number,
                })
    finally:
        if book:
            book.close()
    candidates.sort(key=lambda item: (item["status"] == "需核实", (item["unit_price"] or item["market_reference_price"]) is None, Decimal(item["unit_price"] or item["market_reference_price"] or "0"), item["media_name"]))
    return {
        "source_file": path.name,
        "price_tier": tier,
        "query": query,
        "region": region,
        "price_range": {"min": bounds[0], "max": bounds[1]},
        "stats": stats,
        "returned": min(len(candidates), limit),
        "truncated": len(candidates) > limit,
        "limitation": "仅为报价候选筛选，未验证实时可发、媒体身份、搜索收录或AI引用；候选不等于已选。",
        "candidates": candidates[:limit],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--tier", default="市场价格", choices=TIERS)
    parser.add_argument("--query", default="", help="以空格分隔的主题词，全部匹配名称/分类/门户/渠道")
    parser.add_argument("--region", default="", help="多个区域用逗号分隔；地区未知的记录保留并提示")
    parser.add_argument("--kind", choices=("all", "network", "self"), default="all")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--min-price", help="按选用报价档位筛选最低单价，用于分层配置媒体")
    parser.add_argument("--max-price", help="按选用报价档位筛选最高单价")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("输出文件已存在，请使用新路径：" + str(args.out))
        result = search_media(args.input, args.tier, args.query, args.region, args.kind, args.limit, args.min_price, args.max_price)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps({"output": str(args.out), "returned": result["returned"], "stats": result["stats"]}, ensure_ascii=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
