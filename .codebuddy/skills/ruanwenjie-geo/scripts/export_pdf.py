"""Render customer-only reports; keep internal accounting outside the PDF renderer."""
from __future__ import annotations
import argparse
import copy
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
from geo_data import calculate_budget, validate_delivery_budget, positive_int
import render_geo_diagnosis as renderer

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = {"已选", "待执行", "已发布"}
FILES = {"diagnosis": "GEO诊断报告.pdf", "execution": "品牌传播与GEO执行方案.pdf"}


def load_json(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("输入 JSON 根节点须为对象")
    return obj


def verify_assets():
    manifest = load_json(ROOT / "assets/report-assets-manifest.json")
    for asset in manifest["files"]:
        path = (ROOT / asset["path"]).resolve()
        if ROOT.resolve() not in path.parents or not path.is_file():
            raise ValueError("报告资产缺失或路径越界：" + asset["path"])
        data = path.read_bytes()
        if len(data) != asset["bytes"] or hashlib.sha256(data).hexdigest() != asset["sha256"]:
            raise ValueError("报告资产已被改动：" + asset["path"])


def money(value, currency="CNY"):
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError("客户金额必须为有限非负数")
    return ("¥" if currency == "CNY" else currency + " ") + f"{number:,.2f}"


def selected(plan):
    placements = [p for p in plan.get("placements", []) if p.get("status") in ACTIVE]
    ids = {p["content_id"] for p in placements}
    contents = [c for c in plan.get("contents", []) if c.get("content_id") in ids]
    fees = [f for f in plan.get("fees", []) if f.get("status") in ACTIVE]
    return contents, placements, fees


ROLES = ("权威媒体", "行业媒体", "自媒体")
QUOTE_NAMES = ("普通权重方案", "高权重方案")
QUOTE_RATES = ({"权威媒体": Decimal("450"), "行业媒体": Decimal("200"), "自媒体": Decimal("200")},
               {"权威媒体": Decimal("600"), "行业媒体": Decimal("300"), "自媒体": Decimal("300")})
MIN_MEDIA_FEE = Decimal("12000")


def public_accounting(project, plan, quote_index=0):
    if project.get("currency", "CNY") != "CNY":
        raise ValueError("两档约定单价为人民币，currency须为CNY")
    if any(f.get("status") in ACTIVE for f in plan.get("fees", [])):
        raise ValueError("固定双档不接受额外执行收费fees；基础服务在service_scope列为已含，人工撰写使用manual_writing增项，其他另约费用须先单独确认")
    budget = calculate_budget(project, plan)
    if budget["client"]["missing_count"] or budget["client"]["total"] is None:
        raise ValueError("正式执行方案的客户报价或刊发数量尚未明确")
    validate_delivery_budget(budget)
    contents, placements, fees = selected(plan)
    if not contents or not placements:
        raise ValueError("执行方案须有独立内容与媒体类别配置")
    category_only = plan.get("plan_mode") == "category_only"
    groups = {role: [] for role in ROLES}
    for item in placements:
        if not isinstance(item.get("strategy_basis"), str) or not item["strategy_basis"].strip():
            raise ValueError("有效刊发须有策略角色依据")
        if category_only:
            if any(item.get(key) not in (None, "") for key in ("media_id", "media_name", "source_sheet", "unit_price")):
                raise ValueError("分类报价不指定媒体名称、来源或采购成本")
        elif not all(isinstance(item.get(key), str) and item[key].strip() for key in ("media_id", "media_name", "source_sheet")):
            raise ValueError("有效刊发须有具体资源身份、来源表及策略角色依据")
        role = item.get("strategy_role")
        if role not in ROLES:
            raise ValueError("strategy_role须为权威媒体、行业媒体或自媒体，不能用网络媒体代替")
        unit = Decimal(str(item["client_unit_price"]))
        if unit != QUOTE_RATES[quote_index][role]:
            raise ValueError(f"{QUOTE_NAMES[quote_index]}的{role}须按约定客户单价{QUOTE_RATES[quote_index][role]}元核算")
        cost = item.get("unit_price")
        if cost not in (None, "") and Decimal(str(cost)) > unit:
            raise ValueError("客户单价低于已明确采购成本，请重配资源，不得隐瞒成本倒挂")
        groups[role].append(item)
    summary, media_lines = {}, []
    for role, items in groups.items():
        quantity = sum(positive_int(p["quantity"], "quantity") for p in items)
        subtotal = sum((Decimal(str(p["client_unit_price"]))*positive_int(p["quantity"], "quantity") for p in items), Decimal(0))
        resources = [] if category_only else list(dict.fromkeys(p["media_name"] for p in items))
        summary[role] = {"quantity": quantity, "amount": subtotal, "resources": resources}
        media_lines.append(f"{role}{quantity}次 × {money(QUOTE_RATES[quote_index][role],budget['currency'])} = {money(subtotal,budget['currency'])}")
    if Decimal(budget["client"]["total"]) < MIN_MEDIA_FEE:
        raise ValueError(f"{QUOTE_NAMES[quote_index]}媒体发布费须至少12000元，请调整真实媒体配置与刊次；不得用写作费、虚增服务费或补差项凑足")
    return budget, summary, "\n".join(media_lines)


def service_scope(plan, content_count, budgets):
    scope = plan.get("service_scope")
    if not isinstance(scope, dict) or not isinstance(scope.get("work_items"), list):
        raise ValueError("计划须有service_scope.work_items统一分工和费用包含范围")
    rows, included = [], []
    for item in scope["work_items"]:
        if not isinstance(item, dict) or set(item) != {"task", "provider", "client", "included"}:
            raise ValueError("分工项须含task/provider/client/included四字段")
        if not all(isinstance(item[key], str) and item[key].strip() for key in ("task", "provider", "client")) or type(item["included"]) is not bool:
            raise ValueError("分工须写清事项、软文街工作、贵司配合及是否包含")
        provider = item["provider"] if item["included"] else item["provider"] + "；不含该项实际执行。"
        rows.append([item["task"], provider, item["client"]])
        if item["included"]:
            included.append(item["task"])
    if len({r[0] for r in rows}) != len(rows) or not {"内容策划", "媒体发布", "链接汇总", "阶段复核"}.issubset(included):
        raise ValueError("已含服务须明确内容策划、媒体发布、链接汇总和阶段复核，工作事项不得重复")
    if not isinstance(scope.get("review_schedule"), str) or not scope["review_schedule"].strip():
        raise ValueError("须写明已含阶段复核的具体节点")
    included_work = "；".join(item["task"] + "：" + item["provider"] for item in scope["work_items"] if item["included"])
    if any(word in included_work for word in ("AI起草", "人工简单修改", "人工撰写", "代写", "撰稿", "写稿", "稿件撰写", "文章撰写", "文章写作")):
        raise ValueError("媒体与基础服务不含稿件撰写，请将写作服务单列收费；客户稿件审核与发布排版可列为已含")
    mode = scope.get("writing_mode")
    if mode == "client_provided":
        if scope.get("manual_writing") not in (None, {}):
            raise ValueError("客户供稿项目不承接人工撰写增项")
        if any(word in row[1] for row in rows for word in ("AI起草", "人工简单修改", "人工撰写")):
            raise ValueError("客户供稿项目的软文街工作不应承诺代写或人工撰稿")
        services = "已含" + "、".join(included) + "；贵司供稿并负责专业审核。"
        writing = "贵司提供定稿及公开授权；本方案不含代写或人工撰写增项。"
    elif mode == "separate":
        manual = scope.get("manual_writing", {})
        from geo_data import money as parsed_money
        if not isinstance(manual, dict) or set(manual) != {"unit_price", "original_unit_price"} or parsed_money(manual["unit_price"], "人工撰稿单价") != Decimal("100") or parsed_money(manual["original_unit_price"], "人工撰稿原价") != Decimal("200"):
            raise ValueError("人工撰写增项须按原价200元/篇、打包100元/独立稿明确")
        services = "已含" + "、".join(included) + "；稿件撰写另收费。"
        extra = Decimal("100") * content_count
        for index, budget in enumerate(budgets):
            limit = parsed_money(budget.get("limit"), "budget_limit")
            total = Decimal(budget["client"]["total"]) + extra
            if limit is not None and total > limit:
                raise ValueError(f"{QUOTE_NAMES[index]}媒体与写作总额{money(total)}超出预算上限{money(limit)}，请调整实际执行范围")
        writing = f"写作另计：原价200元/篇，打包100元/独立稿，{content_count}篇共{money(extra)}。\n"
        writing += "媒体＋写作总额：普通" + money(Decimal(budgets[0]["client"]["total"])+extra) + "；高权重" + money(Decimal(budgets[1]["client"]["total"])+extra) + "。"
    elif mode == "ai_assisted":
        raise ValueError("ai_assisted免费写作模式已停用，请使用separate写作另计或client_provided客户供稿")
    else:
        raise ValueError("writing_mode须明确separate或client_provided")
    return rows, services, writing, scope["review_schedule"]


def prepare_document(kind, report, project=None, plan=None, analysis=None):
    errors = renderer.validate_report(report)
    if errors:
        raise ValueError("; ".join(errors))
    if kind not in report:
        raise ValueError("客户报告缺少 " + kind)
    doc = copy.deepcopy(report[kind])
    if kind == "execution":
        if not project or plan is None:
            raise ValueError("执行方案需要 --project（或 --analysis 中的 project）及 --plan")
        options = plan.get("quote_options")
        if not isinstance(options, list) or len(options) != 1:
            raise ValueError("须配置普通、高权重两套真实媒体方案")
        option = options[0]
        if set(option) != {"name", "placements", "fees"} or option["name"] != QUOTE_NAMES[1]:
            raise ValueError("高权重备选须为name/placements/fees且名称为高权重方案")
        alternate = {**plan, "placements": option["placements"], "fees": option["fees"]}
        accounting = [public_accounting(project, plan, 0), public_accounting(project, alternate, 1)]
        budgets = [item[0] for item in accounting]
        budget = budgets[0]
        if analysis is not None and analysis.get("budget") != budget:
            raise ValueError("计划与分析预算不一致，请重新生成 analysis.json 后导出")
        contents, placements, _ = selected(plan)
        _, other_placements, _ = selected(alternate)
        def allocation(records):
            result = Counter()
            for p in records:
                result[(p["content_id"], p["strategy_role"])] += positive_int(p["quantity"], "quantity")
            return result
        if allocation(placements) != allocation(other_placements):
            raise ValueError("两档须有相同独立内容及每篇各策略类的刊发次数")
        if plan.get("plan_mode") != "category_only":
            identities = lambda records: {(p["content_id"], p["source_sheet"], p["media_id"]) for p in records}
            if identities(placements) == identities(other_placements):
                raise ValueError("两档须有实际不同的媒体配置，不能只更改价格")
        pages = doc["pages"]
        groups = defaultdict(list)
        for content in contents:
            group = content.get("content_group")
            if not isinstance(group, str) or not group.strip():
                raise ValueError("已选内容须有具体content_group")
            groups[group].append(content)
        if [g["name"] for g in pages[3]["groups"]] != list(groups):
            raise ValueError("第4页内容组须按实际选中content_group首次出现顺序填写")
        pages[3].update(headers=["内容方向", "篇数", "重点介绍", "主要作用"],
            rows=[[g["name"], f"{len(groups[g['name']])}篇", g["detail"], g["role"]] for g in pages[3]["groups"]],
            note=f"{budget['content_count']}篇不同稿件，围绕各组业务场景展开。",
            subtitle=f"{budget['content_count']}篇不同稿件，围绕各组业务场景展开。")
        if [item["category"] for item in pages[4]["items"]] != list(ROLES):
            raise ValueError("媒体发布页须按权威媒体、行业媒体、自媒体三类顺序填写")
        for card in pages[4]["items"]:
            role = card["category"]
            ordinary, higher = accounting[0][1][role], accounting[1][1][role]
            if plan.get("plan_mode") == "category_only":
                names = ["具体媒体待确认" if ordinary["quantity"] else "本期未配置", "两档不指定具体资源"]
            else:
                names = []
                for label, info in [("普通", ordinary), ("高权重", higher)]:
                    text = "、".join(info["resources"][:2]) or "本期未配置"
                    if len(info["resources"]) > 2:
                        text += f"等{len(info['resources'])}项"
                    names.append(label + "：" + text)
            card.update(resources="\n".join(names), quantity=f"{ordinary['quantity']}次",
                amount="普通"+money(ordinary["amount"],budget["currency"])+" / 高"+money(higher["amount"],budget["currency"]))
        pages[4]["subtitle"] = "＋".join(f"{r}{accounting[0][1][r]['quantity']}次" for r in ROLES) + f"，共{budget['publication_count']}次发布；" + ("两档同范围，具体媒体待确认。" if plan.get("plan_mode") == "category_only" else "两档内容及数量一致。")
        stages = {s["name"]: s for s in plan.get("stages", [])}
        selected_stages = list(dict.fromkeys(c.get("stage") for c in contents))
        if None in selected_stages or any(name not in stages for name in selected_stages):
            raise ValueError("已选内容须关联实际执行阶段")
        if [s["title"] for s in pages[5]["items"]] != selected_stages:
            raise ValueError("阶段卡须按plan实际阶段顺序填写")
        for card, name in zip(pages[5]["items"], selected_stages):
            ids = {c["content_id"] for c in contents if c["stage"] == name}
            stage_totals = []
            stage_dates = [c.get("scheduled_date") for c in contents if c["content_id"] in ids]
            by_role = Counter()
            for index, chosen in enumerate((plan, alternate)):
                _, ps, fs = selected(chosen)
                ps = [p for p in ps if p["content_id"] in ids]
                fs = [f for f in fs if f.get("stage") == name]
                total = sum((Decimal(str(p["client_unit_price"]))*positive_int(p["quantity"], "quantity") for p in ps), Decimal(0))
                total += sum((Decimal(str(f["client_amount"])) for f in fs), Decimal(0))
                stage_totals.append(total)
                stage_dates += [p.get("scheduled_date") for p in ps] + [f.get("scheduled_date") for f in fs]
                if index == 0:
                    for p in ps:
                        by_role[p["strategy_role"]] += positive_int(p["quantity"], "quantity")
            if any(not d for d in stage_dates):
                raise ValueError("已选内容、刊发和计费服务须有计划日期")
            dates = [date.fromisoformat(d) for d in stage_dates]
            start = date.fromisoformat(stages[name]["start_date"]) if stages[name].get("start_date") else min(dates)
            end = date.fromisoformat(stages[name]["end_date"]) if stages[name].get("end_date") else max(dates)
            if start > min(dates) or end < max(dates) or start > end:
                raise ValueError("阶段起止日期未覆盖实际内容、发布或计费服务")
            card.update(period=start.isoformat()+" - "+end.isoformat(),
                counts=f"{len(ids)}篇 / {sum(by_role.values())}次发布",
                media_counts=" / ".join(f"{dict(zip(ROLES,('权威','行业','自媒')))[r]}{by_role[r]}" for r in ROLES),
                amount="普通"+money(stage_totals[0],budget["currency"])+" / 高"+money(stage_totals[1],budget["currency"]))
        for chosen in (plan, alternate):
            if any(f.get("status") in ACTIVE and f.get("stage") not in selected_stages for f in chosen.get("fees", [])):
                raise ValueError("已计费服务须关联实际阶段，确保阶段金额与总价一致")
        work, services, writing, review_schedule = service_scope(plan, budget["content_count"], budgets)
        pages[6].update(headers=["工作事项", "软文街负责", "贵司配合"], rows=work)
        pages[7]["subtitle"] = review_schedule + "分别复核，阶段工作包含在服务中。"
        if [card["name"] for card in pages[8]["items"]] != list(QUOTE_NAMES):
            raise ValueError("费用页须为普通权重方案和高权重方案两档")
        for card, (chosen, _, media) in zip(pages[8]["items"], accounting):
            card.update(total=money(chosen["client"]["total"],chosen["currency"]),
                scale=f"媒体发布费｜{chosen['content_count']}篇 / {chosen['publication_count']}次发布", media=media)
        pages[8].update(services=services, writing=writing)
        pages[8]["subtitle"] = ("两档同稿量同刊次；具体媒体及权益待确认。" if plan.get("plan_mode") == "category_only" else
            "两档同稿量同刊次，基础服务与阶段复核已含；贵司供稿并负责专业审核。"
            if plan["service_scope"]["writing_mode"] == "client_provided" else
            "两档同稿量同刊次，含基础服务与阶段复核；媒体与写作分别报价。")
    config = {"customer": copy.deepcopy(report["customer"]), "purpose": report["purpose"], "pages": doc["pages"]}
    errors = renderer.validate(config, kind)
    if errors:
        raise ValueError("; ".join(errors))
    return config


def export_reports(report, output_dir, kinds=("diagnosis", "execution"), project=None, plan=None, analysis=None, png_scale=1.15, review_root=None):
    verify_assets()
    out = Path(output_dir)
    review_root = Path(review_root) if review_root is not None else out.parent / ".work" / "pdf-review"
    resolved_out, resolved_review = out.resolve(), review_root.resolve()
    private_child = resolved_review.is_relative_to(resolved_out) and ".work" in resolved_review.relative_to(resolved_out).parts
    if resolved_review == resolved_out or (resolved_out in resolved_review.parents and not private_child):
        raise ValueError("页面预览须保存在客户内部工作目录，不能放入正式PDF目录")
    if any((out / FILES[kind]).exists() for kind in kinds):
        raise FileExistsError("输出已存在，拒绝覆盖，请使用新的版本目录")
    configs = {kind: prepare_document(kind,report,project,plan,analysis) for kind in kinds}
    out.parent.mkdir(parents=True,exist_ok=True)
    # Render the complete batch before publishing any requested PDF.
    with tempfile.TemporaryDirectory(prefix="geo-report-",dir=out.parent) as folder:
        staged = Path(folder)
        for kind in kinds:
            renderer.render(configs[kind],staged,kind,png_scale=png_scale)
        if out.exists() and any((out/FILES[kind]).exists() for kind in kinds):
            raise FileExistsError("输出目录存在同名文件，拒绝覆盖")
        review_root.mkdir(parents=True,exist_ok=True)
        review = Path(tempfile.mkdtemp(prefix="review-",dir=review_root))
        out.mkdir(parents=True,exist_ok=True)
        for path in staged.iterdir():
            if path.suffix == ".json":
                audit = json.loads(path.read_text(encoding="utf-8"))
                audit["pdf"] = str(out/Path(audit["pdf"]).name)
                audit["rendered_pages"] = [str(review/Path(p).name) for p in audit["rendered_pages"]]
                (review/path.name).write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8",newline="\n")
            else:
                destination = out if path.suffix == ".pdf" else review
                with (destination/path.name).open("xb") as stream:
                    stream.write(path.read_bytes())
        return {kind:{"pdf":str(out/FILES[kind]),"pages":len(configs[kind]["pages"]),
                      "audit":str(review/(kind+"_layout_audit.json")),"review_dir":str(review)} for kind in kinds}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",required=True)
    parser.add_argument("--output-dir",required=True)
    for name in ("project","analysis","plan"):
        parser.add_argument("--"+name)
    parser.add_argument("--kind",choices=["both","diagnosis","execution"],default="both")
    args = parser.parse_args()
    report = load_json(args.report)
    analysis = load_json(args.analysis) if args.analysis else None
    project = load_json(args.project) if args.project else (analysis or {}).get("project")
    if analysis and args.project and project != analysis.get("project"):
        raise ValueError("project 与 analysis.project 不一致")
    plan = load_json(args.plan) if args.plan else None
    kinds = tuple(FILES) if args.kind == "both" else (args.kind,)
    report_path = Path(args.report).resolve()
    review_root = None if report_path.is_relative_to(ROOT.resolve()) else report_path.parent/"pdf-review"
    result = export_reports(report,args.output_dir,kinds,project,plan,analysis,review_root=review_root)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
