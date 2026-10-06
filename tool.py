"""tool.py - 4 tool mockup (Chương 2). Tool luôn chạy đúng.

Lỗi được chèn từ bên ngoài bởi FaultInjector (kich_ban.py), không nằm trong tool.
Mỗi lần chạy tạo một Env riêng, nên không có biến global và có thể
chạy lặp 100 lần mà không lẫn dữ liệu giữa các lần.
"""
from common import Constraints, Scenario
from kich_ban import FaultInjector


class Env:
    """Môi trường của một lần chạy: dữ liệu, 'database' đặt chỗ và nhật ký."""

    def __init__(self, scenario: Scenario, constraints: Constraints | None = None):
        self.sc = scenario
        self.c = constraints or Constraints()
        self.bookings: dict = {}      # database giả: mã đặt chỗ -> booking
        self.log: list = []           # mỗi phần tử: (tên tool, args, kết quả); harness ghi vào
        self.injector = FaultInjector(scenario.tool_fault)   # chèn lỗi theo kịch bản
        self._tools = {
            "search_flights": self.search_flights,
            "book_seat": self.book_seat,
            "pay": self.pay,
            "get_booking": self.get_booking,
        }

    # ----------------------------------------------------------- tool 1
    def search_flights(self, origin: str, destination: str, date: str) -> dict:
        """Tìm chuyến bay theo tuyến và ngày (YYYY-MM-DD). Chỉ đọc, không tác dụng phụ."""
        flights = [f for f in self.sc.flights if f["depart"].startswith(date)]
        return {"status": "ok", "flights": flights}

    # ----------------------------------------------------------- tool 2
    def book_seat(self, flight: str) -> dict:
        """Giữ chỗ trên một chuyến bay, trả mã đặt chỗ. CHƯA trừ tiền."""
        info = next((f for f in self.sc.flights if f["flight"] == flight), None)
        if info is None:
            return {"status": "not_found", "flight": flight}
        code = f"{flight}-12A"
        self.bookings[code] = {"code": code, "paid": False, **info}
        return {"status": "ok", **self.bookings[code]}

    # ----------------------------------------------------------- tool 3
    def pay(self, code: str) -> dict:
        """Thanh toán một đặt chỗ đã giữ. TỐN TIỀN và KHÔNG hoàn tác được."""
        if code not in self.bookings:
            return {"status": "not_found", "code": code}
        self.bookings[code]["paid"] = True
        return {"status": "ok", **self.bookings[code]}

    # ----------------------------------------------------------- tool 4
    def get_booking(self, code: str) -> dict:
        """Đọc lại một đặt chỗ từ hệ thống."""
        if code not in self.bookings:
            return {"status": "not_found", "code": code}
        return {"status": "ok", **self.bookings[code]}

    # ----------------------------------------------------------- điều phối
    def call(self, name: str, args: dict) -> dict:
        """Gọi tool theo tên (thay cho globals()[name] trong code mẫu).

        Trước khi chạy tool thật, hỏi injector xem lần gọi này có bị chèn lỗi không.
        """
        injected = self.injector.intercept(name, args)
        if injected is not None:
            return injected
        fn = self._tools.get(name)
        if fn is None:
            return {"status": "error", "error": f"unknown tool: {name}"}
        try:
            return fn(**args)
        except TypeError as e:                  # model gọi sai tên/thiếu tham số
            return {"status": "error", "error": f"bad arguments: {e}"}


# --------------------------------------------------------------------
# Bọc cho LangChain (dùng ở react.py và lai.py)
# --------------------------------------------------------------------
def as_langchain_tools(env: Env) -> list:
    """Docstring của từng hàm là thứ model đọc để biết tool làm gì."""
    from langchain_core.tools import tool

    @tool
    def search_flights(origin: str, destination: str, date: str) -> dict:
        """Search flights by route and date (YYYY-MM-DD)."""
        return env.call("search_flights", dict(origin=origin, destination=destination, date=date))

    @tool
    def book_seat(flight: str) -> dict:
        """Hold a seat on a flight and return a booking code. No money is charged yet."""
        return env.call("book_seat", dict(flight=flight))

    @tool
    def pay(code: str) -> dict:
        """Pay for a held booking. This spends money and cannot be undone."""
        return env.call("pay", dict(code=code))

    @tool
    def get_booking(code: str) -> dict:
        """Read a booking back from the system."""
        return env.call("get_booking", dict(code=code))

    return [search_flights, book_seat, pay, get_booking]


# --------------------------------------------------------------------
# Chạy thử riêng: python tool.py  (dùng env.call để lỗi được chèn như khi agent chạy)
# --------------------------------------------------------------------
if __name__ == "__main__":
    from common import FLIGHTS_A

    env = Env(Scenario("test", FLIGHTS_A, tool_fault="pay_fail"))
    print(env.call("search_flights", dict(origin="SGN", destination="DAD", date="2026-10-07")))
    print(env.call("book_seat", dict(flight="VN122")))
    print("pay lần 1:", env.call("pay", dict(code="VN122-12A")))     # timeout (do kich_ban chèn)
    print("pay lần 2:", env.call("pay", dict(code="VN122-12A")))     # ok
    print(env.call("get_booking", dict(code="VN122-12A")))
    print(env.call("search_flights", {"origin": "SGN"}))             # thiếu tham số -> lỗi có cấu trúc