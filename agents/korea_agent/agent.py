from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken
from dotenv import load_dotenv
import os
import asyncio
# ──────────────────── Custom Logging Configuration ──────────────────────────
from utilities.custom_logger import get_logger
logger = get_logger(__name__)

# ──────────────────── Get API Key From .env ───────────────────────────
load_dotenv()

# ──────────────────── KoreaAgent Class Definition ────────────────────
class KoreaAgent:
    """한국 관련 질문에 특화된 AI 에이전트"""
    
    # 지원하는 콘텐츠 타입 정의
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        """KoreaAgent 초기화"""
        # OPENAI_API_KEY 환경 변수 확인
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")

        # OpenAI 채팅 완성 클라이언트 초기화
        self.model_client = OpenAIChatCompletionClient(
            model="gpt-4o",
            api_key=os.getenv("OPENAI_API_KEY")
        )

        # Autogen AssistantAgent 초기화
        self.agent = AssistantAgent(
            name="KoreaAgent",
            system_message=(
                "당신은 한국을 대표하는 에이전트입니다. "
                "한국의 역사, 문화, 음식, 관광지, 언어 등과 관련된 질문에 답변하세요. "
                "한국과 관련된 정보를 제공하거나 요청에 적합한 응답을 생성하세요."
            ),
            model_client=self.model_client
        )

    async def process_message(self, message_text: str) -> str:
        """메시지 처리 (비동기)"""
        try:
            response = await self.agent.on_messages(
                messages=[TextMessage(content=message_text, source="user")],
                cancellation_token=CancellationToken()
            )

            # logging
            logger.a2a(
                f"\n📤 [{self.agent}::]\n"
                f"├── Request Message: {message_text}\n"
                f"├── Response: {response}\n"
                f"└── Status: Done"
            )
            return response.chat_message.content
        except Exception as e:
            logger.error(f"메시지 처리 중 오류 발생: {e}")
            return f"죄송합니다. 처리 중 오류가 발생했습니다: {str(e)}"
