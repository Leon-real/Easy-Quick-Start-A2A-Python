# =============================================================================
# a2a_test/utilities/custom_logger.py
# 커스텀 로그 레벨(A2A)을 추가하고, 로그 레벨 필터링 및 색상 출력 기능을 설정하는 모듈
# =============================================================================

import logging  # 기본 로깅 기능을 제공하는 표준 라이브러리
from colorlog import ColoredFormatter  # 로그를 컬러로 포맷하기 위한 외부 라이브러리

# ─────────────────────────────────────────────────────────────────────────────
# 🔸 A2A 전용 커스텀 로그 레벨 정의
# ─────────────────────────────────────────────────────────────────────────────

A2A_LEVEL = 25  # INFO(20)와 WARNING(30) 사이의 사용자 정의 로그 레벨
logging.addLevelName(A2A_LEVEL, "A2A")  # 숫자 레벨과 문자열 레벨명을 연결하여 등록

def a2a_log(self, message, *args, **kwargs):
    """logger.a2a(...)로 A2A 로그 기록을 가능하게 하는 사용자 정의 메서드"""
    if self.isEnabledFor(A2A_LEVEL):  # 현재 로거가 A2A 레벨 이상이면
        self._log(A2A_LEVEL, message, args, **kwargs)  # 로그를 A2A 레벨로 기록

# Logger 클래스에 a2a() 메서드를 동적으로 추가
logging.Logger.a2a = a2a_log

# ─────────────────────────────────────────────────────────────────────────────
# 🔸 기본 로깅 설정
# ─────────────────────────────────────────────────────────────────────────────

# 기본 로깅 레벨을 INFO로 설정하여, 그 이상 레벨의 로그만 기본 출력
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────
# 🔸 로그 출력 포맷 정의 (컬러 포함)
# ─────────────────────────────────────────────────────────────────────────────

formatter = ColoredFormatter(
    fmt="%(log_color)s[%(levelname)s] %(name)s:%(reset)s \n%(message)s",  # 출력 형식 정의
    log_colors={  # 각 로그 레벨별 컬러 정의
        "DEBUG":    "cyan",
        "INFO":     "green",
        "WARNING":  "yellow",
        "ERROR":    "red",
        "CRITICAL": "bold_red,bg_white",
        "A2A":      "bold_yellow",  # A2A 레벨은 강조된 노란색으로 표시
    }
)

# ─────────────────────────────────────────────────────────────────────────────
# 🔸 로그 레벨 필터 클래스 정의
# ─────────────────────────────────────────────────────────────────────────────

class LogLevelFilter(logging.Filter):
    """
    지정된 로그 레벨만 통과시키는 필터 클래스
    예: "A2A"로 설정 시 A2A 레벨의 로그만 출력됨
    """

    def __init__(self, target_level: str):
        super().__init__()
        self.target_level = target_level.upper()  # 대문자로 변환하여 비교

    def filter(self, record):
        """로그 레벨 필터링 로직"""
        if self.target_level == "ALL":
            return True  # 모든 로그 허용
        elif self.target_level == "A2A":
            return record.levelno == A2A_LEVEL  # A2A만 허용
        elif self.target_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            target_level_num = getattr(logging, self.target_level)
            return record.levelno == target_level_num  # 해당 레벨만 허용
        return True  # 잘못된 값이 들어오면 무시하고 전체 출력

# ─────────────────────────────────────────────────────────────────────────────
# 🔸 전역 필터 적용 함수
# ─────────────────────────────────────────────────────────────────────────────

def configure_global_logging_filter(log_level: str):
    """
    전체 애플리케이션 내 로깅 시스템에 필터를 전역 적용
    핸들러가 달려 있는 모든 로거에 필터를 연결함
    """
    if log_level.upper() == "ALL":
        return  # ALL은 필터링 없이 전체 출력하므로 무시

    log_filter = LogLevelFilter(log_level)  # 대상 레벨 기준의 필터 인스턴스 생성

    # 루트 로거부터 시작해 핸들러마다 필터를 적용
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(log_filter)

    # 현재까지 등록된 모든 로거에 대해 핸들러에 필터를 추가
    for name in logging.Logger.manager.loggerDict:
        logger_obj = logging.getLogger(name)
        if logger_obj.handlers:
            for handler in logger_obj.handlers:
                handler.addFilter(log_filter)

# ─────────────────────────────────────────────────────────────────────────────
# 🔸 get_logger() 함수
# ─────────────────────────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """
    모듈명(파일명)을 기반으로 한 로거 인스턴스를 생성하고 컬러 포맷터를 적용
    """
    logger = logging.getLogger(name)  # 모듈 이름 기반 로거 생성
    logger.setLevel(logging.DEBUG)  # 모든 레벨 허용 (필터는 핸들러에 적용함)

    # 새로운 핸들러 구성
    handler = logging.StreamHandler()  # 콘솔 출력용 스트림 핸들러
    handler.setFormatter(formatter)    # 위에서 설정한 컬러 포맷터 적용

    # 기존 핸들러 제거 후 새 핸들러 설정
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False  # 부모 로거로 메시지 전파 차단 (중복 출력 방지)

    return logger
