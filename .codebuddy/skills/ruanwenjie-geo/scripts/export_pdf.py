"""Create customer-facing Chinese GEO business reports directly as PDF.

The agent writes the business analysis in report.json. This module lays it out
and reads metrics, selected media, schedules and customer prices from the same
analysis.json / plan.json. Requires reportlab and the skill's bundled fonts.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from decimal import Decimal
from html import escape
from io import BytesIO
import json
from pathlib import Path
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, KeepTogether, LongTable, Paragraph, SimpleDocTemplate, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
REGULAR = BOLD = "RWJ-NotoSC"
BLUE, INK, GRAY = colors.HexColor("#245E91"), colors.HexColor("#263645"), colors.HexColor("#60717F")
PALE, LINE = colors.HexColor("#F0F5F9"), colors.HexColor("#D9E4EC")
WIDTH = A4[0] - 88
ACTIVE = {"已选", "待执行", "已发布"}
FILES = {"diagnosis": "GEO诊断报告.pdf", "execution": "品牌传播与GEO执行方案.pdf"}
EMPTY = {"", "待采集", "待填写", "待确认", "暂无", "—", "-"}


def load_json(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("输入 JSON 根节点须为对象")
    return obj


def text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(text(item) for item in value if text(item))
    return str(value).strip()


def customer_text(value):
    result = text(value).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    if re.search(r"(?<![A-Za-z0-9_])(?:Q|C|P)\d{3,}(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])EV-[A-Za-z0-9_-]+|(?<![A-Za-z0-9])[A-Za-z]:[\\/]|/(?:Users|home|opt)/|\.codebuddy[\\/]|\{\{[^}]+\}\}|\$\{[^}]+\}", result):
        raise ValueError("客户正文包含内部编号、本机路径或未替换标记，请改为业务语言")
    if re.search(r"normalize|SKILL\.md|采样范围与方法|采样教程|怎么诊断", result, re.I):
        raise ValueError("客户正文包含处理流程或诊断教程，请改为现状、分析与执行内容")
    return result


def register_fonts():
    if REGULAR not in pdfmetrics.getRegisteredFontNames():
        path = ROOT / "assets/fonts/NotoSansSC-Regular.ttf"
        if not path.is_file():
            raise FileNotFoundError("缺少随 skill 分发的中文字体：NotoSansSC-Regular.ttf")
        pdfmetrics.registerFont(TTFont(REGULAR, str(path)))
    pdfmetrics.registerFontFamily(REGULAR, normal=REGULAR, bold=BOLD, italic=REGULAR, boldItalic=BOLD)


def styles():
    return {
        "title": ParagraphStyle("title", fontName=BOLD, fontSize=22, leading=31, textColor=BLUE, spaceAfter=9, wordWrap="CJK"),
        "client": ParagraphStyle("client", fontName=REGULAR, fontSize=11, leading=18, textColor=INK, spaceAfter=5, wordWrap="CJK"),
        "meta": ParagraphStyle("meta", fontName=REGULAR, fontSize=9, leading=14, textColor=GRAY, spaceAfter=8, wordWrap="CJK"),
        "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=14, leading=21, textColor=BLUE, spaceBefore=14, spaceAfter=7, keepWithNext=True, wordWrap="CJK"),
        "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=11.1, leading=18, textColor=INK, spaceBefore=7, spaceAfter=3, keepWithNext=True, wordWrap="CJK"),
        "body": ParagraphStyle("body", fontName=REGULAR, fontSize=10.4, leading=17.5, textColor=INK, spaceAfter=7, wordWrap="CJK", alignment=TA_LEFT, allowWidows=0, allowOrphans=0),
        "small": ParagraphStyle("small", fontName=REGULAR, fontSize=8.7, leading=14, textColor=GRAY, spaceAfter=6, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontName=REGULAR, fontSize=9, leading=14, textColor=INK, wordWrap="CJK", spaceAfter=0),
        "head": ParagraphStyle("head", fontName=BOLD, fontSize=9.1, leading=14, textColor=colors.white, wordWrap="CJK"),
    }


def paragraph(value, style):
    content = customer_text(value)
    supported = pdfmetrics.getFont(REGULAR).face.charWidths
    missing = sorted({ord(c) for c in content if not c.isspace() and ord(c) not in supported})
    if missing:
        raise ValueError("中文字体不支持正文字符：" + "、".join(f"U+{c:04X}" for c in missing[:8]))
    return Paragraph(escape(content).replace("\n", "<br/>"), style)


def entries(value):
    if isinstance(value, str):
        return [{"title": "", "detail": value}] if value.strip() not in EMPTY else []
    if isinstance(value, dict):
        value = [value]
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("报告章节须为文字或 title/detail 条目列表")
    result = []
    for item in value:
        if isinstance(item, str):
            result.extend(entries(item))
        elif isinstance(item, dict):
            detail = next((text(item.get(key)) for key in ("detail", "description", "finding", "observation", "target") if text(item.get(key))), "")
            title = next((text(item.get(key)) for key in ("title", "name", "keyword", "quarter", "metric") if text(item.get(key))), "")
            if detail not in EMPTY:
                result.append({"title": title, "detail": detail})
        else:
            raise ValueError("报告条目须为文字或 title/detail 对象")
    return result


def add_entries(story, values, st):
    for item in entries(values):
        if item["title"] not in EMPTY:
            story.append(paragraph(item["title"], st["h3"]))
        for block in re.split(r"\n\s*\n", item["detail"]):
            if block.strip():
                story.append(paragraph(block, st["body"]))


def table(headers, rows, widths, st, table_id=""):
    proportions = {
        "decision_path": [.16, .28, .27, .29],
        "response_layers": [.10, .20, .27, .13, .30],
        "recognition": [.20, .29, .51],
        "scene_matrix": [.28, .34, .38],
        "scene_details": [.14, .25, .12, .18, .31],
        "source_layers": [.18, .19, .26, .37],
        "dimensions": [.15, .17, .22, .24, .22],
        "keyword_matrix": [.18, .36, .46],
        "stage_plan": [.08, .07, .16, .12, .13, .23, .21],
        "selected_media": [.17, .10, .37, .08, .14, .14],
        "stage_budget": [.12, .20, .10, .10, .16, .16, .16],
        "content_volume": [.12, .09, .09, .35, .35],
        "risks": [.07, .22, .71],
    }
    if table_id == "actions":
        weights = [.08, .22, .70] if len(headers) == 3 else [.07, .20, .09, .64]
    elif table_id == "article_schedule":
        weights = [.05, .07, .075, .065, .15, .07, .065, .135, .17, .05] if len(headers) == 10 else [.05, .075, .08, .075, .17, .08, .15, .25, .07]
    else:
        weights = proportions.get(table_id, [1] * len(headers))
    widths = widths or [WIDTH * w / sum(weights) for w in weights]
    if len(widths) != len(headers) or any(len(row) != len(headers) for row in rows):
        raise ValueError(f"表格 {table_id} 的列宽、表头与内容列数不一致")
    dense = len(headers) >= 7
    padding = 3.5 if dense else 6
    vertical = 5 if dense else 7
    cell_style = ParagraphStyle("dense-cell", parent=st["cell"], fontSize=7.1 if dense else 8.7, leading=10.8 if dense else 13.6)
    head_style = ParagraphStyle("dense-head", parent=st["head"], fontSize=7.2 if dense else 8.8, leading=11 if dense else 13.5)
    data = [[paragraph(c, head_style) for c in headers]]
    data.extend([[paragraph(c, cell_style) for c in row] for row in rows])
    header_height = max(cell.wrap(width - padding * 2, 10000)[1] for cell, width in zip(data[0], widths)) + vertical * 2
    available_height = A4[1] - 42 - 49 - header_height
    oversized_row = any(max(cell.wrap(width - padding * 2, 10000)[1] for cell, width in zip(row, widths)) + vertical * 2 > available_height for row in data[1:])
    result = LongTable(data, colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=int(oversized_row), hAlign="LEFT", spaceBefore=6, spaceAfter=10)
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), padding), ("RIGHTPADDING", (0, 0), (-1, -1), padding),
        ("TOPPADDING", (0, 0), (-1, -1), vertical), ("BOTTOMPADDING", (0, 0), (-1, -1), vertical),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, BLUE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
    ]))
    return result


def sampled_groups(analysis):
    groups = analysis.get("groups", [])
    contexts = analysis.get("sampled_contexts")
    if contexts is not None:
        key = lambda obj: tuple(str(obj.get(k, "")) for k in ("platform", "mode", "online", "round"))
        allowed = {key(c) for c in contexts}
        groups = [g for g in groups if key(g) in allowed]
    return [g for g in groups if g.get("valid", 0) or g.get("completed", 0)]


def decision_cards(table_id, rows, st):
    accents = [colors.HexColor(x) for x in ("#568743", "#C18A2F", "#3B78B9", "#BB4F4D")]
    if table_id == "decision_path":
        gap = 7
        width = (WIDTH - gap * (len(rows) - 1)) / len(rows)
        cells, widths = [], []
        for i, row in enumerate(rows):
            accent = accents[min(i, 3)]
            head = ParagraphStyle("path-title", parent=st["cell"], fontSize=9.2, leading=14, textColor=accent)
            body = ParagraphStyle("path-body", parent=st["cell"], fontSize=8, leading=12)
            values = [[paragraph(row[0], head)], [paragraph(row[1], body)], [paragraph("当前位置：" + text(row[2]), body)], [paragraph(text(row[3]), body)]]
            card = Table(values, colWidths=[width])
            card.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("LINEABOVE", (0, 0), (-1, 0), 2, accent), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
            if i:
                cells.append(paragraph(">", st["small"])); widths.append(gap)
            cells.append(card); widths.append(width)
        flow = Table([cells], colWidths=widths, hAlign="LEFT", spaceBefore=7, spaceAfter=12)
        flow.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return [KeepTogether([flow])]
    result = []
    for i, row in enumerate(rows):
        accent = accents[min(i, 3)]
        title = ParagraphStyle("layer-title", parent=st["cell"], fontSize=8.6, leading=13, textColor=accent)
        small = ParagraphStyle("layer-copy", parent=st["cell"], fontSize=8.2, leading=12)
        left = paragraph(text(row[0]) + "\n" + text(row[1]), title)
        center = paragraph(text(row[2]) + "\n业务含义：" + text(row[4]), small)
        status = paragraph(row[3], ParagraphStyle("layer-state", parent=small, textColor=accent))
        card = Table([[left, center, status]], colWidths=[WIDTH * .21, WIDTH * .59, WIDTH * .20], spaceAfter=7)
        card.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("LINEBEFORE", (0, 0), (0, -1), 2, accent), ("BOX", (0, 0), (-1, -1), .35, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        result.append(card)
    return [KeepTogether(result)]


def report_date(analysis, report):
    return text(report.get("report_date")) or text((analysis.get("report_scope") or {}).get("report_date")) or date.today().isoformat()


def scope_line(analysis):
    platforms = (analysis.get("report_scope") or {}).get("platforms")
    if not platforms:
        platforms = list(dict.fromkeys(g.get("platform") for g in sampled_groups(analysis) if g.get("platform")))
    completed = analysis.get("counts", {}).get("completed")
    scope = "、".join(platforms or [])
    return (f"本轮观察：{scope}" if scope else "") + (f"，{completed}条回答" if completed is not None else "")


def add_header(story, kind, analysis, report, st):
    project = analysis.get("project", {})
    brand = text(project.get("brand_names")) or text(project.get("client_name"))
    title = "GEO品牌诊断报告" if kind == "diagnosis" else "品牌传播与GEO执行方案"
    story.append(paragraph(f"{brand} · {title}" if brand else title, st["title"]))
    client = text(project.get("client_name"))
    if client and client != brand:
        story.append(paragraph(client, st["client"]))
    story.append(paragraph(f"报告日期：{report_date(analysis, report)}    {scope_line(analysis)}", st["meta"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=BLUE, spaceAfter=8))


def selected_plan(plan):
    placements = [p for p in plan.get("placements", []) if p.get("status") in ACTIVE]
    selected_ids = {p.get("content_id") for p in placements}
    contents = [c for c in plan.get("contents", []) if c.get("status") not in {"取消", "排除"} and (not selected_ids or c.get("content_id") in selected_ids)]
    fees = [f for f in plan.get("fees", []) if f.get("status") in ACTIVE]
    return contents, placements, fees


def verify_budget(analysis, plan):
    from geo_data import calculate_budget
    expected = calculate_budget(analysis.get("project", {}), plan)
    if analysis.get("budget") != expected:
        raise ValueError("计划与分析预算不一致，请重新生成 analysis.json 后导出")
    return expected


def money(amount, currency="CNY"):
    if amount is None or amount == "":
        return "金额待明确"
    prefix = "¥" if currency == "CNY" else currency + " "
    return prefix + f"{Decimal(str(amount)):,.2f}"


def quarter(raw):
    if not raw:
        return "执行期内"
    day = date.fromisoformat(str(raw))
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def template_contract(profile, kind):
    contract = load_json(ROOT / "references/template-contract.json")
    if profile not in contract["profiles"]:
        raise ValueError("report.template_profile 须为 platform 或 service，请先按业务选择原模板")
    return contract["profiles"][profile][kind]


def validate_document(report, kind):
    specs = template_contract(report.get("template_profile"), kind)
    doc = report.get(kind)
    if not isinstance(doc, dict) or not entries(doc.get("summary")):
        raise ValueError(f"report.{kind}.summary 须写完整的本轮核心判断")
    sections = doc.get("sections")
    if not isinstance(sections, list):
        raise ValueError(f"report.{kind}.sections 须按 template-contract.json 完成原模板全部章节")
    keys = [x.get("key") for x in sections if isinstance(x, dict)]
    if len(keys) != len(sections) or len(set(keys)) != len(keys):
        raise ValueError("报告章节须为对象，且 key 不得重复")
    unknown = set(keys) - {spec["key"] for spec in specs}
    if unknown:
        raise ValueError("报告含契约外章节：" + "、".join(sorted(unknown)))
    result = []
    for spec in specs:
        source_doc = report.get("diagnosis", {}) if spec.get("source") == "diagnosis" else doc
        values = source_doc.get("sections", [])
        found = [x for x in values if x.get("key") == spec["key"]]
        if len(found) != 1:
            raise ValueError(f"缺少必需章节：{kind}.{spec['key']}")
        section = found[0]
        if not entries(section.get("paragraphs")):
            raise ValueError(f"章节 {spec['key']} 缺少业务情况与分析 paragraphs")
        supplied = section.get("tables", [])
        if not isinstance(supplied, list) or any(not isinstance(t, dict) for t in supplied):
            raise ValueError(f"章节 {spec['key']} 的 tables 须为对象列表")
        ids = [t.get("id") for t in supplied]
        if len(ids) != len(set(ids)):
            raise ValueError(f"章节 {spec['key']} 表格 id 重复")
        if set(ids) - {t['id'] for t in spec['tables']}:
            raise ValueError(f"章节 {spec['key']} 含契约外表格")
        for required in spec["tables"]:
            matches = [t for t in supplied if t.get("id") == required["id"]]
            if required.get("source") == "plan":
                if matches and matches[0].get("rows"):
                    raise ValueError(f"{required['id']} 从 plan 自动生成，不可手填 rows 覆盖同源数字")
                continue
            if not matches or matches[0].get("columns") != required["columns"]:
                raise ValueError(f"关键矩阵 {required['id']} 缺失或表头不符原模板契约")
            rows = matches[0].get("rows")
            if not isinstance(rows, list) or not rows:
                raise ValueError(f"关键矩阵 {required['id']} 不能为空")
            for row in rows:
                if not isinstance(row, list) or len(row) != len(required["columns"]):
                    raise ValueError(f"矩阵 {required['id']} 行列数不一致")
                if not any(text(cell) not in EMPTY for cell in row):
                    raise ValueError(f"矩阵 {required['id']} 不能使用空占位行")
        result.append((spec, section))
    return result


def content_week(content, project):
    try:
        start = date.fromisoformat(project["start_date"])
        scheduled = date.fromisoformat(content["scheduled_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("逐篇排期须有项目 start_date 和每篇 scheduled_date，不能生成空周次") from exc
    if scheduled < start:
        raise ValueError("内容计划日期早于项目开始日期")
    return (scheduled - start).days // 7 + 1


def plan_context(analysis, plan):
    contents, placements, fees = selected_plan(plan)
    if not contents or not placements:
        raise ValueError("执行方案须有已选独立内容与具体媒体组合")
    project = analysis["project"]
    question_by_id = {q["question_id"]: q.get("text", "") for q in project.get("questions", [])}
    stage_by_name = {}
    for stage in plan.get("stages", []):
        name = text(stage.get("name"))
        if not name or name in stage_by_name:
            raise ValueError("plan.stages 的 name 须非空且不重复")
        if any(not text(stage.get(k)) for k in ("objective", "deliverables", "effect_target")):
            raise ValueError(f"阶段 {name} 须写 objective/deliverables/effect_target")
        stage_by_name[name] = stage
    by_content = {c["content_id"]: c for c in contents}
    by_placement = defaultdict(list)
    for placement in placements:
        name = text(placement.get("media_name"))
        if not name or re.search(r"待报价|待选择|待选定|TBD|类媒体|媒体类型", name, re.I):
            raise ValueError("执行方案应使用资源目录的具体媒体名称")
        by_placement[placement["content_id"]].append(placement)
    for content in contents:
        name = text(content.get("stage"))
        if name not in stage_by_name:
            raise ValueError(f"已选内容的阶段 {name} 在 plan.stages 中没有完整定义")
        for field in ("title", "platform", "source_layer", "content_form", "observation_port"):
            if not text(content.get(field)):
                raise ValueError(f"逐篇排期缺少 contents.{field}，请写实际内容，不用空格代替")
        if not text(content.get("key_facts") or content.get("evidence")):
            raise ValueError("逐篇排期缺少可核验事实或事实边界")
        target = text(content.get("target_question")) or "；".join(question_by_id.get(q, "") for q in content.get("question_ids", []) if question_by_id.get(q))
        if not target:
            raise ValueError("逐篇排期须有 target_question 或有效 question_ids")
        content_week(content, project)
    ordered_stages = sorted({text(c["stage"]) for c in contents}, key=lambda n: min(c["scheduled_date"] for c in contents if c["stage"] == n))
    if project.get("end_date") and (date.fromisoformat(project["end_date"]) - date.fromisoformat(project["start_date"])).days >= 300:
        first, last = date.fromisoformat(project["start_date"]), date.fromisoformat(project["end_date"])
        cursor = date(first.year, ((first.month - 1) // 3) * 3 + 1, 1)
        required = set()
        while cursor <= last:
            required.add(quarter(cursor.isoformat()))
            cursor = date(cursor.year + (cursor.month == 10), 1 if cursor.month == 10 else cursor.month + 3, 1)
        covered = {quarter(p.get("scheduled_date")) for p in placements if p.get("scheduled_date")}
        scheduled = {quarter(c["scheduled_date"]) for c in contents}
        missing = required - (covered & scheduled)
        if missing:
            raise ValueError("年度计划尚缺实际内容与刊发的季度：" + "、".join(sorted(missing)) + "；请配置真实维护或内容安排")
    return project, contents, placements, fees, by_content, by_placement, stage_by_name, ordered_stages, question_by_id


def joined(values):
    return "、".join(dict.fromkeys(text(v) for v in values if text(v)))


def sum_price(records, key="client_unit_price"):
    if any(r.get(key) in (None, "") or r.get("quantity") in (None, "") for r in records):
        return None
    return sum((Decimal(str(r[key])) * int(Decimal(str(r["quantity"]))) for r in records), Decimal(0))


def price_range(records, currency):
    values = sorted({Decimal(str(r["client_unit_price"])) for r in records if r.get("client_unit_price") not in (None, "")})
    return money(values[0], currency) + (" - " + money(values[-1], currency) if len(values) > 1 else "") if values else "未报价"


def automatic_rows(table_id, analysis, plan):
    project, contents, placements, fees, by_content, by_placement, stages, stage_names, questions = plan_context(analysis, plan)
    currency = analysis["budget"].get("currency", "CNY")
    if table_id == "article_schedule":
        rows = []
        for c in sorted(contents, key=lambda c: (c["scheduled_date"], c["content_id"])):
            row = [f"第{content_week(c, project)}周", text(c["source_layer"]), joined(p.get("media_type" if analysis.get("_template_profile") == "platform" else "media_name") for p in by_placement[c["content_id"]]), text(c["content_form"]), text(c["title"]), text(c["platform"])]
            if analysis.get("_template_profile") == "platform":
                row.append(text(c["observation_port"]))
            target = text(c.get("target_question")) or "；".join(questions[q] for q in c.get("question_ids", []) if q in questions)
            row.extend([target, text(c.get("key_facts") or c.get("evidence")), text(c.get("checkpoint")) or "按阶段节点观察"])
            rows.append(row)
        return rows
    if table_id == "stage_plan":
        rows = []
        for name in stage_names:
            cs = [c for c in contents if c["stage"] == name]
            weeks = defaultdict(list)
            for c in cs:
                weeks[content_week(c, project)].append(c)
            ps = [p for c in cs for p in by_placement[c["content_id"]]]
            counts = "；".join(f"W{week}：{len(items)}篇" for week, items in sorted(weeks.items()))
            stage = stages[name]
            rows.append([name, f"第{min(weeks)}-{max(weeks)}周", text(stage["objective"]), counts, f"{len(cs)}篇独立内容\n{sum(int(Decimal(str(p['quantity']))) for p in ps)}次刊发", text(stage["deliverables"]), text(stage["effect_target"])])
        return rows
    if table_id == "content_volume":
        rows = []
        for layer in dict.fromkeys(c["source_layer"] for c in contents):
            cs = [c for c in contents if c["source_layer"] == layer]
            ps = [p for c in cs for p in by_placement[c["content_id"]]]
            targets = joined(c.get("target_question") or "；".join(questions[q] for q in c.get("question_ids", []) if q in questions) for c in cs)
            rows.append([layer, str(len(cs)), str(sum(int(Decimal(str(p['quantity']))) for p in ps)), f"围绕本层实际选题及不同事实分别成稿，逐篇见执行排期", targets])
        return rows
    if table_id == "selected_media":
        buckets = defaultdict(list)
        for p in placements:
            buckets[(p.get("media_id"), p["media_name"], p.get("media_type"))].append(p)
        return [[name, text(kind), "\n".join(dict.fromkeys(by_content[p["content_id"]]["title"] for p in items)), str(sum(int(Decimal(str(p["quantity"]))) for p in items)), price_range(items, currency), money(sum_price(items), currency)] for (_, name, kind), items in buckets.items()]
    if table_id == "media_costs":
        buckets = defaultdict(list)
        for p in placements:
            buckets[text(p.get("media_type"))].append(p)
        return [[kind, str(sum(int(Decimal(str(p["quantity"]))) for p in items)), price_range(items, currency), money(sum_price(items), currency)] for kind, items in buckets.items()]
    if table_id == "quarterly_budget":
        result = []
        for q, totals in analysis["budget"]["client"]["quarterly"].items():
            cs = [c for c in contents if quarter(c["scheduled_date"]) == q]
            ps = [p for p in placements if quarter(p.get("scheduled_date")) == q]
            result.append([q, str(len(cs)), str(sum(int(Decimal(str(p["quantity"]))) for p in ps)), money(totals["total"], currency)])
        return result
    if table_id == "stage_budget":
        rows = []
        assigned_fees = set()
        for name in stage_names:
            cs = [c for c in contents if c["stage"] == name]
            ps = [p for c in cs for p in by_placement[c["content_id"]]]
            dates = sorted(c["scheduled_date"] for c in cs)
            fs = [f for f in fees if f.get("stage") == name]
            assigned_fees.update(f["fee_id"] for f in fs)
            m = sum_price(ps)
            f = sum((Decimal(str(f["client_amount"])) for f in fs), Decimal(0)) if all(f.get("client_amount") not in (None, "") for f in fs) else None
            total = m + f if m is not None and f is not None else None
            rows.append([name, f"{dates[0]}\n至 {dates[-1]}", str(len(cs)), str(sum(int(Decimal(str(p["quantity"]))) for p in ps)), money(m, currency), money(f, currency), money(total, currency)])
        unassigned = [f for f in fees if f["fee_id"] not in assigned_fees]
        if unassigned:
            value = sum((Decimal(str(f["client_amount"])) for f in unassigned), Decimal(0)) if all(f.get("client_amount") not in (None, "") for f in unassigned) else None
            rows.append(["未分配阶段的其他费用", "执行期内", "0", "0", money(0, currency), money(value, currency), money(value, currency)])
        return rows
    raise ValueError(f"不支持的同源表：{table_id}")


def quotation_note(placements):
    bases = joined(p.get("price_basis") for p in placements)
    dates = joined(p.get("quotation_date") for p in placements)
    return "报价口径：" + (bases or "价格依据未注明") + "。报价日期：" + (dates or "未注明") + "。本表为建议媒体投放包，执行价格以当次确认条件为准。"


def document_story(kind, analysis, plan, report, st):
    sections = validate_document(report, kind)
    budget = verify_budget(analysis, plan)
    if kind == "execution":
        from geo_data import validate_delivery_budget
        validate_delivery_budget(budget)
        plan_context(analysis, plan)
    # A private rendering hint on a new dict never changes the analysis source.
    analysis = {**analysis, "_template_profile": report["template_profile"]}
    story = []
    add_header(story, kind, analysis, report, st)
    add_entries(story, report[kind]["summary"], st)
    if kind == "execution":
        project = analysis["project"]
        scope = f"执行周期：{text(project.get('start_date'))} 至 {text(project.get('end_date'))}；{budget['content_count']}篇独立内容、{budget['publication_count']}次刊发；建议已知费用{money(budget['client']['known_subtotal'], budget['currency'])}。"
        story.append(paragraph(scope, st["meta"]))
    for spec, section in sections:
        story.append(paragraph(spec["title"], st["h2"] if spec["level"] == 1 else st["h3"]))
        add_entries(story, section["paragraphs"], st)
        for definition in spec["tables"]:
            if definition.get("source") == "plan":
                rows = automatic_rows(definition["id"], analysis, plan)
            else:
                rows = next(t["rows"] for t in section["tables"] if t["id"] == definition["id"])
            if not rows:
                raise ValueError(f"关键矩阵 {definition['id']} 无可交付内容")
            if definition["id"] in {"decision_path", "response_layers"}:
                story.extend(decision_cards(definition["id"], rows, st))
            else:
                story.append(table(definition["columns"], rows, None, st, table_id=definition["id"]))
        if spec["key"] == "budget":
            client, currency = budget["client"], budget["currency"]
            story.append(paragraph(quotation_note(selected_plan(plan)[1]), st["small"]))
            lines = f"建议媒体费用：{money(client.get('media'), currency)}；其他已列费用：{money(client.get('fees'), currency)}；合计：{money(client.get('total'), currency)}。"
            if budget.get("target") is not None:
                lines += f"建议预算目标：{money(budget['target'], currency)}。"
            if budget.get("limit") is not None:
                lines += f"建议费用上限：{money(budget['limit'], currency)}。"
            story.append(paragraph(lines, st["body"]))
            for fee in selected_plan(plan)[2]:
                story.append(paragraph(text(fee.get("description") or fee.get("category")) + "：" + money(fee.get("client_amount"), currency), st["small"]))
            if not selected_plan(plan)[2]:
                story.append(paragraph("费用口径为本期已列媒体投放，不含未列报价的撰稿、官网建设及后续维护服务。", st["small"]))
            if client.get("missing_count"):
                story.append(paragraph(f"已知金额小计{money(client['known_subtotal'], currency)}；另{client['missing_count']}项未明确金额，未计入已知合计。", st["small"]))
    return story


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, report_label="", **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []
        self.report_label = report_label

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setStrokeColor(LINE)
            self.setLineWidth(.4)
            self.line(44, 34, A4[0] - 44, 34)
            self.setFont(REGULAR, 8)
            self.setFillColor(GRAY)
            self.drawString(44, 21, self.report_label)
            self.drawRightString(A4[0] - 44, 21, f"第 {self._pageNumber} 页 / 共 {total} 页")
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def build_pdf(kind, analysis, plan, report):
    if analysis.get("schema_version") != 1 or not isinstance(analysis.get("project"), dict):
        raise ValueError("请使用同一项目生成的 schema_version=1 analysis.json")
    register_fonts()
    st = styles()
    if kind not in FILES:
        raise ValueError("报告类型无效")
    story = document_story(kind, analysis, plan, report, st)
    target = BytesIO()
    label = "GEO品牌诊断报告" if kind == "diagnosis" else "品牌传播与GEO执行方案"
    doc = SimpleDocTemplate(target, pagesize=A4, rightMargin=44, leftMargin=44, topMargin=42, bottomMargin=49,
                            title=label, author="软文街", subject="客户品牌诊断与业务执行建议", pageCompression=1)
    doc.build(story, canvasmaker=lambda *a, **kw: NumberedCanvas(*a, report_label=label, **kw))
    return target.getvalue()


def export_pdf(kind, analysis, plan, report, output):
    data = build_pdf(kind, analysis, plan, report)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--kind", choices=["both", "diagnosis", "execution"], default="both")
    args = parser.parse_args()
    analysis, plan, report = load_json(args.analysis), load_json(args.plan), load_json(args.report)
    kinds = list(FILES) if args.kind == "both" else [args.kind]
    out = Path(args.output_dir)
    if any((out / FILES[k]).exists() for k in kinds):
        raise FileExistsError("输出已存在，拒绝覆盖，请使用新的输出目录")
    # Validate both reports before writing either customer deliverable.
    rendered = {kind: build_pdf(kind, analysis, plan, report) for kind in kinds}
    out.mkdir(parents=True, exist_ok=True)
    for kind, data in rendered.items():
        path = out / FILES[kind]
        with path.open("xb") as stream:
            stream.write(data)
        print(path)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
