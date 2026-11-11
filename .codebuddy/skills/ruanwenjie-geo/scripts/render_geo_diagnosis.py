"""Render a GEO client report from a customer-only JSON config.

Visuals are retained from the approved, text-free reference. This renderer
does not read AI answers or an evidence ledger. Static checks do not certify
facts or client meaning; review the final PDF independently.
"""
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


def schema_errors(value, schema, path="config", rendered=False):
    """Validate the structural keywords used by the bundled schema, offline."""
    if schema is False:
        return [path+": undeclared array item"]
    if schema is True:
        return []
    if "oneOf" in schema:
        branches = schema["oneOf"]
        results = [schema_errors(value, branch, path,rendered) for branch in branches]
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
            if rendered and child.get("x-render-required") and key not in value:
                errors.append(path+"."+key+": computed field required for rendering")
            if key in value:
                if child.get("readOnly") and not rendered:
                    errors.append(path+"."+key+": computed field; 不可手填")
                errors.extend(schema_errors(value[key], child, path + "." + key,rendered))
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            errors.append(path + ": wrong item count")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            errors.append(path + ": duplicate items")
        for i, child in enumerate(value):
            prefix=schema.get("prefixItems",[])
            child_schema=prefix[i] if i<len(prefix) else schema.get("items", {})
            errors.extend(schema_errors(child, child_schema, f"{path}[{i}]",rendered))
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(path + ": text is too short")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(path + ": invalid text format")
    return errors


DIAGNOSIS_TITLES = ["GEO品牌诊断", "品牌在AI中的认知现状", "同行AI认知对比", "品牌优势与已有基础", "信息冲突汇总", "重点业务场景布局", "内容建设与执行分工", "推进计划与阶段复核"]
DIAGNOSIS_LAYOUTS = ["cover", "cards3", "comparison3", "table3", "table4", "scenes4", "customer-items3", "summary4"]
EXECUTION_TITLES = ["GEO落地执行方案", "品牌印象与目标标签", "GEO执行思路", "内容建设规划", "媒体发布规划", "阶段目标划分", "执行分工与贵司配合", "阶段复测与优化", "费用方案"]
EXECUTION_LAYOUTS = ["cover", "cards3", "steps4-grid", "content-plan", "media-cards3", "stages3", "customer-items3", "review-table", "quotes"]


def validate_report(report, rendered=False):
    schema = json.loads((ROOT / "references/customer-report.schema.json").read_text(encoding="utf-8"))
    errors = schema_errors(report, schema,rendered=rendered)
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
            if page["layout"]=="media-cards3" and [item["category"] for item in page["items"]]!=["权威媒体","行业媒体","自媒体"]:
                errors.append("execution media cards must use authority/industry/self-media in order")
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
                            "purpose": config.get("purpose"), kind: {"pages": config.get("pages")}},rendered=True)


