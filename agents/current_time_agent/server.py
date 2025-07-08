from typing import Dict, Any, List
import asyncio
from datetime import datetime
import uuid

# a2a 라이브러리에서 필요한 타입들 임포트
from a2a.types import (
    AgentCard, AgentCapabilities, AgentSkill, 
    Task, TaskStatus, TaskState, Message, TextPart, Role,
    SendMessageRequest, SendMessageResponse, SendMessageSuccessResponse
)
from a2a.server.apps import A2AStarletteApplication
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils import new_agent_text_message
import uvicorn

from .agent import CurrentTimeAgent

# ──────────────────── Custom Logging Configuration ──────────────────────────
from utilities.custom_logger import get_logger
logger = get_logger(__name__)


# ──────────────────── 현재 시간 에이전트 Executor ───────────────────────────
class CurrentTimeAgentExecutor(AgentExecutor):
    """현재 시간을 알려주기 위한 A2A Executor"""
    
    def __init__(self):
        self.agent = CurrentTimeAgent()
    
    async def execute(self, context: RequestContext, queue: EventQueue) -> None:
        """메시지 실행"""
        try:
            # 사용자 입력 추출
            user_text = context.get_user_input()
            session_id = context.context_id or uuid.uuid4().hex
            
            # logging start
            logger.a2a(
                f"\n📥 [{self.agent}::START]\n"
                f"├── Session ID: {session_id}\n"
                f"├── Input: {user_text}\n"
                f"└── Status: Start"
            )
            
            # CurrentTimeAgent로 처리
            response_text = await self.agent.process_message(user_text)
            
            # 응답 메시지 생성 및 큐에 추가
            await queue.enqueue_event(
                new_agent_text_message(
                    context_id=session_id, 
                    text=f"CurrentTimeAgent: {response_text}"
                )
            )
            
            # logging done
            logger.a2a(
                f"\n📤 [{self.agent}::DONE]\n"
                f"├── Session ID: {session_id}\n"
                f"├── Result: {response_text}\n"
                f"└── Status: Done"
            )
            
        except Exception as e:
            logger.error(f"CurrentTimeAgent 처리 중 오류: {e}")
            await queue.enqueue_event(
                new_agent_text_message(
                    context_id=context.context_id or uuid.uuid4().hex,
                    text=f"죄송합니다. 처리 중 오류가 발생했습니다: {str(e)}"
                )
            )
    
    async def cancel(self, context: RequestContext, queue: EventQueue) -> None:
        """작업 취소 (지원하지 않음)"""
        raise Exception("작업 취소는 지원되지 않습니다")

# ──────────────────── 현재 시간 A2A 서버 ───────────────────────────
class CurrentTimeA2AServer:
    """CurrentTimeAgent를 위한 A2A 서버"""
    
    def __init__(self, host: str = "localhost", port: int = 10000):
        self.host = host
        self.port = port
        
        # 에이전트 카드 생성
        self.agent_card = self._create_agent_card()
        
        # Executor 생성
        self.executor = CurrentTimeAgentExecutor()
        
        # HTTP 핸들러 생성
        self.handler = DefaultRequestHandler(
            agent_executor=self.executor,
            task_store=InMemoryTaskStore(),
        )
        
        # A2A Starlette 애플리케이션 생성
        self.app = A2AStarletteApplication(
            agent_card=self.agent_card,
            http_handler=self.handler
        )
    
    def _create_agent_card(self) -> AgentCard:
        """에이전트 카드 생성"""
        capabilities = AgentCapabilities(streaming=False)
        
        skill = AgentSkill(
            id="current_time_agent",
            name="Current Time Assistant",
            description="Provides the current time.",
            tags=["time", "clock", "datetime"],
            examples=["지금 몇 시야?", "현재 시간 알려줘", "몇 시인지 말해줘"]
        )
        
        return AgentCard(
            name="CurrentTimeAgent",
            description="This agent provides the current time.",
            url=f"http://{self.host}:{self.port}/",
            version="1.0.0",
            defaultInputModes=CurrentTimeAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=CurrentTimeAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill]
        )
    
    def start(self):
        """서버 시작"""
        logger.a2a(f"Start {self.agent_card.name} A2A Agent Server From {self.host}:{self.port}")
        
        # Starlette 앱 빌드 및 실행
        starlette_app = self.app.build()
        
        uvicorn.run(
            starlette_app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
