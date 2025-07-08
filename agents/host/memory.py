# agents/host/memory.py

# 운영체제 인터페이스
import os
# JSON 처리
import json
# UUID 생성
import uuid
# 타입 힌트
from typing import Dict, List

# ─────── Custom Logging Configuration ───────
# 커스텀 로거 임포트
from utilities.custom_logger import get_logger

# ─────── Conversation Memory ───────

class ConversationMemory:
    """대화 기록과 에이전트 결과를 관리하는 클래스"""
    
    # 로그 파일 저장 디렉토리
    LOG_DIR = "./context_log"

    def __init__(self):
        # 대화 기록 저장소 (키: "user_id:chat_id", 값: 대화 리스트)
        self.conversations: Dict[str, List[Dict]] = {}
        # 에이전트 결과 저장소 (키: "user_id:chat_id", 값: {에이전트명: 결과})
        self.agent_results: Dict[str, Dict] = {}
        # 로그 디렉토리 생성 (존재하지 않으면)
        os.makedirs(self.LOG_DIR, exist_ok=True)
        # 로거 인스턴스 생성
        self.logger = get_logger(__name__)
        # 초기화 시 기존 파일들 모두 로드
        self._load_all_files() # Load existing files on initialization

    def key(self, user_id, chat_id):
        """사용자 ID와 채팅 ID를 조합한 키 생성"""
        return f"{user_id}:{chat_id}"

    def _get_log_path(self, user_id, chat_id):
        """로그 파일 경로 생성"""
        return os.path.join(self.LOG_DIR, f"{user_id}_{chat_id}.json")

    def add_conversation(self, user_id, chat_id, role, content):
        """대화 기록 추가"""
        # 키 생성
        key = self.key(user_id, chat_id)
        
        # 해당 키의 대화 기록이 없으면 초기화
        if key not in self.conversations:
            self.conversations[key] = []
            # 파일에서 기존 기록 로드
            self._load_from_file(user_id, chat_id)

        # 새 대화 기록 추가
        self.conversations[key].append({
            "role": role, 
            "content": content, 
            "timestamp": uuid.uuid4().hex[:8]  # 8자리 타임스탬프
        })
        
        # 로그 출력
        self.logger.a2a(f"\t📄 [대화저장] {user_id}/{chat_id} : {role} → {content}")
        
        # 파일에 저장
        self._save_to_file(user_id, chat_id)

    def add_agent_result(self, user_id, chat_id, agent_name, result, step=None):
        """
        멀티턴/스텝 구분 가능하게 각 agent별로 결과를 리스트로 저장.
        step 값 등 추가정보도 entry에 같이 저장.
        """
        key = self.key(user_id, chat_id)
        if key not in self.agent_results:
            self.agent_results[key] = {}
        if agent_name not in self.agent_results[key]:
            self.agent_results[key][agent_name] = []
        elif isinstance(self.agent_results[key][agent_name], str):
            # 과거 문자열 저장된 경우, 리스트로 변환
            self.agent_results[key][agent_name] = [
                {"result": self.agent_results[key][agent_name]}
            ]
        entry = {"result": result}
        if step is not None:
            entry["step"] = step
        self.agent_results[key][agent_name].append(entry)
        self.logger.a2a(f"\t📄 [에이전트결과저장] {user_id}/{chat_id} : {agent_name} → {result} (step={step})")
        self._save_to_file(user_id, chat_id)

    def get_agent_context(
        self, user_id, chat_id, agent_names: list[str]=None, last_n=1, as_list=False
    ):
        """
        멀티턴/워크플로우용 컨텍스트 조회를 구조화해서 제공.
        - agent_names: ["AgentA", ...] 지정시 해당 agent 결과만(최근 last_n개)
        - as_list: True면 [{"agent": agent명, "result": 결과, "step": step}, ...] 리스트 반환
        - as_list: False면 기존대로 string join하여 반환(백워드 호환)
        """
        key = self.key(user_id, chat_id)
        if key not in self.agent_results:
            return [] if as_list else ""
        results = self.agent_results[key]
        out = []

        if agent_names:
            for a in agent_names:
                if a in results and results[a]:
                    for entry in results[a][-last_n:]:
                        # 🔽 entry가 dict가 아니면(=string이면) 감싸서 dict로 변환
                        if isinstance(entry, dict):
                            item = {"agent": a, "result": entry["result"]}
                            if "step" in entry:
                                item["step"] = entry["step"]
                        else:  # string
                            item = {"agent": a, "result": entry}
                        out.append(item)
        else:
            # 전체 agent 중 최근 N개만
            all_items = []
            for a, lst in results.items():
                for entry in lst:
                    if isinstance(entry, dict):
                        item = {"agent": a, "result": entry["result"]}
                        if "step" in entry:
                            item["step"] = entry["step"]
                    else:
                        item = {"agent": a, "result": entry}
                    all_items.append(item)
            all_items = all_items[-last_n:]
            out = all_items

        if as_list:
            return out
        else:
            # string join(구버전 호환)
            return "\n".join(
                f"[{x['agent']}{f' (step {x['step']})' if 'step' in x else ''}] {x['result']}"
                for x in out
            )



    def get_conversation_history(self, user_id, chat_id, last_n=300):
        """최근 N개의 대화 기록 반환"""
        # 키 생성
        key = self.key(user_id, chat_id)
        
        # 해당 키의 대화 기록이 없으면 안내 메시지 반환
        if key not in self.conversations:
            return "대화 기록이 없습니다."

        # 최근 N개 대화 추출
        recent = self.conversations[key][-last_n:]
        lines = []
        
        # 각 대화를 문자열로 변환
        for entry in recent:
            # 역할 표시 변환 (user → 사용자, 그 외 → 어시스턴트)
            role_display = "사용자" if entry["role"] == "user" else "어시스턴트"
            lines.append(f"{role_display}: {entry['content']}")
        
        # 줄바꿈으로 연결하여 반환
        return "\n".join(lines)

    def _save_to_file(self, user_id, chat_id):
        """메모리 데이터를 파일에 저장"""
        # 키 생성
        key = self.key(user_id, chat_id)
        # 파일 경로 생성
        path = self._get_log_path(user_id, chat_id)
        
        # 저장할 데이터 구성
        data = {
            "conversations": self.conversations.get(key, []),
            "agent_results": self.agent_results.get(key, {})
        }

        # JSON 파일로 저장 (UTF-8 인코딩, 들여쓰기 2칸)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 저장 완료 로그
        self.logger.a2a(f"\t 📁 [파일저장] {path}")

    def _load_from_file(self, user_id, chat_id):
        """파일에서 메모리 데이터 로드"""
        # 키 생성
        key = self.key(user_id, chat_id)
        # 파일 경로 생성
        path = self._get_log_path(user_id, chat_id)
        
        # 파일 존재 확인
        if os.path.exists(path):
            # JSON 파일 읽기
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 데이터 복원
            self.conversations[key] = data.get("conversations", [])
            self.agent_results[key] = data.get("agent_results", {})
            
            # 로드 완료 로그
            self.logger.a2a(f"\t🗄️ [파일불러오기] {path} → 대화 {len(self.conversations[key])}건")
        else:
            # 파일이 없는 경우 로그
            self.logger.a2a(f"\t❌ [파일없음] {path}")

    def _load_all_files(self):
        """로그 디렉토리의 모든 파일을 로드"""
        # 디렉토리 내 모든 파일 순회
        for fname in os.listdir(self.LOG_DIR):
            # JSON 파일만 처리
            if fname.endswith(".json"):
                try:
                    # 파일명에서 확장자 제거
                    user_chat = fname[:-5] # remove .json
                    # 언더스코어로 분리하여 user_id, chat_id 추출
                    user_id, chat_id = user_chat.split("_", 1)
                    # 파일에서 데이터 로드
                    self._load_from_file(user_id, chat_id)
                except Exception as e:
                    # 로드 실패 시 에러 출력
                    print(f"Failed to load {fname}: {e}")
