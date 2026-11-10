"""Export editable customer PPTX files from geo_data.py analysis and reviewed prose.

Requires Python 3.10+ and python-pptx. No Codex runtime is used.
Example: python scripts/export_ppt.py --analysis analysis.json --plan plan.json
         --report report.json --output-dir outputs/customer

report.json contains customer-ready prose only. Supported sections: summary,
method_notes, scenarios, competitors, facts, sources, sentiment_summary, findings,
priorities, objectives, keywords, media_notes, quarterly, deliverables, targets,
prerequisites. Table entries use title/detail/evidence_ref. Unknown data stays
unknown. All sampled metrics and customer amounts come from analysis.json.
"""

from __future__ import annotations

import argparse
import copy
from datetime import date
import json
import re
import sys
import unicodedata
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt


FONT = "Microsoft YaHei"
BLUE, INK, PALE, BORDER = "245E91", "243B53", "EDF4FA", "D8E5EF"
MISSING = "待采集"
TEMPLATES = {
    "diagnosis": "GEO诊断报告模板.pptx",
    "execution": "品牌传播与GEO执行方案模板.pptx",
}


def value(item, fallback=MISSING):
    if item is None or item == "" or item == []:
        return fallback
    if isinstance(item, list):
        return "、".join(value(x, "") for x in item)
    return str(item)


def read_json(path, required=False):
    if path is None:
        if required:
            raise ValueError("缺少必需的 JSON 文件")
        return {}
    obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError(f"JSON 根节点须为对象：{path}")
    return obj


def rate(group, key, yes_key, no_key=None, denominator_key=None):
    measured = group.get(key)
    if measured is None:
        return "待核验"
    if not isinstance(measured, (int, float)) or not 0 <= measured <= 1:
        raise ValueError(f"无效比率：{key}")
    numerator = group.get(yes_key)
    denominator = group.get(denominator_key) if denominator_key else None
    if no_key and group.get(yes_key) is not None and group.get(no_key) is not None:
        denominator = group[yes_key] + group[no_key]
    suffix = f"\n{numerator}/{denominator} 已判样本" if denominator is not None else ""
    return f"{measured:.1%}{suffix}"


def scope_rows(analysis):
    project, counts = analysis.get("project", {}), analysis.get("counts", {})
    contexts = project.get("contexts", [])
    context_text = "\n".join(
        f"{value(c.get('platform'))} / {value(c.get('mode'))} / 联网{value(c.get('online'))} / 第{value(c.get('round'))}轮"
        for c in contexts
    ) or MISSING
    return [
        ["采样对象", value(project.get("brand_names"), value(project.get("client_name")))],
        ["平台、模式与轮次", context_text],
        ["问题与计划样本", f"问题 {value(counts.get('questions'))}，计划样本 {value(counts.get('planned'))}，每轮重复 {value(project.get('repeats'))}"],
        ["有效与缺失状态", f"有效 {value(counts.get('valid'))}，失败 {value(counts.get('failed'))}，待复核 {value(counts.get('pending_review'))}，未采 {value(counts.get('uncollected'))}"],
        ["实采日期", sampling_dates(analysis)],
        ["采样条件", f"明确不符合采样条件 {value(counts.get('invalid_conditions'), '待检查')} 条，采样条件未记录 {value(counts.get('condition_unknown'), '待检查')} 条。条件未记录项用于本次描述性观察，跨轮比较须补齐条件。"],
        ["统计边界", "按平台、模式、联网状态、轮次、问题类型与意图分别统计。待复核不计入已判分母。未展示来源不推断为没有检索或训练来源。"],
    ]


def sampling_dates(analysis):
    dates = []
    unknown = 0
    for sample in analysis.get("samples", []):
        timestamp = str(sample.get("采集时间") or "").strip()
        match = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", timestamp)
        if match:
            try:
                dates.append(date.fromisoformat("-".join(match.groups())).isoformat())
            except ValueError:
                unknown += 1
        elif sample.get("采集状态") == "已完成":
            unknown += 1
    if not dates:
        return "采集时间未记录" if unknown else "尚未采集"
    result = f"{min(dates)} 至 {max(dates)}"
    return result + (f"，另有 {unknown} 条已完成记录时间未知" if unknown else "")


