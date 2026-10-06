"""model_gia.py - model giả, không cần API key.

Model giả hành xử theo CHÍNH SÁCH (không theo kịch bản cứng):
    decide(flaw, state, c) -> hành động tiếp theo
nên ReAct (gọi model nhiều lần) và Plan (gọi 1 lần) dùng chung được.

Lỗi của model (model_flaw):
    none         làm đúng
    drift        quên ràng buộc, chọn chuyến RẺ NHẤT; được nhắc (bị chặn) thì sửa
    hallucinate  không đặt gì mà báo "đã đặt VN999"
    loop         luôn gọi search với date="07/10" (sai định dạng), không sửa

Thành phần:
    FlawSource   quyết định lần này model mắc lỗi gì (cố định theo Scenario, hoặc ngẫu nhiên có seed)
    read_state   đọc trạng thái hiện tại từ env.log
    decide       chính sách (thuần Python)
    FakeChat     BaseChatModel cho ReAct (create_agent)
    Plan, Step, FakePlanner   cho Plan-then-Execute và Hybrid

Ghi chú: model giả đọc trạng thái từ env.log. Với LLM thật, cùng thông tin đó
nằm trong lịch sử tin nhắn / tin nhắn phục hồi của Hybrid.
"""
import random
from types import SimpleNamespace
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel


# ====================================================== NGUỒN LỖI
class FlawSource:
    """Mỗi lần model ra quyết định thì hỏi: lần này mắc lỗi gì?

    fixed: lỗi cố định (theo Scenario). drift/hallucinate chỉ xảy ra LẦN ĐẦU,
           sau khi bị harness phản hồi thì model sửa; loop thì lặp mãi.
    p    : nếu có, chế độ ngẫu nhiên: mỗi quyết định có xác suất p mắc drift hoặc
           hallucinate (random.Random(seed), không dùng random toàn cục).
    """

    def __init__(self, fixed: str = "none", p: float | None = None, seed: int = 0):
        self.fixed, self.p = fixed, p
        self.rng = random.Random(seed)

    def draw(self, already_denied: bool) -> str:
        if self.p is not None:
            return self.rng.choice(["drift", "hallucinate"]) if self.rng.random() < self.p else "none"
        if self.fixed in ("drift", "hallucinate") and already_denied:
            return "none"
        return self.fixed


# ====================================================== TRẠNG THÁI TỪ LOG
def read_state(env) -> SimpleNamespace:
    st = SimpleNamespace(flights=None, search_calls=0, booking=None,
                         paid=False, pay_errors=0, denied=False)
    for name, _, res in env.log:
        status = res.get("status")
        if status == "denied":
            st.denied = True
        if name == "search_flights":
            st.search_calls += 1
            if status == "ok" and "flights" in res:
                st.flights = res["flights"]
        elif name == "book_seat" and status == "ok":
            st.booking = res
        elif name == "pay":
            if status == "ok":
                st.paid = True
            elif status == "error":
                st.pay_errors += 1
    return st


# ====================================================== CHÍNH SÁCH
def _tool(name, **args):
    return {"type": "tool", "name": name, "args": args}


def _final(text):
    return {"type": "final", "text": text}


def decide(flaw: str, st, c) -> dict:
    """(lỗi, trạng thái, ràng buộc) -> {"type":"tool",...} hoặc {"type":"final",...}"""
    if st.paid:
        b = st.booking
        return _final(f"Đã đặt {b['flight']}, ghế 12A, thanh toán {b['price']:,} VND.")

    if st.flights is None:                                   # chưa có kết quả search hợp lệ
        if st.search_calls >= 4:
            return _final("Không tìm kiếm được chuyến bay.")
        date = "07/10" if flaw == "loop" else c.date         # loop: sai định dạng, không sửa
        return _tool("search_flights", origin=c.origin, destination=c.destination, date=date)

    if st.booking is None:                                   # đã có danh sách, chưa chọn chuyến
        if flaw == "hallucinate":
            return _final("Xong! Đã đặt VN999, ghế 5C, giá 1,200,000 VND.")
        if not st.flights:
            return _final("Không có chuyến bay nào trong ngày.")
        if flaw == "drift":
            pick = min(st.flights, key=lambda f: f["price"])         # chạy theo "rẻ nhất"
        else:
            valid = c.valid_flights(st.flights)
            if not valid:
                return _final("Không có chuyến nào thoả mọi ràng buộc.")
            pick = min(valid, key=lambda f: f["price"])
        return _tool("book_seat", flight=pick["flight"])

    if st.pay_errors >= 3:                                   # đã giữ chỗ, chưa trả tiền
        return _final("Thanh toán liên tục lỗi, dừng lại.")
    return _tool("pay", code=st.booking["code"])


# ====================================================== MODEL CHO REACT
class FakeChat(BaseChatModel):
    """BaseChatModel giả: mỗi lần gọi -> decide() -> AIMessage (tool_calls hoặc câu trả lời)."""

    env: Any = None
    src: Any = None
    _n: int = 0                       # số lần gọi model

    @property
    def calls(self) -> int:
        return self._n

    @property
    def _llm_type(self) -> str:
        return "btvn3-fake-chat"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeChat":
        return self                   # model giả không cần schema tool

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        self._n += 1
        st = read_state(self.env)
        act = decide(self.src.draw(st.denied), st, self.env.c)
        if act["type"] == "final":
            ai = AIMessage(content=act["text"])
        else:
            ai = AIMessage(content="", tool_calls=[
                {"name": act["name"], "args": act["args"], "id": f"call_{self._n}", "type": "tool_call"}])
        return ChatResult(generations=[ChatGeneration(message=ai)])


# ====================================================== MODEL CHO PLAN
class Step(BaseModel):
    tool: str          # book_seat | pay | get_booking
    args: dict         # vd {"flight": "VN122"} hoặc {"code": "$booking_code"}


class Plan(BaseModel):
    steps: list[Step]  # danh sách RỖNG = "không chuyến nào thoả ràng buộc"


def _book_pay_check(flight: str) -> Plan:
    return Plan(steps=[Step(tool="book_seat", args={"flight": flight}),
                       Step(tool="pay", args={"code": "$booking_code"}),
                       Step(tool="get_booking", args={"code": "$booking_code"})])


class FakePlanner:
    """Viết CẢ kế hoạch trong 1 lần gọi. .invoke({...}) giống một LangChain Runnable.

    Với model thật, thay bằng:  PLANNER_PROMPT | llm.with_structured_output(Plan)
    """

    def __init__(self, c, src: FlawSource):
        self.c, self.src, self.calls = c, src, 0

    def invoke(self, inputs: dict) -> Plan:
        self.calls += 1
        flights, attempt = inputs["flights"], inputs.get("attempt", 1)
        flaw = self.src.draw(already_denied=attempt > 1)
        if flaw == "hallucinate":
            return _book_pay_check("VN999")                  # bịa chuyến không có trong danh sách
        if flaw == "drift" and flights:
            return _book_pay_check(min(flights, key=lambda f: f["price"])["flight"])
        valid = self.c.valid_flights(flights)                # (loop không ảnh hưởng planner)
        if not valid:
            return Plan(steps=[])
        return _book_pay_check(min(valid, key=lambda f: f["price"])["flight"])