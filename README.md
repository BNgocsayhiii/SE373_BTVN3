# SE373 - Đánh giá Kiến trúc AI Agent với Lớp Harness

Hệ thống mô phỏng một Agent đặt vé máy bay tự động, được thiết kế với 3 mẫu suy luận (Reasoning Patterns) khác nhau và được bảo vệ nghiêm ngặt bởi một lớp kiểm soát (Harness).

## 🚀 Các kiến trúc Agent được cài đặt
1. **ReAct (`react.py`):** Vòng lặp suy luận - hành động xen kẽ, sử dụng LangGraph.
2. **Plan-then-Execute (`plan_then_execute.py`):** Lập kế hoạch toàn diện trước, được Harness duyệt bằng code tĩnh rồi mới thực thi tuần tự.
3. **Hybrid / Lai (`lai.py`):** Kết hợp cả hai. Ưu tiên chạy Plan-then-Execute, nếu gặp sự cố sẽ giữ nguyên ngữ cảnh, chuyển giao ngân sách còn lại cho ReAct xử lý tiếp.

## 🛡️ Lớp Harness (Kiểm soát & Bảo vệ)
Toàn bộ hành động của Agent đều phải đi qua `harness.py` với các cơ chế:
- **Data Constraints:** Kiểm tra ràng buộc độc lập, không phụ thuộc vào LLM.
- **Computational Sensor:** Xác nhận hoàn thành bằng trạng thái hệ thống, chống ảo giác (hallucination).
- **Guarded Call:** Kiểm duyệt quyền hạn trước khi thực thi tool (đặc biệt là tác vụ tốn phí như `pay`).
- **Handoff:** Bàn giao rõ ràng ngữ cảnh và trạng thái khi cần con người can thiệp.

## 📂 Cấu trúc repository
- `common.py`: Định nghĩa dữ liệu chuyến bay, kịch bản (Scenario) và ràng buộc.
- `tool.py`, `kich_ban.py`: Các tool mockup và cơ chế tiêm lỗi tự động (Fault Injection).
- `model_gia.py`: LLM giả lập hoạt động theo chính sách, phục vụ việc đánh giá kiến trúc thay vì đánh giá LLM.
- `evaluate.py`: Chạy kiểm thử tự động.

## ⚙️ Hướng dẫn chạy
**1. Cài đặt dependencies:**
\`\`\`bash
pip install -r requirements.txt
\`\`\`

**2. Chạy file đánh giá:**
\`\`\`bash
python evaluate.py
\`\`\`
*Script sẽ chạy Part A (kịch bản cố định) và Part B (chèn lỗi ngẫu nhiên). Kết quả sẽ được in ra console và lưu thành 2 file `.csv` trong thư mục `result/`.*
