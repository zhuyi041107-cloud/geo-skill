"""Export the independent media pool to the original Excel template; retain Word compatibility."""

from __future__ import annotations

import argparse
from copy import copy, deepcopy
import csv
from datetime import date
import gzip
from io import BytesIO
import json
from pathlib import Path
import sys
from math import ceil
from unicodedata import east_asian_width

from docx import Document
from openpyxl import load_workbook

from geo_data import money
from media import TIER_FIELDS, TIERS as PRICE_TIERS, restriction


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/推荐媒体模板.docx"
XLSX_TEMPLATE = ROOT / "templates/推荐媒体模板.xlsx"
CATALOG = ROOT / "references/media-catalog.csv.gz"
TIERS = ("超级代理", "核心代理", "高级代理", "普通代理", "普通会员")
HEADERS = {
    "网络媒体报价": ("序号", "媒体类别", "媒体分类", "媒体名称", "文章案例", "市场价格", *TIERS, "联系方式", "新闻源", "地区", "备注", "简介"),
    "自媒体报价": ("序号", "媒体类别", "媒体分类", "媒体名称", "文章案例", "市场价格", *TIERS, "联系方式", "地区", "粉丝量", "认证", "备注", "认证主体"),
}
SHEET_NAMES = {"网络媒体清单": "网络媒体报价", "自媒体清单": "自媒体报价"}
SHEET_LABELS = {"网络媒体报价": "网络媒体清单", "自媒体报价": "自媒体清单"}
XLSX_SHEETS = {"网络媒体报价": "sheet1", "自媒体报价": "sheet2"}


def text(value):
    return str(value).strip() if value is not None else ""


def price(value):
    parsed = money(value, "媒体报价")
    return format(parsed, ".2f") if parsed is not None else ""


