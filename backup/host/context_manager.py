# =============================================================================
# agents/host/context_manager.py
# =============================================================================
"""
프레임워크 독립적인 컨텍스트 관리자
• 사용자별, 세션별 대화 기록 관리
• 파일 기반 저장 (DB 없이도 동작)
• 향후 다른 프레임워크로 확장 가능
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# ──────────────────── Custom Logging Configuration ──────────────────────────
from utilities.custom_logger import get_logger

logger = get_logger(__name__)

# ──────────────────── Conversation Context ────────────────────────────
class ConversationContext:
    """단일 대화 컨텍스트"""
    
    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id
        self.messages: List[Dict] = []
        self.agent_results: Dict[str, Any] = {}
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def add_message(self, role: str, content: str, agent_name: Optional[str] = None):
        """메시지 추가"""
        self.messages.append({
            "role": role,
            "content": content,
            "agent_name": agent_name,
            "timestamp": datetime.now().isoformat()
        })
        self.updated_at = datetime.now()
        
        logger.debug(f"메시지 추가: {role} - {agent_name or 'user'}")
    
    def get_conversation_history(self, format_type: str = "text", last_n: int = 10) -> str:
        """다양한 형태로 대화 히스토리 반환"""
        recent_messages = self.messages[-last_n:] if last_n > 0 else self.messages
        
        if format_type == "json":
            return json.dumps(recent_messages, ensure_ascii=False, indent=2)
        
        # 텍스트 형태
        history_lines = []
        for msg in recent_messages:
            role_display = "사용자" if msg["role"] == "user" else "어시스턴트"
            if msg.get("agent_name"):
                role_display += f"({msg['agent_name']})"
            history_lines.append(f"{role_display}: {msg['content']}")
        
        return "\n".join(history_lines)
    
    def get_agent_context(self) -> str:
        """에이전트 결과들을 컨텍스트로 반환 (기존 메모리와 호환)"""
        context_lines = []
        for agent_name, result in self.agent_results.items():
            context_lines.append(f"[{agent_name} 결과]: {result}")
        return "\n".join(context_lines)
    
    def add_agent_result(self, agent_name: str, result: str):
        """에이전트 결과 저장"""
        self.agent_results[agent_name] = result

# ──────────────────── Context Manager ────────────────────────────
class ContextManager:
    """프레임워크 독립적인 컨텍스트 관리자"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.contexts: Dict[str, ConversationContext] = {}
        self.storage_path = Path(storage_path) if storage_path else Path("./contexts")
        self.storage_path.mkdir(exist_ok=True)
        
        logger.info(f"컨텍스트 매니저 초기화: {self.storage_path}")
    
    def _get_context_key(self, user_id: str, session_id: str) -> str:
        """컨텍스트 키 생성"""
        return f"{user_id}:{session_id}"
    
    def get_or_create_context(self, user_id: str, session_id: str) -> ConversationContext:
        """컨텍스트 조회 또는 생성"""
        key = self._get_context_key(user_id, session_id)
        
        if key not in self.contexts:
            # 파일에서 로드 시도
            context_file = self.storage_path / f"{key.replace(':', '_')}.json"
            if context_file.exists():
                try:
                    self.contexts[key] = self._load_context_from_file(context_file)
                    logger.debug(f"컨텍스트 파일에서 로드: {key}")
                except Exception as e:
                    logger.warning(f"컨텍스트 로드 실패 ({key}): {e}")
                    self.contexts[key] = ConversationContext(user_id, session_id)
            else:
                self.contexts[key] = ConversationContext(user_id, session_id)
                logger.debug(f"새 컨텍스트 생성: {key}")
        
        return self.contexts[key]
    
    def save_context(self, user_id: str, session_id: str):
        """컨텍스트를 파일에 저장"""
        key = self._get_context_key(user_id, session_id)
        if key in self.contexts:
            context_file = self.storage_path / f"{key.replace(':', '_')}.json"
            try:
                self._save_context_to_file(self.contexts[key], context_file)
                logger.debug(f"컨텍스트 저장: {key}")
            except Exception as e:
                logger.error(f"컨텍스트 저장 실패 ({key}): {e}")
    
    def _load_context_from_file(self, file_path: Path) -> ConversationContext:
        """파일에서 컨텍스트 로드"""
        data = json.loads(file_path.read_text(encoding='utf-8'))
        context = ConversationContext(data['user_id'], data['session_id'])
        context.messages = data.get('messages', [])
        context.agent_results = data.get('agent_results', {})
        
        # 날짜 복원
        if 'created_at' in data:
            context.created_at = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data:
            context.updated_at = datetime.fromisoformat(data['updated_at'])
            
        return context
    
    def _save_context_to_file(self, context: ConversationContext, file_path: Path):
        """컨텍스트를 파일에 저장"""
        data = {
            'user_id': context.user_id,
            'session_id': context.session_id,
            'messages': context.messages,
            'agent_results': context.agent_results,
            'created_at': context.created_at.isoformat(),
            'updated_at': context.updated_at.isoformat()
        }
        file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    
    def list_user_sessions(self, user_id: str) -> List[str]:
        """특정 사용자의 모든 세션 ID 반환"""
        sessions = []
        for file_path in self.storage_path.glob(f"{user_id}_*.json"):
            try:
                parts = file_path.stem.split('_', 1)
                if len(parts) == 2:
                    sessions.append(parts[1])
            except Exception as e:
                logger.warning(f"세션 파일 파싱 실패: {file_path} - {e}")
        return sessions
    
    def cleanup_old_contexts(self, days: int = 30):
        """오래된 컨텍스트 파일 정리"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cleaned_count = 0
        
        for file_path in self.storage_path.glob("*.json"):
            try:
                if file_path.stat().st_mtime < cutoff_date.timestamp():
                    file_path.unlink()
                    cleaned_count += 1
            except Exception as e:
                logger.warning(f"파일 정리 실패: {file_path} - {e}")
        
        if cleaned_count > 0:
            logger.info(f"오래된 컨텍스트 파일 {cleaned_count}개 정리 완료")
