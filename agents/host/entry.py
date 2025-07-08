# =============================================================================
# agents/host/entry.py
# =============================================================================

"""
OrchestratorAgent 를 A2A 서버로 노출한다.
• registry JSON : URL 리스트 또는 AgentCard 리스트 모두 지원
• new_completed_task: 응답을 Task 형태로 감싸 CLI 호환성 확보
"""

# Python 3.7+ 호환성을 위한 future annotations 임포트
from __future__ import annotations

# 비동기 프로그래밍 지원
import asyncio
# JSON 파싱
import json
# UUID 생성
import uuid
# 파일 경로 처리
from pathlib import Path

# CLI 인터페이스 라이브러리
import click
# HTTP 클라이언트
import httpx
# ASGI 서버
import uvicorn

# A2A 클라이언트
from a2a.client import A2AClient
# A2A 서버 애플리케이션
from a2a.server.apps import A2AStarletteApplication
# 에이전트 실행기 및 요청 컨텍스트
from a2a.server.agent_execution import AgentExecutor, RequestContext
# 이벤트 큐
from a2a.server.events import EventQueue
# 기본 요청 핸들러
from a2a.server.request_handlers import DefaultRequestHandler
# 인메모리 작업 저장소
from a2a.server.tasks import InMemoryTaskStore
# A2A 타입 정의들
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
# 에이전트 텍스트 메시지 생성 유틸리티
from a2a.utils import new_agent_text_message

# 오케스트레이터 에이전트 임포트
from .orchestrator import OrchestratorAgent

# ──────────────────── Custom Logging Configuration ──────────────────────────

# 커스텀 로거 임포트
from utilities.custom_logger import get_logger, configure_global_logging_filter

# 현재 모듈 로거 생성
logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Agent discovery
# --------------------------------------------------------------------------- #

async def _fetch_card(http: httpx.AsyncClient, url: str) -> AgentCard:
    """주어진 URL에서 에이전트 카드를 가져오는 함수"""
    # URL 정규화 후 A2A 클라이언트 생성
    client = await A2AClient.get_client_from_agent_card_url(http, url.rstrip("/"))
    # 클라이언트에서 에이전트 카드 반환
    return client.agent_card

async def _safe_fetch_card(http, url):
    """안전하게 에이전트 카드를 가져오는 함수 (예외 처리 포함)"""
    try:
        # 에이전트 카드 가져오기 시도
        return await _fetch_card(http, url)
    except Exception as e: # 네트워크·파싱 오류 모두 흡수
        # 실패 시 경고 로그 출력
        logger.warning("⚠️ %s → card fetch 실패 (%s)", url, e)
        return None # 실패한 URL은 None 반환

def load_agent_cards(path_str: str | None) -> list[AgentCard]:
    """레지스트리 파일에서 에이전트 카드들을 로드하는 함수"""
    # 경로가 제공되지 않은 경우
    if not path_str:
        logger.warning("Registry file not provided - no child agents discovered.")
        return []

    # 경로 객체 생성 (홈 디렉토리 확장)
    path = Path(path_str).expanduser()
    
    # 파일 존재 확인
    if not path.exists():
        logger.error("Registry file not found: %s", path)
        return []

    # JSON 파일 읽기
    data = json.loads(path.read_text())

    # URL 리스트인 경우
    if data and isinstance(data[0], str): # URL 리스트
        async def bulk() -> list[AgentCard]:
            """여러 URL에서 병렬로 에이전트 카드 가져오기"""
            # HTTP 클라이언트 생성 (5초 타임아웃)
            async with httpx.AsyncClient(timeout=5) as http:
                # 모든 URL에 대해 병렬 요청
                results = await asyncio.gather(
                    *(_safe_fetch_card(http, u) for u in data),
                    return_exceptions=False,
                )
            # 실패한 요청(None) 제거 후 반환
            return [card for card in results if card] # 실패 URL 제거

        # 비동기 함수 실행
        return asyncio.run(bulk())

    # AgentCard dict 리스트인 경우
    # 딕셔너리를 AgentCard 객체로 변환
    return [AgentCard(**d) for d in data]

# --------------------------------------------------------------------------- #
# Executor (A2A ↔ OrchestratorAgent 브리지)
# --------------------------------------------------------------------------- #

class OrchestratorExecutor(AgentExecutor):
    """A2A 프로토콜과 OrchestratorAgent 간의 브리지 역할"""
    
    def __init__(self, orch: OrchestratorAgent):
        # 오케스트레이터 에이전트 인스턴스 저장
        self._orch = orch

    async def execute(self, context: RequestContext, queue: EventQueue) -> None:
        """요청 실행 메서드"""
        # 사용자 입력 텍스트 추출
        user_text = context.get_user_input()

        # 1. params 추출: context._params로 접근!
        params = getattr(context, "_params", None)

        # 2. metadata 추출
        metadata = getattr(params, "metadata", None) if params else None

        # 사용자 ID와 채팅 ID 초기화
        user_id = None
        chat_id = None
        
        # 메타데이터에서 ID 추출
        if metadata:
            user_id = metadata.get("user_id")
            chat_id = metadata.get("chat_id")

        # 필수 ID 검증
        if not user_id or not chat_id:
            raise ValueError("user_id와 chat_id를 반드시 metadata로 보내야 합니다.")

        # --- [2] 대화 저장시 반드시 (user_id, chat_id)로 분리 관리
        # 오케스트레이터에게 작업 위임
        reply_text = await self._orch.invoke(user_text, user_id, chat_id)

        # 응답을 이벤트 큐에 추가
        await queue.enqueue_event(
            new_agent_text_message(context_id=chat_id, text=reply_text)
        )

    async def cancel(self, context: RequestContext, queue: EventQueue) -> None: # noqa: D401
        """작업 취소 메서드 (지원하지 않음)"""
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
    """메인 함수 - CLI 진입점"""
    
    # 0) Set Log Level
    # 글로벌 로그 레벨 설정
    configure_global_logging_filter(log_level)
    logger.info(f"🚀 Start Server - Log Level :{log_level.upper()}")

    # 1) registry → AgentCard
    # 레지스트리 파일에서 에이전트 카드들 로드
    cards = load_agent_cards(registry)

    # 2) OrchestratorAgent & Executor
    # 오케스트레이터 에이전트 생성
    orch = OrchestratorAgent(cards)
    # 실행기 생성
    executor = OrchestratorExecutor(orch)

    # 3) HTTP handler
    # HTTP 요청 핸들러 생성
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    # 4) Host-Agent 자신 정보
    # 호스트 에이전트 카드 정의
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
    # A2A 서버 애플리케이션 생성
    app = A2AStarletteApplication(agent_card=orch_card, http_handler=handler)
    # Uvicorn 서버 실행
    uvicorn.run(app.build(), host=host, port=port)

# 스크립트 직접 실행 시 메인 함수 호출
if __name__ == "__main__":
    main()
