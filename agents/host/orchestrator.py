# =============================================================================
# agents/host/orchestrator.py
# =============================================================================

"""
Gemini(OpenAI) LLM을 사용해 사용자 의도를 파악하고
적절한 Child Agent로 위임(delegate)하는 OrchestratorAgent.
"""

# Python 3.7+ 호환성을 위한 future annotations 임포트
from __future__ import annotations

# UUID 생성
import uuid
# 타입 힌트
from typing import Any, Dict, List

# JSON 처리
import json

# 환경 변수 로드
from dotenv import load_dotenv

# ─────── Google ADK / LLM ───────

# Google ADK의 LLM 에이전트
from google.adk.agents.llm_agent import LlmAgent
# LiteLLM 모델 (다양한 LLM 지원)
from google.adk.models.lite_llm import LiteLlm
# 읽기 전용 컨텍스트
from google.adk.agents.readonly_context import ReadonlyContext
# 도구 컨텍스트
from google.adk.tools.tool_context import ToolContext
# 에이전트 실행기
from google.adk.runners import Runner
# 인메모리 세션 서비스
from google.adk.sessions import InMemorySessionService
# 인메모리 메모리 서비스
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
# 인메모리 아티팩트 서비스
from google.adk.artifacts import InMemoryArtifactService

# ─────── A2A Connector ───────

# 에이전트 연결 모듈
from .agent_connect import AgentConnector
# 메모리 관리 모듈
from .memory import ConversationMemory

# ─────── 메시지 래핑용 ───────
# Google GenAI 타입
from google.genai import types

# ─────── 타입 정의 ───────
# A2A 타입들
from a2a.types import AgentCard, Task

# ─────── Custom Logging Configuration ───────
# 커스텀 로거
from utilities.custom_logger import get_logger

# 현재 모듈 로거 생성
logger = get_logger(__name__)

# ─────── Get API Key From .env ───────

# .env 파일에서 환경 변수 로드
load_dotenv()

# ─────── OrchestratorAgent Set-Up ───────

