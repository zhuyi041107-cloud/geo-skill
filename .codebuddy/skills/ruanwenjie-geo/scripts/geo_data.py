"""Portable GEO workbook preparation, evidence statistics and budget exports."""
import argparse
import json
import re
import sys
from collections import defaultdict
from copy import copy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile

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


def prepare_internal(project, out):
    validate_project(project)
    if Path(out).exists():
        raise ValueError(f"输出已存在，拒绝覆盖: {out}")
    wb = openpyxl.load_workbook(ROOT / "references/内部判读底表.xlsx")
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


def prepare(project, out=None, out_dir=None):
    """Produce only the three columns a colleague needs to collect."""
    validate_project(project)
    contexts = project["contexts"]
    if out and (out_dir or len(contexts) != 1):
        raise ValueError("--out仅用于单个context；多个平台/模式请使用--out-dir")
    if not out and not out_dir:
        raise ValueError("请提供--out或--out-dir")
    targets = []
    for i, context in enumerate(contexts, 1):
        label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", f"{context['platform']}-{context['mode']}")[:80]
        target = Path(out) if out else Path(out_dir) / f"{i:02d}-{label}-回答采集.xlsx"
        if target.exists():
            raise ValueError(f"输出已存在，拒绝覆盖: {target}")
        targets.append(target)
    for target in targets:
        wb = openpyxl.load_workbook(ROOT / "templates/AI回答采集表.xlsx")
        put_rows(wb["回答采集"], [[q["text"], None, None] for q in project["questions"] for _ in range(project.get("repeats", 1))])
        save_new(wb, target)
        wb.close()
    return {"outputs": [str(p) for p in targets], "questions": len(project["questions"]), "rows_per_file": len(project["questions"]) * project.get("repeats", 1)}


