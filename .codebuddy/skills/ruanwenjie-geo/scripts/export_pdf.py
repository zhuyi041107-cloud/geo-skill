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
from reportlab.platypus import HRFlowable, LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


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


def section_value(report, kind, key, *legacy):
    nested = report.get(kind) or {}
    if not isinstance(nested, dict):
        raise ValueError(f"report.{kind} 须为对象")
    if key in nested:
        return nested[key]
    for name in legacy:
        if name in report:
            return report[name]
    return None


def add_entries(story, values, st):
    for item in entries(values):
        if item["title"] not in EMPTY:
            story.append(paragraph(item["title"], st["h3"]))
        for block in re.split(r"\n\s*\n", item["detail"]):
            if block.strip():
                story.append(paragraph(block, st["body"]))


def add_section(story, title, values, st):
    if entries(values):
        story.append(paragraph(title, st["h2"]))
        add_entries(story, values, st)


def table(headers, rows, widths, st):
    data = [[paragraph(c, st["head"]) for c in headers]]
    data.extend([[paragraph(c, st["cell"]) for c in row] for row in rows])
    header_height = max(cell.wrap(width - 16, 10000)[1] for cell, width in zip(data[0], widths)) + 14
    available_height = A4[1] - 42 - 49 - header_height
    oversized_row = any(max(cell.wrap(width - 16, 10000)[1] for cell, width in zip(row, widths)) + 14 > available_height for row in data[1:])
    result = LongTable(data, colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=int(oversized_row), hAlign="LEFT", spaceBefore=6, spaceAfter=10)
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
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


def metric(yes, no):
    if not isinstance(yes, int) or not isinstance(no, int) or yes + no == 0:
        return "未核验"
    return f"{yes}/{yes + no}（{yes / (yes + no):.1%}）"


def diagnosis_story(analysis, report, st):
    summary = section_value(report, "diagnosis", "summary", "summary")
    findings = section_value(report, "diagnosis", "key_findings", "findings")
    if not entries(summary) or not entries(findings):
        raise ValueError("诊断报告需要完整的品牌现状摘要和关键问题分析，请由 WorkBuddy 根据本轮材料撰写")
    story = []
    add_header(story, "diagnosis", analysis, report, st)
    story.append(paragraph("一、品牌当前现状", st["h2"]))
    add_entries(story, summary, st)
    add_entries(story, section_value(report, "diagnosis", "brand_status", "brand_status"), st)
    rows = []
    for group in sampled_groups(analysis):
        label = f"{text(group.get('platform'))}\n{text(group.get('question_type'))} · {text(group.get('intent'))}"
        recommendation = metric(group.get("recommendation_yes"), group.get("recommendation_no")) if group.get("question_type") == "自然需求" and group.get("intent") == "推荐" else "-"
        rows.append([label, str(group.get("valid", 0)), metric(group.get("mention_yes"), group.get("mention_no")), recommendation])
    if rows:
        story.append(table(["用户需求入口", "本轮回答", "品牌提及", "推荐提及"], rows, [WIDTH * .36, WIDTH * .13, WIDTH * .255, WIDTH * .255], st))
    sections = [
        ("二、需求入口与推荐位置", "demand_entries", ("scenarios",)),
        ("三、竞品与用户选择逻辑", "competitors", ("competitors",)),
        ("四、品牌事实与实体一致性", "fact_consistency", ("facts",)),
        ("五、信息来源与信任结构", "source_structure", ("sources",)),
        ("六、关键问题与业务影响", "key_findings", ("findings",)),
        ("七、优先结论与落地重点", "priorities", ("priorities",)),
    ]
    for heading, key, legacy in sections:
        add_section(story, heading, section_value(report, "diagnosis", key, *legacy), st)
    return story


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


