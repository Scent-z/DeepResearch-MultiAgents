"""供 Deep Researcher 各服务共享的工具辅助函数."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

CHARS_PER_TOKEN = 4

logger = logging.getLogger(__name__)

def get_config_value(value: Any) -> str:
    """以纯字符串形式返回配置值"""

    return value if isinstance(value, str) else value.value

def strip_thinking_tokens(text: str) -> str:
    """从模型响应中移除 <think> 部分（如果有的话）"""

    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>") + len("</think>")
        text = text[:start] + text[end:]
    return text

def deduplicate_and_format_sources(
    search_response: Dict[str, Any] | List[Dict[str, Any]],
    max_tokens_per_source: int,
    *,
    fetch_full_page: bool = False,
) -> str:
    """对搜索结果进行格式化和去重""" 

    if isinstance(search_response, dict):
        sources_list = search_response.get("results", [])
    else:
        sources_list = search_response

    unique_sources: dict[str, Dict[str, Any]] = {}
    for source in sources_list:
        url = source.get("url")
        if not url:
            continue
        if url not in unique_sources:
            unique_sources[url] = source

    formatted_parts: List[str] = []
    for source in unique_sources.values():
        title = source.get("title") or source.get("url", "")
        content = source.get("content", "")
        formatted_parts.append(f"信息来源: {title}\n\n")
        formatted_parts.append(f"URL: {source.get('url', '')}\n\n")
        formatted_parts.append(f"信息内容: {content}\n\n")

        if fetch_full_page:
            raw_content = source.get("raw_content")
            if raw_content is None:
                logger.debug("raw_content missing for %s", source.get("url", ""))
                raw_content = ""
            char_limit = max_tokens_per_source * CHARS_PER_TOKEN
            if len(raw_content) > char_limit:
                raw_content = f"{raw_content[:char_limit]}... [truncated]"
            formatted_parts.append(
                f"详细信息内容限制为 {max_tokens_per_source} 个 token: {raw_content}\n\n"
            )

    return "".join(formatted_parts).strip()

def format_sources(search_results: Dict[str, Any] | None) -> str:
    """返回一个总结搜索来源的项目符号列表"""

    if not search_results:
        return ""

    results = search_results.get("results", [])
    return "\n".join(
        f"* {item.get('title', item.get('url', ''))} : {item.get('url', '')}"
        for item in results
        if item.get("url")
    )