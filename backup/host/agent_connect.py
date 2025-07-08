# =============================================================================
# agents/host/agent_connect.py
# =============================================================================
"""
원격 A2A 에이전트에 메시지를 보내기 위한 경량 래퍼.

• base_url            : "http://localhost:10010" 처럼 에이전트의 루트 URL
• A2AClient.lazy-load : 실제 호출이 들어올 때 /.well-known/agent.json 을 조회해
                         AgentCard→A2AClient 를 자동 생성한다.
"""
from __future__ import annotations

import uuid

import httpx
from a2a.client import A2AClient, create_text_message_object
from a2a.types import SendMessageRequest, MessageSendParams, Task

# ──────────────────── Custom Logging Configuration ──────────────────────────
from utilities.custom_logger import get_logger
logger = get_logger(__name__)

# ──────────────────── Agent Connector ───────────────────────────
class AgentConnector:
    """child-agent 한 대와 1:1 로 통신하는 헬퍼"""

    def __init__(self, name: str, base_url: str):
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._client: A2AClient | None = None  # Lazy-init
        self._httpx: httpx.AsyncClient | None = None   # ⬅️ 보관용

    async def _get_client(self) -> A2AClient:
        """/.well-known/agent.json 을 읽어 A2AClient 를 생성(1회만)""" 
        # ❶ 처음 한 번만 httpx-client 만들고 재사용
        if self._httpx is None:
            self._httpx = httpx.AsyncClient(timeout=300)

            # ❷ 이 httpx 인스턴스를 넘겨 A2AClient 생성
            self._client = await A2AClient.get_client_from_agent_card_url(
                self._httpx, self._base_url
            )
        return self._client

    # --------------------------------------------------------------------- #
    # public API
    # --------------------------------------------------------------------- #
    async def send_task(self, text: str, session_id: str) -> Task:
        """
        사용자 입력을 Child Agent 로 전달하고 완료 Task 를 돌려받는다.
        """
        # 1. A2AClient 초기화 (Lazy Loading)
        client = await self._get_client() # Agent 카드 조회

        # 2. SendMessageRequest 생성
        request = SendMessageRequest(
            id=uuid.uuid4().hex,  # JSON-RPC ID
            params=MessageSendParams(
                id=uuid.uuid4().hex,            # Task ID
                sessionId=session_id,
                message=create_text_message_object(content=text),
            ),
        )

        logger.a2a(
            f"\n📤 [AgentConnector.send_task]\n"
            f"├── Agent: {self.name}\n"
            f"├── Session ID: {session_id}\n"
            f"└── Request: {text}"
        )
        # 3. Agent에 HTTP POST 요청
        response = await client.send_message(request)

        logger.a2a(
            f"\n📤 [AgentConnector.send_task]\n"
            f"├── Agent: {self.name}\n"
            f"├── Session ID: {session_id}\n"
            f"└── Response: {response}"
        )

        return response.root.result  # → Task