def catalog_records(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return {(row["source_sheet"], row["media_id"]): row for row in csv.DictReader(stream)}


def selected_rows(plan, catalog):
    """Join the complete recommendation pool by source sheet and ID."""
    recommendations = plan.get("media_recommendations")
    if not isinstance(recommendations, list) or not recommendations:
        raise ValueError("缺少独立媒体推荐池plan.media_recommendations；请先按客户业务完成广泛推荐，不能用预算内placements替代")
    result = {sheet: [] for sheet in HEADERS}
    seen = {}
    for placement in recommendations:
        if not isinstance(placement, dict):
            raise ValueError("media_recommendations每项须为媒体对象")
        status = text(placement.get("status")) or "推荐"
        if status in {"取消", "排除"}:
            continue
        if status not in {"推荐", "候选", "需核实"}:
            raise ValueError("独立推荐池status须为推荐、候选或需核实；取消、排除项不导出")
        sheet = SHEET_NAMES.get(text(placement.get("source_sheet")), text(placement.get("source_sheet")))
        if sheet not in HEADERS:
            raise ValueError("推荐媒体必须填写来源source_sheet：网络媒体报价或自媒体报价")
        media_id, name = text(placement.get("media_id")), text(placement.get("media_name"))
        if not media_id or not name:
            raise ValueError("推荐媒体必须有media_id与具体媒体名称")
        key = (sheet, media_id)
        source = catalog.get(key, {})
        if any(restriction(note) == "排除" for note in (source.get("editorial_note"), placement.get("editorial_note"))):
            continue
        tier_prices = placement.get("tier_prices") or {}
        if not isinstance(tier_prices, dict) or any(k not in PRICE_TIERS for k in tier_prices):
            raise ValueError("tier_prices须使用原表的六档中文名")
        if any(value not in (None, "") for value in tier_prices.values()) and not text(placement.get("tier_price_source")):
            raise ValueError("外部档位报价须提供tier_price_source，禁止用市场价或成本价推算")
        supplied_file = text(placement.get("source_file")).replace("\\", "/").rsplit("/", 1)[-1]
        catalog_file = text(source.get("source_file")).replace("\\", "/").rsplit("/", 1)[-1]
        try:
            date.fromisoformat(text(placement.get("quotation_date")))
            dated_quote = True
        except ValueError:
            dated_quote = False
        external_source = supplied_file and supplied_file not in {"未知", "待确认", "待填写", "未提供", "待补充", "无"} and catalog_file and supplied_file.casefold() != catalog_file.casefold()
        if source and external_source and dated_quote and placement.get("market_price") not in (None, ""):
            # A traceable external quote replaces the old row, including its optional attributes.
            source = {}
        notes = list(dict.fromkeys(value for value in (text(source.get("editorial_note")), text(placement.get("editorial_note"))) if value))
        if source and name != text(source.get("media_name")):
            raise ValueError(f"媒体名称与目录的来源sheet及ID不一致：{media_id}")
        supplied_market = placement.get("market_price")
        if supplied_market in (None, ""):
            supplied_market = placement.get("market_reference_price")
        tier_market = tier_prices.get("市场价格")
        if supplied_market not in (None, "") and tier_market not in (None, "") and price(supplied_market) != price(tier_market):
            raise ValueError("tier_prices市场价格与market_price或market_reference_price不一致")
        if supplied_market in (None, ""):
            supplied_market = tier_market
        catalog_market = source.get("market_price")
        if supplied_market not in (None, "") and catalog_market not in (None, "") and price(supplied_market) != price(catalog_market):
            raise ValueError(f"媒体市场价格与目录不一致：{media_id}，请更新同源报价后再导出")
        market = catalog_market if catalog_market not in (None, "") else supplied_market
        row = {
            "媒体类别": text(placement.get("media_group")) or ("网络媒体" if sheet == "网络媒体报价" else "自媒体"),
            "媒体分类": text(placement.get("category")) or text(source.get("category")),
            "媒体名称": name, "文章案例": text(placement.get("article_example")),
            "市场价格": price(market), "联系方式": text(placement.get("contact_policy")),
            "新闻源": text(placement.get("news_source")),
            "地区": text(placement.get("region")) or text(source.get("region")),
            "简介": text(placement.get("description")), "粉丝量": text(placement.get("followers")),
            "认证": text(placement.get("certification")), "认证主体": text(placement.get("certification_subject")),
        }
        if row["联系方式"] not in {"", "带", "不带", "可带", "不可带", "可以带", "不能带", "需确认", "不允许", "允许"}:
            raise ValueError("联系方式列仅填写可否在稿件带联系方式的政策，不能填写联系人或电话")
        note = "；".join(notes)
        if status == "需核实" or restriction(note) == "需核实":
            note = "；".join(value for value in (note, "发布条件需核实，尚未确认可发") if value)
        entry = text(placement.get("entry_type")) or text(source.get("entry_type"))
        row["备注"] = "；".join(v for v in (note, "刊发形态：" + entry if entry and entry not in note else "") if v)
        row.update({tier: price(tier_prices.get(tier) if tier_prices.get(tier) not in (None, "") else source.get(TIER_FIELDS[tier])) for tier in TIERS})
        if key in seen:
            if seen[key] != row:
                raise ValueError(f"同一媒体存在不同属性或报价：{media_id}，请先统一来源")
            continue
        seen[key] = row
        result[sheet].append(row)
    if not seen:
        raise ValueError("独立推荐池没有可列媒体；请完成广泛推荐，并排除取消、排除及明确拒发GEO的资源")
    return result


def replace_cell(cell, value):
    """Keep the template's paragraph and run properties when replacing text."""
    paragraph = cell.paragraphs[0]
    for extra in list(cell.paragraphs)[1:]:
        cell._tc.remove(extra._p)
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    run.text = text(value)
    for extra in list(paragraph.runs)[1:]:
        paragraph._p.remove(extra._r)


def fill_table(table, sheet, rows, brand):
    headers = HEADERS[sheet]
    if len(table.columns) != len(headers) or tuple(c.text for c in table.rows[2].cells) != headers or len(table.rows) != 4:
        raise ValueError("推荐媒体模板的表头、列序或空数据行被更改，请恢复随包模板")
    replace_cell(table.cell(0, 0), brand + "媒体投放计划表（" + SHEET_LABELS[sheet] + "）")
    prototype = deepcopy(table.rows[3]._tr)
    table._tbl.remove(table.rows[3]._tr)
    for index, values in enumerate(rows, 1):
        table._tbl.append(deepcopy(prototype))
        for column, header in enumerate(headers):
            replace_cell(table.rows[-1].cells[column], index if header == "序号" else values.get(header, ""))
    if not rows:
        table._tbl.append(deepcopy(prototype))
        for cell in table.rows[-1].cells:
            replace_cell(cell, "")
        return
    start = 3
    for index in range(4, 3 + len(rows) + 1):
        if index == 3 + len(rows) or rows[index - 3]["媒体类别"] != rows[start - 3]["媒体类别"]:
            if index - start > 1:
                merged = table.cell(start, 1).merge(table.cell(index - 1, 1))
                replace_cell(merged, rows[start - 3]["媒体类别"])
            start = index


def build_docx(analysis, plan, template=TEMPLATE, catalog_path=CATALOG):
    rows = selected_rows(plan, catalog_records(catalog_path))
    document = Document(template)
    if len(document.tables) != 2:
        raise ValueError("推荐媒体模板应保留网络和自媒体两张清单")
    project = analysis.get("project", {})
    brand = text((project.get("brand_names") or [project.get("client_name")])[0])
    if not brand:
        raise ValueError("项目缺少客户品牌名称")
    for table, sheet in zip(document.tables, HEADERS):
        fill_table(table, sheet, rows[sheet], brand)
    document.core_properties.title = brand + "推荐媒体"
    document.core_properties.subject = "媒体投放计划表"
    document.core_properties.author = "软文街"
    target = BytesIO()
    document.save(target)
    return target.getvalue()


def export_docx(analysis, plan, output):
    output = Path(output)
    if output.suffix.lower() != ".docx":
        raise ValueError("输出路径须为推荐媒体.docx等.docx文件")
    if output.exists():
        raise FileExistsError("目标文件已存在，拒绝覆盖：" + str(output))
    content = build_docx(analysis, plan)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(content)
    return output


def build_xlsx(analysis, plan, template=XLSX_TEMPLATE, catalog_path=CATALOG):
    rows = selected_rows(plan, catalog_records(catalog_path))
    project = analysis.get("project", {})
    brand = text((project.get("brand_names") or [project.get("client_name")])[0])
    if not brand:
        raise ValueError("项目缺少客户品牌名称")
    book = load_workbook(template)
    if book.sheetnames != list(XLSX_SHEETS.values()):
        raise ValueError("推荐媒体Excel模板必须严格保留sheet1和sheet2")
    for source_sheet, sheet_name in XLSX_SHEETS.items():
        sheet = book[sheet_name]
        headers = HEADERS[source_sheet]
        if sheet.max_row != 4 or sheet.max_column != len(headers) or tuple(c.value for c in sheet[3]) != headers or any(c.value is not None for c in sheet[4]):
            raise ValueError("推荐媒体Excel模板的表头、列序或空数据行被更改，请恢复随包模板")
        sheet["A1"] = brand + "媒体投放计划表（" + SHEET_LABELS[source_sheet] + "）"
        sheet["A1"].data_type = "s"
        styles = [copy(cell._style) for cell in sheet[4]]
        for index, values in enumerate(rows[source_sheet], 4):
            height = sheet.sheet_format.defaultRowHeight or 15
            for column, header in enumerate(headers, 1):
                cell = sheet.cell(index, column)
                cell._style = copy(styles[column - 1])
                value = index - 3 if header == "序号" else values.get(header, "")
                if header in PRICE_TIERS:
                    value = float(value) if value not in (None, "") else None
                cell.value = value
                if isinstance(value, str):
                    cell.data_type = "s"
                    alignment = copy(cell.alignment)
                    alignment.wrap_text = True
                    cell.alignment = alignment
                    width = next((d.width for d in sheet.column_dimensions.values() if d.min <= column <= d.max), sheet.sheet_format.defaultColWidth or 9)
                    lines = sum(max(1, ceil(sum(2 if east_asian_width(c) in {"W", "F"} else 1 for c in line) / max(1, width - 2))) for line in value.split("\n"))
                    height = max(height, (lines + (lines > 1)) * (cell.font.sz or 11) * 1.4 + 6)
            # shortcut: row heights are estimated at retained fonts; native AutoFit is needed if fonts change.
            sheet.row_dimensions[index].height = min(409, height)
        start = 4
        for index in range(5, 4 + len(rows[source_sheet]) + 1):
            if index == 4 + len(rows[source_sheet]) or rows[source_sheet][index - 4]["媒体类别"] != rows[source_sheet][start - 4]["媒体类别"]:
                if index - start > 1:
                    sheet.merge_cells(start_row=start, start_column=2, end_row=index - 1, end_column=2)
                start = index
    book.properties.title = brand + "推荐媒体"
    target = BytesIO()
    book.save(target)
    book.close()
    return target.getvalue()


def export_xlsx(analysis, plan, output):
    output = Path(output)
    if output.suffix.lower() != ".xlsx":
        raise ValueError("输出路径须为推荐媒体.xlsx等.xlsx文件")
    if output.exists():
        raise FileExistsError("目标文件已存在，拒绝覆盖：" + str(output))
    content = build_xlsx(analysis, plan)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(content)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("推荐媒体.xlsx"))
    args = parser.parse_args()
    try:
        analysis = json.loads(args.analysis.read_text(encoding="utf-8-sig"))
        plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
        exporter = export_docx if args.output.suffix.lower() == ".docx" else export_xlsx
        path = exporter(analysis, plan, args.output)
        print(json.dumps({"output": str(path)}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
