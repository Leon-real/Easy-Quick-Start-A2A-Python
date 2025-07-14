# 🧠 Easy A2A Sample Code 

A sample project based on the A2A (Agent-to-Agent) protocol.
This project features a Host Agent that collaborates with Remote Agents to process user requests. You can easily test the structure via CLI, and both the Host Agent and Remote Agents are simple to customize and extend for your own applications.

---

> 🇰🇷 Want to read in Korean? [README\_KO.md](./README_KO.md)

---

## Project Directory Structure

```bash
/a2a_official
├── agent_registry.json             # Agent registry info JSON (see below)
├── agents                         # Agent source code
│   ├── __init__.py
│   ├── current_time_agent         # Remote Agent providing time information
│   │   ├── __init__.py
│   │   ├── agent.py               # Agent logic
│   │   ├── main.py                # Entry point
│   │   └── server.py              # API server
│   ├── host                       # Host Agent related code
│   │   ├── __init__.py
│   │   ├── agent_connect.py       # Manages remote agent connections (A2A protocol)
│   │   ├── entry.py               # Server entry point, CLI & HTTP server
│   │   ├── memory.py              # Persists conversations and execution results
│   │   └── orchestrator.py        # LLM-based routing and agent orchestration
│   └── korea_agent                # Remote Agent for Korea-related answers
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── main.py
│   │   └── server.py
│   └── agent_template             # Remote Agent template
│       ├── __init__.py
│       ├── agent.py               # Core agent logic (AI)
│       ├── main.py                # CLI entry point
│       └── server.py              # A2A server implementation
├── cli
│   └── cli.py                     # CLI test launcher
├── readme_image
│   └── cli.png                    # CLI screenshot example
├── README.md
└── utilities
    └── custom_logger.py           # Logging utility
```

---

## Architecture Overview

```
[User] --(CLI)--> [Host Agent] --(A2A Protocol)--> [Remote Agent(s)]
```

---

## Setup & Run Guide

### 1. Set up `.env` file

Copy `.env_example` to `.env` and add the following API keys:

```bash
GOOGLE_API_KEY=
OPENAI_API_KEY=
OLLAMA_API_BASE=http://localhost:11434
```

### 2. Create a virtual environment

```bash
python3 -m venv .a2a
```

### 3. Activate the virtual environment

```bash
source .a2a/bin/activate
```

### 4. Start the Agents

#### Remote Agent #1 (Korea Agent)

```bash
source .a2a/bin/activate
python -m agents.korea_agent.main --host localhost --port 10000
```

To view only A2A logs:

```bash
python -m agents.korea_agent.main --host localhost --port 10000 --log-level A2A
```

#### Remote Agent #2 (Current Time Agent)

```bash
source .a2a/bin/activate
python -m agents.current_time_agent.main --host localhost --port 10001
```

To view only A2A logs:

```bash
python -m agents.current_time_agent.main --host localhost --port 10001 --log-level A2A
```

#### Host Agent

```bash
source .a2a/bin/activate
python -m agents.host.entry --host localhost --port 10003
```

To view only A2A logs:

```bash
python -m agents.host.entry --host localhost --port 10003 --log-level A2A
```

### 5. Test via CLI

```bash
cd cli
python cli.py --agent http://localhost:10003 --user test --chat 001
```

* Example result

  * ![CLI Screenshot](./readme_image/cli.png)

---

## Example `agent_registry.json`

```json
[
    "http://localhost:10000",
    "http://localhost:10001"
]
```

---

# Customization Guide

* To add or extend a Remote Agent, create a new folder in `agents/` and implement `agent.py`, `server.py`, and `main.py` with the same structure.
* Make sure to add your new agent's info to `agent_registry.json` so the Host Agent can recognize it.

---

## How to Extend a Remote Agent (Step by Step)

### 1. Copy the template

* Duplicate the `agents/agent_template` folder for your new agent.

### 2. Edit basic info

1. Set the host and port in `main.py`:

```python
@click.option("--host", default='localhost', help="Host to bind the server to")
@click.option("--port", default=10001, help="Port number for the server")
```

2. Edit the agent card info in `server.py`:

```python
def _create_agent_card(self) -> AgentCard:
    skill = AgentSkill(
        id="your_agent_id",                    # Unique agent ID
        name="YourAgentName",                  # Agent name
        description="Describe your agent",      # Agent description
        tags=["tag1", "tag2"],                 # Agent tags
        examples=["Sample question 1", "Sample question 2"]   # Example questions
    )

    return AgentCard(
        name="YourAgentName",
        description="Describe your agent",
        # ... keep the rest as is
    )
```

3. (Optional) Change class names in `server.py`:

```python
class YourAgentExecutor(AgentExecutor):     # TemplateAgentExecutor → YourAgentExecutor
class YourA2AServer:                       # TemplateA2AServer → YourA2AServer
```

### 3. Implement your agent logic

In `agent.py`, implement your AI logic:

```python
class YourAgent:  # TemplateAgent → YourAgent
    def __init__(self):
        # Initialize LLM client
        # Example: self.llm_client = OpenAI(api_key="your-key")
        pass

    def _build_agent(self):
        # Build the agent (e.g., using AutoGen, LangChain, etc.)
        pass

    async def process_message(self, message_text: str) -> str:
        # Core logic for processing messages
        # Example:
        # response = await self.llm_client.chat.completions.create(...)
        # return response.choices[0].message.content
        return f"YourAgent Response: {message_text}"
```

### 4. Run your agent for testing

```bash
python -m agents.your_agent_name.main --port 10001
```

---

## Feedback / Contact

* For improvement requests or bug reports, [open an issue](tutmr999@naver.com) or send a PR!
* By the way I'm not familiar with Github issues, you can contact via email for a quick reply: `tutmr999@naver.com`[tutmr999@naver.com](mailto:tutmr999@naver.com)
