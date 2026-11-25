# GĐ29 — Reference Architecture Mapping
**AlgoTrading V2.0 Paper Trading Bot Base Adaptation**  
**Reference Document:** *Topic 4 - Paper Trading Bot.pdf* (Author: Anil Gaddam)  
**Target Repository:** `D:\AlgoTrading`  
**Base Version:** AlgoTrading V1.0.0 Stable  
**Primary Timeframe:** `1m` (1 Minute)

---

## 1. Executive Summary

Tài liệu này thực hiện đối chiếu chi tiết giữa **12 thành phần kiến trúc** của Paper Trading Bot trong tài liệu tham khảo của Anil Gaddam với hạ tầng công nghệ hiện hữu của hệ thống **AlgoTrading V1**. 

Mục tiêu chiến lược là kế thừa tối đa hạ tầng streaming, broker simulation, và telemetry đã được nghiệm thu trong V1 (GĐ18–GĐ28), đồng thời chỉ phát triển mới các module chuyên biệt mà V1 còn thiếu để hình thành nền tảng **AlgoTrading V2.0**.

---

## 2. Bảng Đối Chiếu 12 Thành Phần Kiến Trúc Tham Khảo

| STT | Thành phần Tham khảo (Anil Gaddam) | Đặc điểm trong Tài liệu Tham khảo | Thành phần Tương đương trong AlgoTrading V1 | Đánh giá Chênh lệch (Delta / Gap) | Quyết định Thích ứng V2 (V2 Decision) |
|:---:|:---|:---|:---|:---|:---|
| **1** | **`TradingConfig`** | Dataclass chứa cấu hình giao dịch, danh sách mã cổ phiếu, số vốn, và trực tiếp chứa API Key / Secret Key của Alpaca. | `.env`, `alpaca_config/keys.py`, `libs/alpaca_paper_gate.py`. | V1 quản lý biến môi trường tách biệt nhưng chưa có sanitized dataclass riêng cho Bot phiên bản tự động. Nguy cơ rò rỉ secret nếu đưa API key vào config object. | **Xây mới `libs.bot.config.TradingConfig`**: Cấu hình chuẩn hóa, zero-secret storage, ép buộc `timeframe="1m"`, `dry_run=True`, và `environment="SIMULATION"`. |
| **2** | **`DataManager`** | Polling dữ liệu nến lịch sử và giá hiện tại qua Alpaca REST API (`get_bars`) hoặc `yfinance` với độ trễ theo chu kỳ phút/giờ. | `continuous_price_producer.py`, `continuous_crypto_producer.py`, Redpanda topics (`stock-prices`, `crypto-bars-1m`). | V1 sử dụng Streaming Architecture (Redpanda + WebSocket) với độ trễ tính bằng mili-giây, vượt trội hoàn toàn so với mô hình REST polling của tài liệu tham khảo. | **Xây dựng Adapter `BotRedpandaConsumerAdapter`**: Lắng nghe trực tiếp từ topic 1m của Redpanda với consumer group riêng biệt (`paper-bot-v2-group`). Giữ REST API chỉ làm fallback backfill. |
| **3** | **`MarketData` Schema** | Cấu trúc nến OHLCV đơn giản, thường dùng Pandas DataFrame dạng `[timestamp, open, high, low, close, volume]`. | Schema Flink/Redpanda trong `ddl_production.sql` và `ddl_crypto.sql` (hỗ trợ `trade_count`, `vwap`, `is_final`, `event_time`). | V1 đã hỗ trợ cơ chế nến tạm thời (provisional) và nến chốt (finalized) qua trường `is_final` và watermark của Flink. | **Chuẩn hóa Domain Entity `MarketDataEvent`**: Đóng gói đầy đủ OHLCV, `trade_count`, `vwap`, `is_final`, và ép buộc timeframe `1m`. |
| **4** | **`TradingStrategy` (Base)** | Lớp trừu tượng `TradingStrategy(ABC)` với phương thức `generate_signals(data, symbol)`. | Chưa có class Python trừu tượng tương đương; V1 tính toán SMA 20/50 trực tiếp trong Flink SQL DDL. | Flink SQL rất mạnh cho streaming aggregation nhưng thiếu linh hoạt khi người dùng muốn chạy các thuật toán Python tùy biến (RSI, Bollinger Bands, ML). | **Xây mới Interface `TradingStrategy`**: Abstract Base Class trong Python, cho phép cắm rút chiến lược linh hoạt, đồng thời hỗ trợ `V1StrategyAdapter` để tái sử dụng tín hiệu từ Flink SQL. |
| **5** | **`MovingAverageCrossover`** | Chiến lược mẫu tính Short MA và Long MA trên Pandas Series, phát tín hiệu BUY/SELL khi có giao cắt. | Flink SQL Continuous Query trong `ddl_production.sql` (SMA 20 và SMA 50). | Flink SQL chạy độc lập trên cụm Flink; cần có bộ tính toán nhẹ tại tầng bot để kiểm tra độc lập và backtest nhanh. | **Hiện thực `MovingAverageCrossoverStrategy`**: Thuật toán Python xác định (deterministic), hỗ trợ cửa sổ tùy chỉnh (mặc định 9/21 trên nến 1m), chỉ kích hoạt khi nến chốt (`is_final=True`). |
| **6** | **`TradingSignal`** | Tín hiệu BUY/SELL đơn giản kèm theo symbol và thời gian. | Schema JSON trong Redpanda topics `trading-signals` và `crypto-signals`. | Tín hiệu V1 rất chi tiết nhưng thiếu trace ID và trường xác nhận môi trường thực thi. | **Chuẩn hóa Domain Entity `StrategySignal`**: Đầy đủ `signal_id`, `strategy_id`, `symbol`, `signal_type`, `price`, `strength`, `reason`, `environment="SIMULATION"`. |
| **7** | **`PortfolioManager`** | Tính toán khối lượng lệnh dựa trên quy tắc rủi ro cố định (Fixed Fractional / 2% Risk Rule) và sức mua. | Chưa có module riêng; V1 Mock Workbench sử dụng khối lượng nhập tay từ UI (`qty: 5.0`). | Thiếu hoàn toàn logic quản lý vốn tự động và phân bổ rủi ro theo quy mô tài khoản trong V1. | **Xây mới Module `BotPortfolioManager`**: Quản lý hạn mức vốn, kiểm tra sức mua, thực thi công thức Position Sizing 2% rủi ro, và phát hành `SignalDecision`. |
| **8** | **`OrderManager`** | Tạo và gửi lệnh trực tiếp qua Alpaca API (`submit_order`). | `libs/mock_trading_broker.py` (Local simulation) và `libs/alpaca_paper_gate.py` (Gate bị khóa). | Tài liệu tham khảo gửi lệnh trực tiếp không qua kiểm duyệt an toàn, không có Idempotency key, rất dễ gây trùng lệnh. | **Xây dựng `SimulationOrderManager` & Adapter**: Tách biệt luồng ý định (`SimulationOrderIntent`) và lệnh giả lập (`SimulatedOrder`), định tuyến 100% vào Simulation Broker sandbox. |
| **9** | **`TradingBot` Orchestrator**| Vòng lặp `while True` với `time.sleep(300)` kiểm tra thị trường theo chu kỳ. | Chưa có bot orchestrator tự động; V1 chỉ có các continuous producers và signal handlers thụ động. | Mô hình polling theo giây/phút trong tài liệu tham khảo gây nghẽn và không tương thích với streaming event-driven. | **Xây mới State Machine `TradingBotLifecycle`**: Vòng đời điều khiển trạng thái chuẩn (`STOPPED` -> `STARTING` -> `RUNNING` -> `PAUSED` -> `STOPPING` -> `ERROR`), phản ứng theo từng nến 1m Redpanda. |
| **10**| **Broker Execution Client** | Alpaca Trade SDK (`REST.submit_order`) thao tác trực tiếp với tài khoản Paper. | `libs/mock_trading_broker.py` và `libs/alpaca_paper_gate.py`. | Alpaca Paper của V1 đang bị khóa chặt bằng `is_gate_open = False` và `TRADING_MODE=DRY_RUN`. Tuyệt đối không mở cổng cho bot tự động. | **Tái sử dụng & Mở rộng `MockTradingBroker`**: Toàn bộ lệnh của V2 Bot được khớp trong Sandbox Simulation độc lập, bảo vệ tuyệt đối Alpaca Paper Read-Only. |
| **11**| **Telemetry & Audit Log** | Logging đơn giản ra console hoặc file text. | FastAPI backend endpoints, WebSocket streams, telemetry metrics trong `data/mock_broker/`, `data/status/`. | V1 có hệ thống telemetry cực kỳ phong phú và bảng điều khiển trực quan. | **Tích hợp `BotAuditEvent` vào Telemetry V1**: Ghi nhật ký có cấu trúc với `trace_id`, liên kết trực tiếp lên giao diện Dashboard V2. |
| **12**| **Scheduler / Runner** | Script chạy trực tiếp từ CLI qua terminal. | PowerShell scripts, runbooks (`run_crypto_pipeline.ps1`, `run_stock_pipeline.ps1`), FastAPI background tasks. | Cần có API kiểm soát Start/Stop/Pause từ Web Dashboard thay vì phụ thuộc CLI thủ công. | **Thiết kế Unified Bot Controller**: Hỗ trợ kích hoạt qua cả FastAPI endpoint và Background Runner an toàn. |

