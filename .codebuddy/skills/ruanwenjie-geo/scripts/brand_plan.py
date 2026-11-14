"""Validate brand-specific diagnosis/action links and user-instructed quotations."""
from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


VERSION = "3.0"
BILLING = {"unit", "package", "included", "unquoted", "client_provided", "not_included"}
CATEGORIES = {"media", "writing", "service", "package"}


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + "须为非空文字")
    return value.strip()


def amount(value, label="金额", optional=False):
    if optional and value in (None, ""):
        return None
    if isinstance(value, bool) or value in (None, ""):
        raise ValueError(label + "尚未明确")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError(label + "须为有限非负金额")
        return number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(label + "须为有限非负金额") from exc


def positive_int(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(label + "须为正整数")
    return value


def records(value, label, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(label + "须为" + ("列表" if allow_empty else "非空列表"))
    result = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(label + "每项须为对象")
        identity = text(item.get("id"), label + ".id")
        if identity in result:
            raise ValueError(label + "存在重复id：" + identity)
        result[identity] = item
    return result


def references(value, lookup, label):
    if not isinstance(value, list) or not value or any(not isinstance(v, str) for v in value):
        raise ValueError(label + "须为非空编号列表")
    if len(value) != len(set(value)):
        raise ValueError(label + "编号重复")
    missing = set(value) - lookup.keys()
    if missing:
        raise ValueError(label + "关联不存在的编号：" + "、".join(sorted(missing)))
    return value


def validate_links(plan, execution=True):
    if not isinstance(plan, dict):
        raise ValueError("品牌计划须为对象")
    evidence = records(plan.get("evidence", []), "evidence", allow_empty=True)
    for item in evidence.values():
        text(item.get("summary"), "证据摘要")
    findings = records(plan.get("findings"), "findings")
    for finding in findings.values():
        for key in ("observation", "analysis", "business_impact"):
            text(finding.get(key), "诊断." + key)
        if finding.get("priority") not in {"high", "medium", "low"}:
            raise ValueError("诊断priority须为high、medium或low")
        supporting = finding.get("evidence", [])
        if supporting and (not isinstance(supporting, list) or any(not isinstance(v, str) or not v.strip() for v in supporting)):
            raise ValueError("诊断evidence须为非空证据摘要文字列表")
        if finding.get("evidence_ids"):
            references(finding["evidence_ids"], evidence, "诊断evidence_ids")
        elif not supporting:
            raise ValueError("关键诊断须有可追溯证据或证据摘要")
    actions = records(plan.get("actions", []), "actions", allow_empty=not execution)
    covered = set()
    for action in actions.values():
        covered.update(references(action.get("finding_ids"), findings, "动作finding_ids"))
        for key in ("task", "content", "media_role", "stage", "owner", "deliverable", "review"):
            text(action.get(key), "动作." + key)
        keywords = action.get("keywords", [])
        if not isinstance(keywords, list) or any(not isinstance(v, str) or not v.strip() for v in keywords):
            raise ValueError("动作keywords须为文字列表")
        if action.get("status", "planned") not in {"planned", "deferred"}:
            raise ValueError("动作status须为planned或deferred")
        if action.get("status") == "deferred":
            text(action.get("defer_reason"), "暂缓动作原因")
    if execution and set(findings) - covered:
        raise ValueError("诊断发现未对应执行或有理由的暂缓动作：" + "、".join(sorted(set(findings) - covered)))
    return findings, actions


def calculate_pricing(plan, project=None):
    findings, actions = validate_links(plan)
    scopes = records(plan.get("service_scope"), "service_scope")
    task_names = set()
    scoped_actions = set()
    for scope in scopes.values():
        for key in ("task", "provider", "client"):
            text(scope.get(key), "分工." + key)
        scoped_actions.update(references(scope.get("action_ids"), actions, "分工action_ids"))
        task_name = re.sub(r"\s+", "", scope["task"])
        if task_name in task_names:
            raise ValueError("分工中同一工作事项不得拆成重复收费身份")
        task_names.add(task_name)
    unscoped = {identity for identity, action in actions.items()
                if action.get("status", "planned") == "planned"} - scoped_actions
    if unscoped:
        raise ValueError("执行动作尚未说明负责方与费用范围：" + "、".join(sorted(unscoped)))
    pricing = plan.get("pricing")
    if not isinstance(pricing, dict):
        raise ValueError("须按本次用户指令填写pricing；不能继承旧版默认价格")
    text(pricing.get("instructions"), "本次用户报价指令")
    currency = pricing.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("报价currency须为三位大写货币代码")
    tax_note = text(pricing.get("tax_note"), "税费口径")
    target = amount(pricing.get("budget_target"), "意向预算", optional=True)
    limit = amount(pricing.get("budget_limit"), "明确预算上限", optional=True)
    project_limit = amount((project or {}).get("budget_limit"), "project预算上限", optional=True)
    if project_limit is not None and project_limit != limit:
        raise ValueError("预算口径冲突，请按最新用户指令统一project与pricing的明确上限")
    if (project or {}).get("currency") and project["currency"] != currency:
        raise ValueError("project与pricing货币口径不一致")
    minimum = amount(pricing.get("minimum_total"), "用户约定最低总价", optional=True)
    minimum_media = amount(pricing.get("minimum_media_total"), "用户约定最低媒体费", optional=True)
    options = pricing.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("pricing.options须列本次要求的单档或多档方案")
    count = pricing.get("required_option_count")
    if count is not None and positive_int(count, "用户要求档数") != len(options):
        raise ValueError("报价档数与本次用户要求不一致")
    names, calculated = set(), []
    for option in options:
        if not isinstance(option, dict) or set(option) != {"name", "items"}:
            raise ValueError("每档报价须且仅含name和items，金额由明细核算")
        name = text(option["name"], "报价名称")
        if name in names:
            raise ValueError("报价方案名称重复")
        names.add(name)
        items = option["items"]
        if not isinstance(items, list) or not items:
            raise ValueError("每档报价须有明确费用与范围明细")
        seen, lines, known, media, missing = set(), [], Decimal("0.00"), Decimal("0.00"), []
        media_unknown = False
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("报价明细须为对象")
            billing, category = item.get("billing"), item.get("category")
            if billing not in BILLING or category not in CATEGORIES:
                raise ValueError("报价billing或category无效")
            common = {"name", "category", "billing", "covers", "note"}
            fields = {"quantity", "unit", "unit_price"} if billing == "unit" else {"amount"} if billing == "package" else set()
            if set(item) - common - fields:
                raise ValueError("费用明细包含与计价方式不符或自行填入的合计字段")
            label = text(item.get("name"), "费用名称")
            covered = references(item.get("covers"), scopes, "费用covers")
            if seen.intersection(covered):
                raise ValueError("同一服务重复计价或已含后又另收：" + "、".join(sorted(seen.intersection(covered))))
            seen.update(covered)
            if item.get("note") is not None:
                text(item["note"], "费用说明")
            quantity, unit, unit_price = None, None, None
            if billing == "unit":
                quantity = positive_int(item.get("quantity"), "计费数量")
                unit = text(item.get("unit"), "计价单位")
                unit_price = amount(item.get("unit_price"), "用户约定单价")
                subtotal = unit_price * quantity
            elif billing == "package":
                subtotal = amount(item.get("amount"), "用户约定整包价")
            elif billing == "unquoted":
                subtotal = None
                missing.append(label)
            else:
                subtotal = Decimal("0.00")
            if category == "package" or (category == "media" and subtotal is None):
                media_unknown = True
            if subtotal is not None:
                known += subtotal
                if category == "media":
                    media += subtotal
            lines.append({"name": label, "category": category, "billing": billing,
                          "covers": list(covered), "quantity": quantity, "unit": unit,
                          "unit_price": unit_price, "amount": subtotal, "note": item.get("note", "")})
        if set(scopes) - seen:
            raise ValueError("报价未说明服务的含/另计/客户提供范围：" + "、".join(sorted(set(scopes) - seen)))
        if limit is not None and known > limit:
            raise ValueError(name + "已明确费用超出用户预算上限")
        complete = not missing
        if complete and minimum is not None and known < minimum:
            raise ValueError(name + "低于本次用户明确要求的最低总价")
        if complete and minimum_media is not None:
            if media_unknown:
                raise ValueError(name + "整包未拆分媒体金额，无法核对本次最低媒体费")
            if media < minimum_media:
                raise ValueError(name + "低于本次用户明确要求的最低媒体费")
        calculated.append({"name": name, "items": lines, "known_subtotal": known,
                           "total": known if complete else None, "missing_prices": missing,
                           "media_total": None if media_unknown else media,
                           "remaining": limit - known if complete and limit is not None else None})
    return {"currency": currency, "tax_note": tax_note, "target": target,
            "limit": limit, "options": calculated, "service_scope": scopes,
            "findings": findings, "actions": actions}


def formatted(value, currency):
    if value is None:
        return "待确认"
    return ("¥" if currency == "CNY" else currency + " ") + f"{value:,.2f}"


def _selected_ids(page, lookup, label):
    if "ids" not in page:
        return list(lookup)
    return references(page["ids"], lookup, label)


def _action_text(action):
    if action.get("status") == "deferred":
        return "暂缓：" + action["task"] + "；" + action["defer_reason"]
    return action["task"]


def _finding_page(base, ids, findings, actions):
    result = dict(base)
    if base["layout"] in {"insights", "cards"}:
        items = []
        for identity in ids:
            finding = findings[identity]
            item = {"heading": finding["observation"], "body": finding["analysis"], "impact": finding["business_impact"]}
            related = [_action_text(action) for action in actions.values() if identity in action["finding_ids"]]
            if related:
                item["action"] = "；".join(related)
            items.append(item)
        result["items"] = items
    elif base["layout"] == "table":
        result.update(headers=["当前情况", "分析", "业务影响"],
                      rows=[[findings[i][key] for key in ("observation", "analysis", "business_impact")] for i in ids])
    else:
        raise ValueError("findings源页使用insights、cards或table")
    return result


def _action_page(base, ids, findings, actions):
    if base["layout"] != "table":
        raise ValueError("action-map源页使用table显示诊断与动作对应")
    rows = []
    for identity in ids:
        action = actions[identity]
        rows.append(["；".join(findings[i]["observation"] for i in action["finding_ids"]),
                     _action_text(action) + "\n" + action["content"] + ("\n关键词：" + "、".join(action.get("keywords", [])) if action.get("keywords") else ""),
                     action["media_role"] + "\n" + action["stage"],
                     action["owner"] + "\n交付：" + action["deliverable"], action["review"]])
    return {**base, "headers": ["对应诊断", "执行动作与内容", "媒体与阶段", "分工与交付", "复核重点"], "rows": rows}


def _quote_page(base, priced):
    if base["layout"] not in {"quotes", "table"}:
        raise ValueError("quotes源页使用quotes或table")
    rows, currency = [], priced["currency"]
    labels = {"included": "已含", "unquoted": "待确认", "client_provided": "客户提供", "not_included": "不在本次范围"}
    options = priced["options"]

    def signature(line):
        return (tuple(sorted(line["covers"])), line["name"], line["category"], line["billing"], line["unit"], line["note"])

    indexed = [{signature(line): line for line in option["items"]} for option in options]
    comparable = 2 <= len(options) <= 3 and all(set(group) == set(indexed[0]) for group in indexed[1:])
    if comparable:
        for line in options[0]["items"]:
            scope = "、".join(priced["service_scope"][identity]["task"] for identity in line["covers"])
            label = line["name"]
            if len(line["covers"]) > 1:
                label += "\n范围：" + scope
            if line["note"]:
                label += "\n" + line["note"]
            values = []
            for group in indexed:
                chosen = group[signature(line)]
                if chosen["billing"] == "unit":
                    method = f"{chosen['quantity']}{chosen['unit']} × {formatted(chosen['unit_price'], currency)}"
                    values.append(method + " = " + formatted(chosen["amount"], currency))
                elif chosen["billing"] == "package":
                    values.append("整包报价：" + formatted(chosen["amount"], currency))
                else:
                    values.append(labels[chosen["billing"]])
            rows.append([label, *values])
        if any(option["missing_prices"] for option in options):
            rows.append(["已明确费用小计", *[formatted(option["known_subtotal"], currency) for option in options]])
        rows.append(["方案总价（" + priced["tax_note"] + "）", *[formatted(option["total"], currency) for option in options]])
        if priced["limit"] is not None:
            rows.append(["明确预算上限／余额", *[formatted(priced["limit"], currency) + "\n余额：" + formatted(option["remaining"], currency) for option in options]])
    for option in ([] if comparable else options):
        for line in option["items"]:
            billing = line["billing"]
            method = f"{line['quantity']}{line['unit']} × {formatted(line['unit_price'], currency)}" if billing == "unit" else "整包报价" if billing == "package" else labels[billing]
            scope = "、".join(priced["service_scope"][identity]["task"] for identity in line["covers"])
            label = line["name"] + "\n范围：" + scope + ("\n" + line["note"] if line["note"] else "")
            value = formatted(line["amount"], currency) if billing in {"unit", "package", "unquoted"} else labels[billing]
            rows.append([option["name"], label, method, value])
        if option["missing_prices"]:
            rows.append([option["name"], "已明确费用小计", "另有待报价项", formatted(option["known_subtotal"], currency)])
        rows.append([option["name"], "方案总价", priced["tax_note"], formatted(option["total"], currency)])
        if priced["limit"] is not None:
            rows.append([option["name"], "明确预算上限／余额", formatted(priced["limit"], currency), formatted(option["remaining"], currency)])
    note = base.get("note", "")
    if priced["target"] is not None:
        note = (note + "；" if note else "") + "意向预算：" + formatted(priced["target"], currency)
    headers = ["项目与范围", *[option["name"] for option in options]] if comparable else ["方案", "项目与范围", "计价口径", "金额"]
    return {**base, "headers": headers, "rows": rows,
            **({"note": note} if note else {})}


def _scope_page(base, priced):
    if base["layout"] != "table":
        raise ValueError("service-scope源页使用table")
    labels = {"unit": "按量另计", "package": "整包已计", "included": "已含", "unquoted": "价格待确认",
              "client_provided": "客户提供", "not_included": "不在本次范围"}
    rows = []
    for identity, scope in priced["service_scope"].items():
        terms, billing_terms = [], set()
        for option in priced["options"]:
            line = next(line for line in option["items"] if identity in line["covers"])
            billing_terms.add(labels[line["billing"]])
            terms.append(option["name"] + "：" + labels[line["billing"]])
        fee_scope = "各档：" + next(iter(billing_terms)) if len(terms) > 1 and len(billing_terms) == 1 else "；".join(terms)
        rows.append([scope["task"], scope["provider"], scope["client"], fee_scope])
    return {**base, "headers": ["工作事项", "软文街负责", "贵司配合", "费用范围"], "rows": rows}


def prepare_document(kind, report, project=None, plan=None, analysis=None):
    import render_brand_report as renderer

    errors = renderer.validate_report(report, rendered=False)
    if errors:
        raise ValueError("; ".join(errors))
    if kind not in report:
        raise ValueError("客户报告缺少 " + kind)
    findings, actions = validate_links(plan, execution=kind == "execution")
    priced = calculate_pricing(plan, project) if kind == "execution" else None
    pages, shown_findings, shown_actions, sources = [], set(), set(), set()
    for page in report[kind]["pages"]:
        source = page.get("source")
        if not source:
            if page.get("layout") == "quotes" or any(word in page.get("title", "") for word in ("报价", "费用", "预算")):
                raise ValueError("本次报价和预算页面须使用quotes源页，不能自由手填金额")
            pages.append(copy.deepcopy(page))
            continue
        sources.add(source)
        base = {key: copy.deepcopy(value) for key, value in page.items() if key not in {"source", "ids"}}
        if source == "findings":
            ids = _selected_ids(page, findings, "findings源页ids")
            shown_findings.update(ids)
            prepared = _finding_page(base, ids, findings, actions)
        elif source == "action-map":
            ids = _selected_ids(page, actions, "action-map源页ids")
            shown_actions.update(ids)
            prepared = _action_page(base, ids, findings, actions)
        elif source in {"quotes", "service-scope"}:
            if kind != "execution" or priced is None:
                raise ValueError("报价和费用分工源页只用于执行方案")
            if "ids" in page:
                raise ValueError("报价与分工源页须完整呈现本次约定范围")
            prepared = _quote_page(base, priced) if source == "quotes" else _scope_page(base, priced)
        else:
            raise ValueError("未知品牌报告source：" + str(source))
        pages.append(prepared)
    required_findings = set(findings) if kind == "diagnosis" else {identity for identity, finding in findings.items() if finding["priority"] == "high"}
    if "findings" not in sources or required_findings - shown_findings:
        raise ValueError("客户页面缺少关键诊断结论，不能仅在内部计划中校验")
    if kind == "execution" and (not {"action-map", "quotes", "service-scope"}.issubset(sources) or set(actions) - shown_actions):
        raise ValueError("执行客户页须完整呈现诊断对应动作、分工及已核报价")
    config = {"customer": copy.deepcopy(report["customer"]), "theme": copy.deepcopy(report["theme"]), "pages": pages}
    if "purpose" in report:
        config["purpose"] = report["purpose"]
    errors = renderer.validate(config, kind=kind, rendered=True)
    if errors:
        raise ValueError("; ".join(errors))
    return config
