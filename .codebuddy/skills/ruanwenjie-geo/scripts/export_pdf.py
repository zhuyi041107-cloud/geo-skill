"""Render customer-only reports; keep internal accounting outside the PDF renderer."""
from __future__ import annotations
import argparse
import copy
from collections import defaultdict
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


def public_accounting(project, plan):
    budget = calculate_budget(project, plan)
    if budget["client"]["missing_count"] or budget["client"]["total"] is None:
        raise ValueError("正式执行方案的客户报价或刊发数量尚未明确")
    validate_delivery_budget(budget)
    contents, placements, fees = selected(plan)
    if not contents or not placements:
        raise ValueError("执行方案须有真实独立内容与具体媒体组合")
    if any(not isinstance(p.get("media_name"), str) or not p["media_name"].strip() for p in placements):
        raise ValueError("有效刊发须填写具体媒体名称")
    groups = defaultdict(list)
    for item in placements:
        groups[item.get("media_type") or "媒体发布"].append(item)
    rows, media_lines = [], []
    currency = budget["currency"]
    for category, items in groups.items():
        count = sum(positive_int(p["quantity"],"quantity") for p in items)
        resources = list(dict.fromkeys(p["media_name"] for p in items))
        names = "、".join(resources[:3])
        if len(resources) > 3:
            names = "代表资源：" + names + f"；共{len(resources)}项资源"
        price_groups = defaultdict(int)
        for item in items:
            price_groups[Decimal(str(item["client_unit_price"]))] += positive_int(item["quantity"],"quantity")
        subtotal = sum(Decimal(str(p["client_unit_price"]))*positive_int(p["quantity"],"quantity") for p in items)
        low, high = min(price_groups), max(price_groups)
        price = money(low,currency) if low == high else money(low,currency)+"-"+money(high,currency)
        rows.append([category, f"{count}次", names, money(subtotal,currency)])
        media_lines.append(f"{category}{count}次，{price}/次，小计{money(subtotal,currency)}")
    for fee in fees:
        label = fee.get("description") or fee.get("category")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("已计费服务须写明对客服务范围")
        media_lines.append(label + " " + money(fee["client_amount"],currency))
    return budget, rows, "；".join(media_lines)


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
        budget, rows, media = public_accounting(project, plan)
        if analysis is not None and analysis.get("budget") != budget:
            raise ValueError("计划与分析预算不一致，请重新生成 analysis.json 后导出")
        pages = doc["pages"]
        if "rows" in pages[4]:
            raise ValueError("媒体数量与金额从 plan 生成，不可在 report 手填 rows")
        pages[4]["rows"] = rows
        pages[4]["note"] = "具体媒体与栏目、公开范围及发布档期在执行前确认。"
        pages[4]["subtitle"] = f"本期{budget['content_count']}篇独立稿件，安排{budget['publication_count']}次媒体刊发。"
        contents, placements, _ = selected(plan)
        groups = defaultdict(list)
        for content in contents:
            group = content.get("content_group") or content.get("source_layer")
            if not isinstance(group,str) or not group.strip():
                raise ValueError("已选内容须有 content_group（或已有 source_layer）")
            groups[group].append(content)
        supplied = pages[3]["groups"]
        if [g["name"] for g in supplied] != list(groups):
            raise ValueError("第4页内容组须按实际选中 contents.content_group 首次出现顺序填写")
        if any(key in pages[3] for key in ("headers","rows","note")):
            raise ValueError("内容组篇数从 plan 生成，不可在 report 手填 headers/rows/note")
        pages[3].update(headers=["内容方向","稿件规模","重点内容","主要作用"],
                        rows=[[g["name"],f"{len(groups[g['name']])}篇",g["detail"],g["role"]] for g in supplied],
                        note=f"本期共{budget['content_count']}篇独立稿件，重点覆盖各组所列业务场景。")
        pages[3]["subtitle"] = pages[3]["note"]
        stages = {s["name"]: s for s in plan.get("stages", [])}
        selected_stages = list(dict.fromkeys(c.get("stage") for c in contents))
        if None in selected_stages or any(name not in stages for name in selected_stages):
            raise ValueError("已选内容须关联 plan.stages 中的真实阶段")
        if len(pages[5]["items"]) != len(selected_stages):
            raise ValueError("第6页阶段卡数与 plan 中实际阶段数量不一致")
        for item, name in zip(pages[5]["items"], selected_stages):
            if item["title"] != name:
                raise ValueError("第6页阶段卡标题须按 plan 中实际阶段顺序填写")
            if any(key in item for key in ("counts","amount","period")):
                raise ValueError("阶段日期、数量与金额从 plan 生成，不可在 report 手填")
            ids = {c["content_id"] for c in contents if c.get("stage") == name}
            stage_placements = [p for p in placements if p["content_id"] in ids]
            stage_fees = [f for f in plan.get("fees",[]) if f.get("status") in ACTIVE and f.get("stage")==name]
            quantity = sum(positive_int(p["quantity"],"quantity") for p in stage_placements)
            item["counts"] = f"{len(ids)}篇 / {quantity}次刊发"
            stage_amount = sum(Decimal(str(p["client_unit_price"]))*positive_int(p["quantity"],"quantity") for p in stage_placements)
            stage_amount += sum((Decimal(str(f["client_amount"])) for f in stage_fees),Decimal(0))
            item["amount"] = money(stage_amount,budget["currency"])
            dates=[c.get("scheduled_date") for c in contents if c["content_id"] in ids]+[p.get("scheduled_date") for p in stage_placements]+[f.get("scheduled_date") for f in stage_fees]
            if any(not d for d in dates):
                raise ValueError("已选阶段的内容、刊发与计费服务须有实际日期")
            dates=[date.fromisoformat(d) for d in dates]
            item["period"] = min(dates).isoformat()+" - "+max(dates).isoformat()
        if any(f.get("status") in ACTIVE and f.get("stage") not in selected_stages for f in plan.get("fees",[])):
            raise ValueError("已计费服务须关联实际执行阶段，确保阶段金额与总价一致")
        options = plan.get("quote_options", [])
        if not isinstance(options, list) or len(options) > 1:
            raise ValueError("只支持主方案及一个真实备选媒体配置")
        cards = pages[8]["items"]
        if len(cards) != 1 + len(options):
            raise ValueError("费用卡数须与真实计划方案数一致，不可补造第二报价")
        baseline = {c["content_id"] for c in contents}
        for index, card in enumerate(cards):
            if any(key in card for key in ("total", "scale", "media")):
                raise ValueError("费用和稿量从 plan 生成，不可在 report 手填 total/scale/media")
            chosen, chosen_media = budget, media
            if index:
                option = options[index-1]
                if set(option) - {"name", "placements", "fees"} or not option.get("name"):
                    raise ValueError("备选方案只能包含 name/placements/fees")
                if card["name"] != option["name"]:
                    raise ValueError("备选费用卡名称与真实方案不一致")
                alternate = {**plan, "placements": option.get("placements", []), "fees": option.get("fees", [])}
                chosen, _, chosen_media = public_accounting(project, alternate)
                other_contents, _, _ = selected(alternate)
                if {c["content_id"] for c in other_contents} != baseline or chosen["publication_count"] != budget["publication_count"]:
                    raise ValueError("双方案须具有相同独立稿件及刊发规模")
            card.update(total=money(chosen["client"]["total"],chosen["currency"]),
                        scale=f"{chosen['content_count']}篇独立稿件 / {chosen['publication_count']}次刊发",media=chosen_media)
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
