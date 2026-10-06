"""common.py - dữ liệu và kiểu dùng chung cho cả 3 mẫu agent."""
from dataclasses import dataclass

# ---------------------------------------------------------------
# 1. RÀNG BUỘC LÀ DỮ LIỆU
# ---------------------------------------------------------------
@dataclass
class Constraints:
    origin: str = "SGN"
    destination: str = "DAD"
    date: str = "2026-10-07"
    depart_before: str = "12:00"
    max_price: int = 2_000_000          # VND

    def to_prompt(self) -> str:
        """Dựng câu yêu cầu gửi cho model từ chính dữ liệu ràng buộc."""
        return (f"Đặt 1 vé {self.origin} -> {self.destination} ngày {self.date}, "
                f"khởi hành trước {self.depart_before}, giá tối đa {self.max_price:,} VND.")

    def is_ok(self, flight: dict) -> bool:
        """Chuyến bay có thoả TẤT CẢ ràng buộc không."""
        return (flight["depart"].startswith(self.date)
                and flight["depart"][11:16] < self.depart_before
                and flight["price"] <= self.max_price)

    def valid_flights(self, flights: list) -> list:
        """Lọc các chuyến hợp lệ (dùng cho handoff và để tạo câu hỏi cho người)."""
        return [f for f in flights if self.is_ok(f)]


# ---------------------------------------------------------------
# 2. DỮ LIỆU CHUYẾN BAY
# ---------------------------------------------------------------
FLIGHTS_A = [   # có 1 chuyến hợp lệ; QH118 là "bẫy" (rẻ hơn nhưng bay buổi chiều)
    {"flight": "VN122", "depart": "2026-10-07T08:10", "price": 1_850_000},
    {"flight": "QH118", "depart": "2026-10-07T15:40", "price": 1_640_000},
]
FLIGHTS_B = [   # không chuyến nào hợp lệ
    {"flight": "VJ604", "depart": "2026-10-07T08:10", "price": 2_480_000},
    {"flight": "QH118", "depart": "2026-10-07T15:40", "price": 1_640_000},
]


# ---------------------------------------------------------------
# 3. KỊCH BẢN = dữ liệu + lỗi của tool + lỗi của model
# ---------------------------------------------------------------
@dataclass
class Scenario:
    name: str
    flights: list
    tool_fault: str = "none"    # none | vague_error | empty | pay_fail
    model_flaw: str = "none"    # none | drift | hallucinate | loop


SCENARIOS = [
    Scenario("normal",       FLIGHTS_A),
    Scenario("drift",        FLIGHTS_A, model_flaw="drift"),
    Scenario("loop",         FLIGHTS_A, tool_fault="vague_error", model_flaw="loop"),
    Scenario("hallucinate",  FLIGHTS_A, model_flaw="hallucinate"),
    Scenario("state",        FLIGHTS_A, tool_fault="empty"),
    Scenario("pay_fail",     FLIGHTS_A, tool_fault="pay_fail"),
    Scenario("no_valid",     FLIGHTS_B),
]


# ---------------------------------------------------------------
# 4. KẾT QUẢ MỘT LẦN CHẠY
# ---------------------------------------------------------------
@dataclass
class Result:
    pattern: str                     # "react" | "plan" | "hybrid"
    scenario: str
    done: bool                       # do is_done() quyết định, không phải model
    model_calls: int = 0
    tool_calls: int = 0
    denied: int = 0                  # số lần harness chặn
    recovered: bool = False          # có lỗi giữa chừng nhưng vẫn DONE
    stop_reason: str | None = None
    handoff: dict | None = None
    reviewable: bool = False         # plan duyệt được trước khi chạy không