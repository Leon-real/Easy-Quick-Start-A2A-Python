# =============================================================================
# a2a_official/utility/cli.py ─ 터미널에서 Host-Agent와 대화하기
# =============================================================================
import asyncio
import asyncclick as click
from uuid import uuid4

import httpx
from a2a.client import A2AClient, create_text_message_object
from a2a.types import SendMessageRequest, MessageSendParams, Message, Task, Part, TextPart,JSONRPCErrorResponse


# --------------------------------------------------------------------------- #
# Part → 텍스트 추출 유틸
# --------------------------------------------------------------------------- #
def _part_to_text(p: Part | TextPart) -> str:
    if isinstance(p, TextPart):
        return p.text
    if hasattr(p, "text"):
        return p.text
    if hasattr(p, "root") and hasattr(p.root, "text"):
        return p.root.text
    return str(p)


# --------------------------------------------------------------------------- #
@click.command()
@click.option("--agent", default="http://localhost:10003", help="Host-Agent URL")
@click.option("--session", default="0", help="세션 ID (0 입력 시 자동 생성)")
@click.option("--history", is_flag=True, help="Task history 출력")
async def cli(agent: str, session: str, history: bool) -> None:
    session_id = uuid4().hex if str(session) == "0" else str(session)

    async with httpx.AsyncClient(timeout=300) as http:
        a2a_client: A2AClient = await A2AClient.get_client_from_agent_card_url(
            http, agent.rstrip("/")
        )

        while True:
            user_input = click.prompt("\n💬 입력 (quit/:q 종료)", prompt_suffix=" ").strip()
            if user_input.lower() in {"quit", ":q"}:
                break
            
            # User Send Message for request something 
            request = SendMessageRequest(
                id=uuid4().hex, # JSON-RPC 요청 ID
                params=MessageSendParams(
                    id=uuid4().hex, # Task ID
                    sessionId=session_id,
                    message=create_text_message_object(content=user_input),
                ),
            )

            try:
                response = await a2a_client.send_message(request)
                result = response.root.result  # Message or Task

                # ① 에러 응답인지 먼저 확인
                if isinstance(response.root, JSONRPCErrorResponse):
                    click.secho(f"❌ A2A Error: {response.root.error.message}", fg="red")
                    continue    # → 다음 사용자 입력으로 넘어감
                
                # ② 정상 응답 처리(기존 로직 유지)
                # ---------- Message ----------
                if isinstance(result, Message):
                    agent_reply = _part_to_text(result.parts[0])
                    click.secho(f"\n🤖 Agent: {agent_reply}", fg="green")

                # ---------- Task ----------
                elif isinstance(result, Task):
                    if result.history:
                        agent_reply = _part_to_text(result.history[-1].parts[0])
                        click.secho(f"\n🤖 Agent: {agent_reply}", fg="green")
                    else:
                        click.secho("⚠️  Task history 비어있음", fg="yellow")

                    if history:
                        click.secho("\n🗂️  히스토리", fg="cyan")
                        for m in result.history:
                            role = "USER " if m.role == "user" else "AGENT"
                            click.echo(f"[{role}] {_part_to_text(m.parts[0])}")

                # ---------- Fallback ----------
                else:
                    click.secho(f"⚠️  Unknown result type: {type(result)}", fg="yellow")

            except Exception as e:
                click.secho(f"\n❌ 오류: {e}", fg="red")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    asyncio.run(cli())