def prose_rows(items, empty="暂无可核验记录", last_key="evidence_ref"):
    rows = []
    for item in items or []:
        if isinstance(item, str):
            rows.append(["观察", item, "待补证据"])
        elif isinstance(item, dict):
            title = next((item[k] for k in ("title", "name", "keyword", "scenario", "metric", "quarter") if item.get(k)), "观察")
            detail = next((item[k] for k in ("detail", "finding", "description", "observation", "result", "target") if item.get(k)), MISSING)
            rows.append([value(title), value(detail), value(item.get(last_key), "待补证据" if last_key == "evidence_ref" else "待确认")])
        else:
            raise ValueError("report 表格条目须为字符串或对象")
    return rows or [[empty, MISSING, "待补证据"]]


def paragraphs(item, fallback):
    if not item:
        return fallback
    if isinstance(item, str):
        return item
    lines = []
    for entry in item if isinstance(item, list) else [item]:
        if isinstance(entry, str):
            lines.append(entry)
        elif isinstance(entry, dict):
            title = value(entry.get("title"), "")
            detail = value(entry.get("detail"), "")
            reference = value(entry.get("evidence_ref"), "")
            lines.append(f"{title}：{detail}".strip("：") + (f"\n证据：{reference}" if reference else ""))
        else:
            raise ValueError("report 叙述条目须为字符串或对象")
    return "\n\n".join(lines)


def diagnosis_sections(analysis, report):
    counts = analysis.get("counts", {})
    summary = paragraphs(report.get("summary"), "本次诊断结论待采集，尚无足够证据形成品牌表现判断。")
    summary += f"\n\n计划样本 {value(counts.get('planned'))}，已完成 {value(counts.get('completed'))}，有效 {value(counts.get('valid'))}。"
    if counts.get("invalid_conditions"):
        summary += f"\n不符合采样条件 {counts['invalid_conditions']} 条，未纳入有效样本。"
    if counts.get("condition_unknown"):
        summary += f"\n采样条件未记录 {counts['condition_unknown']} 条，结果仅作本次描述性观察。"
    platforms = []
    for g in analysis.get("groups", []):
        platforms.append([
            f"{value(g.get('platform'))}\n{value(g.get('mode'))}\n联网{value(g.get('online'))}",
            f"{value(g.get('question_type'))}\n{value(g.get('intent'), '未分组')}\n第{value(g.get('round'))}轮",
            value(g.get("valid")),
            rate(g, "mention_rate", "mention_yes", "mention_no"),
            rate(g, "recommendation_rate", "recommendation_yes", "recommendation_no") if g.get("question_type") == "自然需求" and g.get("intent") == "推荐" else "不适用\n非自然推荐题",
            rate(g, "citation_rate", "citation_supported_samples", denominator_key="citation_known_samples"),
        ])
    sources = prose_rows(report.get("sources"), "AI引用来源待采集")
    sources += [["公开网络声量与舆情", paragraphs(report.get("sentiment_summary"), "未提供独立网络检索证据，暂不判断全网声量与正负面占比。"), value(report.get("sentiment_evidence_ref"), "待补网络证据")]]
    return {
        "summary": summary,
        "method": scope_rows(analysis) + ([["补充方法说明", paragraphs(report["method_notes"], "")]] if report.get("method_notes") else []),
        "platforms": platforms or [[MISSING] * 6],
        "scenarios": prose_rows(report.get("scenarios")),
        "competitors": prose_rows(report.get("competitors")),
        "facts": prose_rows(report.get("facts")),
        "sources": sources,
        "findings": prose_rows(report.get("findings")),
        "next": paragraphs(report.get("priorities"), "优先动作待确认。请先补齐缺失采样、来源证据与品牌事实核验，再确定执行优先级。"),
    }