def execution_story(analysis, plan, report, st):
    budget = verify_budget(analysis, plan)
    client, currency = budget["client"], budget.get("currency", "CNY")
    contents, placements, fees = selected_plan(plan)
    objectives = section_value(report, "execution", "objectives", "objectives")
    if not entries(objectives) or not contents or not placements:
        raise ValueError("执行方案需要业务目标、已选内容和具体媒体组合，不能只生成空版式")
    for placement in placements:
        name = text(placement.get("media_name"))
        if not name or re.search(r"待报价|待选择|待选定|TBD|类媒体|媒体类型", name, re.I):
            raise ValueError("执行方案应选用资源表中的具体媒体名称，不能用媒体类型或待定项代替")
    story = []
    add_header(story, "execution", analysis, report, st)
    summary = section_value(report, "execution", "summary")
    if entries(summary):
        add_entries(story, summary, st)
    add_section(story, "一、品牌传播与GEO目标", objectives, st)
    add_section(story, "二、关键词与内容方向", section_value(report, "execution", "keywords", "keywords"), st)
    add_entries(story, section_value(report, "execution", "content_strategy", "content_strategy"), st)

    story.append(paragraph("三、内容选题与发表安排", st["h2"]))
    by_content = {c["content_id"]: c for c in contents}
    content_rows = [[text(c.get("title")), text(c.get("stage")) or "业务内容", text(c.get("scheduled_date")) or "执行期内"] for c in contents]
    story.append(table(["选题", "内容用途", "建议时间"], content_rows, [WIDTH * .59, WIDTH * .20, WIDTH * .21], st))

    story.append(paragraph("四、媒体组合与配置理由", st["h2"]))
    add_entries(story, section_value(report, "execution", "media_rationale", "media_rationale"), st)
    media_rows = []
    for placement in placements:
        quantity = placement.get("quantity")
        unit = placement.get("client_unit_price")
        subtotal = Decimal(str(unit)) * int(Decimal(str(quantity))) if unit not in (None, "") and quantity not in (None, "") else None
        media_rows.append([
            text(placement.get("media_name")),
            text(by_content.get(placement.get("content_id"), {}).get("title")),
            f"{quantity}次" if quantity not in (None, "") else "次数待明确",
            text(placement.get("scheduled_date")) or "执行期内",
            money(subtotal, currency) + "\n" + (text(placement.get("price_basis")) or "价格依据未注明") + "\n报价日期：\n" + (text(placement.get("quotation_date")) or "未注明"),
        ])
    story.append(table(["媒体名称", "承载内容", "刊发", "建议时间", "建议媒体费用"], media_rows, [WIDTH * .24, WIDTH * .31, WIDTH * .08, WIDTH * .18, WIDTH * .19], st))

    story.append(paragraph("五、季度执行计划", st["h2"]))
    add_entries(story, section_value(report, "execution", "quarterly", "quarterly"), st)
    quarterly_contents = defaultdict(list)
    for content in contents:
        quarterly_contents[quarter(content.get("scheduled_date"))].append(text(content.get("title")))
    quarter_rows = []
    for name, totals in client.get("quarterly", {}).items():
        label = "执行期内" if name == "未排期" else name
        titles = quarterly_contents.get(label) or []
        quarter_rows.append([label, "\n".join(titles) or "按本阶段媒体与内容安排推进", money(totals.get("total"), currency)])
    if quarter_rows:
        story.append(table(["自然季度", "本阶段内容安排", "客户计划费用"], quarter_rows, [WIDTH * .18, WIDTH * .58, WIDTH * .24], st))

    story.append(paragraph("六、费用预算与投入节奏", st["h2"]))
    budget_intro = "以下为按已选媒体、刊发次数及逐项价格依据测算的建议媒体投放包，金额按表内报价日期对应价格形成，执行价格以当次确认条件为准。"
    if budget.get("limit") is not None:
        budget_intro += f"客户预算上限为{money(budget['limit'], currency)}。"
    story.append(paragraph(budget_intro, st["body"]))
    budget_rows = [["媒体投放费用", money(client.get("media"), currency)]]
    for fee in fees:
        budget_rows.append([text(fee.get("description")) or text(fee.get("category")), money(fee.get("client_amount"), currency)])
    budget_rows.append(["本建议费用合计", money(client.get("total"), currency)])
    if client.get("missing_count"):
        budget_rows.append(["已知金额小计", money(client.get("known_subtotal"), currency)])
    story.append(table(["投入项目", "建议金额"], budget_rows, [WIDTH * .70, WIDTH * .30], st))
    if not fees:
        story.append(paragraph("本页为媒体投放费用口径，不含未列入计划的稿件撰写、官网建设等服务费用。", st["small"]))
    if client.get("missing_count"):
        story.append(paragraph(f"其中{client['missing_count']}项金额或刊发次数尚未明确，已知小计不代表完整预算。", st["small"]))

    story.append(paragraph("七、预期交付与效果观察", st["h2"]))
    count_parts = []
    if budget.get("content_count") is not None:
        count_parts.append(f"{budget['content_count']}篇独立内容")
    if budget.get("publication_count") is not None:
        count_parts.append(f"{budget['publication_count']}次媒体刊发")
    if count_parts:
        story.append(paragraph("计划形成" + "、".join(count_parts) + "，实际选题、渠道与季度安排见前述明细。", st["body"]))
    add_entries(story, section_value(report, "execution", "expected_deliverables", "deliverables", "targets"), st)
    story.append(paragraph("内容发布与AI表现分别观察。AI提及、引用、推荐位置及业务转化受平台与市场变化影响，本建议不作结果保证。", st["small"]))
    add_section(story, "八、客户协作与执行重点", section_value(report, "execution", "client_actions", "prerequisites"), st)
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
    story = diagnosis_story(analysis, report, st) if kind == "diagnosis" else execution_story(analysis, plan, report, st)
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
