"""kich_ban.py - chèn lỗi vào tool (fault injection).

Tool (tool.py) luôn chạy đúng. Việc "lần gọi nào bị hỏng" thuộc về kịch bản,
nên nằm ở đây. Lỗi do Scenario.tool_fault quyết định:

    none         không lỗi
    empty        search_flights lần đầu trả {} (dịch vụ timeout, im lặng)
    vague_error  search_flights báo "not found" mơ hồ khi date sai định dạng YYYY-MM-DD
    pay_fail     pay lần đầu báo timeout (chưa trừ tiền)

Lỗi 'empty' và 'pay_fail' chỉ xảy ra ở lần gọi đầu (lỗi tạm thời): nếu lỗi
vĩnh viễn thì không mẫu nào cứu được và bảng so sánh không phân biệt được 3 mẫu.
"""
import re

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")      # định dạng ngày hợp lệ: YYYY-MM-DD


class FaultInjector:
    """Đứng trước tool: với mỗi lời gọi, quyết định có chèn lỗi hay để tool chạy thật."""

    def __init__(self, fault: str = "none"):
        self.fault = fault
        self.search_calls = 0
        self.pay_calls = 0

    def intercept(self, name: str, args: dict) -> dict | None:
        """Trả kết quả lỗi nếu lần gọi này bị chèn lỗi; None = để tool chạy bình thường."""
        if name == "search_flights":
            self.search_calls += 1
            if self.fault == "empty" and self.search_calls == 1:
                return {}
            if self.fault == "vague_error" and not DATE_RE.match(str(args.get("date", ""))):
                return {"status": "error", "error": "not found"}
        elif name == "pay":
            self.pay_calls += 1
            if self.fault == "pay_fail" and self.pay_calls == 1:
                return {"status": "error", "error": "timeout", "code": args.get("code")}
        return None