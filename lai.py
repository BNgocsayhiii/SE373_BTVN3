"""lai.py - Mẫu Lai / Hybrid (Chương 4.3).

    Giai đoạn 1: Plan-then-Execute (plan_phase): viết kế hoạch, harness duyệt, code chạy.
    Giai đoạn 2: nếu gặp sự cố (search lỗi, bước chạy lỗi, kế hoạch bị từ chối hết)
                 -> chuyển sang ReAct, giao trạng thái hiện tại + ngân sách còn lại.
    Cuối: is_done quyết định; thất bại thì handoff.

Không fallback khi planner kết luận "không có chuyến hợp lệ": đó là kết quả đúng,
gọi thêm model chỉ tốn tiền.
"""
from harness import MODEL_BUDGET, finish
from model_gia import FakeChat, FakePlanner, FlawSource
from plan_then_execute import plan_phase
from react import react_loop
from tool import Env


def build_recovery_message(env: Env, reason: str) -> str:
    """Tóm tắt cho giai đoạn ReAct: yêu cầu gốc, đã làm gì, lỗi gì."""
    done = [f"{n}({a}) -> {r.get('status')}" for n, a, r in env.log] or ["chưa làm gì"]
    return (f"{env.c.to_prompt()}\n"
            f"Kế hoạch trước đó dừng giữa chừng: {reason}\n"
            f"Đã thực hiện: {'; '.join(done)}\n"
            "Hãy tiếp tục từ trạng thái hiện tại, không làm lại các bước đã xong.")


def run(scenario, src: FlawSource | None = None, constraints=None):
    env = Env(scenario, constraints)
    src = src or FlawSource(scenario.model_flaw)
    planner = FakePlanner(env.c, src)

    out = plan_phase(env, planner)                      # giai đoạn 1
    model_calls, answer, stop = planner.calls, "", None
    fallback = False

    if out.stage != "ok" and not out.empty_plan:        # giai đoạn 2: ReAct tiếp quản
        remaining = MODEL_BUDGET - planner.calls
        if remaining > 0:
            fallback = True
            model = FakeChat(env=env, src=src)
            answer, stop = react_loop(env, model, remaining, build_recovery_message(env, out.reason))
            model_calls += model.calls
        else:
            stop = out.reason
    elif out.stage != "ok":
        stop = out.reason

    return finish("hybrid", env, model_calls, answer, stop, reviewable=True,
                  extra_problem=out.rejected > 0 or fallback)