def execution_sections(analysis, plan, report):
    budget = analysis.get("budget") or {}
    client = budget.get("client") or {}
    contents = [x for x in plan.get("contents", []) if x.get("status") not in {"取消", "排除"}]
    placements = [x for x in plan.get("placements", []) if x.get("status") in {"已选", "待执行", "已发布"}]
    content_rows = [[
        f"{value(x.get('content_id'))}\n{value(x.get('title'))}", value(x.get("question_ids")),
        f"{value(x.get('platform'))}\n{value(x.get('stage'))}", value(x.get("scheduled_date"), "待排期"),
        f"{value(x.get('evidence'))}\n{value(x.get('status'), '待确认')}",
    ] for x in contents] or [["待确认", MISSING, MISSING, "待排期", MISSING]]
    notes = report.get("media_notes", {})
    if not isinstance(notes, dict):
        raise ValueError("report.media_notes 须为媒体编号到客户可见选用理由的对象")
    media_rows = [[
        f"{value(x.get('media_name'))}\n{value(x.get('media_type'))}", value(x.get("content_id")),
        value(x.get("scheduled_date"), "待排期"), value(notes.get(x.get("media_id")), value(x.get("status"), "选用条件待确认")),
    ] for x in placements] or [["待选定", "待确认", "待排期", "适配条件待核验"]]
    quarters = prose_rows(report.get("quarterly"), "执行季度待确认", "retest")
    if not report.get("quarterly") and client.get("quarterly"):
        quarters = [[q, "按确认的内容与媒体明细执行", "复测与调整待确认"] for q in client["quarterly"]]
    currency = value(budget.get("currency"), "CNY")
    def amount(key):
        return f"{client[key]} {currency}" if client.get(key) is not None else "待报价或存在缺价"
    missing = client.get("missing_prices")
    budget_rows = [
        ["媒体投放", amount("media"), "客户媒体报价汇总"],
        ["其他服务", amount("fees"), "客户服务报价汇总，含税口径及范围见确认单"],
        ["计划合计", amount("total"), "存在缺价时合计保持未知"],
        ["预算上限", f"{budget['limit']} {currency}" if budget.get("limit") is not None else "待确认", "以客户确认预算为准"],
        ["预算状态", "存在待报价项目" if missing else ("超出上限，待调整" if client.get("exceeds_limit") else "按已报价项目测算" if client.get("total") is not None else "待报价"), "不以刊发、搜索收录替代AI引用效果验收"],
    ]
    if client.get("known_subtotal") is not None and client.get("missing_count"):
        budget_rows.append(["已知金额小计", f"{client['known_subtotal']} {currency}", f"待报价或缺数量 {value(client.get('missing_count'))} 项；计划合计缺价时仍保持未知"])
    if client.get("quarterly"):
        budget_rows.extend([[f"{q} 客户计划费用", f"{r['total']} {currency}" if r.get("total") is not None else "待报价或存在缺价", "按自然季度排期归属，未排期单列"] for q, r in client["quarterly"].items()])
    deliverables = prose_rows(report.get("deliverables"), "交付与责任待确认", "time")
    if budget:
        deliverables.insert(0, ["内容与刊发计划", f"计划内容 {value(budget.get('planned_content_count'))} 项，其中已纳入投放内容 {value(budget.get('content_count'))} 项，投放记录 {value(budget.get('placement_count'))} 项，计划刊发 {value(budget.get('publication_count'))} 次", "以明细和发布凭证验收"])
    targets = prose_rows(report.get("targets"), "目标值待客户确认", "method")
    return {
        "objectives": paragraphs(report.get("objectives"), "品牌传播目标待确认。\n\nGEO目标待确认，待建立可复测基线后确定目标值。"),
        "keywords": prose_rows(report.get("keywords")),
        "contents": content_rows, "media": media_rows, "quarterly": quarters,
        "deliverables": deliverables, "budget": budget_rows, "targets": targets,
        "prerequisites": paragraphs(report.get("prerequisites"), "客户确认品牌事实、可公开素材与服务边界。\n\n客户与执行方确认媒体、客户报价、排期及复测条件。"),
    }


