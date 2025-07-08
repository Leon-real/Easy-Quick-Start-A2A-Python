import click
from .server import CurrentTimeA2AServer

# ──────────────────── Custom Logging Configuration ──────────────────────────
from utilities.custom_logger import get_logger, configure_global_logging_filter
logger = get_logger(__name__)

# ──────────────────── A2A 서버 시작 ───────────────────────────
@click.command()
@click.option("--host", default="localhost", help="Host to bind the server to")
@click.option("--port", default=10001, help="Port number for the server")
@click.option("--log-level", default="ALL",type=click.Choice(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "A2A"], case_sensitive=False), help="Set Log Level (ALL: all log, A2A: only A2A log, else level: only that level)")
def main(host: str, port: int, log_level: str) -> None:
    """
    현재 시간을 알려주는 에이전트 서버를 시작합니다.
    """
    # 0) Set Log Level
    configure_global_logging_filter(log_level)
    
    logger.info(f"🚀 Start Server - Log Level :{log_level.upper()}")

    try:
        # A2A 서버 초기화 및 시작
        server = CurrentTimeA2AServer(host=host, port=port)
        server.start()
        
    except Exception as e:
        logger.error(f"서버 시작 중 오류 발생: {e}")
        raise

if __name__ == "__main__":
    main()
