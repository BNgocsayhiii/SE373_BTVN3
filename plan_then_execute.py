"""plan_then_execute.py - Mẫu Plan-then-Execute (Chương 4.2).

    search (code) -> model viết CẢ kế hoạch (1 lần) -> HARNESS duyệt kế hoạch
    -> code chạy từng bước, KHÔNG gọi model nữa -> is_done / handoff

Khác ReAct: model chỉ gọi 1 lần cho mỗi kế hoạch; kế hoạch xem được trước khi chạy;
nhưng bước lỗi thì kế hoạch không tự thích nghi, chỉ dừng.

    auto_review()      harness duyệt kế hoạch thay cho người (input() trong code mẫu)
    fill_placeholders  thay "$booking_code" bằng mã thật
    execute_plan()     chạy từng bước qua guarded_call
    plan_phase()       toàn bộ giai đoạn plan (Hybrid dùng lại)
    run()              chạy một kịch bản -> Result
"""
from dataclasses import dataclass

from harness import finish, guarded_call
from model_gia import FakePlanner, FlawSource, Plan
from tool import Env

MAX_PLANS = 2                                  # model được viết tối đa 2 kế hoạch
ALLOWED_TOOLS = {"book_seat", "pay", "get_booking"}


@dataclass
class PlanOutcome:
    stage: str                  # "ok" | "search" | "plan" | "execute"
    reason: str = ""
    rejected: int = 0           # số kế hoạch bị harness từ chối
    empty_plan: bool = False    # planner kết luận "không có chuyến hợp lệ"


def auto_review(plan: Plan, flights: list, c) -> str | None:
    """Duyệt kế hoạch TRƯỚC khi chạy: tool hợp lệ, chuyến có thật và thoả ràng buộc."""
    known = {f["flight"]: f for f in flights}
    for i, s in enumerate(plan.steps, 1):
        if s.tool not in ALLOWED_TOOLS:
            return f"bước {i}: tool '{s.tool}' không được phép"
        if s.tool == "book_seat":
            f = known.get(s.args.get("flight"))
            if f is None:
                return f"bước {i}: chuyến {s.args.get('flight')} không có trong kết quả tìm kiếm"
            if not c.is_ok(f):
                return f"bước {i}: {f['flight']} vi phạm ràng buộc"
    if not any(s.tool == "pay" for s in plan.steps):
        return "kế hoạch không có bước thanh toán"
    return None


def fill_placeholders(args: dict, env: Env) -> dict:
    """Thay "$booking_code" bằng mã trả về từ book_seat gần nhất."""
    code = next((r["code"] for n, _, r in reversed(env.log)
                 if n == "book_seat" and r.get("status") == "ok"), "$booking_code")
    return {k: (code if v == "$booking_code" else v) for k, v in args.items()}


def execute_plan(plan: Plan, env: Env) -> str | None:
    """Chạy từng bước qua guarded_call. Bước lỗi -> dừng, trả mô tả lỗi."""
    for i, step in enumerate(plan.steps, 1):
        args = fill_placeholders(step.args, env)
        res = guarded_call(env, step.tool, args)
        if res.get("status") != "ok":
            return f"bước {i} {step.tool}({args}) -> {res.get('status')} {res.get('error') or res.get('reason', '')}"
    return None


def plan_phase(env: Env, planner: FakePlanner, max_plans: int = MAX_PLANS) -> PlanOutcome:
    c = env.c
    # GOAL: tìm chuyến bằng code, tham số lấy từ DATA nên không thể sai định dạng
    found = guarded_call(env, "search_flights",
                         dict(origin=c.origin, destination=c.destination, date=c.date))
    if found.get("status") != "ok":
        return PlanOutcome("search", f"search_flights thất bại: {found}")

    rejected, plan, reason = 0, None, "không có kế hoạch"
    for attempt in range(1, max_plans + 1):
        draft = planner.invoke({"goal": c.to_prompt(), "flights": found["flights"], "attempt": attempt})
        if not draft.steps:
            return PlanOutcome("plan", "planner: không chuyến nào thoả ràng buộc",
                               rejected, empty_plan=True)
        problem = auto_review(draft, found["flights"], c)
        if problem:
            rejected += 1
            reason = f"kế hoạch #{attempt} bị từ chối: {problem}"
            continue
        plan = draft
        break
    if plan is None:
        return PlanOutcome("plan", reason, rejected)

    failure = execute_plan(plan, env)
    if failure:
        return PlanOutcome("execute", failure, rejected)
    return PlanOutcome("ok", "", rejected)


def run(scenario, src: FlawSource | None = None, constraints=None):
    env = Env(scenario, constraints)
    src = src or FlawSource(scenario.model_flaw)
    planner = FakePlanner(env.c, src)
    out = plan_phase(env, planner)
    return finish("plan", env, planner.calls,
                  stop_reason=None if out.stage == "ok" else out.reason,
                  reviewable=True, extra_problem=out.rejected > 0)