def line_wrap(text, width_units):
    lines, line, size = [], "", 0.0
    for char in str(text):
        if char == "\n":
            lines.append(line)
            line, size = "", 0.0
            continue
        units = 1.0 if unicodedata.east_asian_width(char) in "WF" else 0.6
        if line and size + units > width_units:
            lines.append(line)
            line, size = "", 0.0
        line += char
        size += units
    lines.append(line)
    return lines


def row_pages(rows, widths):
    expanded = []
    for row in rows:
        if len(row) != len(widths):
            raise ValueError("PPT 表格列数与模板不一致")
        wrapped = [line_wrap(value(cell), max(3, w / 914400 * 72 / 16 - 1.5)) for cell, w in zip(row, widths)]
        for start in range(0, max(map(len, wrapped)), 3):
            current = ["\n".join(lines[start:start + 3]) or ("续" if col == 0 else "") for col, lines in enumerate(wrapped)]
            tail = "".join(cell for cell in current if cell != "续").strip()
            if start and tail and all(unicodedata.category(c).startswith("P") or c.isspace() for c in tail):
                # Keep a sentence fragment with trailing punctuation on continuation rows.
                for col, cell in enumerate(current):
                    if cell and cell != "续":
                        previous = expanded[-1][col].split("\n")
                        current[col] = previous.pop() + "\n" + cell
                        expanded[-1][col] = "\n".join(previous)
            expanded.append(current)
    return [expanded[i:i + 4] for i in range(0, len(expanded), 4)] or [[ [MISSING] * len(widths) ]]


def font(run, size, color, bold=False):
    run.font.name, run.font.size, run.font.bold = FONT, Pt(size), bold
    run.font.color.rgb = RGBColor.from_string(color)
    properties = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        element = properties.find(tag, properties.nsmap)
        if element is None:
            element = OxmlElement(tag)
            properties.append(element)
        element.set("typeface", FONT)


def set_text(shape, content, size=22, color=INK, bold=False):
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    for index, line in enumerate(str(content).split("\n")):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_before = paragraph.space_after = Pt(0)
        paragraph.line_spacing = 1.15
        run = paragraph.add_run()
        run.text = line
        font(run, size, color, bold)


def clone_after(prs, source, after):
    clone = prs.slides.add_slide(source.slide_layout)
    for shape in list(clone.shapes):
        clone.shapes._spTree.remove(shape._element)
    for shape in source.shapes:
        clone.shapes._spTree.insert_element_before(copy.deepcopy(shape.element), "p:extLst")
    ids = prs.slides._sldIdLst
    last = ids[-1]
    ids.remove(last)
    ids.insert(after + 1, last)
    return clone


def update_table(slide, rows):
    shape = next(x for x in slide.shapes if x.has_table)
    old = shape.table
    headers = [cell.text for cell in old.rows[0].cells]
    widths = [column.width for column in old.columns]
    x, y, w = shape.left, shape.top, shape.width
    slide.shapes._spTree.remove(shape._element)
    table_shape = slide.shapes.add_table(len(rows) + 1, len(headers), x, y, w, Pt(42 + 70 * len(rows)))
    table_shape.name = "geo_data_table"
    table = table_shape.table
    for col, width in zip(table.columns, widths):
        col.width = width
    for r, row in enumerate([headers] + rows):
        table.rows[r].height = Pt(42 if r == 0 else 70)
        for c, text in enumerate(row):
            cell = table.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(BLUE if r == 0 else ("FFFFFF" if r % 2 else PALE))
            cell.margin_left = cell.margin_right = Pt(7)
            cell.margin_top = cell.margin_bottom = Pt(5)
            cell.text_frame.clear()
            for n, line in enumerate(str(text).split("\n")):
                p = cell.text_frame.paragraphs[0] if n == 0 else cell.text_frame.add_paragraph()
                p.space_before = p.space_after = Pt(0)
                p.line_spacing = 1.1
                run = p.add_run()
                run.text = line
                font(run, 16, "FFFFFF" if r == 0 else INK, r == 0)


def visible_text(prs):
    parts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text)
            elif shape.has_table:
                parts.extend(cell.text for row in shape.table.rows for cell in row.cells)
    return "\n".join(parts)


