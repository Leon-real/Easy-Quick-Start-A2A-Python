# =============================================================================
# agents/host/entry.py
# =============================================================================
"""
OrchestratorAgent 를 A2A 서버로 노출한다.
• registry JSON     : URL 리스트 또는 AgentCard 리스트 모두 지원
• new_completed_task: 응답을 Task 형태로 감싸 CLI 호환성 확보
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import click
import httpx
import uvicorn
from a2a.client import A2AClient
from a2a.server.apps import A2AStarletteApplication
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from a2a.utils import new_agent_text_message

from .orchestrator import OrchestratorAgent

# ──────────────────── Custom Logging Configuration ──────────────────────────
from utilities.custom_logger import get_logger, configure_global_logging_filter
logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Agent discovery
# --------------------------------------------------------------------------- #
async def _fetch_card(http: httpx.AsyncClient, url: str) -> AgentCard:
    client = await A2AClient.get_client_from_agent_card_url(http, url.rstrip("/"))
    return client.agent_card

async def _safe_fetch_card(http, url):
    try:
        return await _fetch_card(http, url)
    except Exception as e:                       # 네트워크·파싱 오류 모두 흡수
        logger.warning("⚠️  %s → card fetch 실패 (%s)", url, e)
        return None                             # 실패한 URL은 None 반환

def load_agent_cards(path_str: str | None) -> list[AgentCard]:
    if not path_str:
        logger.warning("Registry file not provided – no child agents discovered.")
        return []

    path = Path(path_str).expanduser()
    if not path.exists():
        logger.error("Registry file not found: %s", path)
        return []

    data = json.loads(path.read_text())
    # URL 리스트
    if data and isinstance(data[0], str):       # URL 리스트
        async def bulk() -> list[AgentCard]:
            async with httpx.AsyncClient(timeout=5) as http:
                results = await asyncio.gather(
                    *(_safe_fetch_card(http, u) for u in data),
                    return_exceptions=False,
                )
                return [card for card in results if card]   # 실패 URL 제거
        return asyncio.run(bulk())
    # AgentCard dict 리스트
    return [AgentCard(**d) for d in data]


# --------------------------------------------------------------------------- #
# Executor (A2A ↔ OrchestratorAgent 브리지)
# --------------------------------------------------------------------------- #
class OrchestratorExecutor(AgentExecutor):
    def __init__(self, orch: OrchestratorAgent):
        self._orch = orch

    async def execute(self, context: RequestContext, queue: EventQueue) -> None:
        user_text = context.get_user_input()
        session_id = context.context_id or uuid.uuid4().hex

        reply_text = await self._orch.invoke(user_text, session_id)

        # (✔) Completed Task 로 감싸 history·status 포함
        await queue.enqueue_event(
            new_agent_text_message(context_id=session_id, text=reply_text)
        )

    async def cancel(self, context: RequestContext, queue: EventQueue) -> None:  # noqa: D401
        raise Exception("Cancellation not supported")


# --------------------------------------------------------------------------- #
# CLI entrypoint
# --------------------------------------------------------------------------- #
@click.command()
@click.option("--host", default="localhost", help="Bind host")
@click.option("--port", default=10003, type=int, help="Bind port")
@click.option("--registry", help="agent_registry.json 경로", default="agent_registry.json")
@click.option("--log-level", default="ALL",type=click.Choice(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "A2A"], case_sensitive=False), help="로그 레벨 설정 (ALL: 모든 로그, A2A: A2A 로그만, 기타: 해당 레벨만)")
def main(host: str, port: int, registry: str | None, log_level: str) -> None:
    # 0) Set Log Level
    configure_global_logging_filter(log_level)
    
    logger.info(f"🚀 Start Server - Log Level :{log_level.upper()}")

    # 1) registry → AgentCard
    cards = load_agent_cards(registry)

    # 2) OrchestratorAgent & Executor
    orch = OrchestratorAgent(cards)
    executor = OrchestratorExecutor(orch)

    # 3) HTTP handler
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    # 4) Host-Agent 자신 정보
    orch_card = AgentCard(
        name="Host-Orchestrator",
        description="Routes user tasks to child agents",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="orchestrate",
                name="Task Orchestration",
                description="Delegates tasks to suitable child agents",
                tags=["routing", "delegation"],
            )
        ],
    )

    # 5) 서버 기동
    app = A2AStarletteApplication(agent_card=orch_card, http_handler=handler)
    uvicorn.run(app.build(), host=host, port=port)


if __name__ == "__main__":
    main()
