"""WorkBuddy local stdio entry point; stdout is reserved for MCP."""
from pathlib import Path

from mcp.server.fastmcp import FastMCP
import geo_gpt
import gpt_client

mcp = FastMCP("软文街GEO-GPT", instructions="手动采集AI回答；GPT分析、成稿及实际成品终审。返回pending时每15至30秒调用geo_resume_task持续查询同一任务，不重复发起付费生成；审核通过后才能交付。")


def _dispatch(function, *args):
    try:
        return function(*args)
    except gpt_client.GPTPending as exc:
        return {"status": "pending", "run_dir": str(Path(exc.checkpoint_path).parent.parent),
                "response_id": exc.response_id, "provider_status": exc.status,
                "resume_tool": "geo_resume_task", "retry_after_seconds": 20,
                "message": "GPT仍在处理；请持续查询同一任务，不重复提交生成请求。"}


@mcp.tool()
def geo_status() -> dict:
    """检查本地密钥与客户目录配置；不调用付费API，不证明真实模型连接。"""
    return geo_gpt.status()


@mcp.tool()
def geo_analyze_customer(workspace: str, project_file: str, answers_file: str) -> dict:
    """用GPT判读完整人工回答和截图并分析客户。输入为项目JSON与normalize后的内部XLSX，均在workspace内。会调用OpenAI API。"""
    return _dispatch(geo_gpt.analyze_customer, workspace, project_file, answers_file)


@mcp.tool()
def geo_create_plan(run_dir: str, revision_instructions: str = "", retry_failed_response_id: str = "") -> dict:
    """生成不指定具体媒体的分类投放与两档报价。会调用OpenAI API；失败任务仅在用户明确授权后传其response_id新建一次付费请求。"""
    return _dispatch(geo_gpt.create_plan, run_dir, revision_instructions, retry_failed_response_id)


@mcp.tool()
def geo_write_reports(run_dir: str, revision_instructions: str = "") -> dict:
    """GPT填固定模板，内部生成8页诊断和9页执行PDF；此时成品未通过终审。会调用OpenAI API。"""
    return _dispatch(geo_gpt.write_reports, run_dir, revision_instructions)


@mcp.tool()
def geo_review_deliverables(run_dir: str) -> dict:
    """独立GPT终审：读取实际17页图片与对应原模板、原始依据，并验证分类预算。会调用OpenAI API。"""
    return _dispatch(geo_gpt.review_deliverables, run_dir)


@mcp.tool()
def geo_resume_task(run_dir: str) -> dict:
    """继续查询已保存的GPT后台任务并缓存完成结果；pending时每15至30秒继续本工具，不重新POST付费生成。无任务ID或任务过期会明确报错。"""
    return _dispatch(geo_gpt.resume_task, run_dir)


@mcp.tool()
def geo_publish(run_dir: str, output_dir: str) -> dict:
    """终审通过后，将审核哈希完全一致的两份PDF复制到新的正式输出目录，不覆盖已有成果。只操作本地文件。"""
    return geo_gpt.publish(run_dir, output_dir)


if __name__ == "__main__":
    mcp.run(transport="stdio")