def verify_plan(analysis, plan):
    if not plan and analysis.get("budget") is None:
        return
    from geo_data import calculate_budget
    if analysis.get("budget") != calculate_budget(analysis.get("project", {}), plan):
        raise ValueError("plan.json 与 analysis.json 预算不一致，请重新运行 geo_data.py analyze 后再导出 PPT")


def export(kind, analysis, plan, report, output, template_dir=None):
    if kind == "execution":
        verify_plan(analysis, plan)
    root = Path(template_dir) if template_dir else Path(__file__).resolve().parent.parent / "templates"
    prs = Presentation(root / TEMPLATES[kind])
    sections = diagnosis_sections(analysis, report) if kind == "diagnosis" else execution_sections(analysis, plan, report)
    project = analysis.get("project", {})
    client = value(project.get("client_name"), "客户名称待确认")
    brand = value(project.get("brand_names"), client)
    cover = f"{brand}\n{client}\n报告日期：{value(report.get('report_date'), '待确认')}"
    if kind == "execution":
        cover += f"\n执行周期：{value(project.get('start_date'), '待确认')} 至 {value(project.get('end_date'), '待确认')}"
    for original in list(prs.slides):
        title_shape = next((x for x in original.shapes if x.name.startswith("geo_section_")), None)
        if title_shape is None:
            raise ValueError("模板缺少章节标识，请使用随 skill 发布的模板")
        key, title = title_shape.name.removeprefix("geo_section_"), title_shape.text
        data = cover if key == "cover" else sections.get(key, MISSING)
        table_shape = next((x for x in original.shapes if x.has_table), None)
        if table_shape:
            pages = row_pages(data, [c.width for c in table_shape.table.columns])
        else:
            content = next(x for x in original.shapes if x.name == "geo_content")
            lines = line_wrap(data, content.width / 914400 * 72 / 22 - 1)
            # Continuation pages preserve long customer prose instead of shrinking it.
            limit = 5 if key == "cover" else 10
            pages = ["\n".join(lines[i:i + limit]) for i in range(0, len(lines), limit)]
        slide = original
        for index, page in enumerate(pages):
            if index:
                position = list(prs.slides).index(slide)
                slide = clone_after(prs, original, position)
            heading = next(x for x in slide.shapes if x.name.startswith("geo_section_"))
            set_text(heading, title + (f"（续{index + 1}）" if index else ""), 37.5 if key == "cover" else 32.25, BLUE, True)
            if table_shape:
                update_table(slide, page)
            else:
                content = next(x for x in slide.shapes if x.name == "geo_content")
                set_text(content, page, 22)
    for index, slide in enumerate(prs.slides):
        footer = next((x for x in slide.shapes if x.name == "geo_footer"), None)
        if footer:
            set_text(footer, f"软文街  {index + 1:02d} / {len(prs.slides):02d}", 10.5, "526777")
    if re.search(r"\{\{[^}]+\}\}|\$\{[^}]+\}", visible_text(prs)):
        raise ValueError("客户文案含未替换的模板标记，请补齐 report.json")
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        try:
            prs.save(handle)
        except Exception:
            handle.close()
            target.unlink(missing_ok=True)
            raise
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--plan")
    parser.add_argument("--report")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--kind", choices=["both", "diagnosis", "execution"], default="both")
    args = parser.parse_args()
    analysis = read_json(args.analysis, required=True)
    if analysis.get("schema_version") != 1 or not isinstance(analysis.get("project"), dict):
        raise ValueError("请先使用 geo_data.py 生成 schema_version=1 的 analysis.json")
    plan, report = read_json(args.plan), read_json(args.report)
    if args.kind in {"both", "execution"}:
        verify_plan(analysis, plan)
    for kind in TEMPLATES if args.kind == "both" else [args.kind]:
        name = "GEO诊断报告.pptx" if kind == "diagnosis" else "品牌传播与GEO执行方案.pptx"
        print(export(kind, analysis, plan, report, Path(args.output_dir) / name))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
