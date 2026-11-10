"""Fill sealed HTML templates and print them with the local Chromium browser."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from decimal import Decimal
from html import escape
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
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
    meta_patterns = (
        r"(?:本轮|本次|本报告|本诊断)[^。；\n]{0,75}(?:观察基础|采样|样本|回传|网页端联网)",
        r"(?:以|基于|依据)[^。；\n]{0,65}(?:回答|问答|截图)[^。；\n]{0,12}(?:为|作为)(?:观察|分析|诊断|判断)(?:基础|依据)",
        r"(?:观察|采样|样本|采集)(?:范围|数量|方法|口径)[：:]|(?:样本(?:量|数量)?|采样数量|回答数量)(?:不足|有限|偏少|不够)",
        r"(?:本轮|本次)(?:仅|只)(?:覆盖|观察|收到|回传|采集)|(?:尚未|未)(?:收到|回传|采集)[^。；\n]{0,30}(?:其他|其余|更多)(?:平台|模型)",
        r"(?:按|按照)[^。；\n]{0,20}(?:题型|问题意图)[^。；\n]{0,25}(?:统计|计数|阅读|混算)|(?:问题|问句|回答|提及率)[^。；\n]{0,25}(?:分母|相加当成|混算)",
        r"(?:同一批|同样)[^。；\n]{0,20}(?:问题|问句)[^。；\n]{0,25}(?:网页端|重新采集|按[^。；\n]{0,10}统计)",
        r"(?:本轮|本次)[^。；\n]{0,15}(?:把|按|记为)[^。；\n]{0,25}(?:推荐失败|未承接|计数|分母)|(?:两个客群|题型|通用核验|点名题)[^。；\n]{0,35}(?:合成一个提及率|强求点名|混算)",
        r"(?:采样任务|人工采样|题目数量不是固定|按原模板|历史案例的场景数量|用于展示怎样|以下判定只服务|观察限定|不代表真实(?:平台|检测|客户)|虚构演示情境)",
        r"(?:演示材料|本轮材料|本例来源|本例回答|本例业务推演)|(?:演示|虚构)[^。；\n]{0,25}(?:不形成真实|不承担真实|不代表真实)",
        r"(?:观察端口|文章形态)[^。；\n]{0,20}(?:不由|不按|推断|推测|猜测)[^。；\n]{0,15}(?:端口|抓取|机制|形态)|不暂停整套交付",
        r"(?:达到|满足)[^。；\n]{0,15}(?:目标|预算)[^。；\n]{0,12}(?:九成|90%)|(?:内部采购成本|补差额|凑预算)",
    )
    if any(re.search(pattern, result) for pattern in meta_patterns):
        raise ValueError("客户正文包含观察基础、采样口径或制作说明，请改成品牌具体情况、原因分析与业务影响；事实不确定请在对应事项局部说明")
    return result

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

def report_date(analysis, report):
    return text(report.get("report_date")) or text((analysis.get("report_scope") or {}).get("report_date")) or date.today().isoformat()

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
    if kind == "diagnosis" and report.get("template_profile") == "platform":
        cards = doc.get("priority_cards")
        if not isinstance(cards, list) or len(cards) != 4 or any(not isinstance(row, list) or len(row) != 3 or not all(text(value) for value in row) for row in cards):
            raise ValueError("原模板四张优化卡须填写diagnosis.priority_cards四行[标题,优先级,说明]，不增加新任务或费用")
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
        entries(section.get("paragraphs"))
        if report.get("template_profile") == "platform" and kind == "execution" and spec["key"] == "budget":
            card = section.get("quote_card", {})
            if not isinstance(card, dict) or any(not isinstance(card.get(key), str) or text(card[key]) in EMPTY for key in ("name", "focus", "suitability")):
                raise ValueError("原费用报价卡须填写 quote_card.name/focus/suitability；金额和媒体配置从计划生成")
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
            if required["id"] in {"decision_path", "response_layers"} and len(rows) != 4:
                raise ValueError("原决策图与四层图均为四个固定文字位，不改变原图结构")
            if required["id"] == "recognition" and len(rows) != 3:
                raise ValueError("原品牌现状为三项判定，其他事实写入原说明列")
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

def validate_logic_links(plan, report):
    required_tables = [("priority_actions", "actions", 1)]
    if report.get("template_profile") == "platform":
        required_tables.append(("competitive_tags", "proposed_tags", 0))
    diagnosis_items = set()
    sections = report.get("diagnosis", {}).get("sections", [])
    for section_key, table_id, item_column in required_tables:
        tables = [t for s in sections if s.get("key") == section_key for t in s.get("tables", []) if t.get("id") == table_id]
        if len(tables) != 1 or not tables[0].get("rows"):
            raise ValueError(f"执行方案缺少诊断来源矩阵 {section_key}.{table_id}，无法核对逻辑映射")
        for row in tables[0]["rows"]:
            if not isinstance(row, list) or len(row) <= item_column or not isinstance(row[item_column], str) or text(row[item_column]) in EMPTY:
                raise ValueError(f"诊断来源矩阵 {table_id} 的优先项或标签名称不能为空")
            diagnosis_items.add(text(row[item_column]))
    links = plan.get("logic_links")
    if not isinstance(links, list) or not links:
        raise ValueError("执行方案须有 plan.logic_links，将诊断优先项及建议标签关联到实际内容或客户自有动作")
    contents, placements, _ = selected_plan(plan)
    by_content = {c["content_id"]: c for c in contents}
    stages = {text(stage.get("name")) for stage in plan.get("stages", []) if text(stage.get("name"))}
    by_placement = defaultdict(list)
    for placement in placements:
        by_placement[placement["content_id"]].append(placement)
    covered = set()
    for index, link in enumerate(links, 1):
        if not isinstance(link, dict):
            raise ValueError(f"logic_links 第{index}项须为对象")
        for field in ("diagnosis_item", "basis", "choice_reason", "media_role", "stage", "check_date"):
            if not isinstance(link.get(field), str) or text(link[field]) in EMPTY:
                raise ValueError(f"logic_links 第{index}项的 {field} 须为非空文字")
        item, stage = text(link["diagnosis_item"]), text(link["stage"])
        if item not in diagnosis_items:
            raise ValueError(f"logic_links 的 diagnosis_item 不在实际诊断优先项或建议标签中：{item}")
        if stage not in stages:
            raise ValueError(f"logic_links 引用不存在的阶段：{stage}")
        ids = link.get("content_ids", [])
        if not isinstance(ids, list) or any(not isinstance(i, str) or not i.strip() for i in ids):
            raise ValueError("logic_links.content_ids 须为内容编号列表")
        action = link.get("client_action", "")
        if not isinstance(action, str):
            raise ValueError("logic_links.client_action 须为具体客户自有动作的文字说明")
        if not ids and text(action) in EMPTY:
            raise ValueError(f"logic_links 的 {item} 须关联实际内容或具体 client_action")
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", link["check_date"]):
                raise ValueError()
            check_date = date.fromisoformat(link["check_date"])
        except ValueError as exc:
            raise ValueError("logic_links.check_date 须为有效 YYYY-MM-DD 日期") from exc
        for content_id in ids:
            content = by_content.get(content_id)
            if content is None:
                raise ValueError(f"logic_links 引用不存在或未选用的内容：{content_id}")
            if text(content.get("stage")) != stage:
                raise ValueError(f"logic_links 内容 {content_id} 不属于声明阶段 {stage}，跨阶段请分行映射")
            active = by_placement.get(content_id, [])
            if not active:
                raise ValueError(f"logic_links 内容 {content_id} 没有有效 placement")
            for record in [content, *active]:
                try:
                    scheduled = date.fromisoformat(record["scheduled_date"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"logic_links 内容 {content_id} 及其有效刊发须有计划日期") from exc
                if check_date < scheduled:
                    raise ValueError(f"logic_links 的检查日期早于内容 {content_id} 或其刊发计划日期")
        covered.add(item)
    missing = diagnosis_items - covered
    if missing:
        raise ValueError("诊断优先项或建议标签缺少 logic_links 映射：" + "、".join(sorted(missing)))

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
            row = [f"第{content_week(c, project)}周", text(c["source_layer"]), joined(p.get("media_type") for p in by_placement[c["content_id"]]), text(c["content_form"]), text(c["title"]), text(c["platform"])]
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
            weekly_counts = [len(weeks.get(week, [])) for week in range(min(weeks), max(weeks) + 1)]
            low, high = min(weekly_counts), max(weekly_counts)
            counts = f"每周{low}篇" if low == high else f"每周{low}-{high}篇"
            stage = stages[name]
            rows.append([name, f"第{min(weeks)}-{max(weeks)}周", text(stage["objective"]), counts, f"{len(cs)}篇独立内容\n{sum(int(Decimal(str(p['quantity']))) for p in ps)}次刊发", text(stage["deliverables"]), text(stage["effect_target"])])
        return rows
    if table_id == "content_volume":
        rows = []
        for layer in dict.fromkeys(c["source_layer"] for c in contents):
            cs = [c for c in contents if c["source_layer"] == layer]
            ps = [p for c in cs for p in by_placement[c["content_id"]]]
            targets = joined(c.get("target_question") or "；".join(questions[q] for q in c.get("question_ids", []) if q in questions) for c in cs)
            publications = sum(int(Decimal(str(p['quantity']))) for p in ps)
            basis = f"围绕本层实际选题与不同事实分别成稿；{len(cs)}篇内容、{publications}次刊发"
            rows.append([layer, str(len(cs)), basis, targets] if analysis.get("_template_profile") == "service" else [layer, str(len(cs)), str(publications), basis, targets])
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
        result = []
        for kind, items in buckets.items():
            row = [kind, str(sum(int(Decimal(str(p["quantity"]))) for p in items)), price_range(items, currency), money(sum_price(items), currency)]
            if analysis.get("_template_profile") == "service":
                row += [joined(p.get("media_role") or p.get("category") for p in items), joined(p.get("execution_note") for p in items)]
            result.append(row)
        return result
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
            publication_count = sum(int(Decimal(str(p["quantity"]))) for p in ps)
            if analysis.get("_template_profile") == "service":
                mix = defaultdict(int)
                for p in ps: mix[text(p.get("media_type"))] += int(Decimal(str(p["quantity"])))
                weeks = [content_week(c, project) for c in cs]
                rows.append([name, f"第{min(weeks)}-{max(weeks)}周", f"{len(cs)}篇 / {publication_count}次", " / ".join(f"{kind}{count}次" for kind, count in mix.items()), money(total, currency), text(stages[name].get("budget_note"))])
            else:
                rows.append([name, f"{dates[0]}\n至 {dates[-1]}", str(len(cs)), str(publication_count), money(m, currency), money(f, currency), money(total, currency)])
        unassigned = [f for f in fees if f["fee_id"] not in assigned_fees]
        if unassigned:
            value = sum((Decimal(str(f["client_amount"])) for f in unassigned), Decimal(0)) if all(f.get("client_amount") not in (None, "") for f in unassigned) else None
            rows.append(["其他已列费用", "执行期内", "0", "无媒体刊发", money(value, currency), ""] if analysis.get("_template_profile") == "service" else ["未分配阶段的其他费用", "执行期内", "0", "0", money(0, currency), money(value, currency), money(value, currency)])
        return rows
    raise ValueError(f"不支持的同源表：{table_id}")

def quotation_note(placements):
    bases = joined(p.get("price_basis") for p in placements)
    dates = joined(p.get("quotation_date") for p in placements)
    return "报价口径：" + (bases or "价格依据未注明") + "。报价日期：" + (dates or "未注明") + "。本表为建议媒体投放包，执行价格以当次确认条件为准。"


def template_context(kind, analysis, plan, report):
    sections = validate_document(report, kind)
    budget = verify_budget(analysis, plan)
    if kind == "execution":
        from geo_data import validate_delivery_budget
        validate_delivery_budget(budget)
        plan_context(analysis, plan)
        validate_logic_links(plan, report)
    analysis = {**analysis, "_template_profile": report["template_profile"]}
    project = analysis["project"]
    contents, placements, fees = selected_plan(plan)
    platforms = list(dict.fromkeys(text(c.get("platform")) for c in contents if text(c.get("platform"))))
    sampled = list(dict.fromkeys(text(c.get("platform")) for c in analysis.get("sampled_contexts", []) if text(c.get("platform"))))
    if kind == "diagnosis" and sampled:
        platforms = sampled
    elif not platforms:
        platforms = sampled
    brand = text(project.get("brand_names")) or text(project.get("client_name"))
    card = next((s.get("quote_card", {}) for spec, s in sections if spec["key"] == "budget"), {})
    mix = defaultdict(int)
    for placement in placements:
        mix[text(placement.get("media_type"))] += int(Decimal(str(placement["quantity"])))
    slots = {
        "brand": brand, "client_name": text(project.get("client_name")), "report_date": report_date(analysis, report),
        "report_title": brand + (" · AI 品牌 GEO 知识库诊断报告" if kind == "diagnosis" else " GEO 落地执行方案"),
        "subtitle": text(project.get("industry")), "platform_names": "、".join(platforms),
        "summary": "\n".join(e["detail"] for e in entries(report[kind]["summary"])),
        "business_scope": text(project.get("services")) or text(project.get("industry")),
        "report_purpose": "品牌现状分析与优化规划" if kind == "diagnosis" else "品牌传播与GEO执行安排",
        "execution_period": f"{text(project.get('start_date'))} 至 {text(project.get('end_date'))}",
        "content_count": str(budget["content_count"]), "publication_count": str(budget["publication_count"]),
        "budget_total": money(budget["client"]["total"], budget["currency"]),
        "checkpoints": joined(c.get("checkpoint") for c in contents),
        "quote_name": text(card.get("name")), "quote_focus": text(card.get("focus")), "quote_suitability": text(card.get("suitability")),
        "price_basis": joined(p.get("price_basis") for p in placements), "quotation_date": joined(p.get("quotation_date") for p in placements),
        "media_mix": " / ".join(f"{name}{count}次" for name, count in mix.items()),
        "fees_note": "；".join(text(f.get("description") or f.get("category")) + "：" + money(f.get("client_amount"), budget["currency"]) for f in fees)
        or "本期已列媒体投放，不含未报价的撰稿、官网建设和后续维护。",
    }
    subject = text(project.get("client_name")) if report["template_profile"] == "service" else brand
    if brand and brand not in subject:
        subject += "（品牌：" + brand + "）"
    slots["cover_title"] = subject + (" · AI 品牌 GEO 知识库诊断报告" if kind == "diagnosis" else " GEO 落地执行方案")
    slots["running_title"] = slots["cover_title"]
    slots["port_heading"] = " / ".join(platforms) + "端口"
    extra = report[kind].get("fields", {})
    if not isinstance(extra, dict) or any(not isinstance(v, str) for v in extra.values()):
        raise ValueError("报告fields只能填写模板文字槽，不得提供HTML、CSS或布局配置")
    protected = (set(slots) - {"subtitle", "business_scope", "report_purpose"}) | {"schedule_total", "cognition_status", "decision_status", "recognition_band", "decision_band", "response_title"}
    if protected & set(extra):
        raise ValueError("fields不能覆盖同源项目、计划或费用字段：" + "、".join(sorted(protected & set(extra))))
    slots.update(extra)
    tables, paragraphs = {}, {}
    for spec, section in sections:
        paragraphs[spec["key"]] = entries(section.get("paragraphs"))
        for definition in spec["tables"]:
            if definition.get("source") == "plan":
                tables[definition["id"]] = automatic_rows(definition["id"], analysis, plan)
            else:
                tables[definition["id"]] = next(t["rows"] for t in section["tables"] if t["id"] == definition["id"])
    blocks = report[kind].get("blocks", {})
    if not isinstance(blocks, dict):
        raise ValueError("blocks须按固定模板位置填写文字，不提供新章节或HTML")
    for key, value in blocks.items():
        paragraphs[key] = entries(value)
    if kind == "execution" and fees:
        key = "budget_notes" if report["template_profile"] == "platform" else "fees_scope"
        notes = paragraphs.setdefault(key, [])
        if slots["fees_note"] not in "\n".join(item["detail"] for item in notes):
            notes.append({"title": "", "detail": "其他已列费用：" + slots["fees_note"]})
    for values in paragraphs.values():
        for entry in values:
            customer_text(entry["title"]); customer_text(entry["detail"])
    if "recognition" in tables:
        tables["recognition_cards"] = tables["recognition"]
    if "dimensions" in tables:
        display_rows = []
        for row in tables["dimensions"]:
            display = list(row)
            score = re.fullmatch(r"(.*?)\s*[（(]?\s*(\d+(?:\.\d+)?\s*/\s*5)\s*[）)]?", text(display[0]))
            if score:
                display[0] = score[1].strip()
            display_rows.append(display + [score[2] if score else ""])
        tables["dimensions"] = display_rows
    if "stage_plan" in tables:
        tables["stage_cards"] = tables["stage_plan"]
    layers = tables.get("response_layers", [])
    layer_questions = report.get("diagnosis", {}).get("layer_questions", [])
    if layer_questions and (not isinstance(layer_questions, list) or len(layer_questions) != len(layers) or any(not isinstance(q, str) for q in layer_questions)):
        raise ValueError("layer_questions须与四层图逐项对应，仅填写已有实际问法")
    if layers:
        tables["response_layers"] = [list(row) + [layer_questions[i] if layer_questions else row[1]] for i, row in enumerate(layers)]
    slots.setdefault("cognition_status", text(layers[0][3]) if layers else "")
    slots.setdefault("decision_status", text(layers[1][3]) if len(layers) > 1 else "")
    for alias, key in (("recognition_band", "cognition_status"), ("decision_band", "decision_status"), ("journey_recognition", "cognition_status"), ("journey_decision", "decision_status")):
        slots.setdefault(alias, slots[key])
    slots.setdefault("response_title", "AI 应答的四层结构 · " + brand + "当前位置")
    slots.setdefault("schedule_total", f"合计：{budget['content_count']}篇独立内容 / {budget['publication_count']}次刊发")
    slots.setdefault("maintenance_scope", "后续维护范围与费用按已列任务及报价确认")
    if project.get("start_date") and project.get("end_date"):
        weeks = ((date.fromisoformat(project["end_date"]) - date.fromisoformat(project["start_date"])).days + 7) // 7
        tables["overview_cards"] = [["建设周期", str(weeks) + "周", slots["execution_period"]], ["内容产出", str(budget["content_count"]) + "篇独立内容", "同稿多站只计一篇内容"], ["媒体排布", str(budget["publication_count"]) + "次刊发", slots["media_mix"]]]
    tables["priority_cards"] = report.get("diagnosis", {}).get("priority_cards", [])
    amount = budget["client"]["total"]
    if card and (amount is None or budget["currency"] != "CNY"):
        raise ValueError("原人民币报价卡须有完整对客金额，请用同源已知报价核算，不填写虚构金额")
    quote_amount = ""
    if amount is not None:
        numeric = Decimal(str(amount))
        quote_amount = format(numeric, ",.0f" if numeric == numeric.to_integral_value() else ",.2f")
    tables["quote_cards"] = [[slots["quote_name"], quote_amount, f"{budget['content_count']}篇内容 / {budget['publication_count']}次刊发",
                              "逐项报价与实际刊发量核算", slots["media_mix"], slots["quote_focus"], slots["quote_suitability"]]] if card else []
    tables["article_totals"] = [["合计", f"{budget['content_count']}篇内容", f"{budget['publication_count']}次刊发；客户自有动作不计入", "", "", slots["media_mix"], "", "", ""]]
    for name, value in slots.items():
        slots[name] = customer_text(value)
    for name, rows in tables.items():
        for row in rows:
            for value in row:
                customer_text(value)
        if name == "scene_matrix" and any(text(cell) not in {"已出现", "未出现", "部分出现", "已提及", "未提及", "部分提及", "待核实", "不适用"} for row in rows for cell in row[1:]):
            raise ValueError("scene_matrix原状态格只填短状态；竞品名单和分析请放明细/说明列")
        if name == "scene_details" and any(text(cell) not in {"已出现", "未出现", "部分出现", "已提及", "未提及", "部分提及", "待核实", "不适用"} for row in rows for cell in row[2:4]):
            raise ValueError("scene_details原状态格只填短状态，具体事实写入本行说明")
        if name == "source_layers":
            allowed = [{"有", "无", "部分", "待核实", "不适用"}, {"高", "中", "低", "待核实", "—", "不适用"}, {"是", "否", "部分", "待核实", "不适用"}]
            if any(text(value) not in allowed[i] for row in rows for i, value in enumerate(row[1:])):
                raise ValueError("source_layers原三种状态格只填覆盖/质量/引用短值，具体资产与原因放说明文字")
    ordered = sorted(contents, key=lambda c: (c["scheduled_date"], c["content_id"]))
    return {"slots": slots, "paragraphs": paragraphs, "tables": tables, "stages": [text(c["stage"]) for c in ordered]}


def fill_template(profile, kind, context):
    name = f"{profile}-{kind}.html"
    path = ROOT / "templates" / name
    manifest = load_json(ROOT / "templates/pdf-template-manifest.json")
    if manifest["templates"].get(name, {}).get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError("固定PDF模板已被改动，请恢复原安装包；WorkBuddy只填写report/plan内容")
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    if soup.find("script") or soup.find("link", href=True):
        raise ValueError("固定模板不得执行脚本或加载外部样式")
    for section in soup.select("[data-optional-section]"):
        key = section["data-optional-section"]
        if not context.get("paragraphs", {}).get(key) and not context.get("slots", {}).get(key):
            section.decompose()
    prototypes = {node["data-row"]: node.decode_contents() for node in soup.select("template[data-row]")}
    stage_prototypes = {node["data-stage-row"]: node.decode_contents() for node in soup.select("template[data-stage-row]")}
    group_prototypes = {node["data-group-row"]: node.decode_contents() for node in soup.select("template[data-group-row]")}
    paragraph_template = soup.select_one("template[data-paragraph]")
    for node in soup.select("[data-slot]"):
        if node.attrs is None:
            continue
        if node.find_parent("template"):
            continue
        optional = node.has_attr("data-optional") or node.find_parent(attrs={"data-optional-row": True})
        if node["data-slot"] not in context.get("slots", {}) and not optional:
            raise ValueError("请填写固定模板文字位 fields." + node["data-slot"] + "，不删除或重排该位置")
        value = text(context.get("slots", {}).get(node["data-slot"], ""))
        if not optional and value in EMPTY:
            raise ValueError("固定模板必填文字位不能为空：fields." + node["data-slot"])
        node.clear()
        node.append(value)
        if not value and optional:
            (node.find_parent(attrs={"data-optional-row": True}) or node).decompose()
    for container in soup.select("[data-paragraphs]"):
        items = context.get("paragraphs", {}).get(container["data-paragraphs"], [])
        if container.has_attr("data-required") and not items:
            raise ValueError("请填写原独立说明 blocks." + container["data-paragraphs"] + "，不能留下只有标题的空段")
        container.clear()
        for item in items:
            if paragraph_template is None:
                raise ValueError("固定模板缺少段落原型")
            fragment = BeautifulSoup(paragraph_template.decode_contents(), "html.parser")
            for node in fragment.select("[data-field]"):
                value = text(item.get(node["data-field"]))
                if not value:
                    node.decompose()
                else:
                    node.clear(); node.append(value)
            for node in list(fragment.contents):
                container.append(node.extract())
    for container in soup.select("[data-table]"):
        if container.find_parent("template"):
            continue
        name = container["data-table"]
        if name not in prototypes:
            raise ValueError("固定模板缺少行原型：" + name)
        rows = context.get("tables", {}).get(name, [])
        if not rows and not container.has_attr("data-optional"):
            raise ValueError("请填写固定模板原数据位 " + name + "，不能用空表或删除该组件替代")
        container.clear()
        last_stage = None
        last_group = None
        rendered = []
        for index, row in enumerate(rows):
            if container.has_attr("data-group-column"):
                group = text(row[int(container["data-group-column"])])
                if group != last_group:
                    fragment = BeautifulSoup(group_prototypes[name].replace("{{group_label}}", escape(group)), "html.parser")
                    for node in list(fragment.contents): container.append(node.extract())
                    last_group = group
            if name == "article_schedule" and name in stage_prototypes and context.get("stages"):
                stage = context["stages"][index]
                if stage != last_stage:
                    fragment = BeautifulSoup(stage_prototypes[name].replace("{{stage_label}}", escape(stage)), "html.parser")
                    for node in list(fragment.contents): container.append(node.extract())
                    last_stage = stage
            markup = prototypes[name]
            for column, value in enumerate(row):
                markup = markup.replace("{{cell" + str(column) + "}}", escape(text(value)))
            fragment = BeautifulSoup(markup, "html.parser")
            rendered.append(fragment.find("tr"))
            for node in list(fragment.contents): container.append(node.extract())
        if name == "article_schedule":
            merge_columns = [int(value) for value in container.get("data-merge-columns", "").split(",") if value.strip()]
            for column in merge_columns:
                start = 0
                while start < len(rows):
                    end = start + 1
                    while end < len(rows) and rows[end][0] == rows[start][0] and rows[end][column] == rows[start][column] and (not context.get("stages") or context["stages"][end] == context["stages"][start]):
                        end += 1
                    if end - start > 1 and text(rows[start][column]):
                        cells = [row.find_all("td", recursive=False) for row in rendered[start:end]]
                        # Defer removal until every column's spans have been collected.
                        if all(len(cs) == len(rows[0]) for cs in cells):
                            cells[0][column]["rowspan"] = str(end - start)
                            for cs in cells[1:]: cs[column]["data-merge-remove"] = "1"
                    start = end
            for node in container.select("[data-merge-remove]"): node.decompose()
    palette = {**dict.fromkeys(("已出现", "已提及", "有", "高", "是", "可以", "可完整召回", "表述基本准确"), "on"), **dict.fromkeys(("未出现", "未提及", "无", "否", "暂未进入", "未进入候选"), "off"), **dict.fromkeys(("部分出现", "部分", "中"), "partial")}
    for node in soup.select("[data-value]"):
        value = re.sub(r"^[✅❌✔✓✗✕\s]+", "", node["data-value"])
        node["class"] = [*node.get("class", []), palette.get(value, "unknown")]
    for node in soup.find_all("template"): node.decompose()
    result = str(soup)
    if re.search(r"\{\{[A-Za-z0-9_]+\}\}", result):
        raise ValueError("固定模板仍有未绑定文字或表格单元格，请按原字段补全")
    return result


def build_html(kind, analysis, plan, report):
    if analysis.get("schema_version") != 1 or not isinstance(analysis.get("project"), dict):
        raise ValueError("请使用同一项目生成的 schema_version=1 analysis.json")
    if kind not in FILES:
        raise ValueError("报告类型无效")
    return fill_template(report.get("template_profile"), kind, template_context(kind, analysis, plan, report))


def find_browser():
    candidates = [Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
                  Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe"]
    candidates += [Path(found) for name in ("chrome", "msedge", "chromium", "chromium-browser") if (found := shutil.which(name))]
    return next((path for path in candidates if path.is_file()), None)


def print_html(html):
    browser = find_browser()
    if browser is None:
        raise FileNotFoundError("固定模板PDF需要本机Chrome或Edge；不能回退到通用排版器")
    if sys.platform == "win32" and not all((Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name).is_file() for name in ("msyh.ttc", "msyhbd.ttc")):
        raise FileNotFoundError("原模板需要微软雅黑常规与粗体，缺字体时先恢复字体，不替换版式或缩字")
    with tempfile.TemporaryDirectory(prefix="geo-fixed-pdf-") as folder:
        folder = Path(folder)
        source, target = folder / "report.html", folder / "report.pdf"
        source.write_text(html, encoding="utf-8")
        command = [str(browser), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--disable-background-networking", "--no-pdf-header-footer", "--user-data-dir=" + str(folder / "browser"), "--print-to-pdf=" + str(target), source.as_uri()]
        result = subprocess.run(command, capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode or not target.is_file():
            raise RuntimeError("浏览器未完成固定模板打印：" + result.stderr.decode("utf-8", errors="replace")[-400:])
        data = target.read_bytes()
        reader = PdfReader(BytesIO(data))
        if not reader.pages:
            raise ValueError("固定模板PDF没有可用页面")
        fonts = {str(font.get_object().get("/BaseFont", "")) for page in reader.pages if "/Font" in page["/Resources"].get_object() for font in page["/Resources"].get_object()["/Font"].get_object().values()}
        if not any("MicrosoftYaHei-Bold" in font for font in fonts) or not any("MicrosoftYaHei" in font and "Bold" not in font for font in fonts):
            raise ValueError("浏览器未使用原模板微软雅黑常规/粗体，拒绝以替代字体交付")
        return data


def build_pdf(kind, analysis, plan, report):
    return print_html(build_html(kind, analysis, plan, report))


def export_pdf(kind, analysis, plan, report, output):
    target = Path(output)
    if target.exists(): raise FileExistsError("输出已存在，拒绝覆盖：" + str(target))
    data = build_pdf(kind, analysis, plan, report)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream: stream.write(data)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("analysis", "plan", "report", "output-dir"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--kind", choices=["both", "diagnosis", "execution"], default="both")
    args = parser.parse_args()
    analysis, plan, report = load_json(args.analysis), load_json(args.plan), load_json(args.report)
    kinds = list(FILES) if args.kind == "both" else [args.kind]
    out = Path(args.output_dir)
    if any((out / FILES[kind]).exists() for kind in kinds):
        raise FileExistsError("输出已存在，拒绝覆盖，请使用新的输出目录")
    htmls = {kind: build_html(kind, analysis, plan, report) for kind in kinds}
    rendered = {kind: print_html(html) for kind, html in htmls.items()}
    out.mkdir(parents=True, exist_ok=True)
    for kind, data in rendered.items():
        with (out / FILES[kind]).open("xb") as stream: stream.write(data)
        print(out / FILES[kind])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    main()
