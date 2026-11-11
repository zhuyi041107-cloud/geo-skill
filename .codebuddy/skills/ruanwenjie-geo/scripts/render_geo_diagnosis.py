"""Render a GEO client report from a customer-only JSON config.

Visuals are retained from the approved, text-free reference. This renderer
does not read AI answers or an evidence ledger. Static checks do not certify
facts or client meaning; review the final PDF independently.
"""
import argparse
import html
import io
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "geo-diagnosis-template"
WIDTH, HEIGHT = 1200, 675
COLORS = {"green": "#009875", "ink": "#18343d", "muted": "#6a7c82",
          "amber": "#9a682c", "blue": "#386882", "white": "#ffffff",
          "pale": "#b1c8cc", "mint": "#70ddbf"}
PLATFORMS = {"doubao", "qwen", "deepseek"}
ICON_NAMES = {"豆包":"doubao", "通义千问":"qwen", "千问":"qwen", "DeepSeek":"deepseek"}
LAYOUTS = {"cover": 0, "cards3": 1, "table-status": 2, "table3": 4,
           "checklist": 5, "scenes4": 6, "actions3": 8,
           "customer-items3": 9, "summary4": 11}
PROCESS = json.loads((ROOT / "assets" / "client-report-process-patterns.json").read_text(encoding="utf-8"))
PLACEHOLDERS = [r"\{\{", r"\}\}", r"\$\{", r"TODO", r"待填写", r"占位",
                r"示例客户", r"XX公司", r"<[^>]+>"]


