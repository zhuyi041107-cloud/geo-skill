"""WorkBuddy local stdio entry point; stdout is reserved for MCP."""
from mcp.server.fastmcp import FastMCP
import geo_gpt

mcp = FastMCP("软文街GEO-GPT", instructions="手动采集AI回答；GPT分析、成稿及实际成品终审。依次调用业务工具，审核通过后才能交付。")


@mcp.tool()
def geo_status() -> dict:
    """检查本地密钥与客户目录配置；不调用付费API，不证明真实模型连接。"""
    return geo_gpt.status()


@mcp.tool()
def geo_analyze_customer(workspace: str, project_file: str, answers_file: str) -> dict:
    """用GPT判读完整人工回答和截图并分析客户。输入为项目JSON与normalize后的内部XLSX，均在workspace内。会调用OpenAI API。"""
    return geo_gpt.analyze_customer(workspace, project_file, answers_file)


@mcp.tool()
def geo_search_media(run_dir: str, query: str, kind: str = "all", region: str = "") -> dict:
    """本地检索内置原价目录，kind为all/network/self。保存全部匹配到candidate_file，返回有限预览，不调用API。"""
    return geo_gpt.search_media(run_dir, query, kind, region)


@mcp.tool()
def geo_create_plan(run_dir: str, candidate_files: list[str], revision_instructions: str = "") -> dict:
    """用GPT依据分析与真实媒体候选生成阶段、内容、三类媒体和两档执行计划；本地补原价并核算。会调用OpenAI API。"""
    return geo_gpt.create_plan(run_dir, candidate_files, revision_instructions)


@mcp.tool()
def geo_write_reports(run_dir: str, revision_instructions: str = "") -> dict:
    """GPT填固定模板，内部生成8页诊断、9页执行及两sheet推荐表；此时成品未通过终审。会调用OpenAI API。"""
    return geo_gpt.write_reports(run_dir, revision_instructions)


@mcp.tool()
def geo_review_deliverables(run_dir: str) -> dict:
    """独立GPT终审：读取实际17页图片与对应原模板、原始依据，并验证成品原价与预算。会调用OpenAI API。"""
    return geo_gpt.review_deliverables(run_dir)


@mcp.tool()
def geo_publish(run_dir: str, output_dir: str) -> dict:
    """终审通过后，将审核哈希完全一致的三件成品复制到本客户新的正式输出目录，不覆盖已有成果。只操作本地文件。"""
    return geo_gpt.publish(run_dir, output_dir)


if __name__ == "__main__":
    mcp.run(transport="stdio")
