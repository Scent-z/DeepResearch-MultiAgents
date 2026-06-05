"""Orchestrator coordinating the deep research workflow."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any, Callable, Iterator

from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool

from config import Configuration
from prompts import (
    report_writer_instructions,
    task_summarizer_instructions,
    todo_planner_system_prompt,
)
from models import SummaryState, SummaryStateOutput, TodoItem

from agents import Planner
from agents import Reporter
from agents import Summarizer

# from services.planner import PlanningService
# from services.reporter import ReportingService
# from services.summarizer import SummarizationService
# from services.search import dispatch_search, prepare_research_context
from tools.search import dispatch_search, prepare_research_context
from tools.tool_events import ToolCallTracker

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """Coordinator orchestrating TODO-based research workflow using HelloAgents."""

    # ✅️
    def __init__(self, config: Configuration | None = None) -> None:
        """Initialise the coordinator with configuration and shared tools."""
        self.config = config or Configuration.from_env()
        self.llm = self._init_llm()

        self.note_tool = (
            NoteTool(workspace=self.config.notes_workspace)
            if self.config.enable_notes
            else None
        )
        self.tools_registry: ToolRegistry | None = None
        if self.note_tool:
            registry = ToolRegistry()
            registry.register_tool(self.note_tool)
            self.tools_registry = registry

        self._tool_tracker = ToolCallTracker(
            self.config.notes_workspace if self.config.enable_notes else None
        )
        self._tool_event_sink_enabled = False
        self._state_lock = Lock()

        self.todo_agent = self._create_tool_aware_agent(
            name="研究规划专家",
            system_prompt=todo_planner_system_prompt.strip(),
        )
        self.report_agent = self._create_tool_aware_agent(
            name="报告撰写专家",
            system_prompt=report_writer_instructions.strip(),
        )

        self._summarizer_factory: Callable[[], ToolAwareSimpleAgent] = lambda: self._create_tool_aware_agent(  # noqa: E501
            name="任务总结专家",
            system_prompt=task_summarizer_instructions.strip(),
        )

        self.planner = Planner(self.todo_agent, self.config)
        self.reporter = Reporter(self.report_agent, self.config)
        self.summarizer = Summarizer(self._summarizer_factory, self.config)

        # self.planner = PlanningService(self.todo_agent, self.config)
        # self.summarizer = SummarizationService(self._summarizer_factory, self.config)
        # self.reporting = ReportingService(self.report_agent, self.config)
        self._last_search_notices: list[str] = []

    # ✅️
    def _init_llm(self) -> HelloAgentsLLM:
        """Instantiate HelloAgentsLLM following configuration preferences."""
        llm_kwargs: dict[str, Any] = {"temperature": 0.0}

        model_id = self.config.llm_model_id or self.config.local_llm
        if model_id:
            llm_kwargs["model"] = model_id

        provider = (self.config.llm_provider or "").strip()
        if provider:
            llm_kwargs["provider"] = provider

        if provider == "ollama":
            llm_kwargs["base_url"] = self.config.sanitized_ollama_url()
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif provider == "lmstudio":
            llm_kwargs["base_url"] = self.config.lmstudio_base_url
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
        else:
            if self.config.llm_base_url:
                llm_kwargs["base_url"] = self.config.llm_base_url
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key

        return HelloAgentsLLM(**llm_kwargs)

    # ✅️
    def _create_tool_aware_agent(self, *, name: str, system_prompt: str) -> ToolAwareSimpleAgent:
        """Instantiate a ToolAwareSimpleAgent sharing tool registry and tracker."""
        return ToolAwareSimpleAgent(
            name=name,
            llm=self.llm,
            system_prompt=system_prompt,
            enable_tool_calling=self.tools_registry is not None,
            tool_registry=self.tools_registry,
            tool_call_listener=self._tool_tracker.record,
        )

    def _set_tool_event_sink(self, sink: Callable[[dict[str, Any]], None] | None) -> None:
        """Enable or disable immediate tool event callbacks."""
        self._tool_event_sink_enabled = sink is not None
        self._tool_tracker.set_event_sink(sink)

    # ✅️
    def run(self, topic: str) -> SummaryStateOutput:
        """Execute the research workflow and return the final report."""
        state = SummaryState(research_topic=topic)
        state.todo_items = self.planner.plan_todo_list(state)
        self._drain_tool_events(state)

        if not state.todo_items:
            # logger.info("No TODO items generated; falling back to single task")
            logger.info("没有任务创建, 触发兜底任务策略")
            state.todo_items = [self.planner.create_fallback_task(state)]

        for task in state.todo_items:
            self._execute_task(state, task, emit_stream=False)

        report = self.reporter.generate_report(state)
        self._drain_tool_events(state)
        state.structured_report = report
        state.running_summary = report
        self._persist_final_report(state, report)

        return SummaryStateOutput(
            running_summary=report,
            report_markdown=report,
            todo_items=state.todo_items,
        )

    # ✅️
    def run_stream(self, topic: str) -> Iterator[dict[str, Any]]:
        """Execute the workflow yielding incremental progress events."""
        state = SummaryState(research_topic=topic)
        logger.debug("Starting streaming research: topic=%s", topic)
        yield {"type": "status", "message": "初始化研究流程"}

        state.todo_items = self.planner.plan_todo_list(state)
        for event in self._drain_tool_events(state, step=0):
            yield event
        if not state.todo_items:
            state.todo_items = [self.planner.create_fallback_task(state)]

        channel_map: dict[int, dict[str, Any]] = {}
        for index, task in enumerate(state.todo_items, start=1):
            token = f"task_{task.id}"
            task.stream_token = token  # 为每个任务创建流式推送的唯一标识符
            channel_map[task.id] = {"step": index, "token": token}

        # 产出任务列表事件，让客户端知道有哪些任务要执行
        yield {
            "type": "todo_list",
            "tasks": [self._serialize_task(t) for t in state.todo_items],
            "step": 0,
        }

        event_queue: Queue[dict[str, Any]] = Queue()

        # 核心设计模式：生产者-消费者模型 
        # 生产者: Worker 线程，执行任务并调用 enqueue() 放入事件; 消费者: 主线程，调用 event_queue.get() 取出事件并 yield
        # 缓冲区: event_queue ，线程安全的 Queue; 线程安全: Queue 内部有锁，多线程同时读写不会冲突
        # 阻塞获取: event_queue.get() 会阻塞直到有事件; 非阻塞获取: event_queue.get_nowait() 立即返回或抛出 Empty
        # 守护线程: daemon=True ，主进程退出时自动终止; 优雅关闭: finally 块中 thread.join() 等待所有线程结束
        # 内部信号: __task_done__ 用于追踪 Worker 完成状态，不发给客户端
        """
        ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
        │   Worker 1   │────▶│              │────▶│   主线程      │
        ├──────────────┤     │ event_queue  │     │  (yield事件)  │
        │   Worker 2   │────▶│              │────▶│              │
        ├──────────────┤     │   (Queue)    │     └──────────────┘
        │   Worker N   │────▶│              │
        └──────────────┘     └──────────────┘
        """
        """
        ┌─────────────────────────────────────────────────────────────────────────────┐
        │                          生产者-消费者模型架构                                  │
        ├─────────────────────────────────────────────────────────────────────────────┤
        │                                                                             │
        │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                       │
        │   │  Worker 线程1│   │ Worker 线程2 │   │ Worker 线程N│   ← 生产者             │
        │   │  (任务1)     │   │  (任务2)     │   │  (任务N)    │                       │
        │   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘                       │
        │          │                 │                 │                              │
        │          │ enqueue()       │ enqueue()       │ enqueue()                    │
        │          ▼                 ▼                 ▼                              │
        │   ┌─────────────────────────────────────────────────────┐                   │
        │   │                    event_queue                      │   ← 缓冲区         │
        │   │              (Queue 线程安全队列)                     │                   │
        │   └─────────────────────────┬───────────────────────────┘                   │
        │                             │                                               │
        │                             │ event_queue.get()                             │
        │                             ▼                                               │
        │   ┌─────────────────────────────────────────────────────┐                   │
        │   │              主线程 (run_stream)                     │   ← 消费者         │
        │   │              yield event → 客户端                    │                   │
        │   └─────────────────────────────────────────────────────┘                   │
        │                                                                             │
        └─────────────────────────────────────────────────────────────────────────────┘
        """
        # 封装了事件入队逻辑，自动为事件添加 task_id 、 step 、 stream_token 等元数据，所有 Worker 线程都通过这个函数向队列发送事件
        def enqueue(
            event: dict[str, Any],
            *,
            task: TodoItem | None = None,
            step_override: int | None = None,
        ) -> None:
            payload = dict(event)
            target_task_id = payload.get("task_id")
            if task is not None:
                target_task_id = task.id
                payload["task_id"] = task.id

            channel = channel_map.get(target_task_id) if target_task_id is not None else None
            if channel:
                payload.setdefault("step", channel["step"])
                payload["stream_token"] = channel["token"]
            if step_override is not None:
                payload["step"] = step_override
            event_queue.put(payload)  # 阻塞式入队
            # 使用阻塞时入队和出队的好处
            # (1) 主线程不需要"轮询"（不断检查队列是否为空） (2) 队列为空时，主线程自动休眠，不消耗 CPU (3) 一旦有事件入队，主线程立即被唤醒处理

        # 工具事件接收函数
        def tool_event_sink(event: dict[str, Any]) -> None:
            enqueue(event)

        # 注册到工具追踪器，当 LLM 调用工具（如笔记工具）时，事件会自动通过这个 sink 进入队列
        self._set_tool_event_sink(tool_event_sink)

        threads: list[Thread] = []

        # Worker 线程函数
        # 每个任务在独立线程中执行, 异常被捕获并转换为失败事件, __task_done__ 是内部信号, 用于通知主线程"这个 Worker 完成了"
        def worker(task: TodoItem, step: int) -> None:
            try:
                # 发送任务开始事件
                enqueue(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "in_progress",
                        "title": task.title,
                        "intent": task.intent,
                        "note_id": task.note_id,
                        "note_path": task.note_path,
                    },
                    task=task,
                )

                # 执行任务，获取流式事件
                for event in self._execute_task(state, task, emit_stream=True, step=step):
                    enqueue(event, task=task)
            except Exception as exc:  # pragma: no cover - defensive guardrail
                logger.exception("Task execution failed", exc_info=exc)
                # 发送任务失败事件
                enqueue(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "failed",
                        "detail": str(exc),
                        "title": task.title,
                        "intent": task.intent,
                        "note_id": task.note_id,
                        "note_path": task.note_path,
                    },
                    task=task,
                )
            finally:
                # 无论成功失败都执行，发送内部完成信号
                enqueue({"type": "__task_done__", "task_id": task.id})

        # 启动多线程
        for task in state.todo_items:
            step = channel_map.get(task.id, {}).get("step", 0)
            thread = Thread(target=worker, args=(task, step), daemon=True)  # 守护线程，主线程结束时自动结束
            threads.append(thread)
            thread.start()

        # 关键同步机制实现
        # 事件收集与转发循环
        active_workers = len(state.todo_items)  # 记录总 Worker 数量
        finished_workers = 0  # 已完成的 Worker 计数器

        # 消费者循环（主线程）
        try:
            # # 循环消费，直到所有生产者完成
            while finished_workers < active_workers:
                # 阻塞等待队列中的事件（消费者操作）
                event = event_queue.get()  # 阻塞式出队（队列为空时等待）
                if event.get("type") == "__task_done__":
                    finished_workers += 1
                    continue
                # 产出事件给客户端
                yield event

            # 清空队列中剩余事件
            while True:
                try:
                    # 非阻塞式出队（队列为空时抛异常）, 此时队列可能还有剩余事件，但不会再有新事件入队, 因此用非阻塞快速清空剩余事件，不用无限等待
                    event = event_queue.get_nowait()
                except Empty:
                    break
                if event.get("type") != "__task_done__":
                    yield event
        finally:
            # 取消工具事件接收器
            self._set_tool_event_sink(None)
            # 阻塞主线程，遍历所有线程，逐个等待它们执行完毕，即等待所有线程结束
            for thread in threads:
                thread.join()

        report = self.reporting.generate_report(state)
        final_step = len(state.todo_items) + 1
        for event in self._drain_tool_events(state, step=final_step):
            yield event
        state.structured_report = report
        state.running_summary = report

        note_event = self._persist_final_report(state, report)
        if note_event:
            yield note_event

        yield {
            "type": "final_report",
            "report": report,
            "note_id": state.report_note_id,
            "note_path": state.report_note_path,
        }
        yield {"type": "done"}

    # ✅️
    def _execute_task(
        self,
        state: SummaryState,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Run search + summarization for a single task."""
        task.status = "in_progress"

        search_result, notices, answer_text, backend = dispatch_search(
            task.query,
            self.config,
            state.research_loop_count,
        )
        self._last_search_notices = notices
        task.notices = notices

        if emit_stream:
            for event in self._drain_tool_events(state, step=step):
                yield event
        else:
            self._drain_tool_events(state)

        if notices and emit_stream:
            for notice in notices:
                if notice:
                    yield {
                        "type": "status",
                        "message": notice,
                        "task_id": task.id,
                        "step": step,
                    }

        if not search_result or not search_result.get("results"):
            task.status = "skipped"
            if emit_stream:
                for event in self._drain_tool_events(state, step=step):
                    yield event
                yield {
                    "type": "task_status",
                    "task_id": task.id,
                    "status": "skipped",
                    "title": task.title,
                    "intent": task.intent,
                    "note_id": task.note_id,
                    "note_path": task.note_path,
                    "step": step,
                }
            else:
                self._drain_tool_events(state)
            return
        else:
            if not emit_stream:
                self._drain_tool_events(state)

        sources_summary, context = prepare_research_context(
            search_result,
            answer_text,
            self.config,
        )

        task.sources_summary = sources_summary

        with self._state_lock:
            state.web_research_results.append(context)
            state.sources_gathered.append(sources_summary)
            state.research_loop_count += 1

        summary_text: str | None = None

        if emit_stream:
            # 取出工具事件并 yield
            for event in self._drain_tool_events(state, step=step):
                yield event
            # 产出来源事件，包含搜索结果和来源信息
            yield {
                "type": "sources",
                "task_id": task.id,
                "latest_sources": sources_summary,
                "raw_context": context,
                "step": step,
                "backend": backend,
                "note_id": task.note_id,
                "note_path": task.note_path,
            }

            summary_stream, summary_getter = self.summarizer.stream_task_summary(state, task, context)
            try:
                for event in self._drain_tool_events(state, step=step):
                    yield event
                for chunk in summary_stream:
                    if chunk:
                        # 产出总结片段事件
                        yield {
                            "type": "task_summary_chunk",
                            "task_id": task.id,
                            "content": chunk,
                            "note_id": task.note_id,
                            "step": step,
                        }
                    for event in self._drain_tool_events(state, step=step):
                        yield event
            finally:
                summary_text = summary_getter()
        else:
            summary_text = self.summarizer.summarize_task(state, task, context)
            self._drain_tool_events(state)

        task.summary = summary_text.strip() if summary_text else "暂无可用信息"
        task.status = "completed"

        if emit_stream:
            for event in self._drain_tool_events(state, step=step):
                yield event
            yield {
                "type": "task_status",
                "task_id": task.id,
                "status": "completed",
                "summary": task.summary,
                "sources_summary": task.sources_summary,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": step,
            }
        else:
            self._drain_tool_events(state)

    # 事件同步机制，确保工具调用结果能正确更新到任务状态，用于提取和处理工具调用事件，同步任务的 note_id
    # 规划任务后、执行任务后、生成报告后都需要进行同步 note_id
    def _drain_tool_events(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]:
        """Proxy to the shared tool call tracker."""
        events = self._tool_tracker.drain(state, step=step)
        if self._tool_event_sink_enabled:
            return []
        return events

    @property
    def _tool_call_events(self) -> list[dict[str, Any]]:
        """Expose recorded tool events for legacy integrations."""
        return self._tool_tracker.as_dicts()

    # ✅️
    def _serialize_task(self, task: TodoItem) -> dict[str, Any]:
        """Convert task dataclass to serializable dict for frontend."""
        return {
            "id": task.id,
            "title": task.title,
            "intent": task.intent,
            "query": task.query,
            "status": task.status,
            "summary": task.summary,
            "sources_summary": task.sources_summary,
            "note_id": task.note_id,
            "note_path": task.note_path,
            "stream_token": task.stream_token,
        }

    # ✅️
    def _persist_final_report(self, state: SummaryState, report: str) -> dict[str, Any] | None:
        if not self.note_tool or not report or not report.strip():
            return None

        note_title = f"研究报告：{state.research_topic}".strip() or "研究报告"
        tags = ["deep_research", "report"]
        content = report.strip()

        # 查找已有报告笔记, 如果存在尝试更新, 如果更新失败创建新笔记 
        note_id = self._find_existing_report_note_id(state)
        response = ""

        if note_id:
            response = self.note_tool.run(
                {
                    "action": "update",
                    "note_id": note_id,
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            if response.startswith("❌"):
                note_id = None

        if not note_id:
            response = self.note_tool.run(
                {
                    "action": "create",
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            note_id = self._extract_note_id_from_text(response)

        if not note_id:
            return None

        state.report_note_id = note_id
        if self.config.notes_workspace:
            note_path = Path(self.config.notes_workspace) / f"{note_id}.md"
            state.report_note_path = str(note_path)
        else:
            note_path = None

        payload = {
            "type": "report_note",
            "note_id": note_id,
            "title": note_title,
            "content": content,
        }
        if note_path:
            payload["note_path"] = str(note_path)

        return payload

    # 查找已有报告笔记
    def _find_existing_report_note_id(self, state: SummaryState) -> str | None:
        if state.report_note_id:
            return state.report_note_id

        for event in reversed(self._tool_tracker.as_dicts()):
            if event.get("tool") != "note":
                continue

            parameters = event.get("parsed_parameters") or {}
            if not isinstance(parameters, dict):
                continue

            action = parameters.get("action")
            if action not in {"create", "update"}:
                continue

            note_type = parameters.get("note_type")
            if note_type != "conclusion":
                title = parameters.get("title")
                if not (isinstance(title, str) and title.startswith("研究报告")):
                    continue

            note_id = parameters.get("note_id")
            if not note_id:
                note_id = self._tool_tracker._extract_note_id(event.get("result", ""))  # type: ignore[attr-defined]

            if note_id:
                return note_id

        return None

    # 提取笔记ID
    @staticmethod
    def _extract_note_id_from_text(response: str) -> str | None:
        if not response:
            return None

        match = re.search(r"ID:\s*([^\n]+)", response)
        if not match:
            return None

        return match.group(1).strip()


def run_deep_research(topic: str, config: Configuration | None = None) -> SummaryStateOutput:
    """Convenience function mirroring the class-based API."""
    agent = DeepResearchAgent(config=config)
    return agent.run(topic)
