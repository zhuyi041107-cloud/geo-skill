"""Portable GEO workbook preparation, evidence statistics and budget exports."""
import argparse
import json
import sys
from collections import defaultdict
from copy import copy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
QUESTION_HEADERS = ["question_id", "问题类型", "意图", "问题主题", "目标问题", "优先级", "备注"]
SAMPLE_HEADERS = ["sample_id", "question_id", "平台", "模型或模式", "联网状态", "轮次", "重复序号", "采集状态", "采集时间", "新对话", "回答全文", "引用展示", "品牌提及", "品牌推荐", "排名", "回答证据路径", "采集人", "备注"]
CITATION_HEADERS = ["citation_id", "sample_id", "URL", "标题", "网站或媒体", "核验状态", "支持品牌", "支持内容", "证据路径", "备注"]
GROUP_HEADERS = ["平台", "模型或模式", "联网状态", "轮次", "问题类型", "意图", "计划样本", "完成", "失败", "待核验", "未采集", "有效样本", "提及是", "提及否", "提及待判", "提及率", "推荐率", "可观察引用样本", "引用已判样本", "支持品牌引用样本", "引用率", "未展示引用样本", "采样条件不符"]
CONTENT_HEADERS = ["content_id", "标题", "question_ids", "平台", "阶段", "计划日期", "事实依据", "状态"]
MEDIA_HEADERS = ["placement_id", "content_id", "media_id", "媒体名称", "媒体类型", "原报价文件", "原报价sheet", "原报价行", "价格档位", "内部单价", "刊发次数", "内部金额", "客户单价", "客户金额", "状态", "计划日期"]
FEE_HEADERS = ["fee_id", "费用类别", "说明", "内部金额", "客户金额", "状态", "计划日期"]
STATUSES = {"未采集", "已完成", "失败", "待核验"}
TYPES = {"自然需求", "品牌认知"}
INTENTS = {"认知", "推荐", "决策", "对比", "其他"}
YES_NO = {"是", "否", "待判"}
ACTIVE = {"已选", "待执行", "已发布"}
PLACEMENT_STATUSES = ACTIVE | {"候选", "取消", "排除"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"不支持的JSON数据类型: {type(value).__name__}")


def write_json(value, path=None):
    text = json.dumps(value, ensure_ascii=False, indent=2, default=json_default)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    else:
        print(text)


def text(value):
    return str(value).strip() if value is not None else ""


def unique(records, key, label):
    seen = set()
    for record in records:
        value = text(record.get(key))
        if not value or value in seen:
            raise ValueError(f"{label}: 缺失或重复 {key}: {value!r}")
        seen.add(value)
    return seen


def positive_int(value, label):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} 必须为正整数") from None
    if not parsed.is_finite() or parsed < 1 or parsed != parsed.to_integral_value():
        raise ValueError(f"{label} 必须为正整数")
    return int(parsed)


def money(value, label):
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{label}: 价格不是数值") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label}: 金额须为有限非负数")
    return result


def amount(value):
    return format(value.quantize(Decimal("0.01")), "f") if value is not None else None


def load_rows(wb, name, headers):
    ws = wb[name]
    actual = [c.value for c in next(ws.iter_rows(max_row=1))][:len(headers)]
    if actual != headers:
        raise ValueError(f"{name}: 表头与模板不一致")
    result = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        values = row[:len(headers)]
        if any(v not in (None, "") for v in values):
            result.append(dict(zip(headers, values)))
    return result


def put_rows(ws, rows):
    for r, row in enumerate(rows, 2):
        for c, value in enumerate(row, 1):
            if isinstance(value, str) and len(value) > 32767:
                raise ValueError(f"{ws.title}!{openpyxl.utils.get_column_letter(c)}{r}: 文本超过Excel单元格32767字符，请使用外部原始证据文件，禁止静默截断")
            cell = ws.cell(r, c, value)
            if r > 201:
                cell._style = copy(ws.cell(201, c)._style)
            if isinstance(value, str):
                cell.data_type = "s"
    if len(rows) >= 200:
        for rule in ws.data_validations.dataValidation:
            for bounded in list(rule.sqref.ranges):
                if bounded.max_row == 201:
                    rule.sqref.remove(bounded)
                    rule.add(f"{openpyxl.utils.get_column_letter(bounded.min_col)}{bounded.min_row}:{openpyxl.utils.get_column_letter(bounded.max_col)}{len(rows) + 1}")


def save_new(wb, path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        wb.save(stream)


def validate_project(project):
    for key in ("project_id", "client_name"):
        if not text(project.get(key)):
            raise ValueError(f"项目缺少 {key}")
    if not isinstance(project.get("brand_names"), list) or not project["brand_names"]:
        raise ValueError("brand_names 必须为非空品牌名称列表")
    questions = project.get("questions", [])
    unique(questions, "question_id", "问题清单")
    for q in questions:
        if q.get("type") not in TYPES or q.get("intent") not in INTENTS or not text(q.get("text")):
            raise ValueError(f"问题 {q.get('question_id')}: 类型/意图/原始问句缺失或无效")
    contexts = project.get("contexts", [])
    if not questions or not contexts:
        raise ValueError("至少需要一个问题和一个采样context")
    seen = set()
    for ctx in contexts:
        key = tuple(text(ctx.get(k)) for k in ("platform", "mode", "online", "round"))
        if key in seen or not key[0] or not key[1] or ctx.get("online") not in {"是", "否", "未知"}:
            raise ValueError("context重复或缺少平台/模式/联网状态")
        positive_int(ctx.get("round"), "round")
        seen.add(key)
    positive_int(project.get("repeats", 1), "repeats")
    for key in ("start_date", "end_date"):
        if project.get(key):
            date.fromisoformat(project[key])
    if project.get("start_date") and project.get("end_date") and project["start_date"] > project["end_date"]:
        raise ValueError("项目结束日早于开始日")
    money(project.get("budget_limit"), "budget_limit")


def inspect_client(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb["客户素材清单"]
        fields = []
        for row in ws.iter_rows(min_row=3, values_only=False):
            a, b, c, d, e, f = [cell.value for cell in row[:6]]
            if e not in {"必填", "选填"} or f == "客户填写":
                continue
            fields.append({"row": row[0].row, "field": a if row[0].row <= 7 else b,
                           "required": e == "必填", "filled": f not in (None, ""),
                           "value": f, "requirement": c})
        return {"fields": fields, "total": len(fields),
                "required_missing": [f["field"] for f in fields if f["required"] and not f["filled"]],
                "filled": sum(f["filled"] for f in fields)}
    finally:
        wb.close()


def prepare(project, out):
    validate_project(project)
    if Path(out).exists():
        raise ValueError(f"输出已存在，拒绝覆盖: {out}")
    wb = openpyxl.load_workbook(ROOT / "templates/AI回答采集表.xlsx")
    metadata = {k: v for k, v in project.items() if k != "questions"}
    put_rows(wb["项目配置"], [[k, json.dumps(v, ensure_ascii=False), "由WorkBuddy配置"] for k, v in metadata.items()])
    put_rows(wb["问题清单"], [[q["question_id"], q["type"], q["intent"], q.get("theme"), q["text"], q.get("priority"), q.get("notes")] for q in project["questions"]])
    samples = []
    for q in project["questions"]:
        for i, ctx in enumerate(project["contexts"], 1):
            for repeat in range(1, project.get("repeats", 1) + 1):
                samples.append([f"{q['question_id']}-C{i:03d}-R{repeat:02d}", q["question_id"], ctx["platform"], ctx["mode"], ctx["online"], int(ctx["round"]), repeat, "未采集", None, None, None, "待核验", "待判", "待判", None, None, None, None])
    put_rows(wb["回答记录"], samples)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    save_new(wb, out)
    wb.close()
    return {"output": str(out), "questions": len(project["questions"]), "samples": len(samples)}


def fraction(yes, no):
    return yes / (yes + no) if yes + no else None


def analyze(path, plan=None):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        config = load_rows(wb, "项目配置", ["字段", "值(JSON)", "说明"])
        project = {r["字段"]: json.loads(r["值(JSON)"]) for r in config}
        questions = load_rows(wb, "问题清单", QUESTION_HEADERS)
        samples = load_rows(wb, "回答记录", SAMPLE_HEADERS)
        citations = load_rows(wb, "引用明细", CITATION_HEADERS)
    finally:
        wb.close()
    project["questions"] = [{"question_id": q["question_id"], "type": q["问题类型"], "intent": q["意图"], "theme": q["问题主题"], "text": q["目标问题"], "priority": q["优先级"]} for q in questions]
    validate_project(project)
    question_ids = unique(questions, "question_id", "问题")
    sample_ids = unique(samples, "sample_id", "回答")
    unique(citations, "citation_id", "引用")
    question_by_id = {q["question_id"]: q for q in questions}
    refs = defaultdict(list)
    verified = 0
    for ref in citations:
        if ref["sample_id"] not in sample_ids:
            raise ValueError(f"孤儿引用: {ref['citation_id']}")
        url = urlparse(text(ref["URL"]))
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError(f"引用URL必须为http(s): {ref['citation_id']}")
        if ref["核验状态"] not in {"已核验", "无效", "待核验"} or ref["支持品牌"] not in YES_NO:
            raise ValueError(f"引用核验状态/支持品牌缺失: {ref['citation_id']}")
        refs[ref["sample_id"]].append(ref)
    groups = {}
    evidence = []
    issues = []
    identities = set()
    contexts = {tuple(text(c[k]) for k in ("platform", "mode", "online", "round")) for c in project["contexts"]}
    for sample in samples:
        sid = sample["sample_id"]
        if sample["question_id"] not in question_ids:
            raise ValueError(f"回答引用未知问题: {sid}")
        context = tuple(text(sample[k]) for k in ("平台", "模型或模式", "联网状态", "轮次"))
        if context not in contexts:
            raise ValueError(f"样本context不在项目配置中: {sid}")
        repeat = positive_int(sample["重复序号"], f"{sid} 重复序号")
        identity = (sample["question_id"], context, repeat)
        if identity in identities:
            raise ValueError(f"重复采样任务: {sid}")
        identities.add(identity)
        if sample["采集状态"] not in STATUSES:
            raise ValueError(f"样本采集状态无效: {sid}")
        q = question_by_id[sample["question_id"]]
        key = context + (q["问题类型"], q["意图"])
        if key not in groups:
            groups[key] = dict(zip(("platform", "mode", "online", "round", "question_type", "intent"), key))
            groups[key].update({k: 0 for k in ["planned", "completed", "failed", "pending_review", "uncollected", "valid", "invalid_conditions", "mention_yes", "mention_no", "mention_pending", "recommendation_yes", "recommendation_no", "recommendation_pending", "observable_citation_samples", "citation_known_samples", "citation_supported_samples", "unobserved_sources"]})
        group = groups[key]
        group["planned"] += 1
        group[{"已完成": "completed", "失败": "failed", "待核验": "pending_review", "未采集": "uncollected"}[sample["采集状态"]]] += 1
        if sample["采集状态"] != "已完成":
            continue
        if not text(sample["回答全文"]):
            raise ValueError(f"已完成样本缺少原始回答: {sid}")
        if sample["品牌提及"] not in YES_NO or sample["品牌推荐"] not in YES_NO:
            raise ValueError(f"样本判读字段无效: {sid}")
        if sample["品牌提及"] == "否" and sample["品牌推荐"] == "是":
            raise ValueError(f"矛盾判读：推荐品牌却未提及品牌: {sid}")
        if sample["引用展示"] not in {"已展示", "未展示", "待核验", "不适用"}:
            raise ValueError(f"引用展示状态无效: {sid}")
        if sample["引用展示"] == "未展示" and refs[sid]:
            raise ValueError(f"未展示引用却有引用明细: {sid}")
        condition_issues = []
        if sample["新对话"] != "是":
            condition_issues.append("未确认使用独立新对话")
        collected_at = sample["采集时间"]
        try:
            if not isinstance(collected_at, datetime):
                datetime.fromisoformat(text(collected_at))
        except ValueError:
            condition_issues.append("采集时间缺失或格式无效")
        if collected_at and ((isinstance(collected_at, date) and not isinstance(collected_at, datetime)) or len(text(collected_at)) == 10):
            issues.append({"sample_id": sid, "issue": "采集时间仅记录日期，时分和时区精度未确认"})
        elif isinstance(collected_at, datetime) and collected_at.tzinfo is None:
            issues.append({"sample_id": sid, "issue": "Excel采集时间未记录时区，需核验"})
        evidence.append({"evidence_id": f"EV-{sid}", "sample_id": sid, "question_id": sample["question_id"],
                         "question_type": q["问题类型"], "intent": q["意图"], "platform": sample["平台"],
                         "mode": sample["模型或模式"], "online": sample["联网状态"], "round": int(sample["轮次"]),
                         "answer": sample["回答全文"], "mention": sample["品牌提及"], "recommendation": sample["品牌推荐"],
                         "source": sample["回答证据路径"], "comparable": not condition_issues, "condition_issues": condition_issues,
                         "verified_citation_ids": [r["citation_id"] for r in refs[sid] if r["核验状态"] == "已核验" and r["支持品牌"] == "是"]})
        if condition_issues:
            group["invalid_conditions"] += 1
            issues.append({"sample_id": sid, "issue": "；".join(condition_issues) + "；已排除标准可比指标"})
            continue
        group["valid"] += 1
        verified += sum(r["核验状态"] == "已核验" and r["支持品牌"] == "是" for r in refs[sid])
        if sample["品牌提及"] == "待判" or sample["品牌推荐"] == "待判":
            issues.append({"sample_id": sid, "issue": "品牌提及或推荐待判"})
        group[{"是": "mention_yes", "否": "mention_no", "待判": "mention_pending"}[sample["品牌提及"]]] += 1
        if q["意图"] == "推荐":
            group[{"是": "recommendation_yes", "否": "recommendation_no", "待判": "recommendation_pending"}[sample["品牌推荐"]]] += 1
        if sample["联网状态"] == "是" and sample["引用展示"] == "未展示":
            group["unobserved_sources"] += 1
            group["citation_known_samples"] += 1
            issues.append({"sample_id": sid, "issue": "未展示可观察引用；不等于没有使用信源"})
        if sample["联网状态"] == "是" and sample["引用展示"] == "已展示":
            group["observable_citation_samples"] += 1
            sample_refs = refs[sid]
            supported = any(r["核验状态"] == "已核验" and r["支持品牌"] == "是" for r in sample_refs)
            known = supported or (bool(sample_refs) and all(r["核验状态"] != "待核验" and r["支持品牌"] != "待判" for r in sample_refs))
            group["citation_known_samples"] += known
            group["citation_supported_samples"] += supported
    expected = {(q["question_id"], tuple(text(c[k]) for k in ("platform", "mode", "online", "round")), r)
                for q in project["questions"] for c in project["contexts"]
                for r in range(1, project.get("repeats", 1) + 1)}
    if identities != expected:
        raise ValueError("采样任务缺失或重复序号超出项目配置；请用prepare重新生成并保留全部任务")
    result_groups = list(groups.values())
    for group in result_groups:
        group["round"] = int(group["round"])
        group["mention_rate"] = fraction(group["mention_yes"], group["mention_no"])
        group["recommendation_rate"] = fraction(group["recommendation_yes"], group["recommendation_no"]) if group["intent"] == "推荐" else None
        group["citation_rate"] = group["citation_supported_samples"] / group["citation_known_samples"] if group["citation_known_samples"] else None
    counts = {k: sum(g[k] for g in result_groups) for k in ["planned", "completed", "failed", "pending_review", "uncollected", "valid", "invalid_conditions"]}
    counts.update(questions=len(questions), citations=len(citations), verified_supporting_citations=verified)
    return {"schema_version": 1, "project": project, "groups": result_groups, "counts": counts, "samples": samples,
            "citations": citations, "evidence": evidence, "issues": issues,
            "budget": calculate_budget(project, plan) if plan is not None else None}


def quarter(value):
    if not value:
        return "未排期"
    parsed = date.fromisoformat(value)
    return f"{parsed.year}Q{(parsed.month - 1) // 3 + 1}"


def excel_date(value):
    return date.fromisoformat(value) if value else None


def calculate_budget(project, plan):
    contents = plan.get("contents", [])
    placements = plan.get("placements", [])
    fees = plan.get("fees", [])
    content_ids = unique(contents, "content_id", "内容")
    unique(placements, "placement_id", "投放")
    unique(fees, "fee_id", "费用")
    for p in placements:
        if p.get("status") not in PLACEMENT_STATUSES:
            raise ValueError(f"投放状态无效: {p.get('placement_id')}")
        if p.get("content_id") not in content_ids:
            raise ValueError(f"投放关联不存在的content_id: {p.get('placement_id')}")
        if p.get("quantity") not in (None, ""):
            positive_int(p["quantity"], "quantity")
    limit = money(project.get("budget_limit"), "budget_limit")
    for f in fees:
        if f.get("status") not in PLACEMENT_STATUSES:
            raise ValueError(f"费用状态无效: {f.get('fee_id')}")
    active = [p for p in placements if p.get("status") in ACTIVE]
    active_fees = [f for f in fees if f.get("status") in ACTIVE]
    for record in active + active_fees:
        scheduled = record.get("scheduled_date")
        if scheduled:
            parsed = date.fromisoformat(scheduled)
            if (project.get("start_date") and parsed < date.fromisoformat(project["start_date"])) or (project.get("end_date") and parsed > date.fromisoformat(project["end_date"])):
                raise ValueError("已选执行项计划日期超出项目起止范围，不可计入本期预算")
    content_status = {c["content_id"]: c.get("status") for c in contents}
    if any(content_status[p["content_id"]] in {"取消", "排除"} for p in active):
        raise ValueError("有效投放关联已取消或排除的内容")
    publication_count = sum(positive_int(p["quantity"], "quantity") for p in active) if all(p.get("quantity") not in (None, "") for p in active) else None
    result = {"currency": project.get("currency", "CNY"), "limit": amount(limit),
              "planned_content_count": len([c for c in contents if c.get("status") not in {"取消", "排除"}]),
              "content_count": len({p["content_id"] for p in active}), "candidate_placement_count": sum(p.get("status") == "候选" for p in placements),
              "placement_count": len(active), "publication_count": publication_count}
    for audience in ("internal", "client"):
        price_key, fee_key = ("unit_price", "amount") if audience == "internal" else ("client_unit_price", "client_amount")
        entries = []
        missing = []
        for p in active:
            unit = money(p.get(price_key), f"{p['placement_id']} {price_key}")
            qty = positive_int(p["quantity"], "quantity") if p.get("quantity") not in (None, "") else None
            value = unit * qty if unit is not None and qty is not None else None
            if value is None:
                missing.append(p["placement_id"])
            entries.append(("media", quarter(p.get("scheduled_date")), value))
        for fee in active_fees:
            value = money(fee.get(fee_key), f"{fee['fee_id']} {fee_key}")
            if value is None:
                missing.append(fee["fee_id"])
            entries.append(("fees", quarter(fee.get("scheduled_date")), value))
        def totals(selected):
            obj = {}
            for kind in ("media", "fees"):
                values = [v for k, _, v in selected if k == kind]
                obj[kind] = amount(sum(values, Decimal(0))) if values and all(v is not None for v in values) else ("0.00" if selected and not values else None)
            values = [v for _, _, v in selected]
            obj["total"] = amount(sum(values, Decimal(0))) if values and all(v is not None for v in values) else None
            return obj
        summary = totals(entries)
        summary.update(missing_prices=missing, missing_count=len(missing), known_subtotal=amount(sum((v for _, _, v in entries if v is not None), Decimal(0))), exceeds_limit=(Decimal(summary["total"]) > limit if summary["total"] is not None and limit is not None else None), quarterly={q: totals([e for e in entries if e[1] == q]) for q in sorted({e[1] for e in entries})})
        result[audience] = summary
    return result


def export_excel(project, analysis, plan, out_dir):
    validate_project(project)
    if analysis.get("project", {}).get("project_id") != project["project_id"]:
        raise ValueError("分析文件与项目ID不一致")
    budget = calculate_budget(project, plan)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = ["内部诊断与执行明细.xlsx", "客户诊断与执行明细.xlsx"]
    if any((out_dir / name).exists() for name in names):
        raise ValueError("导出文件已存在，拒绝覆盖；请使用新输出目录")
    results = {}
    for audience, name in [("internal", "内部诊断与执行明细.xlsx"), ("client", "客户诊断与执行明细.xlsx")]:
        wb = openpyxl.load_workbook(ROOT / "templates/诊断与执行明细模板.xlsx")
        selected = {p["content_id"] for p in plan.get("placements", []) if p.get("status") in ACTIVE}
        visible_contents = [c for c in plan.get("contents", []) if audience == "internal" or c["content_id"] in selected]
        visible_placements = [p for p in plan.get("placements", []) if audience == "internal" or p.get("status") in ACTIVE]
        visible_fees = [f for f in plan.get("fees", []) if audience == "internal" or f.get("status") in ACTIVE]
        gkeys = ["platform", "mode", "online", "round", "question_type", "intent", "planned", "completed", "failed", "pending_review", "uncollected", "valid", "mention_yes", "mention_no", "mention_pending", "mention_rate", "recommendation_rate", "observable_citation_samples", "citation_known_samples", "citation_supported_samples", "citation_rate", "unobserved_sources", "invalid_conditions"]
        put_rows(wb["平台指标"], [[g.get(k) for k in gkeys] for g in analysis.get("groups", [])])
        put_rows(wb["内容排期"], [[c.get("content_id"), c.get("title"), ",".join(c.get("question_ids", [])), c.get("platform"), c.get("stage"), excel_date(c.get("scheduled_date")), c.get("evidence"), c.get("status")] for c in visible_contents])
        put_rows(wb["诊断证据"], [[e.get("evidence_id"), f"品牌提及：{e.get('mention')}；品牌推荐：{e.get('recommendation')}", "AI实测", e.get("question_id"), e.get("sample_id"), e.get("source"), "待核验" if e.get("mention") == "待判" or not e.get("comparable", True) else "已核验", "；".join(e.get("condition_issues", [])) or "仅代表记录平台、模式、联网状态与轮次下的样本", None, e.get("answer")] for e in analysis.get("evidence", [])])
        media_rows = []
        for p in visible_placements:
            price = money(p.get("unit_price"), "unit_price")
            client_price = money(p.get("client_unit_price"), "client_unit_price")
            media_rows.append([p.get(k) for k in ["placement_id", "content_id", "media_id", "media_name", "media_type", "source_file", "source_sheet", "source_row", "price_tier"]] + [float(price) if price is not None else None, p.get("quantity"), None, float(client_price) if client_price is not None else None, None, p.get("status"), excel_date(p.get("scheduled_date"))])
        put_rows(wb["媒体投放"], media_rows)
        for r in range(2, max(202, len(media_rows) + 2)):
            wb["媒体投放"].cell(r, 12, f'=IF(OR(A{r}="",J{r}="",K{r}=""),"",J{r}*K{r})')
            wb["媒体投放"].cell(r, 14, f'=IF(OR(A{r}="",M{r}="",K{r}=""),"",M{r}*K{r})')
        fee_rows = []
        for f in visible_fees:
            cost, quoted = money(f.get("amount"), "amount"), money(f.get("client_amount"), "client_amount")
            fee_rows.append([f.get("fee_id"), f.get("category"), f.get("description"), float(cost) if cost is not None else None, float(quoted) if quoted is not None else None, f.get("status"), excel_date(f.get("scheduled_date"))])
        put_rows(wb["其他费用"], fee_rows)
        b = budget[audience]
        numeric = lambda v: float(v) if v is not None else None
        summary = [["项目", project.get("client_name")], ["币种", budget["currency"]], ["预算上限", numeric(budget["limit"])], ["独立内容篇数", budget["content_count"]], ["投放记录数", budget["placement_count"]], ["刊发次数", budget["publication_count"]], ["媒体费用", numeric(b["media"])], ["其他费用", numeric(b["fees"])], ["总金额", numeric(b["total"])], ["待报价或缺数量ID", ", ".join(b["missing_prices"])], ["超预算", "待确定" if b["exceeds_limit"] is None else ("是" if b["exceeds_limit"] else "否")]]
        summary += [["已知费用小计", numeric(b["known_subtotal"])], ["缺价或缺数量项数", b["missing_count"]]]
        summary += [[q, numeric(v["total"])] for q, v in b["quarterly"].items()]
        put_rows(wb["预算汇总"], summary)
        for r in [4, 8, 9, 10] + list(range(13, len(summary) + 2)):
            wb["预算汇总"].cell(r, 2).number_format = '#,##0.00'
        if audience == "client":
            ws = wb["媒体投放"]
            ws.data_validations.dataValidation.clear()
            for col in [12, 10, 9, 8, 7, 6]:
                ws.delete_cols(col)
            # Deleting source/cost columns does not reliably rewrite openpyxl formulas.
            for r in range(2, max(202, len(media_rows) + 2)):
                ws.cell(r, 8, f'=IF(OR(A{r}="",G{r}="",F{r}=""),"",G{r}*F{r})')
            wb["其他费用"].delete_cols(4)
            wb["其他费用"].data_validations.dataValidation.clear()
            wb["说明"].delete_rows(2, wb["说明"].max_row - 1)
            put_rows(wb["说明"], [["项目", project.get("client_name")], ["统计口径", "自然需求与品牌认知分开；平台、模式、联网状态与轮次分别统计。"], ["未知值", "空白表示尚不能确定，不等于零。未展示可观察引用不等于没有使用信源。"], ["执行预算", "仅计已选、待执行、已发布项目；未排期费用不分配到已知季度。"]])
        target = out_dir / name
        save_new(wb, target)
        wb.close()
        results[audience] = str(target)
    results["budget"] = budget
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect-client", "analyze"):
        p = sub.add_parser(name)
        p.add_argument("--input", required=True)
        p.add_argument("--out")
        if name == "analyze":
            p.add_argument("--plan")
    p = sub.add_parser("prepare")
    p.add_argument("--project", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("export-excel")
    p.add_argument("--project", required=True)
    p.add_argument("--analysis", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect-client":
            write_json(inspect_client(args.input), args.out)
        elif args.command == "prepare":
            write_json(prepare(read_json(args.project), args.out))
        elif args.command == "analyze":
            write_json(analyze(args.input, read_json(args.plan) if args.plan else None), args.out)
        else:
            write_json(export_excel(read_json(args.project), read_json(args.analysis), read_json(args.plan), args.out_dir))
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"错误: {exc}\n")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