def strings(value, path="config"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(v, path + "." + k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from strings(v, f"{path}[{i}]")


def schema_errors(value, schema, path="config"):
    """Validate the structural keywords used by the bundled schema, offline."""
    if "oneOf" in schema:
        branches = schema["oneOf"]
        results = [schema_errors(value, branch, path) for branch in branches]
        if sum(not result for result in results) == 1:
            return []
        if isinstance(value, dict):
            selected = [result for branch, result in zip(branches, results)
                        if branch.get("properties", {}).get("layout", {}).get("const") == value.get("layout")
                        and "layout" in value]
            if len(selected) == 1:
                return selected[0]
        return [path + ": does not match exactly one declared structure"]
    types = {"object": dict, "array": list, "string": str, "boolean": bool}
    kind = schema.get("type")
    if kind in types and not isinstance(value, types[kind]):
        return [path + ": must be " + kind]
    errors = []
    if "const" in schema and value != schema["const"]:
        errors.append(path + ": unexpected constant")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(path + ": unsupported value")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(path + "." + key + ": required")
        if schema.get("additionalProperties") is False:
            for key in value.keys() - properties.keys():
                errors.append(path + "." + key + ": undeclared field")
        for key, child in properties.items():
            if key in value:
                errors.extend(schema_errors(value[key], child, path + "." + key))
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            errors.append(path + ": wrong item count")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            errors.append(path + ": duplicate items")
        for i, child in enumerate(value):
            errors.extend(schema_errors(child, schema.get("items", {}), f"{path}[{i}]"))
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(path + ": text is too short")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(path + ": invalid text format")
    return errors


DIAGNOSIS_TITLES = ["GEO品牌诊断", "品牌在AI中的认知现状", "同行AI认知对比", "品牌优势与已有基础", "信息冲突汇总", "重点业务场景布局", "内容建设与执行分工", "推进计划与阶段复核"]
DIAGNOSIS_LAYOUTS = ["cover", "cards3", "cards3", "table3", "checklist", "scenes4", "actions3", "summary4"]
EXECUTION_TITLES = ["GEO落地执行方案", "品牌印象与目标标签", "GEO执行思路", "内容建设规划", "媒体发布规划", "阶段目标划分", "执行分工与贵司配合", "阶段复测与优化", "费用方案"]
EXECUTION_LAYOUTS = ["cover", "cards3", "steps4", "content-plan", "media-plan", "stages3", "customer-items3", "cards3", "quotes"]


def validate_report(report):
    schema = json.loads((ROOT / "references/customer-report.schema.json").read_text(encoding="utf-8"))
    errors = schema_errors(report, schema)
    if errors:
        return errors
    try:
        date.fromisoformat(report["customer"]["date"])
    except ValueError:
        errors.append("customer.date must be YYYY-MM-DD")
    for kind, titles in [("diagnosis", DIAGNOSIS_TITLES), ("execution", EXECUTION_TITLES)]:
        if kind not in report:
            continue
        pages = report[kind]["pages"]
        for i, (page, title) in enumerate(zip(pages, titles)):
            if page["title"] != title:
                errors.append(f"{kind}.pages[{i}].title must be {title}")
            layouts = DIAGNOSIS_LAYOUTS if kind == "diagnosis" else EXECUTION_LAYOUTS
            if page["layout"] != layouts[i]:
                errors.append(f"{kind}.pages[{i}].layout must be {layouts[i]}")
    if not any(kind in report for kind in ("diagnosis", "execution")):
        errors.append("report requires diagnosis or execution")
    for path, value in strings(report):
        if not value.strip():
            errors.append(path + ": text must not be blank")
        if path.endswith((".layout", ".color", ".platform")) or "observed_platforms" in path:
            continue
        for pattern in PROCESS + PLACEHOLDERS + [r"(?<![A-Za-z0-9_])(?:Q|C|P)\d{3,}(?![A-Za-z0-9_])", r"[A-Za-z]:[\\/]", r"/(?:Users|home|opt)/", r"SKILL\.md"]:
            if re.search(pattern, value, re.I):
                errors.append(path + ": prohibited internal/placeholder expression " + pattern)
        if re.search(r"https?://", value):
            errors.append(path + ": source URLs belong in the internal record")
    return errors


def validate(config, kind="diagnosis"):
    if not isinstance(config,dict) or set(config)-{"customer","purpose","pages"}:
        return ["renderer accepts only customer/purpose/pages"]
    return validate_report({"schema_version": "2.0", "customer": config.get("customer"),
                            "purpose": config.get("purpose"), kind: {"pages": config.get("pages")}})


def render(config, out, kind="diagnosis", png_scale=1.15, pdf_name=None):
    import fitz
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor
    errors = validate(config, kind)
    if errors:
        raise ValueError("; ".join(errors))
    out.mkdir(parents=True, exist_ok=True)
    font = ASSETS / "font.ttf"
    pdfmetrics.registerFont(TTFont("GEO", str(font)))
    report_name = "GEO 品牌诊断" if kind == "diagnosis" else "GEO 落地执行方案"
    customer = config["customer"]
    pages = config["pages"]
    buf = io.BytesIO(); cv = canvas.Canvas(buf, pagesize=(WIDTH, HEIGHT))
    logs = []
    def text(s, x, y, w, size=18, lead=None, h=80, color="ink", align=0):
        st = ParagraphStyle("p", fontName="GEO", fontSize=size, leading=lead or size*1.45,
                            textColor=HexColor(COLORS.get(color, color)), wordWrap="CJK", alignment=align)
        p = Paragraph(html.escape(s).replace("\n", "<br/>"), st)
        _, height = p.wrap(w, 1000)
        if height > h + .1:
            raise ValueError(f"Page {cv.getPageNumber()} overflow {height:.1f}>{h}: {s}")
        p.drawOn(cv, x, HEIGHT-y-height)
        logs.append({"page": cv.getPageNumber(), "text": s, "rect": [x,y,x+w,y+height], "font": size})
    def icon(name, x, y, w=28, h=26):
        name=ICON_NAMES.get(name,name)
        if name in PLATFORMS:
            cv.drawImage(str(ASSETS / (name+".png")), x, HEIGHT-y-h, width=w, height=h, mask="auto")
        else:
            text(name,x,y,w,10,12,h)
    def box(x, y, w, h, color):
        cv.setFillColor(HexColor(color)); cv.rect(x, HEIGHT-y-h, w, h, fill=1, stroke=0)
    def roundbox(x,y,w,h,color,radius=10):
        cv.setFillColor(HexColor(color));cv.roundRect(x,HEIGHT-y-h,w,h,radius,fill=1,stroke=0)
    def platforms(names, x, y, w, size=14, color="ink"):
        for n, name in enumerate(names):
            if ICON_NAMES.get(name,name) in PLATFORMS:
                icon(name, x + n*w/len(names), y, 25, 24)
            else:
                text(name, x+n*w/len(names), y, w/len(names)-5, size, size*1.2, 40,color)
    def footer(i, dark=False):
        col = "pale" if dark else "muted"
        text("软文街 / " + report_name,44,647,360,11,14,18,col)
        text(customer["brand"]+" · "+customer["date"].replace("-","."),420,647,360,11,14,18,col,1)
        text(f"{i:02d} / {len(pages):02d}",1086,647,70,11,14,18,col,2)
    def frame(page, i):
        if kind == "execution":
            numeral=["一","二","三","四","五","六","七","八"][i-2]
            text(numeral+"、"+page["title"],60,32,930,30,42,48,"#13263d")
            if page.get("subtitle"):
                text(page["subtitle"],60,87,1090,15,21,28,"muted")
            footer(i)
            platforms(customer["observed_platforms"],1030,38,120,13)
            text(page["banner"]["label"],62,588,100,14,20,28,"white")
            text(page["banner"]["text"],175,588,958,14,20,28,"white")
            return
        text(page["title"],44,52,920,31,42,48,"green")
        footer(i)
        box(987,36,169,72,"#f5f7f7")
        platforms(customer["observed_platforms"], 990, 53, 165, 14)
        text(page["banner"]["label"],64,582,120,17,24,28,"white")
        text(page["banner"]["text"],202,582,930,17,24,28,"white")
    def table(headers, rows, xs, ws, row_count, status=False, emphasis=False):
        # Defaults retain the exact original table geometry. Shorter tables
        # retain the component footprint and redistribute rows evenly.
        for s,x,w in zip(headers,xs,ws):text(s,x,161 if not status else 134,w,15,21,26,"muted")
        if status:
            ys=[177+75*i for i in range(row_count)] if row_count==5 else [177+375/row_count*i for i in range(row_count)]
            if row_count!=5:
                box(44,165,1112,375,"#ffffff")
                for i,y in enumerate(ys):
                    if i%2:box(44,y-12,1112,375/row_count,"#f5f8f8")
            for row,y in zip(rows,ys):
                binding = row.get("platform", [])
                binding = [binding] if isinstance(binding, str) else binding
                text(row["subject"],66,y+3,(184 if len(binding)>2 else 210) if binding else 245,18,26,min(65,375/row_count-12))
                icon_x = 260 if len(binding)>2 else 284
                for n,name in enumerate(binding):icon(name,icon_x+24*n,y+4,21,20)
                text(row["status"],339,y+12,125,16,23,30,row.get("color","blue"),1)
                text(row["diagnosis"],498,y,310,16,23,min(65,375/row_count-12))
                text(row["recommendation"],838,y,294,16,23,min(65,375/row_count-12),"muted")
        else:
            is_four = row_count==4
            ys=[209+(85 if is_four else 68)*i for i in range(row_count)] if row_count in [4,5] else [195+340/row_count*i for i in range(row_count)]
            if row_count not in [4,5]:
                box(44,194,1112,346,"#ffffff")
                for i,y in enumerate(ys):
                    if i%2:box(44,y-15,1112,340/row_count,"#f5f8f8")
            for row,y in zip(rows,ys):
                for j,(s,x,w) in enumerate(zip(row,xs,ws)):
                    text(s,x,y,w,17 if is_four else 16,24,min(76 if is_four else 65,340/row_count-4),"ink" if j<2 else "muted")
    source_indices=[]
    for idx,page in enumerate(pages,1):
        layout=page["layout"];source=idx-1 if kind=="execution" else LAYOUTS.get(layout, 11)
        if layout=="table3" and len(page["rows"])==4:source=3
        source_indices.append(source)
        if layout=="cover":
            if kind == "execution":
                platforms(customer["observed_platforms"],1030,38,120,13,"pale")
                text(customer["brand"],45,204,650,34,45,50,"white")
                text(page["title"],44,292,710,57,75,83,"white")
                text(page["headline"],44,421,700,24,33,40,"mint")
                text(page["scope"],45,481,700,17,24,30,"pale")
                text("方案目标",64,582,100,15,22,28,"white")
                text(page["diagnosis"],182,582,947,16,23,30,"white")
                footer(idx,True)
                cv.showPage()
                continue
            text(customer["brand"],48,162,650,34,45,50,"white")
            text(customer["company"],49,212,650,15,22,26,"pale")
            text(page["title"],44,272,710,66,86,95,"white")
            text(page["headline"],49,401,680,29,40,45,"mint")
            text(page["scope"],49,461,650,19,28,32,"pale")
            platforms(customer["observed_platforms"], 997, 65, 159, 14,"pale")
            meta=[("品牌主体",customer["company"]),("主营业务",page["scope"]),("方案目标",config["purpose"]),("报告日期",customer["date"])]
            for i,(k,v) in enumerate(meta):
                y=175+i*90;text(k,790,y,350,13,19,22,"pale")
                text(v,790,y+23,350,18,26,55,"white")
            text(page["diagnosis"],65,572,1060,19,27,31,"white");footer(idx,True)
        else:
            frame(page,idx)
            if layout=="cards3":
                for i,item in enumerate(page["items"]):
                    if kind == "execution":
                        x=66+377*i
                        text(item["label"],x,154,314,13,19,25,"green")
                        text(item["heading"],x,193,314,23,32,68)
                        text(item["body"],x,259,314,16,23,152)
                        text(item["footer"],x,477,314,14,20,45,"muted")
                        continue
                    x=70+377*i;text(item["label"],x,179,306,16,23,28,"muted")
                    text(item["heading"],x,224,306,27,37,82,item.get("color","green"))
                    text(item["body"],x,314,306,18,28,118)
                    text(item["footer"],x,448,306,17,25,79,"muted")
                    if item.get("platform"):icon(item["platform"],x+260,176,25,24)
            elif layout=="table-status":
                table(page["headers"],page["rows"],[66,339,498,838],[245,125,310,294],len(page["rows"]),True)
            elif layout=="table3":
                if kind == "execution":
                    box(44, 149, 1112, 391, "#ffffff")
                table(page["headers"],page["rows"],[62,306 if len(page["rows"])==4 else 297,740],[220,405,392],len(page["rows"]))
                if page.get("platform"):icon(page["platform"],1105,124,24,23)
            elif layout=="checklist":
                text(page["left_heading"],66,166,690,18,26,32,"amber");text(page["right_heading"],812,166,300,18,26,32,"green")
                for i,row in enumerate(page["rows"]):
                    y=210+63*i;text(row["topic"],66,y,96,17,25,52);text(row["observation_a"],174,y,270,16,23,52)
                    text(row["observation_b"],469,y,270,16,23,52);text(row["request"],812,y,310,17,25,52)
            elif layout=="scenes4":
                # Hide unused slots. The fill compensates PDF RGB rounding to match the asset.
                for unused in range(len(page["items"]), 4):
                    box(393, 149+100*unused, 764, 88, "#f6f8f8")
                f=page["focus"]
                for key,x,y,w,sz,h,col in [("label",70,176,270,16,30,"green"),("heading",70,222,280,31,82,"ink"),("scope",70,286,285,18,35,"green"),("body",70,337,285,19,96,"ink"),("footer",70,445,285,17,65,"muted")]:
                    text(f[key],x,y,w,sz,None,h,col)
                for i,item in enumerate(page["items"]):
                    y=163+100*i;text(item["label"],427,y+8,93,15,21,26,"green" if i<2 else "muted",1)
                    text(item["title"],552,y,560,21,30,36);text(item["description"],552,y+34,560,16,23,50,"muted")
            elif layout=="actions3":
                for i,item in enumerate(page["items"]):
                    x=68+377*i;col=item.get("color",["green","blue","amber"][i])
                    text(item["number"],x,171,65,42,56,62,col);text(item["title"],x+70,180,230,24,32,38)
                    text(item["subtitle"],x+70,214,230,18,26,33,"muted");text(item["rationale"],x,253,306,15,22,42,"muted")
                    for label,key,y,h in [("实施内容","action",308,64),("交付内容","deliverable",388,50),("观察目标","review",458,55)]:
                        text(label,x,y,306,14,20,24,col);text(item[key],x,y+25,306,16,23,h)
            elif layout=="customer-items3":
                if kind == "execution":
                    roundbox(44,136,1112,399,"#ffffff")
                    for j in range(len(page["rows"])):
                        if j%2:box(44,175+j*360/len(page["rows"]),1112,360/len(page["rows"]),"#f8fafc")
                    for s,x,w in zip(page["headers"],[58,258,712],[180,434,422]):text(s,x,147,w,13,19,26,"muted")
                    for j,row in enumerate(page["rows"]):
                        for cell,x,w in zip(row,[58,258,712],[180,434,422]):text(cell,x,186+j*340/len(page["rows"]),w,15,22,61)
                    cv.showPage()
                    continue
                for s,x,w in zip(page["headers"],[62,297,709],[210,380,420]):text(s,x,161,w,15,21,26,"muted")
                for i,row in enumerate(page["rows"]):
                    for j,(s,x,w) in enumerate(zip(row,[62,297,709],[210,380,420])):text(s,x,209+78*i,w,17,24,62,"ink" if j<2 else "muted")
                if page.get("note"):text(page["note"],62,533,1070,14,20,28,"muted")
            elif layout=="summary4":
                slots = [(43,149), (609,149), (43,329), (609,329)]
                for x, y in slots[len(page["items"]):]:
                    box(x, y, 548, 160, "#f6f8f8")
                for item,(x,y) in zip(page["items"],[(68,170),(634,170),(68,350),(634,350)]):
                    text(item["title"],x+16,y,480,22,31,38,item.get("color","green"));text(item["body"],x,y+43,490,18,27,95)
                if page.get("note"):text(page["note"],48,517,1080,14,21,28,"muted")
            elif layout=="steps4":
                for i,item in enumerate(page["items"]):
                    x=64+i*283
                    text(f"{i+1:02d}",x,165,220,36,46,51,"green")
                    text(item["title"],x,225,225,21,30,65)
                    text(item["body"],x,289,225,16,23,150)
                    text(item["footer"],x,472,225,13,19,45,"muted")
            elif layout=="content-plan":
                roundbox(44,130,1112,431,"#ffffff")
                rows=page["rows"];height=390/len(rows)
                for j,row in enumerate(rows):
                    if j%2:box(44,169+j*height,1112,height,"#f8fafc")
                    for cell,x,w in zip(row,[58,238,338,918],[165,85,560,220]):text(cell,x,178+j*height,w,14,21,height-10)
                for cell,x,w in zip(page["headers"],[58,238,338,918],[165,85,560,220]):text(cell,x,141,w,13,19,25,"muted")
            elif layout=="media-plan":
                roundbox(44,141,1112,375,"#ffffff")
                rows=page["rows"];height=335/len(rows)
                for j,row in enumerate(rows):
                    if j%2:box(44,180+j*height,1112,height,"#f8fafc")
                    for cell,x,w in zip(row,[58,258,408,878],[180,130,450,258]):text(cell,x,191+j*height,w,15,22,height-20)
                for cell,x,w in zip(page["headers"],[58,258,408,878],[180,130,450,258]):text(cell,x,152,w,13,19,26,"muted")
                if page.get("note"):text(page["note"],64,535,1060,14,20,25,"muted")
            elif layout=="stages3":
                count=len(page["items"]);stride=1131/count;width=stride-19;inner=width-40
                if count!=3:
                    box(44,136,1112,414,"#f4f6f9")
                    for j in range(count):roundbox(44+j*stride,136,width,414,"#ffffff")
                for i,item in enumerate(page["items"]):
                    x=44+i*stride
                    text(item["period"],x+20,160,inner,13,19,44,"green")
                    text(item["title"],x+20,211,inner,22,31,65)
                    text(item["counts"],x+20,285,inner,16,23,28,"blue")
                    text(item["amount"],x+20,317,inner,16,22,27,"blue")
                    text("主要工作",x+20,356,inner,14,20,24,"muted")
                    text(item["work"],x+20,384,inner,15,21,66)
                    text("客户配合",x+20,462,inner,14,20,24,"muted")
                    text(item["cooperation"],x+20,490,inner,14,20,43)
            elif layout=="quotes":
                cards=page["items"]
                for i,item in enumerate(cards):
                    x=44+566*i;col="green" if i==0 else "#4267ff"
                    box(x+21,354,503,128,"#ffffff")
                    for line_y in (356,440,462):
                        cv.setStrokeColor(HexColor("#e6eaf0"));cv.setLineWidth(.6)
                        cv.line(x+21,HEIGHT-line_y,x+524,HEIGHT-line_y)
                    text(f"方案{['一','二'][i]}",x+21,150,120,13,18,24,"muted")
                    text(item["tag"],x+390,149,130,12,17,24,col)
                    text(item["name"],x+21,187,505,22,30,36)
                    text(item["total"],x+21,225,505,35,45,52,col)
                    text(item["scale"],x+21,273,505,13,19,25,"muted")
                    text(item["description"],x+21,310,505,14,20,40)
                    for label,key,y,h in [("媒体配置","media",365,70),("配置重点","focus",443,18),("适用考虑","suitability",465,18)]:
                        text(label,x+21,y,83,12,17,20,"muted")
                        text(item[key],x+110,y,414,12,14,h)
                if len(cards)==1:
                    box(608,130,550,356,"#f4f6f9")
                    text("执行前确认事项",632,174,450,25,35,45,"green")
                    text("确认具体媒体资源与发布档期，核对稿件公开范围及客户授权；按本期约定落实服务权益。",632,240,450,19,29,205)
                text("费用范围",64,518,100,14,20,26,"green")
                text(page["scope"],190,512,940,15,22,44,"muted")
        cv.showPage()
    cv.save()
    background = ROOT/"assets/geo-execution-template/backgrounds.pdf" if kind=="execution" else ASSETS/"backgrounds.pdf"
    reference=fitz.open(background)
    if reference.get_toc() or any(page.get_text().strip() or page.get_links() for page in reference):
        raise ValueError("Visual backgrounds must be text-free and link-free")
    overlay=fitz.open(stream=buf.getvalue(),filetype="pdf");doc=fitz.open()
    for i,source in enumerate(source_indices):
        doc.insert_pdf(reference,from_page=source,to_page=source)
        doc[-1].show_pdf_page(doc[-1].rect,overlay,i)
    doc.set_metadata({"title":customer["brand"]+"｜"+report_name, "author":"软文街"})
    doc.set_toc([[1,page["title"],i+1] for i,page in enumerate(pages)])
    basename = "GEO诊断报告" if kind == "diagnosis" else "品牌传播与GEO执行方案"
    pdf = out / (pdf_name or basename + ".pdf")
    if pdf.exists():
        raise FileExistsError("输出已存在，拒绝覆盖：" + str(pdf))
    doc.save(pdf,garbage=4,deflate=True)
    rendered=[]
    for i,page in enumerate(doc):
        png=page.get_pixmap(matrix=fitz.Matrix(png_scale,png_scale)).tobytes("png")
        name=out/f"{kind}_page_{i+1:02d}.png"
        name.write_bytes(png);rendered.append(str(name))
    audit={"schema_version":"2.0","kind":kind,"page_count":len(doc),"blocks":logs,"rendered_pages":rendered,"pdf":str(pdf)}
    audit_path=out/(kind+"_layout_audit.json")
    audit_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    doc.close();reference.close();overlay.close()
    return {"pdf":str(pdf),"pages":len(pages),"audit":str(audit_path),"rendered_pages":rendered}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config",type=Path)
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--kind",choices=["diagnosis","execution"],default="diagnosis")
    parser.add_argument("--validate-only",action="store_true")
    args=parser.parse_args()
    config=json.loads(args.config.read_text(encoding="utf-8-sig"))
    errors=validate(config,args.kind)
    if errors:
        raise ValueError("; ".join(errors))
    if args.validate_only:
        print(json.dumps({"valid":True,"semantic_review_required":True}));return
    if not args.output_dir:parser.error("--output-dir required")
    print(json.dumps(render(config,args.output_dir,args.kind),ensure_ascii=False))


if __name__=="__main__":main()
