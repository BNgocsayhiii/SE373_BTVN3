"""react.py - Mẫu ReAct (Chương 4.1).

Model quyết định TỪNG bước, sau mỗi kết quả tool (vòng model <-> tools).
create_agent của LangChain dựng vòng này trên LangGraph; harness cắm vào bằng
middleware @wrap_tool_call: mọi lời gọi tool đi qua guarded_call.

    react_loop()  vòng ReAct dùng lại được (Hybrid cũng gọi hàm này)
    run()         chạy một kịch bản -> Result
"""
import json

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphRecursionError

from harness import MODEL_BUDGET, StopAgent, finish, guarded_call
from model_gia import FakeChat, FlawSource
from tool import Env, as_langchain_tools

SYSTEM_PROMPT = ("You are a flight booking agent. Use the tools: search_flights, "
                 "book_seat, pay. Only book a flight that meets ALL constraints. "
                 "If no flight meets them, stop and say so.")


def react_loop(env: Env, model: FakeChat, run_limit: int, user_text: str) -> tuple[str, str | None]:
    """Chạy vòng ReAct. Trả (câu trả lời cuối, lý do dừng bất thường hoặc None)."""

    @wrap_tool_call
    def gate(request, handler):                       # mọi tool call đi qua harness
        call = request.tool_call
        result = guarded_call(env, call["name"], call["args"])
        if result.get("status") == "stopped":         # lặp -> dừng cả agent
            raise StopAgent(result["reason"])
        return ToolMessage(content=json.dumps(result), tool_call_id=call["id"], name=call["name"])

    agent = create_agent(
        model=model,
        tools=as_langchain_tools(env),
        system_prompt=SYSTEM_PROMPT,
        middleware=[gate, ModelCallLimitMiddleware(run_limit=run_limit, exit_behavior="end")],
    )
    try:
        out = agent.invoke({"messages": [{"role": "user", "content": user_text}]},
                           {"recursion_limit": 60})
        return str(out["messages"][-1].content), None
    except StopAgent as e:
        return "", str(e)
    except GraphRecursionError as e:
        return "", f"RECURSION LIMIT: {e}"


def run(scenario, src: FlawSource | None = None, constraints=None):
    env = Env(scenario, constraints)
    src = src or FlawSource(scenario.model_flaw)
    model = FakeChat(env=env, src=src)
    answer, stop = react_loop(env, model, MODEL_BUDGET, env.c.to_prompt())
    return finish("react", env, model.calls, answer, stop, reviewable=False)