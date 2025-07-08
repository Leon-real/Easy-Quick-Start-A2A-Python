"""A2A 서버 구현"""
import uuid
from typing import Dict, Any
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from a2a.server.apps import A2AStarletteApplication
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils import new_agent_text_message
import uvicorn
from utilities.custom_logger import get_logger
from .agent import TemplateAgent
logger = get_logger(__name__)

class TemplateAgentExecutor(AgentExecutor):
    """에이전트 실행자"""

    def __init__(self):
        # 에이전트 초기화   
        self.agent = TemplateAgent()

    # ──────────────────── TemplateAgentExecutor ───────────────────────────
    async def execute(self, context: RequestContext, queue: EventQueue) -> None:
        """메시지 실행 - A2A 표준에 따른 구현"""
        try:
            # 1. 컨텍스트에서 사용자 입력 추출
            user_text = context.get_user_input()
            session_id = context.context_id or uuid.uuid4().hex
            
            # 2. 로깅 (필요시 추가)
            ###
            
            # 3. 에이전트 처리 (여기서 실제 AI 로직 실행)
            response_text = await self.agent.process_message(user_text)
            
            # 4. 응답 메시지 이벤트를 큐에 발행 (A2A 표준)
            await queue.enqueue_event(
                new_agent_text_message(
                    context_id=session_id,
                    text=f"TemplateAgent: {response_text}"
                )
            )
            
            # 5. 완료 로깅 (필요시 추가)
            ###
            pass
            
        except Exception as e:
            # 에러 발생 시 에러 메시지도 이벤트로 발행
            logger.error(f"TemplateAgent 처리 중 오류: {e}")
            await queue.enqueue_event(
                new_agent_text_message(
                    context_id=context.context_id or uuid.uuid4().hex,
                    text=f"죄송합니다. 처리 중 오류가 발생했습니다: {str(e)}"
                )
            )

    async def cancel(self, context: RequestContext, queue: EventQueue) -> None:
        """작업 취소"""
        raise Exception("작업 취소는 지원되지 않습니다")

class TemplateA2AServer:
    """A2A 서버 - 거의 수정할 필요 없음"""

    def __init__(self, host: str = None, port: int = 10000):
        self.host = host or "localhost"
        self.port = port or 10000

        # 에이전트 카드 생성
        self.agent_card = self._create_agent_card()

        # 실행자 및 핸들러 생성
        self.executor = TemplateAgentExecutor()
        self.handler = DefaultRequestHandler(
            agent_executor=self.executor,
            task_store=InMemoryTaskStore()
        )

        # A2A 애플리케이션 생성
        self.app = A2AStarletteApplication(
            agent_card=self.agent_card,
            http_handler=self.handler
        )

    def _create_agent_card(self) -> AgentCard:
        """에이전트 카드 생성 - 기본값 사용"""
        capabilities = AgentCapabilities(streaming=False)
        skill = AgentSkill(
            id="template_agent",
            name="TemplateAgent",
            description="템플릿 에이전트입니다",
            tags=["template", "general"],
            examples=["안녕하세요", "도움이 필요합니다"]
        )

        return AgentCard(
            name="TemplateAgent",
            description="템플릿 에이전트입니다",
            url=f"http://{self.host}:{self.port}/",
            version="1.0.0",
            defaultInputModes=["text", "text/plain"],
            defaultOutputModes=["text", "text/plain"],
            capabilities=capabilities,
            skills=[skill]
        )

    def start(self):
        """서버 시작"""
        logger.a2a(f"Start TemplateAgent A2A Server From {self.host}:{self.port}")
        starlette_app = self.app.build()
        uvicorn.run(starlette_app, host=self.host, port=self.port, log_level="info")
