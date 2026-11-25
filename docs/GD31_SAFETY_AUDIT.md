# GĐ31 — Safety & Execution Guardrails Audit
**AlgoTrading V2.0 Safety Architecture Compliance Audit**  
**Repository:** `D:\AlgoTrading`  
**Phase:** GĐ31 — Python Strategy Engine & Indicator Library  
**Trading Mode:** `TRADING_MODE=DRY_RUN`  
**Execution Gate:** `PaperExecutionGate.is_gate_open = False` (LOCKED)

---

## 1. Kiểm Toán 14 Ràng Buộc An Toàn Tuyệt Đối (The 14 Invariants Audit)

| STT | Ràng Buộc Bất Biến (Invariant) | Hiện Trạng Thực Tế trong GĐ31 | Bằng Chứng Kiểm Tra & Mã Nguồn | Kết Luận |
|:---:|:---|:---|:---|:---:|
| **1** | Giữ `TRADING_MODE=DRY_RUN` | Được duy trì tuyệt đối trong cấu hình hệ thống. | `libs/bot/config.py` ép buộc `dry_run=True`. | **COMPLIANT** |
| **2** | Giữ `PaperExecutionGate.is_gate_open = False` | Khóa cổng fail-closed, chặn mọi lệnh gửi. | `libs/alpaca_paper_gate.py:71` (`is_gate_open=False`). | **COMPLIANT** |
| **3** | Không gửi, sửa, hủy lệnh qua Alpaca Paper | Hoàn toàn không có thao tác broker write nào. | `tests/test_gd31_strategy_engine.py:test_35`. | **COMPLIANT** |
| **4** | Không có đường thực thi Live | Mọi URL Live (`api.alpaca.markets`) đều bị chặn ném lỗi. | `libs/alpaca_paper_gate.py:84`. | **COMPLIANT** |
| **5** | Không gọi Alpaca Order API | Strategy Engine không import hay kết nối Order API. | `tests/test_gd31_strategy_engine.py:test_33`. | **COMPLIANT** |
| **6** | Không thay đổi Production Flink Strategy 1 | Giữ nguyên trạng các tệp `ddl_production.sql` và jobs Flink. | Git status xác nhận Flink SQL jobs nguyên vẹn. | **COMPLIANT** |
| **7** | Không thay đổi Flink SQL production jobs | Cụm Flink và streaming jobs tiếp tục chạy độc lập. | Không can thiệp Flink containers. | **COMPLIANT** |
| **8** | Không sửa các Redpanda market data topics | Các topic `stock-prices` và `crypto-bars-1m` nguyên trạng. | Schema và topic configuration không thay đổi. | **COMPLIANT** |
| **9** | Không thay đổi offset/group của V1 và GĐ30 | Duy trì nhóm `paper-bot-v2-group`, checkpoint lưu riêng. | `data/paper_bot/market_data/checkpoints/`. | **COMPLIANT** |
| **10**| Không làm gián đoạn runtime V1 | Các container và dịch vụ V1 không bị kill hoặc restart. | Runtime V1 duy trì liên tục. | **COMPLIANT** |
| **11**| Không ghi fixture vào topic thị trường tự nhiên| Dữ liệu fixture chỉ phục vụ test nội bộ trong memory/disk. | `tests/test_gd31_strategy_engine.py:test_38`. | **COMPLIANT** |
| **12**| Nhãn `environment=SIMULATION` bắt buộc | 100% tín hiệu sinh ra đều gắn nhãn SIMULATION. | `tests/test_gd31_strategy_engine.py:test_37`. | **COMPLIANT** |
| **13**| Không triển khai dữ liệu 1-second | Chuẩn hóa cố định trên nến 1 phút (`timeframe="1m"`). | `BaseStrategy.required_timeframe = "1m"`. | **COMPLIANT** |
| **14**| Không tự ý tối ưu tham số trên dữ liệu lịch sử| Tham số SMA (20/50) và RSI (14, 30/70) giữ đúng chuẩn tài liệu. | Tham số giữ nguyên theo tài liệu Anil Gaddam. | **COMPLIANT** |

---

## 2. Ranh Giới Chức Năng Của Giai Đoạn GĐ31

Để bảo đảm tính an toàn và phân kỳ rõ ràng của dự án AlgoTrading V2:
- **Phạm vi được phép trong GĐ31:**
  - Tính toán chỉ báo kỹ thuật (SMA, EMA, RSI, MACD, Bollinger Bands).
  - Đánh giá điều kiện kỹ thuật và phát hành `StrategySignal`.
  - Khử trùng lặp và lưu trữ tín hiệu vào `data/paper_bot/strategies/`.
  - So sánh đối soát tín hiệu với Apache Flink ở chế độ Read-Only.
- **Phạm vi nghiêm cấm trong GĐ31:**
  - Tuyệt đối KHÔNG tính toán định cỡ vị thế hay quản lý rủi ro (thuộc về **GĐ32 — Portfolio & Risk Management Engine**).
  - Tuyệt đối KHÔNG tạo lệnh mô phỏng, không ghi nhận sổ lệnh hay giả lập khớp lệnh (thuộc về **GĐ33 — Simulation Broker & Advanced Fill Engine**).
  - Tuyệt đối KHÔNG khởi tạo vòng đời phiên giao dịch tự động hoàn chỉnh (thuộc về **GĐ34 — Bot Orchestrator & State Machine**).
