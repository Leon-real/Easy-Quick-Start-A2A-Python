"""에이전트 핵심 로직"""
from __future__ import annotations

class TemplateAgent:
    """템플릿 에이전트 - 다른 에이전트 만들 때 복사해서 사용"""
    
    def __init__(self):
        """에이전트 초기화"""
        pass
    
    def _build_agent(self):
        """에이전트 빌드 - 필요시 재정의"""
        pass
    async def process_message(self, message_text: str) -> str:
        """메시지 처리 - 핵심 로직"""
        pass