---

## 3. Phân Tích Chuyên Sâu Các Quyết Định Thích Ứng

### 3.1. Chuyển Dịch Từ Polling Sang Event-Driven Streaming (1m Timeframe)
- **Tài liệu tác giả:** Sử dụng vòng lặp `time.sleep(60)` hoặc `schedule.every(5).minutes` để gọi Alpaca REST API lấy dữ liệu nến. Hạn chế: Giới hạn tần suất gọi API (Rate limits), dữ liệu trễ, không đồng bộ với thời điểm nến đóng.
- **Thích ứng V2:** Tận dụng hạ tầng Redpanda có sẵn trong V1 (`stock-prices` và `crypto-bars-1m`). Bot đăng ký consumer group riêng `paper-bot-v2-group`. Mỗi khi một nến 1m đóng (`is_final=True`), sự kiện được đẩy tức thì vào chiến lược. Độ trễ từ khi nến đóng đến khi sinh tín hiệu giảm từ vài giây xuống dưới 50 mili-giây.

### 3.2. Độc Lập Quản Lý Vốn Và Định Cỡ Lệnh (2% Risk Rule)
- **Tài liệu tác giả:** Đưa ra công thức định cỡ vị thế mẫu dựa trên 2% vốn khả dụng chia cho khoảng cách Stop Loss:
  $$\text{Quantity} = \frac{\text{Equity} \times \text{RiskPercentage}}{|\text{EntryPrice} - \text{StopLossPrice}|}$$
- **Thích ứng V2:** Chuẩn hóa công thức trên vào interface `BotPortfolioManager`. Khác với V1 chỉ hỗ trợ số lượng cố định, V2 tự động tính toán số lượng cổ phiếu/crypto dựa trên biến động giá và số dư tài khoản ảo hiện tại, ngăn ngừa rủi ro cháy tài khoản mô phỏng.

### 3.3. Bảo Vệ An Toàn Tuyệt Đối (Air-Gap Simulation)
- **Tài liệu tác giả:** Hướng dẫn cấu hình API Key thật vào script và gửi lệnh thẳng lên Alpaca Paper.
- **Thích ứng V2:** Tuân thủ triệt để nguyên tắc an toàn V1. Cấu hình `TradingConfig` hoàn toàn **Zero-Secret**. Tất cả lệnh từ bot tự động chỉ được phép đi vào `BotSimulationBrokerAdapter`, tuyệt đối không có đường dẫn nào chạm tới `AlpacaPaperGate.submit_paper_order` khi chưa có phê duyệt nghiệm thu đặc biệt.
