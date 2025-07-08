"""실행 진입점"""
import click
from utilities.custom_logger import get_logger, configure_global_logging_filter
from .server import TemplateA2AServer

logger = get_logger(__name__)

@click.command()
@click.option("--host", default='localhost', help="Host to bind the server to")
@click.option("--port", default=10000, help="Port number for the server")
@click.option("--log-level", default="ALL", 
              type=click.Choice(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "A2A"], case_sensitive=False),
              help="Set Log Level")
def main(host: str, port: int, log_level: str) -> None:
    """템플릿 에이전트 A2A 서버 시작"""
    
    # 로그 레벨 설정
    configure_global_logging_filter(log_level)
    logger.info(f"🚀 Start {host}:{port} Server - Log Level: {log_level.upper()}")
    
    try:
        server = TemplateA2AServer(host=host, port=port)
        server.start()
    except Exception as e:
        logger.error(f"서버 시작 중 오류 발생: {e}")
        raise

if __name__ == "__main__":
    main()
