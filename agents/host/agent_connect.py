# =============================================================================
# agents/host/agent_connect.py
# =============================================================================

"""
원격 A2A 에이전트에 메시지를 보내기 위한 경량 래퍼.
• base_url : "http://localhost:10010" 처럼 에이전트의 루트 URL
• A2AClient.lazy-load : 실제 호출이 들어올 때 /.well-known/agent.json 을 조회해
AgentCard→A2AClient 를 자동 생성한다.
"""

# Python 3.7+ 호환성을 위한 future annotations 임포트
from __future__ import annotations

# UUID 생성을 위한 표준 라이브러리
import uuid

# JSON 파싱을 위한 표준 라이브러리
import json

# HTTP 클라이언트 라이브러리 (비동기 지원)
import httpx

# A2A 프로토콜 클라이언트 및 메시지 생성 함수
from a2a.client import A2AClient, create_text_message_object

# A2A 프로토콜 타입 정의들
from a2a.types import SendMessageRequest, MessageSendParams, Task

# ──────────────────── Custom Logging Configuration ──────────────────────────

# 커스텀 로거 가져오기
from utilities.custom_logger import get_logger

# 현재 모듈명으로 로거 인스턴스 생성
logger = get_logger(__name__)

# ──────────────────── Agent Connector ───────────────────────────

class AgentConnector:
    """child-agent 한 대와 1:1 로 통신하는 헬퍼"""

    def __init__(self, name: str, base_url: str):
        # 에이전트 이름 저장
        self.name = name
        # URL 끝의 슬래시 제거하여 정규화
        self._base_url = base_url.rstrip("/")
        # A2A 클라이언트 지연 초기화 (처음엔 None)
        self._client: A2AClient | None = None # Lazy-init
        # HTTP 클라이언트 인스턴스 보관용 (재사용)
        self._httpx: httpx.AsyncClient | None = None # ⬅️ 보관용

    async def _get_client(self) -> A2AClient:
        """/.well-known/agent.json 을 읽어 A2AClient 를 생성(1회만)"""
        
        # ❶ 처음 한 번만 httpx-client 만들고 재사용
        if self._httpx is None:
            # 300초 타임아웃으로 HTTP 클라이언트 생성
            self._httpx = httpx.AsyncClient(timeout=300)

        # ❷ 이 httpx 인스턴스를 넘겨 A2A Client 생성
        # 에이전트 카드 URL에서 클라이언트 정보를 가져와 A2AClient 생성
        self._client = await A2AClient.get_client_from_agent_card_url(
            self._httpx, self._base_url
        )

        # 생성된 클라이언트 반환
        return self._client

    # --------------------------------------------------------------------- #
    # public API
    # --------------------------------------------------------------------- #

    async def send_task(self, text: str, chat_id: str) -> Task:
        """
        사용자 입력을 Child Agent 로 전달하고 완료 Task 를 돌려받는다.
        """

        # 1. A2AClient 초기화 (Lazy Loading)
        client = await self._get_client() # Agent 카드 조회

        # 2. SendMessageRequest 생성
        request = SendMessageRequest(
            # JSON-RPC 요청 ID (고유 식별자)
            id=uuid.uuid4().hex, # JSON-RPC ID
            params=MessageSendParams(
                # 작업 ID (고유 식별자)
                id=uuid.uuid4().hex, # Task ID
                # 세션 ID (채팅방 구분용)
                sessionId=chat_id,
                # 텍스트 메시지 객체 생성
                message=create_text_message_object(content=text),
            ),
        )


        # (1) Request 로그
        try:
            text_log = json.dumps(json.loads(text), ensure_ascii=False)
        except Exception:
            text_log = text

        # 요청 로그 출력
        logger.a2a(
            f"\n📤 [AgentConnector.send_task]\n"
            f"├── Agent: {self.name}\n"
            f"├── Chat ID: {chat_id}\n"
            f"└── Request: {text_log}"
        )

        # 3. Agent에 HTTP POST 요청
        response = await client.send_message(request)
        
        # (2) Response 로그
        try:
            resp_log = json.dumps(json.loads(str(response)), ensure_ascii=False)
        except Exception:
            resp_log = str(response)
        # 응답 로그 출력
        logger.a2a(
            f"\n📤 [AgentConnector.send_task]\n"
            f"├── Agent: {self.name}\n"
            f"├── Chat ID: {chat_id}\n"
            f"└── Response: {resp_log}"
        )

        # 응답에서 Task 결과 반환
        return response.root.result # → Task
