
from datetime import datetime, timedelta, timezone


# ──────────────────── Custom Logging Configuration ──────────────────────────
from utilities.custom_logger import get_logger
logger = get_logger(__name__)


# ──────────────────── 현재 시간 에이전트 클래스 ───────────────────────────
class CurrentTimeAgent:
    """현재 시간 알려주는 질문에 특화된 AI 에이전트"""
    
    # 지원하는 콘텐츠 타입 정의
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        pass
    
    async def process_message(self, message_text: str) -> str:
        """메시지 처리 (비동기)"""
        try:
            return f"현재 시간은 {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')}입니다. "
        except Exception as e:
            logger.error(f"메시지 처리 중 오류 발생: {e}")
            return f"죄송합니다. 처리 중 오류가 발생했습니다: {str(e)}"