class OrchestratorAgent:
    """LLM + Tool로 child-agent 호출을 조합"""

    # 지원하는 콘텐츠 타입 정의
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, agent_cards: list[AgentCard]):
        # Child-agent 이름 ↔ AgentConnector 매핑
        self.connectors: dict[str, AgentConnector] = {
            card.name: AgentConnector(card.name, card.url) for card in agent_cards
        }

        # 🔥 핵심: agent_cards를 저장해서 재활용
        self.agent_cards = agent_cards  # ← 이 한 줄만 추가
        # 🚀 새로운 부분: 초기화 시점에 instruction 미리 생성
        self._cached_agent_info = self._generate_agent_info()

        # 메모리 추가
        self.memory = ConversationMemory()
        
        # LLM 에이전트 구성
        self._agent = self._build_agent()
        
        # 기본 사용자 ID
        self._user_id = "orchestrator_user"
        
        # 에이전트 실행기 구성
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    def _generate_agent_info(self) -> str:
        """초기화 시점에 에이전트 정보를 한 번만 생성"""
        
        def format_agent_card(card: AgentCard) -> str:
            """AgentCard를 A2A 규격에 맞춰 포맷팅"""
            
            # 기본 정보
            info_lines = [
                f"**{card.name}** (v{card.version})",
                f"  📝 Description: {card.description}",
                f"  🌐 URL: {card.url}",
                f"  📋 Protocol: {getattr(card, 'protocolVersion', 'N/A')}"
            ]
            
            # 프로바이더 정보
            if card.provider:
                provider_name = getattr(card.provider, 'name', 'Unknown')
                info_lines.append(f"  🏢 Provider: {provider_name}")
            
            # 입출력 모드
            if card.defaultInputModes:
                info_lines.append(f"  📥 Input Modes: {', '.join(card.defaultInputModes)}")
            if card.defaultOutputModes:
                info_lines.append(f"  📤 Output Modes: {', '.join(card.defaultOutputModes)}")
            
            # 능력 정보
            if card.capabilities:
                capabilities_info = []
                if hasattr(card.capabilities, 'streaming'):
                    capabilities_info.append(f"Streaming: {card.capabilities.streaming}")
                if capabilities_info:
                    info_lines.append(f"  ⚡ Capabilities: {', '.join(capabilities_info)}")
            
            # 스킬 정보
            if card.skills:
                skills_info = []
                for skill in card.skills:
                    skill_parts = []
                    if hasattr(skill, 'name'):
                        skill_parts.append(f"Name: {skill.name}")
                    if hasattr(skill, 'description'):
                        skill_parts.append(f"Description: {skill.description}")
                    if hasattr(skill, 'examples') and skill.examples:
                        skill_parts.append(f"Examples: {', '.join(skill.examples)}")
                    if hasattr(skill, 'tags') and skill.tags:
                        skill_parts.append(f"Tags: {', '.join(skill.tags)}")
                    
                    if skill_parts:
                        skills_info.append(f"[{'; '.join(skill_parts)}]")
                
                if skills_info:
                    info_lines.append(f"  🛠️ Skills: {'; '.join(skills_info)}")
            
            # 추가 정보들
            if hasattr(card, 'documentationUrl') and card.documentationUrl:
                info_lines.append(f"  📚 Documentation: {card.documentationUrl}")
            
            if hasattr(card, 'iconUrl') and card.iconUrl:
                info_lines.append(f"  🎨 Icon: {card.iconUrl}")
            
            if hasattr(card, 'preferredTransport') and card.preferredTransport:
                info_lines.append(f"  🚀 Preferred Transport: {card.preferredTransport}")
            
            if hasattr(card, 'additionalInterfaces') and card.additionalInterfaces:
                interface_info = []
                for interface in card.additionalInterfaces:
                    if hasattr(interface, 'transport'):
                        interface_info.append(interface.transport)
                if interface_info:
                    info_lines.append(f"  🔗 Additional Interfaces: {', '.join(interface_info)}")
            
            if hasattr(card, 'security') and card.security:
                info_lines.append(f"  🔒 Security: Required")
            
            if hasattr(card, 'supportsAuthenticatedExtendedCard') and card.supportsAuthenticatedExtendedCard:
                info_lines.append(f"  🔐 Extended Card Support: Yes")
            
            return "\n".join(info_lines)
        
        # 모든 에이전트 정보를 한 번만 생성
        agent_info = "\n\n".join(format_agent_card(card) for card in self.agent_cards)
        logger.a2a(f"🔍 [AGENT INFO] Available agents:\n{agent_info}")
        return agent_info
    # --------------- LLM Agent 구성 ---------------

    def _build_agent(self) -> LlmAgent:
        """LLM 에이전트 빌드"""
        return LlmAgent(
            # OpenAI GPT-4o 모델 사용
            model=LiteLlm(model="openai/gpt-4o"),
            name="orchestrator_agent",
            description="Routes user queries to child agents with planning.",
            # 루트 인스트럭션 설정
            instruction=self._root_instruction,
            # 사용 가능한 도구들
            tools=[
                self._list_agents,
                self._delegate_task,
                self._get_conversation_history,
                self._create_plan
            ],
        )

    def _root_instruction(self, ctx: ReadonlyContext) -> str:
        """LLM에게 제공할 루트 인스트럭션"""
        # LLM Instruction 반환
        return (
            "You are a STRICT TASK ROUTER. Your ONLY job is to route user queries to appropriate remote agents.\n\n"

            "🚨 ABSOLUTE RULES (NEVER VIOLATE):\n"
            "1. NEVER provide direct answers to user questions\n"
            "2. NEVER use your own knowledge to answer anything\n"
            "3. ALWAYS delegate information queries to remote agents (except system/memory requests)\n"
            "4. ALWAYS create a plan using create_plan() before delegation\n"
            "5. ONLY respond directly for:\n"
            "   - Agent list requests (use list_agents())\n"
            "   - Conversation history requests (use get_conversation_history())\n"
            "   - System errors or failures\n"
            "   - Clarification requests when user input is unclear\n\n"

            "📝 SPECIAL POLICY FOR CONVERSATION HISTORY AND CONTEXT:\n"
            "- Whenever the user refers to or requests previous conversations (e.g., 'previous conversation', 'last time', 'what I said before', '지난 번 얘기', '전에 했던 질문', '그때 대답 기억나?', 'based on what I asked earlier', etc.), you MUST first analyze the user's intent and request.\n"
            "- If the user is simply asking whether you remember, or wants a confirmation (e.g., 'Do you remember our conversation?', '나랑 대화했던 거 기억나?'), reply briefly that you remember and have the conversation history stored, without outputting the entire conversation, unless the user explicitly requests to see the history.\n"
            "- If the user requests to see all previous conversations, or explicitly asks for the history (e.g., 'show me the conversation', '대화 기록 다 보여줘', '지난 대화 모두 알려줘'), you MUST output the entire raw result of get_conversation_history(), verbatim, with no omission, summarization, or paraphrasing.\n"
            "- If the user requests a summary or asks a question based on a previous conversation (e.g., 'summarize what we discussed before', '지난번 얘기 기반으로 알려줘'), you MUST use get_conversation_history() as reference context for agent calls or your output, and make it clear which previous parts are relevant.\n"
            "- If the history is too long for one reply, display as much as possible and inform the user about truncation."

            
            "📋 MANDATORY WORKFLOW:\n"
            "Step 1: ANALYZE the user query intent and scope:\n"
            "   - Is it a simple confirmation request? → Brief direct response\n"
            "   - Is it a specific information request? → Plan and delegate\n"
            "   - Is it a detailed history request? → Use appropriate tool with matching scope\n"
            "   - Is it a complex request combining multiple needs? → Handle each component appropriately\n"
            "Step 2: PLAN using create_plan() - explain which agent to use, why, and the required step order.\n"
            "Step 3: For each step in the plan, generate the **minimal, agent-specific sub-query** for the target agent, based on its purpose and specialization. "
            "Do NOT simply forward or paraphrase the entire user query unless it is truly required for that agent to function. "
            "For example, when invoking a time agent, send only a direct time request (e.g., 'What is the current time?'). "
            "When invoking an agent that needs previous step results (such as a food agent needing time information), synthesize a new sub-query by combining ONLY the necessary outputs from prior agents with the specific user intent. "
            "Always respond to every tool_call_id with a proper tool message. If multiple tools are called, reply to each one in order."
            "NEVER include more context than needed, and always minimize the query. \n"
            "Step 4: DELEGATE using delegate_task() to send each sub-query and required context to the corresponding agent.\n"
            "Step 5: RELAY each agent's response without any modification or addition.\n\n"
            
            "🔗 CONTEXT POLICY:\n"
            "- When delegating to a remote agent, always include **only the minimum required context for that specific agent and sub-query**.\n"
            "- If the user query requires a multi-turn chain (delegation to multiple agents), for each agent, always generate a specialized sub-query and pass ONLY the outputs from agents"
            "- Do NOT send the entire conversation or all agent results by default. Dynamically construct the context to include only the necessary outputs from previous steps, never more.\n"
            "- For real-time or time-sensitive queries (time, date, weather, stock prices, etc.), always fetch **fresh** data from the appropriate agent, even if previous similar results exist.\n"
            "- If the user query requires combining or synthesizing results from many agents, do so step-by-step: first gather the required data, then pass it to the next relevant agent as context for final synthesis.\n"
            "- Never include irrelevant information in agent calls. The more minimal the query and context, the better.\n"

            "🎯 AGENT SELECTION & SCALABILITY:\n"
            "- Select agents based on their specializations and the requirements of the query.\n"
            "- In cases where many agents might be relevant (large-scale scenarios), prioritize only those directly related to the query. Do NOT broadcast or fan out to all agents unless the task truly requires all their data.\n"
            "- If a query requires a large number of agent results (e.g., aggregate info from many agents), manage context size and agent call efficiency carefully—**plan, fetch, and compose results modularly.**\n"

            "❌ FORBIDDEN BEHAVIORS:\n"
            "- Never answer questions yourself, never summarize or synthesize beyond routing.\n"
            "- Never simply copy and forward the original user query to all agents.\n"
            "- Do not include unnecessary context or history when delegating.\n"
            "- Never overload agents with irrelevant information or excessive context.\n"
            "- Never simply copy and forward the original user query to all agents. Always create step- and agent-specific sub-queries.\n"

            "⚠️ IMPORTANT NOTES:\n"
            "- You are a ROUTER, not a knowledge provider. Route efficiently, contextually, and with minimal overhead.\n"
            "- For each agent, pass only what is necessary for that agent to fulfill its role.\n"
            "- For complex workflows, dynamically manage dependencies and context.\n"
            "- Trust agents to provide accurate answers—never alter or interpret their outputs yourself.\n"

            f"Available agents and informations:\n{self._cached_agent_info}\n\n"

            "Remember: ROUTE, DON'T ANSWER. For each step, generate and delegate only the minimal, most relevant sub-query and context for the agent, based strictly on the agent's function and the planned workflow."
        )


    # ----- Tool 1 -----

    def _list_agents(self) -> list[str]:
        """사용 가능한 에이전트 목록 반환"""
        # 에이전트 이름 리스트 생성
        agent_list = list(self.connectors.keys())
        
        # 로그 출력
        logger.a2a(f"🔍 [TOOL_CALL] list_agents() → {agent_list}")
        return agent_list

    # ----- Tool 2 -----

    async def _delegate_task(
        self,
        agent_name: str,
        message: str,
        tool_context: ToolContext,
        **kwargs        # ← 이거 추가!
    ) -> str:
        """
        특정 에이전트에게 작업 위임 (구조화된 context object 전달, granularity 조절)
        """

        # user_id, chat_id 추출
        user_id = tool_context.state.get("user_id", "")
        chat_id = tool_context.state.get("chat_id", "")

        # [step_number] 플랜별(즉, 이번 요청별) 카운터 증가
        if "step_number" not in tool_context.state:
            tool_context.state["step_number"] = 1
        else:
            tool_context.state["step_number"] += 1
        step_number = tool_context.state["step_number"]

        logger.a2a(f"\t🟢 [EXECUTE-{step_number}] {agent_name} 실행 중...")

        # Agent validation
        if agent_name not in self.connectors:
            raise ValueError(f"Unknown agent: {agent_name}")

        # 3) context object 생성 (여기서 원하는 형태로 조정)
        context_obj = {
            "user_message": message,
        }

        logger.a2a(f"\t🟢 [CONTEXT] {agent_name}에게 messeage : {message} 전달 ")

        try:
            # 4) json 직렬화해서 전달 (agent에서 object로 바로 파싱 가능)
            result = await self.connectors[agent_name].send_task(
                json.dumps(context_obj), chat_id
            )

            # 아래 결과 파싱/저장 로직은 기존과 동일
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

            # 결과 저장 (step 추가 가능)
            self.memory.add_agent_result(user_id, chat_id, agent_name, response_text, step=step_number)
            logger.a2a(f"\t✅ [EXECUTE-{step_number}] {agent_name} Success.")
            return response_text

        except Exception as e:
            logger.error(f"에이전트 {agent_name} 호출 중 오류: {e}")
            logger.error(f"❌ [EXECUTE-{step_number}] {agent_name} Fail: {e}")
            return f"죄송합니다. {agent_name} 에이전트 호출 중 오류가 발생했습니다: {str(e)}"

    # ----- Tool 3 -----

    def _get_conversation_history(self, tool_context: ToolContext) -> str:
        """대화 기록 가져오기"""
        # 컨텍스트에서 ID 추출
        user_id = tool_context.state.get("user_id", "")
        chat_id = tool_context.state.get("chat_id", "")
        
        # 메모리에서 대화 기록 반환
        return self.memory.get_conversation_history(user_id, chat_id)

    # ----- Tool 4 -----

    def _create_plan(
        self,
        query: str,
        reasoning: str,
        tool_context: ToolContext,
    ) -> str:
        """실행 계획 생성"""
        
        # Plan 생성 로그
        logger.a2a(
            f"\t📋 [PLAN] Execution plan created:\n"
            f"\t├── User Query: {query}\n"
            f"\t├── Reasoning: {reasoning}\n"
            f"\t└── Next Action: Delegate to appropriate agent"
        )

        # 계획 설정 완료 메시지 반환
        return "A Plan is set up"

    # ---- 진입점 (Executor에서 사용) ----

    async def invoke(self, query: str, user_id: str, chat_id: str) -> str:
        """오케스트레이터 호출 진입점"""
        
        # 사용자 입력을 대화 기록에 추가
        self.memory.add_conversation(user_id, chat_id, "user", query)
        
        # 워크플로우 시작 로그
        logger.a2a(f"\t🟢 [START WORKFLOW] Start workflow for User ID={user_id}")
        logger.a2a(f"\t🟢 [USER_INPUT] {query} (Chat ID={chat_id})")

        # 세션 서비스에 chat_id를 session_id로 전달
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=chat_id,
        )

        if session is None:
            # 세션이 없으면 새로 생성
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=chat_id,
                state={"user_id": user_id, "chat_id": chat_id},
            )
        else:
            # 기존 세션에 상태 업데이트
            session.state["user_id"] = user_id
            session.state["chat_id"] = chat_id

        # 사용자 메시지 콘텐츠 생성
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)],
        )

        # 이벤트 수집용 리스트
        events = []
        
        # 에이전트 실행 (비동기 스트림)
        async for ev in self._runner.run_async(
            user_id=self._user_id,
            session_id=session.id,
            new_message=content,
        ):
            events.append(ev)

        # 응답이 없는 경우 빈 문자열 반환
        if not events or not events[-1].content or not events[-1].content.parts:
            return ""

        # 최종 응답 텍스트 추출
        final_response = "\n".join(
            p.text for p in events[-1].content.parts if getattr(p, "text", "")
        )

        # 응답 로그
        logger.a2a(f"\t✅ [AGENT] {final_response}")
        logger.a2a(f"\t✅ [END WORKFLOW] End workflow for Chat ID={chat_id}")

        # 어시스턴트 응답을 대화 기록에 추가
        self.memory.add_conversation(user_id, chat_id, "assistant", final_response)

        # 최종 응답 반환
        return final_response
