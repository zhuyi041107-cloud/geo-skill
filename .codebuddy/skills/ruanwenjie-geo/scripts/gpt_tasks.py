"""Persistent local business tasks built from fixed, checkpointed GPT requests."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import gpt_client


SPEC_KEYS = {"format_version", "run_dir", "workspace", "kind", "arguments", "inputs", "requests", "context", "model", "effort"}
TASK_KEYS = SPEC_KEYS | {"task_id", "spec_sha256"}
SAFE_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
SHA256 = re.compile(r"[0-9a-f]{64}")


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise gpt_client.GPTError("任务描述必须为可持久化的JSON数据") from None


def _read(path):
    def reject_constant(_value):
        raise ValueError("任务记录不接受非有限JSON数值")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=reject_constant)
    except (OSError, ValueError, UnicodeError):
        raise gpt_client.GPTError("任务记录无法读取或已损坏") from None


def _inside(path, workspace):
    candidate = Path(path).resolve()
    if not candidate.is_relative_to(Path(workspace).resolve()):
        raise gpt_client.GPTError("任务文件路径超出本次客户工作目录")
    return candidate


def _hash(path):
    if not Path(path).is_file():
        raise gpt_client.GPTError("任务输入或输出文件不存在")
    result = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                result.update(chunk)
    except OSError:
        raise gpt_client.GPTError("任务输入或输出文件无法读取") from None
    return result.hexdigest()


def _workspace(run_dir):
    run = Path(run_dir).resolve()
    state = _read(run / "run.json")
    if not isinstance(state, dict) or not isinstance(state.get("workspace"), str):
        raise gpt_client.GPTError("本次运行缺少客户工作目录")
    workspace = Path(state["workspace"]).resolve()
    if not workspace.is_dir() or not run.is_relative_to(workspace):
        raise gpt_client.GPTError("任务运行目录不在客户工作目录内")
    return run, workspace


def _atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".task-", suffix=".tmp", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _path(task, suffix=".json"):
    return _inside(Path(task["run_dir"]) / "tasks" / (task["task_id"] + suffix), task["workspace"])


def _validate_task(task, check_descriptor=True):
    if not isinstance(task, dict) or set(task) != TASK_KEYS:
        raise gpt_client.GPTError("任务描述字段不完整或包含未知内容")
    if task["format_version"] != 1 or not isinstance(task["kind"], str) or SAFE_NAME.fullmatch(task["kind"]) is None:
        raise gpt_client.GPTError("任务类型或版本无效")
    spec = {key: task[key] for key in SPEC_KEYS}
    sha = hashlib.sha256(_canonical(spec)).hexdigest()
    if task["spec_sha256"] != sha or task["task_id"] != task["kind"] + "-" + sha[:16]:
        raise gpt_client.GPTError("任务描述哈希不一致，拒绝续跑被改写的任务")
    run, workspace = _workspace(task["run_dir"])
    if str(run) != task["run_dir"] or str(workspace) != task["workspace"]:
        raise gpt_client.GPTError("任务运行目录或客户目录已改变")
    if task["model"] != gpt_client.MODEL or task["effort"] != gpt_client.REASONING_EFFORT:
        raise gpt_client.GPTError("任务模型或推理强度已改变，不能混用旧请求")
    if check_descriptor and _read(_path(task)) != task:
        raise gpt_client.GPTError("任务描述文件与当前任务不一致")
    return run, workspace


def validate_inputs(task):
    _, workspace = _validate_task(task)
    if not isinstance(task["inputs"], dict):
        raise gpt_client.GPTError("任务输入哈希清单无效")
    for raw, expected in task["inputs"].items():
        if not isinstance(raw, str) or not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
            raise gpt_client.GPTError("任务输入哈希清单无效")
        path = _inside(raw, workspace)
        if str(path) != raw or _hash(path) != expected:
            raise gpt_client.GPTError("任务输入文件已变化，不能续跑旧模型请求")
    return task


def _check_active_task(run, task):
    if not (run / "task-current.json").exists():
        return
    previous = load_current(run)
    if previous["task_id"] == task["task_id"] or cached_result(previous) is not None:
        return
    # A different request must not turn an unfinished or ambiguous paid task into a fresh POST.
    with task_lock(previous):
        for request in previous["requests"]:
            checkpoint = _inside(run / "requests" / (previous["task_id"] + "-" + request["name"] + ".json"), previous["workspace"])
            if not checkpoint.is_file():
                raise gpt_client.GPTError("已有未完成任务，请先调用geo_resume_task；未创建新的付费请求")
            state = _read(checkpoint)
            if not isinstance(state, dict) or state.get("version") != 1:
                raise gpt_client.GPTError("已有后台任务记录不完整，请人工核查；禁止新建付费请求")
            status = state.get("status")
            if status in {"queued", "in_progress"}:
                raise gpt_client.GPTError("已有GPT后台任务正在执行，请调用geo_resume_task；未创建新的付费请求")
            if status != "completed":
                raise gpt_client.GPTError("已有后台任务失败、过期或提交状态未确认，请人工核查；禁止新建付费请求")
            if (not isinstance(state.get("response_id"), str) or re.fullmatch(r"resp_[A-Za-z0-9_-]+", state["response_id"]) is None
                    or not isinstance(state.get("request_fingerprint"), str) or SHA256.fullmatch(state["request_fingerprint"]) is None
                    or state.get("model") != previous["model"] or not isinstance(state.get("result"), dict)):
                raise gpt_client.GPTError("已有后台完成记录不完整，请人工核查；禁止新建付费请求")
            gpt_client.validate_json(state["result"], request["schema"])
        revision = task["arguments"].get("revision_instructions")
        if task["kind"] != previous["kind"] or not isinstance(revision, str) or not revision.strip():
            raise gpt_client.GPTError("已有模型结果尚未完成本地校验，请先geo_resume_task；仅明确同阶段修正可创建新任务")


def create_task(run_dir, kind, arguments, inputs, requests, context=None):
    run, workspace = _workspace(run_dir)
    if not isinstance(kind, str) or SAFE_NAME.fullmatch(kind) is None:
        raise gpt_client.GPTError("任务类型只能使用1至64位字母、数字、下划线或短横线")
    if not isinstance(arguments, dict) or not isinstance(inputs, dict) or not isinstance(requests, list) or not requests:
        raise gpt_client.GPTError("任务须有参数对象、输入哈希清单及非空请求列表")
    if context is not None and not isinstance(context, dict):
        raise gpt_client.GPTError("任务上下文须为对象")
    normalized_inputs = {}
    for raw, expected in inputs.items():
        path = _inside(raw, workspace)
        if not isinstance(expected, str) or SHA256.fullmatch(expected) is None or _hash(path) != expected:
            raise gpt_client.GPTError("任务输入哈希不符或文件已改变")
        if str(path) in normalized_inputs:
            raise gpt_client.GPTError("任务输入路径重复")
        normalized_inputs[str(path)] = expected
    normalized_requests, names = [], set()
    required = {"name", "instructions", "payload", "schema", "images", "max_output_tokens"}
    for request in requests:
        if not isinstance(request, dict) or set(request) != required:
            raise gpt_client.GPTError("任务请求字段不完整或包含未知内容")
        name = request["name"]
        if not isinstance(name, str) or SAFE_NAME.fullmatch(name) is None or name in names:
            raise gpt_client.GPTError("任务请求名称无效或重复")
        if not isinstance(request["instructions"], str) or not request["instructions"].strip() or not isinstance(request["payload"], dict):
            raise gpt_client.GPTError("任务请求缺少指令或业务数据")
        if not isinstance(request["schema"], dict) or request["schema"].get("type") != "object":
            raise gpt_client.GPTError("任务请求须有对象输出schema")
        if type(request["max_output_tokens"]) is not int or not 1 <= request["max_output_tokens"] <= 128000:
            raise gpt_client.GPTError("任务输出token上限无效")
        if not isinstance(request["images"], list):
            raise gpt_client.GPTError("任务图片须为列表")
        images = []
        for image in request["images"]:
            if not isinstance(image, dict) or set(image) != {"label", "path"} or not isinstance(image["label"], str) or not image["label"].strip():
                raise gpt_client.GPTError("任务图片须有标签和路径")
            path = _inside(image["path"], workspace)
            sha = _hash(path)
            if str(path) in normalized_inputs and normalized_inputs[str(path)] != sha:
                raise gpt_client.GPTError("任务图片与已保存输入不一致")
            normalized_inputs[str(path)] = sha
            images.append({"label": image["label"], "path": str(path)})
        names.add(name)
        normalized_requests.append({**request, "images": images})
    spec = {"format_version": 1, "run_dir": str(run), "workspace": str(workspace), "kind": kind,
            "arguments": arguments, "inputs": normalized_inputs, "requests": normalized_requests,
            "context": context or {}, "model": gpt_client.MODEL, "effort": gpt_client.REASONING_EFFORT}
    sha = hashlib.sha256(_canonical(spec)).hexdigest()
    task = json.loads(_canonical({**spec, "task_id": kind + "-" + sha[:16], "spec_sha256": sha}))
    path = _path(task)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gpt_client.file_lock(_inside(run / "tasks" / ".registration.lock", workspace)):
        _check_active_task(run, task)
        existed = path.exists()
        try:
            with path.open("xb") as output:
                output.write(_canonical(task) + b"\n")
                output.flush()
                os.fsync(output.fileno())
        except FileExistsError:
            if _read(path) != task:
                raise gpt_client.GPTError("同名任务描述冲突，拒绝覆盖") from None
        validate_inputs(task)
        pointer = _inside(run / "task-current.json", workspace)
        if existed and pointer.exists() and _read(pointer)["task_id"] != task["task_id"] and cached_result(task) is not None:
            return task
        _atomic(pointer, {"task_id": task["task_id"], "path": str(path)})
    return task


def load_current(run_dir):
    run, workspace = _workspace(run_dir)
    pointer = _read(_inside(run / "task-current.json", workspace))
    if not isinstance(pointer, dict) or set(pointer) != {"task_id", "path"}:
        raise gpt_client.GPTError("本次运行缺少有效的当前任务指针")
    path = _inside(pointer["path"], workspace)
    task = _read(path)
    if not isinstance(task, dict) or task.get("task_id") != pointer["task_id"] or task.get("run_dir") != str(run):
        raise gpt_client.GPTError("当前任务指针与任务描述不一致")
    _validate_task(task)
    if path != _path(task):
        raise gpt_client.GPTError("当前任务指针未指向固定任务文件")
    validate_inputs(task)
    return task


def run_requests(task):
    run, workspace = _validate_task(task)
    checkpoint_dir = _inside(run / "requests", workspace)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for request in task["requests"]:
        validate_inputs(task)
        checkpoint = _inside(checkpoint_dir / (task["task_id"] + "-" + request["name"] + ".json"), workspace)
        results[request["name"]] = gpt_client.complete_json(
            request["instructions"], request["payload"], request["schema"], images=request["images"],
            schema_name=request["name"], max_output_tokens=request["max_output_tokens"], checkpoint_path=checkpoint)
    validate_inputs(task)
    return results


def cached_result(task):
    validate_inputs(task)
    path = _path(task, ".result.json")
    if not path.exists():
        return None
    receipt = _read(path)
    keys = {"task_id", "spec_sha256", "result", "outputs", "receipt_sha256"}
    if not isinstance(receipt, dict) or set(receipt) != keys:
        raise gpt_client.GPTError("任务结果收据无效")
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt["receipt_sha256"] != hashlib.sha256(_canonical(body)).hexdigest():
        raise gpt_client.GPTError("任务结果收据哈希不一致")
    if receipt["task_id"] != task["task_id"] or receipt["spec_sha256"] != task["spec_sha256"] or not isinstance(receipt["result"], dict) or not isinstance(receipt["outputs"], dict):
        raise gpt_client.GPTError("任务结果收据与请求不一致")
    for raw, expected in receipt["outputs"].items():
        path = _inside(raw, task["workspace"])
        if not isinstance(expected, str) or SHA256.fullmatch(expected) is None or _hash(path) != expected:
            raise gpt_client.GPTError("任务完成后的输出已改变，不能复用结果")
    return receipt["result"]


def finish_task(task, result, output_paths=()):
    validate_inputs(task)
    if not isinstance(result, dict):
        raise gpt_client.GPTError("任务结果须为对象")
    result = json.loads(_canonical(result))
    outputs = {}
    for raw in output_paths:
        path = _inside(raw, task["workspace"])
        outputs[str(path)] = _hash(path)
    path = _path(task, ".result.json")
    with gpt_client.file_lock(path.with_suffix(".lock")):
        existing = cached_result(task)
        if existing is not None:
            if existing != result or _read(path)["outputs"] != outputs:
                raise gpt_client.GPTError("任务已有不同的完成结果，拒绝覆盖")
            return existing
        receipt = {"task_id": task["task_id"], "spec_sha256": task["spec_sha256"], "result": result, "outputs": outputs}
        receipt["receipt_sha256"] = hashlib.sha256(_canonical(receipt)).hexdigest()
        _atomic(path, receipt)
    return result


@contextmanager
def task_lock(task):
    _validate_task(task)
    with gpt_client.file_lock(_path(task, ".lock")):
        validate_inputs(task)
        yield task
