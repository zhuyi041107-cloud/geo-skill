"""Read local evidence and apply GPT judgments to a new internal workbook."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import openpyxl

import geo_data


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}


def evidence_bundle(internal_path):
    source = Path(internal_path).resolve(strict=True)
    analysis = geo_data.analyze(source)
    base = source.parent
    images = {}

    def include(raw, label):
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"{label}缺少截图路径")
        path = (base / raw.strip()).resolve()
        if not path.is_relative_to(base):
            raise ValueError(f"{label}截图路径超出内部工作簿所在目录")
        if not path.is_file():
            raise ValueError(f"{label}截图文件不存在：{path.name}")
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError(f"{label}截图格式不支持：{path.suffix}")
        if path in images:
            images[path]["label"] += "；" + label
        else:
            images[path] = {"label": label, "path": path}

    for sample in analysis["samples"]:
        for number, raw in enumerate(str(sample.get("回答证据路径") or "").splitlines(), 1):
            if raw.strip():
                include(raw, f"样本{sample['sample_id']}截图{number}")
    loose = analysis["project"].get("unlocated_screenshots", [])
    if not isinstance(loose, list):
        raise ValueError("未定位截图记录必须为列表")
    for number, item in enumerate(loose, 1):
        if not isinstance(item, dict):
            raise ValueError("未定位截图记录必须包含path")
        include(item.get("path"), f"未定位截图{number}（{item.get('original_location') or '问题行未确认'}）")
    return analysis, list(images.values())


def judged_copy(internal_path, judgments, out_path):
    source = Path(internal_path).resolve(strict=True)
    destination = Path(out_path).resolve()
    if destination == source or destination.exists():
        raise FileExistsError("判读结果须写入新的内部工作簿，拒绝覆盖已有文件")
    if destination.suffix.lower() != ".xlsx":
        raise ValueError("判读副本输出路径须为.xlsx")
    analysis = geo_data.analyze(source)
    expected = {
        row["sample_id"] for row in analysis["samples"]
        if row["采集状态"] == "已完成" and geo_data.text(row["回答全文"])
    }
    if not expected:
        raise ValueError("没有可判读的成功原始回答")
    if not isinstance(judgments, list):
        raise ValueError("GPT判读结果须为列表")
    by_id = {}
    for item in judgments:
        if not isinstance(item, dict) or set(item) != {"sample_id", "mention", "recommendation", "reason"}:
            raise ValueError("GPT判读项须包含sample_id、mention、recommendation、reason四字段")
        sample_id = item["sample_id"]
        if not isinstance(sample_id, str) or not sample_id.strip() or sample_id in by_id:
            raise ValueError("GPT判读sample_id缺失或重复")
        if any(not isinstance(item[key], str) or item[key] not in {"是", "否"} for key in ("mention", "recommendation")):
            raise ValueError("品牌提及与推荐判读须为是或否")
        if item["recommendation"] == "是" and item["mention"] != "是":
            raise ValueError("推荐品牌却未提及品牌，判读自相矛盾")
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ValueError("GPT判读须保留具体理由")
        by_id[sample_id] = item
    if set(by_id) != expected:
        raise ValueError("GPT判读须与成功原始回答的sample_id全集一对一，存在缺失或额外项")

    book = openpyxl.load_workbook(source)
    try:
        sheet = book["回答记录"]
        columns = {name: index + 1 for index, name in enumerate(geo_data.SAMPLE_HEADERS)}
        for row in sheet.iter_rows(min_row=2):
            item = by_id.get(row[0].value)
            if item is None:
                continue
            for header, key in (("品牌提及", "mention"), ("品牌推荐", "recommendation")):
                cell = sheet.cell(row[0].row, columns[header], item[key])
                cell.data_type = "s"
            note = sheet.cell(row[0].row, columns["备注"])
            original = geo_data.text(note.value)
            note.value = "\n".join(value for value in (original, "GPT判读：" + item["reason"].strip()) if value)
            note.data_type = "s"
            if len(note.value) > 32767:
                raise ValueError("判读理由与原备注合计超过Excel单元格长度")
        stream = BytesIO()
        book.save(stream)
    finally:
        book.close()
    raw = stream.getvalue()
    result = geo_data.analyze(BytesIO(raw))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(raw)
    return result
