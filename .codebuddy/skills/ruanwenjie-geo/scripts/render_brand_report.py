"""Render branded client modules with automatic pagination, offline.

Business conclusions, action links and quoted amounts are validated upstream.
This module validates and lays out only the customer-visible document.
"""
from __future__ import annotations

import html
import io
import json
from datetime import date
from pathlib import Path
import re

import render_geo_diagnosis as legacy

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1200, 675
DEFAULTS = {"background": "#F6F7F9", "text": "#172633"}
FONT = "GEOBrand"


def _luminance(color):
    values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
    return sum(v * weight for v, weight in zip(values, (.2126, .7152, .0722)))


def _contrast(first, second):
    a, b = sorted((_luminance(first), _luminance(second)))
    return (b + .05) / (a + .05)


def _mix(first, second, ratio):
    return "#" + "".join(f"{round(int(first[i:i+2],16)*(1-ratio)+int(second[i:i+2],16)*ratio):02X}" for i in (1, 3, 5))


def _reverse(color):
    return max(("#FFFFFF", "#101820"), key=lambda choice: _contrast(choice, color))


def validate_report(report, rendered=False):
    schema = json.loads((ROOT / "references/brand-report.schema.json").read_text(encoding="utf-8"))
    errors = legacy.schema_errors(report, schema)
    if errors:
        return errors
    try:
        date.fromisoformat(report["customer"]["date"])
    except ValueError:
        errors.append("customer.date must be YYYY-MM-DD")
    theme = {**DEFAULTS, **report["theme"]}
    if _contrast(theme["background"], theme["text"]) < 4.5:
        errors.append("theme.text and theme.background need readable contrast")
    if not any(kind in report for kind in ("diagnosis", "execution")):
        errors.append("report requires diagnosis or execution")
    for kind in ("diagnosis", "execution"):
        for index, page in enumerate(report.get(kind, {}).get("pages", [])):
            if rendered and ("source" in page or "ids" in page):
                errors.append(f"{kind}.pages[{index}]: unresolved internal source")
            if "rows" in page and any(len(row) != len(page["headers"]) for row in page["rows"]):
                errors.append(f"{kind}.pages[{index}]: row/header column count differs")
    for path, value in legacy.strings(report):
        if path.startswith("config.theme.") or path.endswith((".layout", ".source", ".schema_version")) or ".ids[" in path:
            continue
        if not value.strip():
            errors.append(path + ": text must not be blank")
            continue
        for pattern in legacy.PROCESS + legacy.PLACEHOLDERS + [r"[A-Za-z]:[\\/]", r"/(?:Users|home|opt)/", r"SKILL\.md", r"https?://"]:
            if re.search(pattern, value, re.I):
                errors.append(path + ": internal/placeholder content is not client copy")
                break
    return errors


def validate(config, kind="diagnosis", rendered=True):
    if not isinstance(config, dict) or set(config) - {"customer", "theme", "purpose", "pages"}:
        return ["renderer accepts only customer/theme/purpose/pages"]
    if kind not in {"diagnosis", "execution"}:
        return ["kind must be diagnosis or execution"]
    report = {"schema_version": "3.0", "customer": config.get("customer"), "theme": config.get("theme"),
              kind: {"pages": config.get("pages")}}
    if "purpose" in config:
        report["purpose"] = config["purpose"]
    return validate_report(report, rendered=rendered)


def _logo(theme, asset_root):
    value = theme.get("logo")
    if value is None:
        return None
    if "://" in value:
        raise ValueError("品牌Logo仅接受本地文件，不读取网络资源")
    root = Path(asset_root or ROOT).resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {".png", ".jpg", ".jpeg"} or not path.is_file():
        raise ValueError("品牌Logo须为asset_root内的本地PNG/JPG文件")
    return path


