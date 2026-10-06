"""evaluate.py - đánh giá 3 mẫu agent (Chương 5).

    python evaluate.py            chạy cả hai phần
    Phần A  run_fixed()   3 mẫu x 7 kịch bản cố định (tất định)
    Phần B  run_flaky()   FlawSource ngẫu nhiên có seed, lặp N lần mỗi mẫu

Kết quả ghi vào ../result/ (CSV) và in ra bảng để dán vào báo cáo.
Lưu ý: model là giả, nên số liệu phản ánh KIẾN TRÚC chứ không phải chất lượng LLM thật.
"""
import csv
import sys
from pathlib import Path

import lai
import plan_then_execute
import react
from common import FLIGHTS_A, SCENARIOS, Constraints, Scenario
from model_gia import FlawSource

PATTERNS = {"react": react, "plan": plan_then_execute, "hybrid": lai}

RESULT_DIR = Path(__file__).resolve().parent.parent / "result"
RESULT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------- tiêu chí
def expected_done(sc: Scenario) -> bool:
    """Có chuyến hợp lệ thì kết quả đúng là DONE; không có thì kết quả đúng là dừng + bàn giao."""
    return bool(Constraints().valid_flights(sc.flights))


def handoff_ok(h: dict | None) -> bool:
    return bool(h) and all(h.get(k) for k in ("stop_reason", "done_so_far", "tried", "question"))


def correct(res, sc: Scenario) -> bool:
    if expected_done(sc):
        return res.done
    return (not res.done) and handoff_ok(res.handoff)       # an toàn: dừng đúng chỗ, báo đúng người


# ---------------------------------------------------------------- phần A
def run_fixed() -> list[dict]:
    rows = []
    for sc in SCENARIOS:
        for name, mod in PATTERNS.items():
            r = mod.run(sc)
            rows.append(dict(
                scenario=sc.name, pattern=name,
                expected="DONE" if expected_done(sc) else "HANDOFF",
                outcome="DONE" if r.done else "FAILED",
                correct=correct(r, sc),
                model_calls=r.model_calls, tool_calls=r.tool_calls, denied=r.denied,
                recovered=r.recovered, reviewable=r.reviewable,
                handoff_ok=handoff_ok(r.handoff) if not r.done else "",
                stop_reason=(r.stop_reason or "")[:70],
            ))
    return rows


def print_fixed(rows):
    print("\n=== PHẦN A: 3 mẫu x 7 kịch bản cố định ===")
    head = f"{'kịch bản':<12}{'mẫu':<8}{'đúng':<6}{'kết quả':<8}{'model':>6}{'tool':>6}{'chặn':>6}  {'phục hồi':<9}stop_reason"
    print(head)
    print("-" * len(head))
    for r in rows:
        print(f"{r['scenario']:<12}{r['pattern']:<8}{'✓' if r['correct'] else '✗':<6}{r['outcome']:<8}"
              f"{r['model_calls']:>6}{r['tool_calls']:>6}{r['denied']:>6}  "
              f"{'có' if r['recovered'] else '-':<9}{r['stop_reason']}")

    print("\n--- Tổng hợp theo mẫu ---")
    for name in PATTERNS:
        sub = [r for r in rows if r["pattern"] == name]
        n = len(sub)
        print(f"{name:<8} đúng {sum(r['correct'] for r in sub)}/{n} | "
              f"model TB {sum(r['model_calls'] for r in sub) / n:.2f} | "
              f"tool TB {sum(r['tool_calls'] for r in sub) / n:.2f} | "
              f"phục hồi {sum(r['recovered'] for r in sub)} | "
              f"duyệt trước được: {'có' if sub[0]['reviewable'] else 'không'}")


# ---------------------------------------------------------------- phần B
FAULTS = ["none", "empty", "pay_fail"]       # luân phiên lỗi tool qua các lần chạy


def run_flaky(p: float = 0.3, n: int = 100, seed: int = 0) -> list[dict]:
    rows = []
    for name, mod in PATTERNS.items():
        rs = []
        for i in range(n):
            sc = Scenario(f"flaky_p{p}", FLIGHTS_A, tool_fault=FAULTS[i % len(FAULTS)])
            rs.append(mod.run(sc, src=FlawSource(p=p, seed=seed + i)))
        rows.append(dict(
            p=p, pattern=name, n=n,
            success_rate=sum(r.done for r in rs) / n,
            handoff_ok_rate=sum(handoff_ok(r.handoff) for r in rs if not r.done) / max(1, sum(not r.done for r in rs)),
            avg_model_calls=sum(r.model_calls for r in rs) / n,
            avg_tool_calls=sum(r.tool_calls for r in rs) / n,
            avg_denied=sum(r.denied for r in rs) / n,
            recovered_rate=sum(r.recovered for r in rs) / n,
        ))
    return rows


def print_flaky(rows):
    print(f"\n=== PHẦN B: model ngẫu nhiên (xác suất lỗi p), {rows[0]['n']} lần/mẫu ===")
    print(f"{'p':<6}{'mẫu':<8}{'thành công':>11}{'model TB':>10}{'tool TB':>9}{'chặn TB':>9}{'phục hồi':>10}{'handoff đủ':>12}")
    for r in rows:
        print(f"{r['p']:<6}{r['pattern']:<8}{r['success_rate']:>10.0%}{r['avg_model_calls']:>10.2f}"
              f"{r['avg_tool_calls']:>9.2f}{r['avg_denied']:>9.2f}{r['recovered_rate']:>10.0%}"
              f"{r['handoff_ok_rate']:>12.0%}")


def write_csv(path: Path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig để Excel đọc đúng tiếng Việt
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    fixed = run_fixed()
    print_fixed(fixed)
    write_csv(RESULT_DIR / "ket_qua_co_dinh.csv", fixed)

    flaky = []
    for p in (0.1, 0.3, 0.5):
        flaky += run_flaky(p=p, n=100, seed=0)
    print_flaky(flaky)
    write_csv(RESULT_DIR / "ket_qua_ngau_nhien.csv", flaky)
    print(f"\nĐã ghi CSV vào {RESULT_DIR}")