# =============================================================================
# agents/host/orchestrator.py
# =============================================================================

"""
Gemini(OpenAI) LLM 을 사용해 사용자 의도를 파악하고
적절한 Child Agent 로 위임(delegate)하는 OrchestratorAgent.
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List
from dotenv import load_dotenv

# ──────────────────── Google ADK / LLM ────────────────────
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.artifacts import InMemoryArtifactService

# ──────────────────── A2A Connector ───────────────────────
from .agent_connect import AgentConnector

# ──────────────────── 메시지 래핑용 ────────────────────────
from google.genai import types

# ──────────────────── 타입 정의 ───────────────────────────
from a2a.types import AgentCard, Task

# ──────────────────── Custom Logging Configuration ──────────────────────────
from utilities.custom_logger import get_logger

logger = get_logger(__name__)

# ──────────────────── Get API Key From .env ───────────────────────────
load_dotenv() # OPENAI_API_KEY 등 환경변수 로드

# ──────────────────── Conversation Memory ────────────────────────────
class ConversationMemory:
    """대화 기록 관리"""
    
    def __init__(self):
        self.conversations: Dict[str, List[Dict]] = {}
        self.agent_results: Dict[str, Dict] = {} # 세션별 에이전트 결과 저장

    def add_conversation(self, session_id: str, role: str, content: str):
        if session_id not in self.conversations:
            self.conversations[session_id] = []
        self.conversations[session_id].append({
            "role": role, "content": content, "timestamp": uuid.uuid4().hex[:8]
        })

    def add_agent_result(self, session_id: str, agent_name: str, result: str):
        """에이전트 결과 저장"""
        if session_id not in self.agent_results:
            self.agent_results[session_id] = {}
        self.agent_results[session_id][agent_name] = result

    def get_agent_context(self, session_id: str) -> str:
        """이전 에이전트 결과들을 컨텍스트로 반환"""
        if session_id not in self.agent_results:
            return ""
        
        context_lines = []
        for agent_name, result in self.agent_results[session_id].items():
            context_lines.append(f"[{agent_name} 결과]: {result}")
        return "\n".join(context_lines)
    
    def get_conversation_history(self, session_id: str, last_n: int = 5) -> str:
        """대화 기록 조회 - 누락된 메서드 추가"""
        if session_id not in self.conversations:
            return "대화 기록이 없습니다."
        
        recent = self.conversations[session_id][-last_n:]
        history_lines = []
        for entry in recent:
            role_display = "사용자" if entry["role"] == "user" else "어시스턴트"
            history_lines.append(f"{role_display}: {entry['content']}")
        
        return "\n".join(history_lines)

# ──────────────────── OrchestratorAgent Set-Up ────────────────────────────
class OrchestratorAgent:
    """LLM + Tool 로 child-agent 호출을 조합"""
    
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, agent_cards: list[AgentCard]):
        # Child-agent 이름 ↔ AgentConnector
        self.connectors: dict[str, AgentConnector] = {
            card.name: AgentConnector(card.name, card.url) for card in agent_cards
        }
        
        # 메모리 추가
        self.memory = ConversationMemory()
        
        self._agent = self._build_agent()
        self._user_id = "orchestrator_user"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    # ------------------------------------------------------------------ #
    # LLM Agent 구성
    # ------------------------------------------------------------------ #
    def _build_agent(self) -> LlmAgent:
        """
        • system‐prompt = _root_instruction()
        • tools = list_agents(), delegate_task()
        """
        return LlmAgent(
            model=LiteLlm(model="openai/gpt-4o"),
            name="orchestrator_agent",
            description="Routes user queries to child agents with planning.",
            instruction=self._root_instruction,
            tools=[self._list_agents,
                   self._delegate_task,
                   self._get_conversation_history,
                   self._create_plan
            ],
        )

    def _root_instruction(self, ctx: ReadonlyContext) -> str:
        agent_list = "\n".join(f"- {name}" for name in self.connectors)
        return (
            "You are a task-router that analyzes user queries and creates execution plans.\n\n"
        
            "Your workflow:\n"
            "1. ANALYZE user query to understand what information is needed\n"
            "2. PLAN which agents to call and in what order (use create_plan tool)\n"
            "3. EXECUTE plan step by step, passing information between agents\n\n"
            
            "Available Tools:\n"
            "1) list_agents() - List all available agents\n"
            "2) create_plan(query, reasoning) - Create and log execution plan\n"  # 새 도구
            "3) delegate_task(agent_name, message) - Send task to a single agent\n"
            "4) get_conversation_history() - Get previous conversation context\n\n"
            
            "IMPORTANT: Always use create_plan() before executing any delegate_task() calls.\n"
            
            f"Available agents:\n{agent_list}\n\n"
        )

    # ----------------------------- Tool 1 ----------------------------- #
    def _list_agents(self) -> list[str]:
        agent_list = list(self.connectors.keys())
        logger.a2a(f"🔍 [TOOL_CALL] list_agents() → {agent_list}")
        return agent_list

    # ----------------------------- Tool 2 ----------------------------- #
    async def _delegate_task(
            self,
            agent_name: str,
            message: str,
            tool_context: ToolContext,
        ) -> str:

        # 실행 단계 로그 추가 (step number 수정)
        session_id = tool_context.state.get("session_id", "")
        current_results = self.memory.get_agent_context(session_id)
        
        if current_results:
            # 이전 결과가 있으면 줄바꿈으로 나누어 개수 계산
            step_number = len([line for line in current_results.split('\n') if line.strip()]) + 1
        else:
            # 이전 결과가 없으면 첫 번째 단계
            step_number = 1
        
        logger.a2a(f"\t🟢 [EXECUTE-{step_number}] {agent_name} 실행 중...")

        # 로직 시작
        if agent_name not in self.connectors:
            raise ValueError(f"Unknown agent: {agent_name}")

        # 세션 유지
        if "session_id" not in tool_context.state:
            tool_context.state["session_id"] = uuid.uuid4().hex
        session_id: str = tool_context.state["session_id"]
        
        # 이전 에이전트 결과를 컨텍스트로 추가
        previous_context = self.memory.get_agent_context(session_id)
        if previous_context:
            enhanced_message = f"Previous Context:\n{previous_context}\nUser Request: {message}"
            logger.a2a(f"\t🟢 [CONTEXT] 이전 단계 결과를 {agent_name}에게 전달")
        else:
            enhanced_message = message
            logger.a2a(f"\t🟢 [CONTEXT] {agent_name}에게 직접 전달 (첫 번째 단계)")

        try:
            # enhanced_message를 실제로 사용하도록 수정
            result = await self.connectors[agent_name].send_task(enhanced_message, session_id)
            
            # 기존 응답 추출 로직 유지
            if hasattr(result, 'history') and result.history:
                if result.history[-1].parts:
                    last_part = result.history[-1].parts[0]
                    if hasattr(last_part, 'text'):
                        response_text = last_part.text
                    elif hasattr(last_part, 'root') and hasattr(last_part.root, 'text'):
                        response_text = last_part.root.text
                    else:
                        response_text = "응답을 처리할 수 없습니다."
            elif hasattr(result, 'parts') and result.parts:
                last_part = result.parts[0]
                if hasattr(last_part, 'text'):
                    response_text = last_part.text
                elif hasattr(last_part, 'root') and hasattr(last_part.root, 'text'):
                    response_text = last_part.root.text
                else:
                    response_text = "응답을 처리할 수 없습니다."
            else:
                response_text = "응답을 처리할 수 없습니다."
            
            # 에이전트 결과를 메모리에 저장
            self.memory.add_agent_result(session_id, agent_name, response_text)
            
            logger.a2a(f"\t✅ [EXECUTE-{step_number}] {agent_name} 완료 → 결과 저장")
            
            return response_text
            
        except Exception as e:
            logger.error(f"에이전트 {agent_name} 호출 중 오류: {e}")
            logger.error(f"❌ [EXECUTE-{step_number}] {agent_name} 실행 실패: {e}")
            return f"죄송합니다. {agent_name} 에이전트 호출 중 오류가 발생했습니다: {str(e)}"

    # ----------------------------- Tool 3 ----------------------------- #
    def _get_conversation_history(self, tool_context: ToolContext) -> str:
        """대화 기록 조회"""
        session_id = tool_context.state.get("session_id", "default")
        return self.memory.get_conversation_history(session_id)

    # ----------------------------- Tool 4 ----------------------------- #
    def _create_plan(
        self,
        query: str,
        reasoning: str,
        tool_context: ToolContext,
    ) -> str:
        """계획 수립 도구"""
        logger.a2a(
            f"\t📋 [PLAN] Execute plane:\n"
            f"\t├── User Query: {query}\n"
            f"\t└── Plan: {reasoning}"
        )
        return "A Plan is set up"
    # ------------------------------------------------------------------ #
    # 외부 호출 진입점 (Executor 에서 사용)
    # ------------------------------------------------------------------ #
    async def invoke(self, query: str, session_id: str) -> str:
        # 대화 기록에 사용자 쿼리 추가
        self.memory.add_conversation(session_id, "user", query)
        
        # 워크플로우 시작 로그
        logger.a2a(f"\t🟢 [START WORKFLOW] Start workflow for session_id={session_id}")
        logger.a2a(f"\t🟢 [USER_INPUT] {query} (session_id={session_id})")
        

        # 세션 조회/생성 (비동기)
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )

        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=session_id,
                state={},
            )

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)],
        )

        # 비동기 LLM 실행
        events = []
        async for ev in self._runner.run_async(
            user_id=self._user_id,
            session_id=session.id,
            new_message=content,
        ):
            events.append(ev)

        if not events or not events[-1].content or not events[-1].content.parts:
            return ""

        final_response = "\n".join(
            p.text for p in events[-1].content.parts if getattr(p, "text", "")
        )
        # 워크플로우 완료 로그
        logger.a2a(f"\t✅ [AGENT] {final_response}")
        logger.a2a(f"\t✅ [END WORKFLOW] End workflow for session_id={session_id}")
        
        # 대화 기록에 응답 추가
        self.memory.add_conversation(session_id, "assistant", final_response)
        
        return final_response
