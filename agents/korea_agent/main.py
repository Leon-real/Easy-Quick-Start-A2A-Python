import click
from .server import KoreaA2AServer

# ──────────────────── Custom Logging Configuration ──────────────────────────
from utilities.custom_logger import get_logger,configure_global_logging_filter
logger = get_logger(__name__)


# ──────────────────── KoreaAgent A2A Server ──────────────────────────
@click.command()
@click.option("--host", default="localhost", help="Host to bind the server to")
@click.option("--port", default=10000, help="Port number for the server")
@click.option("--log-level", default="ALL",type=click.Choice(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "A2A"], case_sensitive=False), help="Set Log Level (ALL: all log, A2A: only A2A log, else level: only that level)")
def main(host: str, port: int, log_level: str) -> None:
    """
    KoreaAgent A2A 서버를 설정하고 시작합니다.
    
    이 서버는 python-a2a-sdk를 사용하여 Google A2A Protocol을 구현하며,
    한국어 및 한국 문화 관련 질문에 특화된 AI 에이전트를 제공합니다.
    """
    # 0) Set Log Level
    configure_global_logging_filter(log_level)
    
    logger.info(f"🚀 Start Server - Log Level :{log_level.upper()}")

    try:
        # A2A 서버 초기화 및 시작
        server = KoreaA2AServer(host=host, port=port)
        server.start()
        
    except Exception as e:
        logger.error(f"서버 시작 중 오류 발생: {e}")
        raise

if __name__ == "__main__":
    main()
