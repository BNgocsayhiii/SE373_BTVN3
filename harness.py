"""harness.py - các lớp harness (Chương 3).

Harness = code Python thường, KHÔNG gọi model, KHÔNG tin model.
Cả 3 mẫu agent đều đi qua cùng các hàm ở đây, nên so sánh mới công bằng.

    check_permission  Kiểm quyền       chạy TRƯỚC mỗi tool
    is_done           Hoàn thành       đọc lại booking từ hệ thống, không tin lời model
    handoff           Bàn giao         đã làm gì / đã thử gì / hỏi người câu gì
    is_looping        Chống lặp        cùng (tool, args) lặp lại
    is_empty          Chống state corruption   kết quả rỗng = lỗi tool
    ungrounded_facts  Chống bịa        mã chuyến/giá trong câu trả lời phải có trong kết quả tool
    guarded_call      CỔNG DUY NHẤT trước khi chạm tool (gom các lớp ở trên)
    finish            Đóng gói Result cho evaluate.py

Ràng buộc là dữ liệu: nằm ở Constraints (common.py), harness chỉ đọc nó.
"""
import json
import re

from common import Result
from tool import Env

MODEL_BUDGET = 10          # ngân sách: tối đa 10 lần gọi model cho một lần chạy
LOOP_WINDOW = 6            # nhìn 6 lời gọi gần nhất
LOOP_MAX_REPEAT = 2        # đã có 2 lần giống hệt thì lần thứ 3 bị chặn


class StopAgent(Exception):
    """Harness ném ra để dừng agent ngay, kèm lý do."""


# ============================================================ 1. KIỂM QUYỀN
def check_permission(env: Env, name: str, args: dict) -> str | None:
    """None = được phép; chuỗi = lý do chặn. Chỉ dựa vào dữ liệu ràng buộc."""
    c = env.c
    if name == "book_seat":
        flight = next((f for f in env.sc.flights if f["flight"] == args.get("flight")), None)
        if flight is None or not c.is_ok(flight):
            return f"{args.get('flight')} vi phạm ràng buộc: {c.to_prompt()}"
        if any(b["paid"] for b in env.bookings.values()):
            return "đã có một vé được thanh toán, không đặt thêm"
    if name == "pay":                       # pay tốn tiền và không hoàn tác -> kiểm kỹ nhất
        b = env.bookings.get(args.get("code"))
        if b is None:
            return f"không có booking {args.get('code')} để thanh toán"
        if not c.is_ok(b):
            return f"booking {b['code']} vi phạm ràng buộc, không được thanh toán"
        if b["paid"]:
            return f"booking {b['code']} đã thanh toán rồi (pay không hoàn tác được)"
    return None


# ============================================================ 2. HOÀN THÀNH
def is_done(env: Env) -> bool:
    """Xong = có booking đã trả tiền VÀ thoả ràng buộc. Đọc lại từ hệ thống."""
    for code in env.bookings:
        b = env.get_booking(code)
        if b.get("status") == "ok" and b["paid"] and env.c.is_ok(b):
            return True
    return False


# ============================================================ 3. BÀN GIAO
def handoff(env: Env, stop_reason: str | None) -> dict:
    """Đủ 3 thứ: đã làm gì, đã thử gì, câu hỏi cụ thể cho người."""
    valid = env.c.valid_flights(env.sc.flights)
    if valid:
        question = ("Các chuyến hợp lệ: " + ", ".join(f["flight"] for f in valid)
                    + ". Có đặt một trong số này không?")
    else:
        question = ("Không chuyến nào thoả mọi ràng buộc. "
                    "Nới ràng buộc nào: giờ khởi hành hay giá tối đa?")
    return {
        "stop_reason": stop_reason or "GOAL NOT REACHED",
        "done_so_far": [f"{c}: paid={b['paid']}" for c, b in env.bookings.items()]
                       or ["Chưa đặt, chưa trả tiền"],
        "tried": [f"{n}({a}) -> {r.get('status')}" for n, a, r in env.log],
        "question": question,
    }


# ============================================================ 4. CHỐNG LẶP
def is_looping(env: Env, name: str, args: dict) -> bool:
    recent = [(n, a) for n, a, r in env.log if r.get("status") != "stopped"][-LOOP_WINDOW:]
    return sum(1 for n, a in recent if n == name and a == args) >= LOOP_MAX_REPEAT


# ============================================================ 5. CHỐNG STATE CORRUPTION
def is_empty(result: dict) -> bool:
    return not result or "status" not in result


# ============================================================ 6. CHỐNG BỊA
def ungrounded_facts(answer: str, env: Env) -> list:
    """Mã chuyến và giá trong câu trả lời mà không tool nào từng trả về."""
    tool_text = json.dumps([r for _, _, r in env.log])
    facts = re.findall(r"\b[A-Z]{2}\d{3}\b", answer)                          # VN122
    facts += [p.replace(",", "") for p in re.findall(r"\d{1,3}(?:,\d{3})+", answer)]  # 1,850,000
    return [f for f in facts if f not in tool_text]


# ============================================================ CỔNG DUY NHẤT
def guarded_call(env: Env, name: str, args: dict) -> dict:
    """Loop -> quyền -> chạy tool -> kiểm rỗng -> ghi log.

    Trả kết quả CÓ CẤU TRÚC (không ném exception) để cả 3 mẫu dùng chung:
      status = ok | error | not_found | denied | stopped
    """
    if is_looping(env, name, args):
        result = {"status": "stopped", "reason": f"LOOP: {name}({args}) đã gọi {LOOP_MAX_REPEAT} lần"}
    else:
        reason = check_permission(env, name, args)
        if reason:
            result = {"status": "denied", "reason": reason}
        else:
            result = env.call(name, args)
            if is_empty(result):                         # {} KHÔNG có nghĩa là "không có chuyến"
                result = {"status": "error", "error": "empty_result",
                          "hint": "tool trả về rỗng: đây là lỗi tool, không phải 'không có chuyến'. Thử lại."}
    env.log.append((name, args, result))
    return result


# ============================================================ ĐÓNG GÓI KẾT QUẢ
def finish(pattern: str, env: Env, model_calls: int, answer: str = "",
           stop_reason: str | None = None, reviewable: bool = False,
           extra_problem: bool = False) -> Result:
    """Harness quyết định kết quả cuối, không phải model.

    extra_problem: có sự cố mà log tool không thấy (vd plan bị từ chối rồi viết lại).
    """
    fake = ungrounded_facts(answer, env) if answer else []
    if fake:
        stop_reason = f"HALLUCINATION: {fake} không có trong kết quả tool nào"
    done = is_done(env) and not fake

    statuses = [r.get("status") for _, _, r in env.log]
    had_problem = extra_problem or any(s in ("error", "denied", "stopped") for s in statuses)
    if not done and not stop_reason:
        stop_reason = "GOAL NOT REACHED"

    return Result(
        pattern=pattern, scenario=env.sc.name, done=done,
        model_calls=model_calls,
        tool_calls=sum(1 for s in statuses if s not in ("denied", "stopped")),
        denied=statuses.count("denied"),
        recovered=done and had_problem,
        stop_reason=None if done else stop_reason,
        handoff=None if done else handoff(env, stop_reason),
        reviewable=reviewable,
    )