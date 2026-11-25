# GĐ21.3 — THIẾT KẾ RÀO CHẮN & CỔNG THỰC THI ALPACA PAPER
## PAPER EXECUTION GATE ARCHITECTURE & SAFEGUARD SPECIFICATION

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ21 — Alpaca Paper Trading Integration (GĐ21.3)  
**Chế độ bắt buộc:** `TRADING_MODE=DRY_RUN`  
**Mã nguồn cổng thực thi:** [`libs/alpaca_paper_gate.py`](file:///d:/AlgoTrading/libs/alpaca_paper_gate.py)  
**Trạng thái Cổng thực thi:** **`LOCKED / FAIL-CLOSED`** (`is_gate_open = False`)  

---

## 1. Nguyên lý Thiết kế Cổng Thực thi (Execution Gate Philosophy)

Để chuẩn bị cho việc tương tác với Alpaca Paper trong tương lai mà không gây ra bất kỳ rủi ro nào cho hệ thống hiện tại, dự án áp dụng mô hình **Cổng Thực thi Đóng Mặc định (Fail-Closed Execution Gate)**:

```
+---------------------------------------------------------------------------------------------------+
|                                 MÔ HÌNH CỔNG THỰC THI (PAPER EXECUTION GATE)                      |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [Yêu cầu Đặt/Sửa/Hủy Lệnh]                                                                       |
|               |                                                                                   |
|               v                                                                                   |
|  [Kiểm tra Base URL] ==================> Chứa Live URL ("api.alpaca.markets" không có "paper")    |
|               |                                              |                                    |
|               | (Hợp lệ: paper-api)                          v                                    |
|               v                            [NÉM LiveTradingProhibitedError NGAY LẬP TỨC]          |
|  [Kiểm tra Trạng thái Cổng (Gate)]                                                                |
|               |                                                                                   |
|       +-------+-------+                                                                           |
|       |               |                                                                           |
| (is_gate_open=False)  (is_gate_open=True - CHƯA KÍCH HOẠT)                                        |
|       |                                                                                           |
|       +------> [Có cờ fake_transport=True?]                                                       |
|                     |                                                                             |
|            +--------+--------+                                                                    |
|            |                 |                                                                    |
|         (Không)             (Có)                                                                  |
|            |                 |                                                                    |
|            v                 v                                                                    |
|  [CHẶN ĐỨNG HOÀN TOÀN]    [Xác thực Schema Lệnh Giả lập]                                          |
|  Ném PaperExecutionGate-  Trả về kết quả mock, ZERO network HTTP calls                            |
|  ClosedError              Gắn nhãn: gate_status="CLOSED_MOCK_TRANSPORT"                          |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Các Tầng Kiểm soát An toàn (Safety Guardrails)

### 2.1. Kiểm tra Base URL Ngăn chặn Triệt để Live Trading (TC-G21-20)
- Phương thức `_verify_safety_invariants()` tự động kích hoạt trước mọi thao tác:
  ```python
  if "api.alpaca.markets" in url_lower and "paper" not in url_lower:
      raise LiveTradingProhibitedError(
          f"CRITICAL SECURITY VIOLATION: Endpoint '{self.base_url}' points to Live Alpaca! "
          "Only 'https://paper-api.alpaca.markets' is permitted."
      )
  ```
- **Kết quả Kiểm thử:** Nếu truyền URL của sàn thật `https://api.alpaca.markets`, adapter ném ngay lập tức ngoại lệ `LiveTradingProhibitedError` và hủy bỏ tiến trình.

### 2.2. Trạng thái Khóa Cứng Cổng Thực thi (Fail-Closed Default - TC-G21-15 $\rightarrow$ TC-G21-18)
Trong giai đoạn GĐ21, thuộc tính `is_gate_open` được gán cố định là `False`:
- **Thử nghiệm Submit Order (`submit_paper_order`):** Không có cờ `fake_transport` $\rightarrow$ Ném ngoại lệ `PaperExecutionGateClosedError`.
- **Thử nghiệm Replace Order (`replace_paper_order`):** Không có cờ `fake_transport` $\rightarrow$ Ném ngoại lệ `PaperExecutionGateClosedError`.
- **Thử nghiệm Cancel Order (`cancel_paper_order`):** Không có cờ `fake_transport` $\rightarrow$ Ném ngoại lệ `PaperExecutionGateClosedError`.
- **Thử nghiệm Bulk Cancel (`cancel_all_paper_orders`):** Không có cờ `fake_transport` $\rightarrow$ Ném ngoại lệ `PaperExecutionGateClosedError`.

### 2.3. Kiểm thử Xác thực Cấu trúc qua Vận chuyển Giả lập (Fake Transport - TC-G21-19)
- Khi nhà phát triển hoặc bộ kiểm thử tự động cần xác minh tính hợp lệ của schema lệnh (Market, Limit, Qty, Notional, v.v.), tham số `fake_transport=True` được sử dụng:
  - Adapter thực hiện kiểm tra đầy đủ các ràng buộc nghiệp vụ (symbol hợp lệ, side hợp lệ, qty và notional loại trừ lẫn nhau).
  - Trả về đối tượng phản hồi mẫu với các thuộc tính:
    - `status: "fake_accepted"`
    - `gate_status: "CLOSED_MOCK_TRANSPORT"`
    - `data_source: "ALPACA_PAPER_FAKE"`
    - `broker: "ALPACA_PAPER_SIMULATED"`
    - `is_mock: True`
  - **Cam kết Mạng:** Tuyệt đối không phát sinh bất kỳ lời gọi HTTP (`POST`, `PATCH`, `DELETE`) nào ra ngoài Internet.

---

## 3. Phân định Ba Phân hệ Giao dịch Độc lập (Architectural Tri-Segregation)

Hệ thống thiết lập ranh giới tách bạch 3 thành phần giao dịch độc lập:

| Đặc tính | 1. Mock Broker (`MockTradingBroker`) | 2. Paper Gate (`AlpacaPaperGate`) | 3. Live Trading Execution |
| :--- | :--- | :--- | :--- |
| **Vị trí** | `libs/mock_trading_broker.py` | `libs/alpaca_paper_gate.py` | **HOÀN TOÀN KHÔNG TỒN TẠI** |
| **Mục đích** | Môi trường Sandbox thử nghiệm giao diện | Cổng kiểm soát kết nối Alpaca Paper | Cấm đưa vào mã nguồn |
| **Quyền Ghi** | Cho phép ghi vào tệp JSON cục bộ | **BỊ KHÓA CỨNG (FAIL-CLOSED)** | Bị cấm |
| **Kho Dữ liệu** | `data/mock_broker/mock_broker_state.json` | Bộ nhớ đệm chỉ đọc (In-Memory REST/Stream) | Không có |
| **Gắn nhãn** | `is_mock: True`, `SIMULATED_MOCK_BROKER` | `ALPACA_PAPER` (đọc) / `ALPACA_PAPER_FAKE` | N/A |
| **Trạng thái GĐ21**| **HOẠT ĐỘNG HOÀN TOÀN** | **CHỈ ĐỌC + CỔNG GHI ĐÓNG** | **BỊ LOẠI TRỪ 100%** |

---

## 4. Điều kiện Tiên quyết cho Việc Kích hoạt trong Tương lai

> [!WARNING]
> **Quy định Nghiêm ngặt về Kích hoạt Lệnh Paper Thật:**
> 1. Giai đoạn GĐ21 **tuyệt đối không bật hoặc sử dụng chức năng gửi lệnh thật tới Alpaca Paper**.
> 2. Bất kỳ kế hoạch mở Cổng Thực thi (`is_gate_open = True`) trong tương lai đều phải:
>    - Là một giai đoạn phát triển độc lập với phê duyệt rõ ràng từ ban điều hành dự án.
>    - Vượt qua bộ kiểm tra an toàn cấp cao (Multi-stage Pre-Flight Safety Checks).
>    - Có cơ chế ngắt mạch tự động khẩn cấp (Emergency Kill Switch).
>    - Thiết lập giới hạn trần rủi ro tối đa về vốn và số lượng lệnh trên mỗi phiên.

---

## 5. Kết luận GĐ21.3

Adapter `AlpacaPaperGate` xây dựng thành công lớp phòng thủ rào chắn vững chắc, ngăn chặn 100% việc vô tình gửi lệnh thật ra broker trong khi vẫn cung cấp đầy đủ công cụ xác thực schema phục vụ kiểm thử.