def render(config, out, kind="diagnosis", png_scale=1.15, pdf_name=None, asset_root=None):
    import pymupdf as fitz
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, NextPageTemplate, PageBreak, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.utils import ImageReader

    errors = validate(config, kind)
    if errors:
        raise ValueError("; ".join(errors))
    if not .1 <= png_scale <= 3:
        raise ValueError("png_scale须在0.1至3之间")
    out = Path(out)
    basename = "GEO诊断报告" if kind == "diagnosis" else "品牌传播与GEO执行方案"
    filename = pdf_name or basename + ".pdf"
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".pdf":
        raise ValueError("PDF名称须为当前输出目录下的.pdf文件名")
    pdf_path = out / filename
    audit_path = out / (kind + "_layout_audit.json")
    if pdf_path.exists() or audit_path.exists() or list(out.glob(kind + "_page_*.png")):
        raise FileExistsError("输出已存在，拒绝覆盖，请使用新的版本目录")
    theme = {**DEFAULTS, **config["theme"]}
    logo = _logo(theme, asset_root)
    customer = config["customer"]
    pdfmetrics.registerFont(TTFont(FONT, str(ROOT / "assets/geo-diagnosis-template/font.ttf")))
    primary, accent, background, ink = (theme[key] for key in ("primary", "accent", "background", "text"))
    editorial = theme["cover_style"] == "editorial"
    reverse = _reverse(primary)
    heading = primary if _contrast(primary, background) >= 4.5 else ink
    muted = _mix(ink, background, .18)
    panel = _mix(background, ink, .035)
    border = _mix(background, ink, .16)
    margin = 60 if editorial else 50
    usable = WIDTH - 2 * margin
    report_label = "GEO品牌诊断" if kind == "diagnosis" else "品牌传播与GEO执行方案"

    def style(name, size=18, leading=28, color=ink, **options):
        return ParagraphStyle(name, fontName=FONT, fontSize=size, leading=leading, textColor=HexColor(color), wordWrap="CJK", **options)

    body_style = style("body")
    title_style = style("title", 29, 42, heading, keepWithNext=True, spaceAfter=14)
    lead_style = style("lead", 17, 26, muted, spaceAfter=18)
    table_style = style("cell", 16, 24)
    header_style = style("header", 15, 23, reverse)
    item_title = style("itemtitle", 21, 31, heading, spaceAfter=8)

    def para(value, chosen=body_style):
        return Paragraph(html.escape(str(value)).replace("\n", "<br/>"), chosen)

    def draw_logo(canvas, x, y, max_width, max_height):
        if logo:
            reader = ImageReader(str(logo))
            width, height = reader.getSize()
            ratio = min(max_width / width, max_height / height)
            canvas.drawImage(reader, x, y, width=width * ratio, height=height * ratio, mask="auto")

    def footer(canvas, doc, dark=False):
        canvas.setFillColor(HexColor(reverse if dark else muted))
        canvas.setFont(FONT, 11)
        canvas.drawString(margin, 23, "软文街 · " + report_label)
        canvas.drawRightString(WIDTH - margin, 23, f"{customer['date']}     {doc.page:02d}")

    def on_cover(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor(primary if editorial else background))
        canvas.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
        if editorial:
            canvas.setFillColor(HexColor(accent))
            canvas.rect(0, 0, 14, HEIGHT, fill=1, stroke=0)
            canvas.setStrokeColor(HexColor(_mix(primary, reverse, .2)))
            canvas.setLineWidth(1)
            canvas.circle(WIDTH + 35, 100, 360, stroke=1, fill=0)
            canvas.circle(WIDTH + 35, 100, 300, stroke=1, fill=0)
        else:
            canvas.setFillColor(HexColor(primary))
            canvas.rect(0, 0, 20, HEIGHT, fill=1, stroke=0)
            canvas.rect(WIDTH - 300, 0, 300, 18, fill=1, stroke=0)
            canvas.setStrokeColor(HexColor(border))
            canvas.setLineWidth(.4)
            for x in range(800, 1200, 40):
                canvas.line(x, 50, x, HEIGHT - 100)
            for y in range(70, 600, 40):
                canvas.line(800, y, WIDTH - 30, y)
        draw_logo(canvas, WIDTH - margin - 180, HEIGHT - 82, 180, 46)
        footer(canvas, doc, editorial)
        canvas.restoreState()

    def on_body(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor(background))
        canvas.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
        canvas.setFillColor(HexColor(primary))
        if editorial:
            canvas.rect(0, HEIGHT - 9, WIDTH, 9, fill=1, stroke=0)
        else:
            canvas.rect(0, 0, 12, HEIGHT, fill=1, stroke=0)
        canvas.setFillColor(HexColor(accent))
        canvas.rect(WIDTH - margin - 19, HEIGHT - 54, 19, 5, fill=1, stroke=0)
        canvas.setFillColor(HexColor(heading))
        canvas.setFont(FONT, 12)
        canvas.drawString(margin, HEIGHT - 45, customer["brand"])
        if customer.get("observed_platforms"):
            canvas.setFont(FONT, 10)
            canvas.setFillColor(HexColor(muted))
            canvas.drawString(margin, HEIGHT - 64, " / ".join(customer["observed_platforms"]))
        canvas.setStrokeColor(HexColor(border))
        canvas.line(margin, 43, WIDTH - margin, 43)
        draw_logo(canvas, WIDTH - margin - 150, HEIGHT - 78, 150, 30)
        footer(canvas, doc)
        canvas.restoreState()

    frame = lambda name: Frame(margin, 56, usable, HEIGHT - 132, id=name, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    templates = {"cover": PageTemplate(id="cover", frames=[frame("cover")], onPage=on_cover),
                 "body": PageTemplate(id="body", frames=[frame("body")], onPage=on_body)}
    first = "cover" if config["pages"][0]["layout"] == "cover" else "body"
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=(WIDTH, HEIGHT), title=customer["brand"] + "｜" + report_label, author="软文街")
    doc.addPageTemplates([templates[first], templates["body" if first == "cover" else "cover"]])
    story = []

    class WholeRowTable(Table):
        def split(self, availWidth, availHeight):
            # Keep ordinary rows intact; in-row fallback leaves short tails and repeated headers.
            parts = super().split(availWidth, availHeight)
            if parts:
                return parts
            repeated = self.repeatRows if isinstance(self.repeatRows, int) else len(self.repeatRows)
            if self._nrows <= repeated:
                return []
            header_height = sum(self._rowHeights[:repeated])
            if self._rowHeights[repeated] + header_height > HEIGHT - 132:
                # Split only oversized rows, including their repeated headers.
                return self._splitRows(availHeight, doInRowSplit=True)
            return []

    def component_table(rows, widths, header=False, padding=12):
        table = WholeRowTable(rows, colWidths=widths, repeatRows=1 if header else 0, splitByRow=1, splitInRow=0, hAlign="LEFT")
        commands = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14), ("TOPPADDING", (0, 0), (-1, -1), padding),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), padding), ("BACKGROUND", (0, 0), (-1, -1), HexColor(panel)),
                    ("LINEBELOW", (0, 0), (-1, -1), .5, HexColor(border))]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), HexColor(primary)),
                         ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(background), HexColor(panel)])]
        table.setStyle(TableStyle(commands))
        return table

    for index, module in enumerate(config["pages"]):
        layout = module["layout"]
        if index:
            story.extend([NextPageTemplate("cover" if layout == "cover" else "body"), PageBreak()])
        if layout == "cover":
            color = reverse if editorial else ink
            story.extend([Spacer(1, 42), para(customer["brand"], style("coverbrand", 23, 34, color)), Spacer(1, 10),
                          para(customer["company"], style("covercompany", 14, 23, color)), Spacer(1, 24),
                          para(module["title"], style("covertitle", 45, 62, color, spaceAfter=24))])
            if module.get("headline"):
                story.extend([para(module["headline"], style("coverheadline", 26, 39, color)), Spacer(1, 20)])
            if module.get("body"):
                story.extend([para(module["body"], style("coverbody", 19, 29, color)), Spacer(1, 16)])
            if config.get("purpose"):
                story.append(para(config["purpose"], style("coverpurpose", 17, 27, color)))
            continue
        story.append(para(module["title"], title_style))
        if module.get("lead"):
            story.append(para(module["lead"], lead_style))
        story.extend([HRFlowable(width=usable, thickness=2, color=HexColor(accent)), Spacer(1, 18)])
        if layout == "text":
            for value in module["paragraphs"]:
                story.extend([para(value), Spacer(1, 16)])
        elif layout in {"insights", "cards"}:
            columns = 2 if editorial or layout == "insights" else 3
            for start in range(0, len(module["items"]), columns):
                group = module["items"][start:start + columns]
                cells = []
                for item in group:
                    cell = [para(item["heading"], item_title), para(item["body"])]
                    for field, label in (("impact", "业务影响"), ("action", "应对重点")):
                        if item.get(field):
                            cell.extend([Spacer(1, 12), para(label, style("label", 13, 21, heading)), para(item[field])])
                    cells.append(cell)
                story.extend([component_table([cells], [usable / len(cells)] * len(cells)), Spacer(1, 16)])
        elif layout == "timeline":
            rows = [[para(item["period"], style("period", 16, 25, heading)),
                     [para(item["title"], item_title), para(item["body"])]] for item in module["items"]]
            story.append(component_table(rows, [usable * .22, usable * .78]))
        elif layout in {"table", "quotes"}:
            rows = [[para(value, header_style) for value in module["headers"]]]
            rows.extend([[para(value, table_style) for value in row] for row in module["rows"]])
            story.append(component_table(rows, [usable / len(module["headers"])] * len(module["headers"]), True, padding=8 if layout == "quotes" else 12))
        if module.get("note"):
            story.extend([Spacer(1, 14), para(module["note"], lead_style)])

    try:
        doc.build(story)
    except Exception as exc:
        raise ValueError("品牌报告排版失败，内容未截断或缩字；请调整模块：" + str(exc)) from exc
    document = fitz.open(stream=buffer.getvalue(), filetype="pdf")
    logs = []
    for number, page in enumerate(document, 1):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    rect = fitz.Rect(span["bbox"])
                    if rect.x0 < -.5 or rect.y0 < -.5 or rect.x1 > WIDTH + .5 or rect.y1 > HEIGHT + .5:
                        document.close()
                        raise ValueError(f"第{number}页实际文字边界溢出，拒绝交付")
                    logs.append({"page": number, "text": span["text"], "rect": list(rect), "font": span["size"]})
    out.mkdir(parents=True, exist_ok=True)
    with pdf_path.open("xb") as stream:
        stream.write(document.tobytes(garbage=4, deflate=True))
    rendered = []
    for number, page in enumerate(document, 1):
        path = out / f"{kind}_page_{number:02d}.png"
        page.get_pixmap(matrix=fitz.Matrix(png_scale, png_scale), alpha=False).save(path)
        rendered.append(str(path))
    audit = {"schema_version": "3.0", "kind": kind, "module_count": len(config["pages"]), "page_count": len(document),
             "theme": {key: value for key, value in theme.items() if key != "logo"}, "bounds_ok": True,
             "blocks": logs, "rendered_pages": rendered, "pdf": str(pdf_path)}
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    document.close()
    return {"pdf": str(pdf_path), "pages": len(rendered), "audit": str(audit_path), "rendered_pages": rendered}
