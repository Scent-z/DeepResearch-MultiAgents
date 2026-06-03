"""通过 HTTP 对外暴露 DeepResearchAgent 的 FastAPI 入口"""
# ✅️

from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, Iterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration, SearchAPI
from deepresearch_agent import DeepResearchAgent

# 添加控制台日志处理程序
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)

# 添加错误日志文件处理程序
logger.add(
    sink=sys.stderr,
    level="ERROR",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


class ResearchRequest(BaseModel):
    """一次研究任务请求"""

    topic: str = Field(..., description="由用户提供的研究主题")
    search_api: SearchAPI | None = Field(
        default=None,
        description="通过环境配置覆盖默认的搜索api",
    )


class ResearchResponse(BaseModel):
    """包含生成报告和结构化任务的 HTTP 响应"""

    report_markdown: str = Field(
        ..., description="Markdown格式的研究报告"
    )
    todo_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="带有总结和搜索源的结构化待办项",
    )


def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """对敏感信息进行脱敏处理，同时保留首尾字符"""
    if not value:
        return "unset"

    if len(value) <= visible * 2:
        return "*" * len(value)

    return f"{value[:visible]}...{value[-visible:]}"

def _build_config(payload: ResearchRequest) -> Configuration:
    overrides: Dict[str, Any] = {}

    if payload.search_api is not None:
        overrides["search_api"] = payload.search_api

    return Configuration.from_env(overrides=overrides)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期事件处理器，替代已弃用的 on_event"""
    # Startup: 应用启动时执行
    config = Configuration.from_env()

    if config.llm_provider == "ollama":
        base_url = config.sanitized_ollama_url()
    elif config.llm_provider == "lmstudio":
        base_url = config.lmstudio_base_url
    else:
        base_url = config.llm_base_url or "unset"

    logger.info(
        "深度研究多智能体配置已加载: provider=%s model=%s base_url=%s search_api=%s "
        "max_loops=%s fetch_full_page=%s tool_calling=%s strip_thinking=%s api_key=%s",
        config.llm_provider,
        config.resolved_model() or "unset",
        base_url,
        (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
        config.max_web_research_loops,
        config.fetch_full_page,
        config.use_tool_calling,
        config.strip_thinking_tokens,
        _mask_secret(config.llm_api_key),
    )

    yield  # 应用运行期间

    # Shutdown: 应用关闭时执行（如有需要可添加清理逻辑）
    logger.info("深度研究多智能体应用关闭")


def create_app() -> FastAPI:
    app = FastAPI(title="深度研究多智能体", lifespan=lifespan)

    # 配置了 CORS 中间件，允许 任何域名 的前端使用 任何 HTTP 方法 和 任何请求头 访问后端，同时允许携带凭证（Cookie/Token）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允许所有域名的前端访问后端
        allow_credentials=True,  # 允许前端携带凭证（Cookie、HTTP 认证、客户端 SSL 证书）
        allow_methods=["*"],  # 允许所有 HTTP 方法
        allow_headers=["*"],  # 允许所有请求头
    )

    @app.get("/healthz")
    def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
            result = agent.run(payload.topic)
        except ValueError as exc:  # Likely due to unsupported configuration
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive guardrail
            raise HTTPException(status_code=500, detail="Research failed") from exc

        todo_payload = [
            {
                "id": item.id,
                "title": item.title,
                "intent": item.intent,
                "query": item.query,
                "status": item.status,
                "summary": item.summary,
                "sources_summary": item.sources_summary,
                "note_id": item.note_id,
                "note_path": item.note_path,
            }
            for item in result.todo_items
        ]

        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
        )

    @app.post("/research/stream")
    def stream_research(payload: ResearchRequest) -> StreamingResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        def event_iterator() -> Iterator[str]:
            try:
                for event in agent.run_stream(payload.topic):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:  # pragma: no cover - defensive guardrail
                logger.exception("Streaming research failed")
                error_payload = {"type": "error", "detail": str(exc)}
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",  # 设置 HTTP 响应的 Content-Type 头 ，告诉客户端返回的是什么类型的数据，此时为SSE 流式事件
            headers={  # 设置额外的 HTTP 响应头 ，控制客户端如何处理响应
                "Cache-Control": "no-cache",  # 告诉浏览器不要缓存这个响应，SSE 是实时推送的数据，每次请求结果都不同，不能缓存
                "Connection": "keep-alive",  # 告诉浏览器保持 TCP 连接，不要断开，SSE 需要长时间连接，持续推送数据
            },
        )

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    # run之前执行lifescan yield前的代码，然后执行run，run结束后再执行yield后的代码
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )