"""OpenAI Responses calls and the adapter for the sealed, local report contract."""
from __future__ import annotations

import base64
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
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


class GPTPending(GPTError):
    """A submitted response can be continued without another paid POST."""

    def __init__(self, checkpoint_path, response_id, status):
        self.checkpoint_path = str(Path(checkpoint_path).resolve())
        self.response_id = response_id
        self.status = status
        super().__init__("GPT后台任务尚未完成；继续同一任务将安全查询已有response_id，不会重新提交")


class _RequestError(GPTError):
    def __init__(self, message, http_status=None):
        self.http_status = http_status
        super().__init__(message)


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


def complete_json(instructions, payload, schema, *, images=None, schema_name="geo_result", max_output_tokens=32000, checkpoint_path=None):
    """Create once or resume an existing request without echoing private data."""
    if not isinstance(instructions, str) or not instructions.strip():
        raise GPTError("GPT任务指令不能为空")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise GPTError("API输出schema根节点须为object")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", schema_name):
        raise GPTError("API输出schema名称无效")
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 128000:
        raise GPTError("max_output_tokens须为1至128000的整数")
    try:
        content = [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)}]
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
        request_data = {
            "model": MODEL,
            "instructions": instructions,
            "input": [{"role": "user", "content": content}],
            "reasoning": {"effort": REASONING_EFFORT},
            "truncation": "disabled",
            "store": False,
            "max_output_tokens": max_output_tokens,
            "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
        }
        if checkpoint_path is not None:
            request_data["background"] = True
        body = json.dumps(request_data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise GPTError("本地单次请求超过64MB（含图片base64和文字），请拆分材料后再分析")
    except GPTError:
        raise
    except (TypeError, ValueError, KeyError, OSError):
        raise GPTError("GPT请求数据或审核图片无效") from None
    if checkpoint_path is not None:
        return _background_json(checkpoint_path, body, schema)
    return _result_from_response(_request_json("POST", ENDPOINT, body, timeout=600), schema)


def _api_key():
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise GPTError("未配置OPENAI_API_KEY，请先在本机配置密钥")
    if "\r" in key or "\n" in key:
        raise GPTError("本机API密钥格式无效")
    return key


def _request_json(method, url, body=None, *, timeout):
    request = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + _api_key(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }, method=method)
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise _RequestError(f"OpenAI请求失败（HTTP {error.code}）；请检查账号权限、余额和模型权限", error.code) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise _RequestError("OpenAI网络连接失败或超时；未自动重试，请确认本次调用状态后再试") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise GPTError("OpenAI响应超过本地大小限制")
    try:
        result = _json(raw)
    except (ValueError, UnicodeError):
        raise GPTError("OpenAI返回的响应不是有效JSON") from None
    if not isinstance(result, dict):
        raise GPTError("OpenAI响应根节点须为对象")
    return result


def _validate_model(result):
    actual_model = result.get("model")
    if not isinstance(actual_model, str) or not (actual_model == MODEL or actual_model.startswith(MODEL + "-")):
        raise GPTError("OpenAI返回的模型与指定模型不一致")


def _result_from_response(result, schema):
    if result.get("status") != "completed" or result.get("error"):
        raise GPTError("OpenAI未完成本次请求；禁止使用截断或失败结果")
    _validate_model(result)
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


def _now():
    return datetime.now(timezone.utc).isoformat()


def _save_checkpoint(path, state, *, create=False):
    state["updated_at"] = _now()
    raw = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if create:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def file_lock(path):
    """Hold a nonblocking process lock released automatically on process exit."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise GPTError("同一后台任务正在处理，请稍后继续；未重新提交") from None
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise GPTError("同一后台任务正在处理，请稍后继续；未重新提交") from None
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _response_id(value):
    return isinstance(value, str) and re.fullmatch(r"resp_[A-Za-z0-9_-]+", value) is not None


def _background_json(checkpoint_path, body, schema):
    path = Path(checkpoint_path).resolve()
    canonical = json.dumps(_json(body), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with file_lock(path.with_name(path.name + ".lock")):
        if path.exists():
            try:
                state = _json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError):
                raise GPTError("后台任务记录损坏或不可读取；禁止自动重新提交，请人工核查") from None
            if not isinstance(state, dict) or state.get("version") != 1:
                raise GPTError("后台任务记录格式无效；禁止自动重新提交")
            if state.get("request_fingerprint") != fingerprint:
                raise GPTError("本次请求与已有后台任务内容不一致；禁止覆盖或重新提交，请继续原任务或明确创建新任务")
            status = state.get("status")
            if status == "completed":
                value = state.get("result")
                if not _response_id(state.get("response_id")) or not isinstance(value, dict):
                    raise GPTError("后台任务完成记录缺少有效ID或结果；禁止自动重新提交")
                validate_json(value, schema)
                return value
            if status in {"submitting", "unknown"}:
                raise GPTError("后台提交状态未确认且没有可恢复结果；禁止再次POST，请人工核查原请求")
            if status in {"failed", "expired"}:
                raise GPTError("后台任务已过期或失败；禁止自动重新提交，请人工核查后决定是否创建新任务")
            response_id = state.get("response_id")
            if status not in {"queued", "in_progress"} or not _response_id(response_id):
                raise GPTError("后台任务记录状态或response_id无效；禁止自动重新提交")
            _api_key()
            try:
                response = _request_json("GET", ENDPOINT + "/" + response_id, timeout=60)
            except GPTError as error:
                if isinstance(error, _RequestError) and error.http_status == 404:
                    state.update(status="expired", error="已提交响应无法检索或已过期；禁止自动重新提交")
                    _save_checkpoint(path, state)
                    raise GPTError("已提交响应无法检索或已过期；禁止自动重新提交，请人工核查") from None
                else:
                    state["error"] = "查询已有响应失败；保留response_id，可安全继续查询"
                _save_checkpoint(path, state)
                raise GPTError("查询已有响应失败；response_id已保留，可继续同一任务安全查询，未重新提交") from None
        else:
            _api_key()
            state = {"version": 1, "request_fingerprint": fingerprint, "response_id": None,
                     "status": "submitting", "model": MODEL, "created_at": _now()}
            _save_checkpoint(path, state, create=True)
            try:
                response = _request_json("POST", ENDPOINT, body, timeout=90)
            except GPTError as error:
                state.update(status="failed" if isinstance(error, _RequestError) and error.http_status else "unknown",
                             error="后台提交未取得可恢复ID；禁止自动重新提交，请人工核查")
                _save_checkpoint(path, state)
                raise GPTError("后台提交未取得可恢复response_id；禁止自动重新提交，请人工核查原请求") from None
        response_id = response.get("id")
        if not _response_id(response_id) or (state.get("response_id") and response_id != state["response_id"]):
            state.update(status="unknown" if state.get("response_id") is None else "failed",
                         error="后台响应ID缺失或不一致；禁止自动重新提交")
            _save_checkpoint(path, state)
            raise GPTError(state["error"])
        state["response_id"] = response_id
        try:
            _validate_model(response)
            status = response.get("status")
            if status in {"queued", "in_progress"} and not response.get("error"):
                state.update(status=status)
                state.pop("error", None)
                _save_checkpoint(path, state)
                raise GPTPending(path, response_id, status)
            value = _result_from_response(response, schema)
        except GPTPending:
            raise
        except GPTError:
            state.update(status="failed", error="后台响应未通过状态、模型或输出结构检查；禁止自动重新提交")
            _save_checkpoint(path, state)
            raise
        state.update(status="completed", result=value)
        state.pop("error", None)
        _save_checkpoint(path, state)
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
