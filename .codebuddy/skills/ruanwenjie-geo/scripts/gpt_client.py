"""OpenAI Responses calls and the adapter for the sealed, local report contract."""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request


MODEL = "gpt-6.1-sol"
REASONING_EFFORT = "max"
MODEL_CONTEXT_WINDOW_TOKENS = 1_050_000
ENDPOINT = "https://api.openai.com/v1/responses"
ROOT = Path(__file__).resolve().parents[1]
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_IMAGES = 1500


class GPTError(ValueError):
    """An API failure safe to show without exposing credentials or customer text."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _bad_constant(_value):
    raise ValueError("non-finite JSON number")


def _json(raw):
    return json.loads(raw, parse_constant=_bad_constant)


def validate_json(value, schema, path="result", root=None):
    """Validate the JSON-schema subset used by our API contracts, offline."""
    root = schema if root is None else root
    if schema is True:
        return
    if schema is False:
        raise GPTError(path + ": 不允许额外内容")
    if "$ref" in schema:
        target = root
        reference = schema["$ref"]
        if not reference.startswith("#/"):
            raise GPTError("仅支持本地schema引用")
        try:
            for key in reference[2:].split("/"):
                target = target[key.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            raise GPTError("schema引用无效") from None
        return validate_json(value, target, path, root)
    for keyword in ("anyOf", "oneOf"):
        if keyword in schema:
            matches = 0
            for child in schema[keyword]:
                try:
                    validate_json(value, child, path, root)
                    matches += 1
                except GPTError:
                    pass
            if not matches or (keyword == "oneOf" and matches != 1):
                raise GPTError(path + ": 不符合声明的结构")
    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected] if expected else []
    checks = {
        "null": lambda v: v is None,
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: type(v) is bool,
        "integer": lambda v: type(v) is int,
        "number": lambda v: type(v) in (int, float),
    }
    if types and (any(t not in checks for t in types) or not any(checks[t](value) for t in types)):
        raise GPTError(path + ": 字段类型错误")
    if "const" in schema and value != schema["const"]:
        raise GPTError(path + ": 固定值不一致")
    if "enum" in schema and value not in schema["enum"]:
        raise GPTError(path + ": 枚举值无效")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", [])):
            raise GPTError(path + ": 缺少必填字段")
        extra = value.keys() - properties.keys()
        if extra and schema.get("additionalProperties") is False:
            raise GPTError(path + ": 出现未声明字段")
        for key, item in value.items():
            child = properties.get(key, schema.get("additionalProperties", True))
            validate_json(item, child, path + "." + key, root)
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise GPTError(path + ": 数量超出结构限制")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            raise GPTError(path + ": 含重复项")
        for index, item in enumerate(value):
            prefix = schema.get("prefixItems", [])
            child = prefix[index] if index < len(prefix) else schema.get("items", True)
            validate_json(item, child, f"{path}[{index}]", root)
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            raise GPTError(path + ": 文本长度不符合限制")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise GPTError(path + ": 文本格式错误")
    elif type(value) in (int, float):
        if value < schema.get("minimum", -float("inf")) or value > schema.get("maximum", float("inf")):
            raise GPTError(path + ": 数值超出限制")


def _image_content(image):
    path = Path(image["path"])
    label = image["label"]
    if not isinstance(label, str) or not label.strip():
        raise GPTError("审核图片须有非空标签")
    if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
        raise GPTError("审核图片不存在或超过20MB")
    raw = path.read_bytes()
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        mime = "image/webp"
    elif raw.startswith((b"GIF87a", b"GIF89a")):
        # Keep GIF bytes intact: the provider rejects animation rather than losing frames.
        mime = "image/gif"
    elif raw.startswith((b"BM", b"II*\x00", b"MM\x00*")):
        import pymupdf as fitz
        content = []
        try:
            with fitz.open(stream=raw, filetype="bmp" if raw.startswith(b"BM") else "tiff") as document:
                for index, page in enumerate(document):
                    if page.rect.width * page.rect.height > 30_000_000:
                        raise GPTError("截图转换像素过大，请拆分为较小截图")
                    png = page.get_pixmap(colorspace=fitz.csRGB, alpha=False).tobytes("png")
                    if len(png) > MAX_IMAGE_BYTES:
                        raise GPTError("截图转换后超过20MB，请拆分为较小截图")
                    page_label = label if len(document) == 1 else f"{label}／图像第{index + 1}页"
                    content.extend([
                        {"type": "input_text", "text": page_label},
                        {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"), "detail": "high"},
                    ])
                    if len(content) // 2 > MAX_IMAGES or sum(len(part.get("image_url", "")) for part in content) > MAX_REQUEST_BYTES:
                        raise GPTError("截图展开超过本地单次请求限制，请拆分材料后再分析")
        except GPTError:
            raise
        except Exception:
            raise GPTError("BMP或TIFF截图无法转换，请提供可打开的截图文件") from None
        if not content:
            raise GPTError("截图不包含可读取页面")
        return content
    else:
        raise GPTError("审核图片须为PNG、JPEG、WebP、GIF、BMP或TIFF")
    return [
        {"type": "input_text", "text": label},
        {"type": "input_image", "image_url": "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii"), "detail": "high"},
    ]


def complete_json(instructions, payload, schema, *, images=None, schema_name="geo_result", max_output_tokens=32000):
    """Make one paid request; errors never echo provider bodies or input data."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise GPTError("未配置OPENAI_API_KEY，请先在本机配置密钥")
    if "\r" in key or "\n" in key:
        raise GPTError("本机API密钥格式无效")
    if not isinstance(instructions, str) or not instructions.strip():
        raise GPTError("GPT任务指令不能为空")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise GPTError("API输出schema根节点须为object")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", schema_name):
        raise GPTError("API输出schema名称无效")
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 128000:
        raise GPTError("max_output_tokens须为1至128000的整数")
    try:
        content = [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False, allow_nan=False)}]
        image_count = image_bytes = 0
        for image in images or []:
            parts = _image_content(image)
            image_count += sum(part["type"] == "input_image" for part in parts)
            image_bytes += sum(len(part.get("image_url", "")) for part in parts)
            if image_count > MAX_IMAGES:
                raise GPTError("单次请求最多支持1500张图片，请拆分材料后再分析")
            if image_bytes > MAX_REQUEST_BYTES:
                raise GPTError("本地单次请求超过64MB（含图片base64），请拆分材料后再分析")
            content.extend(parts)
        body = json.dumps({
            "model": MODEL,
            "instructions": instructions,
            "input": [{"role": "user", "content": content}],
            "reasoning": {"effort": REASONING_EFFORT},
            "truncation": "disabled",
            "store": False,
            "max_output_tokens": max_output_tokens,
            "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
        }, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise GPTError("本地单次请求超过64MB（含图片base64和文字），请拆分材料后再分析")
    except GPTError:
        raise
    except (TypeError, ValueError, KeyError, OSError):
        raise GPTError("GPT请求数据或审核图片无效") from None
    request = urllib.request.Request(ENDPOINT, data=body, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }, method="POST")
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=600) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise GPTError(f"OpenAI请求失败（HTTP {error.code}）；请检查账号权限、余额和模型权限") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GPTError("OpenAI网络连接失败或超时；未自动重试，请确认本次调用状态后再试") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise GPTError("OpenAI响应超过本地大小限制")
    try:
        result = _json(raw)
    except (ValueError, UnicodeError):
        raise GPTError("OpenAI返回的响应不是有效JSON") from None
    if not isinstance(result, dict) or result.get("status") != "completed" or result.get("error"):
        raise GPTError("OpenAI未完成本次请求；禁止使用截断或失败结果")
    actual_model = result.get("model")
    if not isinstance(actual_model, str) or not (actual_model == MODEL or actual_model.startswith(MODEL + "-")):
        raise GPTError("OpenAI返回的模型与指定模型不一致")
    output = result.get("output")
    if not isinstance(output, list):
        raise GPTError("OpenAI响应缺少结果")
    texts = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        if item.get("status", "completed") != "completed":
            raise GPTError("OpenAI消息未完成")
        parts = item.get("content", [])
        if not isinstance(parts, list):
            raise GPTError("OpenAI消息结构无效")
        for part in parts:
            if not isinstance(part, dict):
                raise GPTError("OpenAI消息结构无效")
            if part.get("type") == "refusal":
                raise GPTError("OpenAI拒绝了本次任务；未生成可交付结果")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
    try:
        value = _json("".join(texts))
    except (ValueError, UnicodeError):
        raise GPTError("GPT结果不是完整JSON；未生成可交付结果") from None
    if not isinstance(value, dict):
        raise GPTError("GPT结果根节点须为对象")
    validate_json(value, schema)
    return value