def render(config, out, kind="diagnosis", png_scale=1.15, pdf_name=None):
    import pymupdf as fitz
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor

    errors=validate(config,kind)
    if errors:
        raise ValueError("; ".join(errors))
    customer,pages=config["customer"],config["pages"]
    background=ROOT/"assets"/("geo-"+kind+"-template")/"backgrounds.pdf"
    reference=fitz.open(background)
    if len(reference)!=len(pages) or reference.get_toc() or any(p.get_text().strip() or p.get_links() for p in reference):
        raise ValueError("Background must match the fixed page count and contain no text or links")
    out=Path(out)
    basename="GEO诊断报告" if kind=="diagnosis" else "品牌传播与GEO执行方案"
    pdf=out/(pdf_name or basename+".pdf")
    if pdf.exists():
        raise FileExistsError("输出已存在，拒绝覆盖："+str(pdf))
    out.mkdir(parents=True,exist_ok=True)
    pdfmetrics.registerFont(TTFont("GEO",str(ASSETS/"font.ttf")))
    buf=io.BytesIO();cv=canvas.Canvas(buf,pagesize=(WIDTH,HEIGHT));logs=[]
    def text(value,x,y,w,size=18,lead=None,h=80,color="ink",align=0):
        style=ParagraphStyle("p",fontName="GEO",fontSize=size,leading=lead or size*1.45,
            textColor=HexColor(COLORS.get(color,color)),wordWrap="CJK",alignment=align)
        paragraph=Paragraph(html.escape(value).replace("\n","<br/>"),style)
        _,height=paragraph.wrap(w,1000)
        if height>h+.1:
            raise ValueError(f"Page {cv.getPageNumber()} overflow {height:.1f}>{h}: {value}")
        paragraph.drawOn(cv,x,HEIGHT-y-height)
        logs.append({"page":cv.getPageNumber(),"text":value,"rect":[x,y,x+w,y+height],"font":size})
    def box(x,y,w,h,color):
        cv.setFillColor(HexColor(color));cv.rect(x,HEIGHT-y-h,w,h,fill=1,stroke=0)
    def roundbox(x,y,w,h,color,radius=10):
        cv.setFillColor(HexColor(color));cv.roundRect(x,HEIGHT-y-h,w,h,radius,fill=1,stroke=0)
    def platforms(dark=False):
        names=customer["observed_platforms"]
        for i,name in enumerate(names):
            x=997+159/len(names)*i;icon=ICON_NAMES.get(name,name)
            if icon in PLATFORMS:
                cv.drawImage(str(ASSETS/(icon+".png")),x,HEIGHT-65-26,width=28,height=26,mask="auto")
            else:
                text(name,x,65,159/len(names)-5,14,19,40,"pale" if dark else "ink")
    def footer(i,dark=False):
        color="pale" if dark else "muted";y=647 if kind=="diagnosis" else 648
        text("软文街 / GEO 品牌诊断" if kind=="diagnosis" else "软文街 / GEO落地执行方案",44,y,360,11,14,18,color)
        text(customer["brand"]+" · "+customer["date"].replace("-","."),420,y,360,11,14,18,color,1)
        text(f"{i:02d} / {len(pages):02d}",1086,y,70,11,14,18,color,2)
    def frame(page,i):
        if kind=="diagnosis":
            text(page["title"],44,52,920,31,42,48,"green")
            text(page["banner"]["label"],64,582,120,17,24,28,"white")
            text(page["banner"]["text"],202,582,930,17,24,28,"white")
        else:
            text(page["title"],64,45,930,31,42,48,"#16323d")
            if page.get("subtitle"):text(page["subtitle"],46,99,1090,17,24,48,"#647a83")
            text(page["banner"]["text"],65,599,1065,16,23,28,"white")
        platforms();footer(i)
    def table(page,xs,widths,header_y,first_y,footprint,size,leading):
        rows=page["rows"];height=footprint/len(rows)
        panel_y=150 if kind=="diagnosis" else 150
        panel_end=536 if kind=="diagnosis" else 570
        roundbox(44,panel_y,1112,panel_end-panel_y,"#ffffff")
        for i,row in enumerate(rows):
            if kind=="diagnosis" and i==len(rows)-1:
                box(45,first_y-13+i*height,1110,height,"#e6f4ee")
            elif i%2:
                box(45,first_y-13+i*height,1110,height,"#f5f8f8" if kind=="diagnosis" else "#edf3f4")
            colors=(["ink","ink","muted"] if kind=="diagnosis" else
                    ["green","#16323d","#647a83","#647a83"] if page["layout"]=="content-plan" else
                    ["green","#16323d","#647a83"])
            for value,x,w,color in zip(row,xs,widths,colors):text(value,x,first_y+i*height,w,size,leading,height-10,color)
        for value,x,w in zip(page["headers"],xs,widths):text(value,x,header_y,w,15 if kind=="diagnosis" else 14,21,27,"muted" if kind=="diagnosis" else "#647a83")
    for index,page in enumerate(pages,1):
        layout=page["layout"]
        if layout=="cover":
            if kind=="diagnosis":
                text(customer["brand"],48,162,650,34,45,50,"white")
                text(customer["company"],49,212,650,15,22,26,"pale")
                text(page["title"],44,272,710,66,86,95,"white")
                text(page["headline"],49,401,680,29,40,45,"mint")
                text(page["scope"],49,461,650,19,28,32,"pale")
                meta=[("品牌主体",customer["company"]),("业务范围",page["scope"]),("建设重点",config["purpose"]),("报告日期",customer["date"])]
                for n,(label,value) in enumerate(meta):
                    y=175+n*90;text(label,790,y,350,13,19,22,"pale");text(value,790,y+23,350,18,26,55,"white")
                text(page["diagnosis"],65,572,1060,19,27,31,"white")
            else:
                text(customer["brand"],48,169,650,35,46,52,"white")
                text(customer["company"],49,220,650,16,23,28,"pale")
                text(page["title"],44,294,710,55,73,82,"white")
                text(page["headline"],49,409,1060,29,40,48,"mint")
                text(page["scope"],49,477,1060,23,32,40,"pale")
                text("执行重点",65,579,110,17,24,29,"white")
                text(page["diagnosis"],202,576,930,19,27,32,"white")
            platforms(True);footer(index,True)
        else:
            frame(page,index)
            if layout in {"cards3","comparison3"}:
                for n,item in enumerate(page["items"]):
                    if kind=="diagnosis":
                        x=70+377*n
                        text(item["label"],x,179,306,16,23,28,"muted")
                        text(item["heading"],x,224,306,27,37,82,item.get("color","green"))
                        text(item["body"],x,314,306,18,28,118)
                        text(item["footer"],x,448,306,17,25,79,"muted")
                    else:
                        x=67+379*n
                        text(item["label"],x,178,308,15,21,27,"muted")
                        text(item["heading"],x,212,308,24,34,76,"#4d67ff" if n==1 else "green")
                        text(item["body"],x,257,308,18,25.6,110)
                        text(item["footer"],x,386,308,18,25.6,141)
            elif layout in {"table3","customer-items3"}:
                if kind=="diagnosis":table(page,[62,306,740],[220,405,392],161,209,340,17,24)
                else:table(page,[59,255,713],[175,438,420],158,196,380,16,22.7)
            elif layout=="table4":
                rows=page["rows"];height=375/len(rows)
                box(44,165,1112,375,"#ffffff")
                for n,row in enumerate(rows):
                    y=177+n*height
                    if n%2:box(44,165+n*height,1112,height,"#f5f8f8")
                    text(row[0],66,y+3,245,18,26,height-13)
                    text(row[1],339,y+12,125,16,23,36,"blue",1)
                    text(row[2],498,y,310,16,23,height-12)
                    text(row[3],838,y,294,16,23,height-12,"muted")
                for value,x,w in zip(page["headers"],[66,339,498,838],[245,125,310,294]):text(value,x,134,w,15,21,26,"muted")
            elif layout=="scenes4":
                for unused in range(len(page["items"]),4):box(393,149+100*unused,764,88,"#f5f7f7")
                focus=page["focus"]
                for key,x,y,w,size,h,color in [("label",70,176,270,16,30,"green"),("heading",70,222,280,31,82,"ink"),("scope",70,286,285,18,35,"green"),("body",70,337,285,19,96,"ink"),("footer",70,445,285,17,65,"muted")]:text(focus[key],x,y,w,size,None,h,color)
                for n,item in enumerate(page["items"]):
                    y=163+100*n;text(item["label"],427,y+8,93,15,21,26,"green",1)
                    text(item["title"],552,y,560,21,30,36);text(item["description"],552,y+34,560,16,23,50,"muted")
            elif layout=="summary4":
                for item,(x,y),color in zip(page["items"],[(68,170),(634,170),(68,350),(634,350)],["green","blue","amber","green"]):
                    text(item["title"],x+16,y,480,22,31,38,color)
                    text(item["body"],x,y+43,490,18,27,95)
            elif layout=="steps4-grid":
                for n,(item,(x,y)) in enumerate(zip(page["items"],[(67,175),(633,175),(67,371),(633,371)]),1):
                    text(f"{n:02d} "+item["title"],x,y,490,24,34,42,"#4d67ff" if n%2==0 else "green")
                    text(item["body"],x,y+45,490,18,25.6,77)
                    text(item["footer"],x,y+128,490,14,20,25,"muted")
            elif layout=="content-plan":
                table(page,[59,285,363,866],[205,58,482,267],158,196,364,16,22.7)
            elif layout=="media-cards3":
                for n,item in enumerate(page["items"]):
                    x=67+378*n
                    text(item["category"],x,178,310,25,35,43,"green")
                    text(item["quantity"],x,234,310,38,50,60,"#4d67ff")
                    text(item["role"]+"\n"+item["focus"],x,305,310,18,25.6,78)
                    text(item["resources"],x,390,310,16,22.7,95,"muted")
                text("费用配置",63,523,120,17,24,29,"green")
                text("；".join(item["category"]+"："+item["amount"] for item in page["items"]),205,517,925,16,22.7,53)
            elif layout=="stages3":
                count=len(page["items"]);stride=1128/count;width=stride-16;inner=width-36
                if count!=4:
                    box(44,153,1112,418,"#f5f7f7")
                    for n in range(count):roundbox(44+n*stride,154,width,416,"#ffffff")
                for n,item in enumerate(page["items"]):
                    x=62+n*stride
                    text(item["period"],x,174,inner,17,24,47,"green")
                    text(item["title"],x,219,inner,23,32,65)
                    text(item["counts"],x,283,inner,15,21,25,"#4d67ff")
                    text(item["media_counts"],x,309,inner,15,21,43,"#4d67ff")
                    text(item["amount"],x,355,inner,14,20,42,"blue")
                    text("实施内容",x,399,inner,14,20,24,"muted")
                    text(item["work"],x,425,inner,16,22,67)
                    text("贵司配合",x,497,inner,14,20,24,"muted")
                    text(item["cooperation"],x,523,inner,15,21,43)
            elif layout=="review-table":
                table(page,[59,254,713],[175,439,420],158,196,364,17,24.1)
            elif layout=="quotes":
                for n,item in enumerate(page["items"]):
                    x=66+566*n;color="green" if n==0 else "#4d67ff"
                    text("方案"+["一","二"][n],x,167,160,14,20,26,"muted")
                    text(item["tag"],x+323,169,179,14,20,27,color)
                    text(item["name"],x,204,502,25,35,44)
                    text(item["total"],x,247,502,40,53,62,color)
                    text(item["scale"],x,311,502,16,23,29,"muted")
                    lines=item["media"].splitlines()
                    if len(lines)!=3:raise ValueError("费用卡须有三类媒体明细")
                    for row,(category,line) in enumerate(zip(["权威媒体","行业媒体","自媒体"],lines)):
                        if not line.startswith(category):raise ValueError("费用卡媒体类别顺序错误")
                        text(category,x,357+33*row,148,16,23,28,"muted")
                        text(line[len(category):].lstrip(" ：:|｜"),x+168,357+33*row,334,17,24,30)
                    text(page["services"],x,456,502,15,21,43,"muted")
                text("撰写费用",64,529,120,17,24,29,"green")
                text(page["writing"],201,522,930,16,22.7,50)
        cv.showPage()
    cv.save();overlay=fitz.open(stream=buf.getvalue(),filetype="pdf");doc=fitz.open()
    for i in range(len(pages)):
        doc.insert_pdf(reference,from_page=i,to_page=i)
        doc[-1].show_pdf_page(doc[-1].rect,overlay,i)
    doc.set_metadata({"title":customer["brand"]+"｜"+basename,"author":"软文街"})
    doc.set_toc([[1,page["title"],i+1] for i,page in enumerate(pages)])
    doc.save(pdf,garbage=4,deflate=True)
    rendered=[]
    for i,page in enumerate(doc):
        path=out/f"{kind}_page_{i+1:02d}.png";page.get_pixmap(matrix=fitz.Matrix(png_scale,png_scale)).save(path);rendered.append(str(path))
    audit={"schema_version":"2.0","kind":kind,"page_count":len(doc),"background_pages":list(range(1,len(doc)+1)),"blocks":logs,"rendered_pages":rendered,"pdf":str(pdf)}
    audit_path=out/(kind+"_layout_audit.json");audit_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8",newline="\n")
    doc.close();reference.close();overlay.close()
    return {"pdf":str(pdf),"pages":len(pages),"audit":str(audit_path),"rendered_pages":rendered}