def normalize_collection(input_path, project, context, out, base=None):
    """Import three columns using the user's current-round convention for gaps."""
    project = dict(project, contexts=[dict(c) for c in project.get("contexts", [])])
    original_contexts = [dict(c) for c in project["contexts"]]
    for c in project["contexts"]:
        if c.get("mode") in (None, "", "未知", "未记录"):
            c["mode"] = "网页端"
        if c.get("online") in (None, "", "未知", "未记录"):
            c["online"] = "是"
    validate_project(project)
    input_path, out = Path(input_path).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError(f"输出已存在，拒绝覆盖: {out}")
    options = project["contexts"]
    if str(context).isdigit():
        selected = int(context) - 1
        if selected < 0 or selected >= len(options):
            raise ValueError("context序号超出范围（从1开始）")
    else:
        matches = [i for i, c in enumerate(options) if c["platform"] == context]
        if len(matches) != 1:
            raise ValueError("平台不唯一或不存在，请使用context序号")
        selected = matches[0]
    source = openpyxl.load_workbook(input_path, data_only=False)
    visible = [s for s in source if s.sheet_state == "visible"]
    if len(visible) != 1 or [c.value for c in next(visible[0].iter_rows(max_row=1))][:3] != ["问题", "引用截图", "答案"]:
        source.close()
        raise ValueError("采集表须有一个可见sheet，表头为：问题、引用截图、答案")
    ws = visible[0]
    if ws.max_column > 3 and any(c.value not in (None, "") for row in ws.iter_rows(min_col=4) for c in row):
        raise ValueError("三列外存在内容，请由WorkBuddy确认后再导入，避免丢失数据")
    images = defaultdict(list)
    unlocated = []
    for image in ws._images:
        marker = getattr(image.anchor, "_from", None)
        if marker is None or marker.row < 1:
            unlocated.append((image, "未确定对应问题行", image.format))
            continue
        images[marker.row + 1].append(image)
    with ZipFile(input_path) as package:
        media = [n for n in package.namelist() if n.startswith("xl/media/") and not n.endswith("/")]
        if any("cellimages" in n.lower() or n.startswith("xl/richData/") for n in package.namelist()) or len(media) > len(ws._images):
            unlocated.extend((package.read(n), n, Path(n).suffix.lstrip(".")) for n in media)
    metadata = dict(project.get("sampling_metadata") or {})
    metadata.update(options[selected].get("sampling_metadata") or {})
    if metadata.get("collected_at") in (None, "", "未知", "未记录"):
        metadata["collected_at"] = date.today().isoformat()
    by_question = defaultdict(list)
    for q in project["questions"]:
        by_question[text(q["text"])].append(q)
    used = defaultdict(int)
    records = []
    for row_index, row in enumerate(ws.iter_rows(min_row=2, max_col=3), 2):
        question, screenshot, answer = [c.value for c in row]
        if not text(question) and row_index in images:
            unlocated.extend((image, f"原表第{row_index}行无问题", image.format) for image in images.pop(row_index))
            if not text(answer) and not text(screenshot):
                continue
        if not any(v not in (None, "") for v in (question, screenshot, answer)) and row_index not in images:
            continue
        candidates = by_question.get(text(question), [])
        occurrence = used[text(question)]
        if not candidates or occurrence >= len(candidates) * project.get("repeats", 1):
            raise ValueError(f"第{row_index}行问题不在项目配置或超出重复次数，请让WorkBuddy核对实际问句")
        q = candidates[occurrence // project.get("repeats", 1)]
        repeat = occurrence % project.get("repeats", 1) + 1
        used[text(question)] += 1
        records.append((row_index, q, repeat, screenshot, answer))
    represented = {r[0] for r in records}
    for row_index in set(images) - represented:
        unlocated.extend((image, f"原表第{row_index}行未对应问题", image.format) for image in images[row_index])
    if base:
        target = openpyxl.load_workbook(base)
        config = {r["字段"]: json.loads(r["值(JSON)"]) for r in load_rows(target, "项目配置", ["字段", "值(JSON)", "说明"])}
        old_questions = load_rows(target, "问题清单", QUESTION_HEADERS)
        old_contexts = config.get("contexts", [])
        mismatch = len(old_contexts) != len(original_contexts)
        for old, supplied in zip(old_contexts, original_contexts):
            mismatch |= any(old.get(k) != supplied.get(k) for k in ("platform", "round"))
            mismatch |= any(old.get(k) not in (None, "", "未知", "未记录") and supplied.get(k) not in (None, "", "未知", "未记录") and old.get(k) != supplied.get(k) for k in ("mode", "online"))
        if mismatch or config.get("project_id") != project.get("project_id") or [(q["question_id"], q["目标问题"]) for q in old_questions] != [(q["question_id"], q["text"]) for q in project["questions"]] or config.get("repeats", 1) != project.get("repeats", 1):
            raise ValueError("--base与项目配置/问题/contexts不一致，不能合并")
        project["contexts"] = [dict(c) for c in old_contexts]
        for key in ("mode", "online"):
            if project["contexts"][selected].get(key) in (None, "", "未知", "未记录"):
                project["contexts"][selected][key] = options[selected][key]
        for row in target["项目配置"].iter_rows(min_row=2):
            if row[0].value == "contexts":
                row[1].value = json.dumps(project["contexts"], ensure_ascii=False)
    else:
        prepare_internal(project, out)
        target = openpyxl.load_workbook(out)
    target_rows = {r[0].value: r[0].row for r in target["回答记录"].iter_rows(min_row=2) if r[0].value}
    for sid, row in target_rows.items():
        if f"-C{selected+1:03d}-R" in sid:
            for header, key in [("模型或模式", "mode"), ("联网状态", "online")]:
                target["回答记录"].cell(row, SAMPLE_HEADERS.index(header) + 1, project["contexts"][selected][key])
    if not any(row[0].value == "collection_convention" for row in target["项目配置"].iter_rows(min_row=2)):
        last = max(row[0].row for row in target["项目配置"].iter_rows() if row[0].value) + 1
        target["项目配置"].cell(last, 1, "collection_convention")
        target["项目配置"].cell(last, 2, json.dumps("缺失日期按本轮本地日期，缺失模式/联网按网页端直接联网；这是用户本轮约定，网页端不是实测模型名", ensure_ascii=False))
    refs = [[r.get(h) for h in CITATION_HEADERS] for r in load_rows(target, "引用明细", CITATION_HEADERS)]
    extracted, warnings = [], []
    attachment_dir = out.parent / "引用截图" / out.stem
    try:
        loose_paths = []
        for i, (item, location, extension) in enumerate(unlocated, 1):
            extension = re.sub(r"[^a-z0-9]", "", extension.lower()) or "bin"
            path = attachment_dir / f"unlocated-{i:03d}.{extension}"
            attachment_dir.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(item if isinstance(item, bytes) else item._data())
            extracted.append(path)
            loose_paths.append({"path": str(path), "original_location": location})
        if loose_paths:
            warnings.append(f"{len(loose_paths)}张未定位截图已保留供内部判读，未强绑问题，不影响已有答案分析")
            rows = [r for r in target["项目配置"].iter_rows(min_row=2) if r[0].value == "unlocated_screenshots"]
            row = rows[0][0].row if rows else max(r[0].row for r in target["项目配置"].iter_rows() if r[0].value) + 1
            prior = json.loads(rows[0][1].value) if rows else []
            target["项目配置"].cell(row, 1, "unlocated_screenshots")
            target["项目配置"].cell(row, 2, json.dumps(prior + loose_paths, ensure_ascii=False))
        for original_row, q, repeat, attachment, answer in records:
            sid = f"{q['question_id']}-C{selected+1:03d}-R{repeat:02d}"
            row = target_rows[sid]
            if target["回答记录"].cell(row, SAMPLE_HEADERS.index("回答全文") + 1).value not in (None, ""):
                raise ValueError(f"任务{sid}已有答案，拒绝覆盖；新采样请建立新轮次")
            paths = []
            no_display = text(attachment) in {"未展示", "未展示可观察引用"}
            for index, image in enumerate(images.get(original_row, []), 1):
                data = image._data()
                extension = re.sub(r"[^a-z0-9]", "", image.format.lower()) or "png"
                path = attachment_dir / f"row-{original_row:04d}-image-{index:02d}.{extension}"
                attachment_dir.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(data)
                extracted.append(path)
                paths.append(str(path))
            for label in ([] if no_display else text(attachment).splitlines()):
                if not label.strip():
                    continue
                candidate = (input_path.parent / label.strip()).resolve()
                if not candidate.is_relative_to(input_path.parent):
                    warnings.append(f"第{original_row}行附件未读取：路径超出采集表目录")
                    paths.append(label)
                elif candidate.is_file() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}:
                    path = attachment_dir / f"row-{original_row:04d}-attachment-{len(paths)+1:02d}{candidate.suffix.lower()}"
                    attachment_dir.mkdir(parents=True, exist_ok=True)
                    with path.open("xb") as stream:
                        stream.write(candidate.read_bytes())
                    extracted.append(path)
                    paths.append(str(path))
                else:
                    warnings.append(f"第{original_row}行截图附件待定位，已保留原记录")
                    paths.append(label)
            status = "未采集" if not text(answer) else ("失败" if re.match(r"^(?:采集失败|失败)(?:$|[:：])", text(answer)) else "已完成")
            values = {"采集状态": status, "回答全文": answer, "引用展示": "未展示" if no_display else "待核验",
                      "采集时间": metadata.get("collected_at"), "新对话": metadata.get("new_conversation"),
                      "回答证据路径": "\n".join(paths) or None, "备注": f"原采集表 {input_path.name}，第{original_row}行"}
            for header, value in values.items():
                cell = target["回答记录"].cell(row, SAMPLE_HEADERS.index(header) + 1, value)
                if isinstance(value, str):
                    cell.data_type = "s"
            for i, path in enumerate([] if no_display else paths, 1):
                refs.append([f"{sid}-CIT{i:02d}", sid, None, None, None, "待核验", "待判", None, path, "仅记录截图证据，来源名称及URL须由WorkBuddy查看后核验"])
        put_rows(target["引用明细"], refs)
        # This file was created above by this call; the user's input is never edited.
        if base:
            save_new(target, out)
        else:
            target.save(out)
    except Exception:
        target.close()
        if not base:
            out.unlink(missing_ok=True)
        for path in extracted:
            path.unlink(missing_ok=True)
        raise
    finally:
        target.close()
        source.close()
    return {"output": str(out), "context": selected + 1, "imported_rows": len(records), "screenshots": len(extracted), "unlocated_screenshots": loose_paths, "warnings": warnings}


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
    used_convention = False
    for index, ctx in enumerate(project.get("contexts", []), 1):
        linked = [s for s in samples if f"-C{index:03d}-R" in text(s["sample_id"])]
        for key, header, default in [("mode", "模型或模式", "网页端"), ("online", "联网状态", "是")]:
            if ctx.get(key) in (None, "", "未知", "未记录"):
                recorded = {s[header] for s in linked if s[header] not in (None, "", "未知", "未记录")}
                ctx[key] = next(iter(recorded)) if len(recorded) == 1 else default
                used_convention = True
            for s in linked:
                if s[header] in (None, "", "未知", "未记录"):
                    s[header] = ctx[key]
                    used_convention = True
    ref_sample_ids = {r["sample_id"] for r in citations}
    for sample in samples:
        if (sample["采集状态"] != "未采集" or text(sample["回答全文"]) or text(sample["回答证据路径"]) or sample["sample_id"] in ref_sample_ids) and sample["采集时间"] in (None, "", "未知", "未记录"):
            sample["采集时间"] = date.today().isoformat()
            used_convention = True
    if used_convention:
        project.setdefault("collection_convention", "缺失日期按本轮本地日期，缺失模式/联网按网页端直接联网；这是用户本轮约定，网页端不是实测模型名")
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
        if text(ref["URL"]) and (url.scheme not in {"http", "https"} or not url.netloc):
            raise ValueError(f"引用URL必须为http(s): {ref['citation_id']}")
        if not text(ref["URL"]) and not (text(ref["证据路径"]) and ref["核验状态"] == "待核验"):
            raise ValueError(f"无URL引用须保留截图证据并标为待核验: {ref['citation_id']}")
        if ref["核验状态"] not in {"已核验", "无效", "待核验"} or ref["支持品牌"] not in YES_NO:
            raise ValueError(f"引用核验状态/支持品牌缺失: {ref['citation_id']}")
        refs[ref["sample_id"]].append(ref)
    groups = {}
    evidence = []
    issues = []
    identities = set()
    contexts = {tuple(text(c[k]) for k in ("platform", "mode", "online", "round")) for c in project["contexts"]}
    sampled = {tuple(text(s[k]) for k in ("平台", "模型或模式", "联网状态", "轮次")) for s in samples
               if s["采集状态"] != "未采集" or text(s["回答全文"]) or text(s["回答证据路径"]) or s["sample_id"] in refs}
    scoped_sample_ids = {s["sample_id"] for s in samples if tuple(text(s[k]) for k in ("平台", "模型或模式", "联网状态", "轮次")) in sampled}
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
        if context not in sampled:
            continue
        q = question_by_id[sample["question_id"]]
        key = context + (q["问题类型"], q["意图"])
        if key not in groups:
            groups[key] = dict(zip(("platform", "mode", "online", "round", "question_type", "intent"), key))
            groups[key].update({k: 0 for k in ["planned", "completed", "failed", "pending_review", "uncollected", "valid", "invalid_conditions", "condition_unknown", "mention_yes", "mention_no", "mention_pending", "recommendation_yes", "recommendation_no", "recommendation_pending", "observable_citation_samples", "citation_known_samples", "citation_supported_samples", "unobserved_sources"]})
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
        condition_issues, unknown_conditions = [], []
        if sample["新对话"] == "否":
            condition_issues.append("已知不是独立新对话")
        collected_at = sample["采集时间"]
        try:
            if not isinstance(collected_at, datetime):
                datetime.fromisoformat(text(collected_at))
        except ValueError:
            unknown_conditions.append("采集时间未记录或格式未确认")
        if not project.get("collection_convention") and collected_at and ((isinstance(collected_at, date) and not isinstance(collected_at, datetime)) or len(text(collected_at)) == 10):
            issues.append({"sample_id": sid, "issue": "采集时间仅记录日期，时分和时区精度未确认"})
        elif not project.get("collection_convention") and isinstance(collected_at, datetime) and collected_at.tzinfo is None:
            issues.append({"sample_id": sid, "issue": "Excel采集时间未记录时区，需核验"})
        evidence.append({"evidence_id": f"EV-{sid}", "sample_id": sid, "question_id": sample["question_id"],
                         "question_type": q["问题类型"], "intent": q["意图"], "platform": sample["平台"],
                         "mode": sample["模型或模式"], "online": sample["联网状态"], "round": int(sample["轮次"]),
                         "answer": sample["回答全文"], "mention": sample["品牌提及"], "recommendation": sample["品牌推荐"],
                         "source": sample["回答证据路径"], "comparable": not condition_issues and not unknown_conditions, "condition_issues": condition_issues + unknown_conditions,
                         "verified_citation_ids": [r["citation_id"] for r in refs[sid] if r["核验状态"] == "已核验" and r["支持品牌"] == "是"]})
        if condition_issues:
            group["invalid_conditions"] += 1
            issues.append({"sample_id": sid, "issue": "；".join(condition_issues) + "；保留本次事实，排除标准可比指标"})
            continue
        if unknown_conditions:
            group["condition_unknown"] += 1
            issues.append({"sample_id": sid, "issue": "采样条件未记录；" + "；".join(unknown_conditions) + "；仅作本次描述性分析"})
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
                for r in range(1, project.get("repeats", 1) + 1)
                if tuple(text(c[k]) for k in ("platform", "mode", "online", "round")) in sampled}
    if {i for i in identities if i[1] in sampled} != expected:
        raise ValueError("采样任务缺失或重复序号超出项目配置；请用prepare重新生成并保留全部任务")
    result_groups = list(groups.values())
    for group in result_groups:
        group["round"] = int(group["round"])
        group["mention_rate"] = fraction(group["mention_yes"], group["mention_no"])
        group["recommendation_rate"] = fraction(group["recommendation_yes"], group["recommendation_no"]) if group["intent"] == "推荐" else None
        group["citation_rate"] = group["citation_supported_samples"] / group["citation_known_samples"] if group["citation_known_samples"] else None
    counts = {k: sum(g[k] for g in result_groups) for k in ["planned", "completed", "failed", "pending_review", "uncollected", "valid", "invalid_conditions", "condition_unknown"]}
    scoped_citations = [c for c in citations if c["sample_id"] in scoped_sample_ids]
    counts.update(questions=len({s["question_id"] for s in samples if s["sample_id"] in scoped_sample_ids}), citations=len(scoped_citations),
                  visible_sources=sum(bool(text(c["标题"]) or text(c["网站或媒体"])) for c in scoped_citations),
                  pending_source_verification=sum(c["核验状态"] == "待核验" for c in scoped_citations), verified_supporting_citations=verified)
    sampled_contexts = [dict(platform=c[0], mode=c[1], online=c[2], round=int(c[3])) for c in sorted(sampled)]
    collected_dates = sorted({text(s["采集时间"])[:10] for s in samples if s["sample_id"] in scoped_sample_ids and s["采集时间"]})
    report_scope = {"platforms": sorted({c["platform"] for c in sampled_contexts}), "contexts": sampled_contexts,
                    "report_date": date.today().isoformat(), "round_date": collected_dates[0] if len(collected_dates) == 1 else None,
                    "collected_dates": collected_dates, "metadata_note": project.get("collection_convention")}
    return {"schema_version": 1, "project": project, "groups": result_groups, "counts": counts, "samples": samples,
            "sampled_contexts": sampled_contexts, "report_scope": report_scope, "citations": citations, "evidence": evidence, "issues": issues,
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
    if analysis.get("project", {}).get("project_id") != project["project_id"]:
        raise ValueError("分析文件与项目ID不一致")
    project = dict(project, contexts=analysis.get("project", {}).get("contexts", project.get("contexts", [])))
    validate_project(project)
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
        scope = analysis.get("report_scope", {})
        if scope:
            notes = [["本轮采样范围", "、".join(scope.get("platforms", []))], ["采样日期", scope.get("round_date") or "、".join(scope.get("collected_dates", []))], ["本轮约定", scope.get("metadata_note")]]
            for label, value in notes:
                if value:
                    row = wb["说明"].max_row + 1
                    for col, item in enumerate([label, value], 1):
                        cell = wb["说明"].cell(row, col, item)
                        cell.data_type = "s"
                        cell._style = copy(wb["说明"].cell(2, col)._style)
                    wb["说明"].row_dimensions[row].height = 40
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
    p.add_argument("--out")
    p.add_argument("--out-dir")
    p = sub.add_parser("normalize", aliases=["import-collection"])
    p.add_argument("--input", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--context", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--base")
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
            write_json(prepare(read_json(args.project), args.out, args.out_dir))
        elif args.command in {"normalize", "import-collection"}:
            write_json(normalize_collection(args.input, read_json(args.project), args.context, args.out, args.base))
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