def _report_schema():
    return json.loads((ROOT / "references/customer-report.schema.json").read_text(encoding="utf-8"))


def _tuple_keys(schema, name):
    prefix = "page" if name == "pages" else "item"
    return [f"{prefix}_{index + 1:02d}" for index in range(len(schema["prefixItems"]))]


def _api_schema(schema, name="", root=None):
    root = schema if root is None else root
    if "$ref" in schema:
        target = root
        reference = schema["$ref"]
        if not reference.startswith("#/"):
            raise GPTError("报告schema仅支持本地引用")
        for key in reference[2:].split("/"):
            target = target[key.replace("~1", "/").replace("~0", "~")]
        return _api_schema(target, name, root)
    if "prefixItems" in schema:
        properties = {key: _api_schema(child, key, root) for key, child in zip(_tuple_keys(schema, name), schema["prefixItems"])}
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    result = {key: copy.deepcopy(value) for key, value in schema.items()
              if key in {"type", "description", "title", "enum", "minItems", "maxItems", "minLength", "maxLength", "pattern", "minimum", "maximum"}}
    if "const" in schema:
        result["enum"] = [schema["const"]]
    if "enum" in result and "type" not in result:
        sample = result["enum"][0]
        result["type"] = "string" if isinstance(sample, str) else "boolean" if type(sample) is bool else "integer" if type(sample) is int else "number"
    if schema.get("type") == "object":
        properties = {}
        required = schema.get("required", [])
        for key, child in schema.get("properties", {}).items():
            if child.get("readOnly"):
                continue
            converted = _api_schema(child, key, root)
            if key not in required and key not in {"diagnosis", "execution"}:
                converted = {"anyOf": [converted, {"type": "null"}]}
            properties[key] = converted
        result.update(properties=properties, required=list(properties), additionalProperties=False)
    if schema.get("type") == "array":
        result["items"] = _api_schema(schema.get("items", {}), name, root)
    return result


def report_api_schema():
    """Expose named pages and nullable optional fields accepted by strict outputs."""
    result = _api_schema(_report_schema())
    # Fixed titles are maintained by the renderer, independently of this API adapter.
    import render_geo_diagnosis as renderer
    for kind, titles in (("diagnosis", renderer.DIAGNOSIS_TITLES), ("execution", renderer.EXECUTION_TITLES)):
        pages = result["properties"][kind]["properties"]["pages"]["properties"]
        for page, title in zip(pages.values(), titles):
            page["properties"]["title"] = {"type": "string", "enum": [title]}
    return result


def _convert_report(value, schema, name="", to_api=False):
    if "prefixItems" in schema:
        keys = _tuple_keys(schema, name)
        if to_api:
            return {key: _convert_report(item, child, key, True) for key, item, child in zip(keys, value, schema["prefixItems"])}
        return [_convert_report(value[key], child, key) for key, child in zip(keys, schema["prefixItems"])]
    if schema.get("type") == "object":
        converted = {}
        for key, child in schema.get("properties", {}).items():
            if child.get("readOnly"):
                continue
            if key in value and value[key] is not None:
                converted[key] = _convert_report(value[key], child, key, to_api)
            elif to_api:
                converted[key] = None
        return converted
    if schema.get("type") == "array":
        return [_convert_report(item, schema["items"], name, to_api) for item in value]
    return value


def report_to_api(value):
    """Convert an existing authoring report to the API shape for examples/tests."""
    import render_geo_diagnosis as renderer
    if renderer.validate_report(value) or not all(key in value for key in ("diagnosis", "execution")):
        raise GPTError("报告不符合完整固定模板契约")
    result = _convert_report(value, _report_schema(), to_api=True)
    validate_json(result, report_api_schema())
    return result


def report_from_api(value):
    """Restore arrays and omit nullable optional fields before local validation."""
    validate_json(value, report_api_schema())
    result = _convert_report(value, _report_schema())
    import render_geo_diagnosis as renderer
    if renderer.validate_report(result):
        raise GPTError("GPT报告未通过本地固定模板及客户语言检查")
    return result
