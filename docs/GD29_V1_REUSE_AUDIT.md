# GĐ29 — V1 Component Reuse Audit
**AlgoTrading V2.0 Paper Trading Bot Base Adaptation**  
**Repository:** `D:\AlgoTrading`  
**Classification System:** 5-Tier Component Taxonomy  
**Status:** AUDITED & VALIDATED

---

## 1. Mục Đích & Tiêu Chí Phân Loại

Tài liệu này kiểm kê và phân loại toàn bộ mã nguồn của hệ sinh thái **AlgoTrading V1.0.0** nhằm tối ưu hóa khả năng tái sử dụng cho **V2.0 Paper Trading Bot**, tránh việc lập trình lại các thành phần đã ổn định và đảm bảo tuân thủ các ranh giới an toàn.

Hệ thống phân loại gồm **5 tầng (5-Tier Taxonomy)**:
1. **Tier 1 — Direct Reuse (Tái sử dụng trực tiếp 100%):** Các module hoạt động hoàn chỉnh, giữ nguyên vẹn không sửa đổi mã nguồn.
2. **Tier 2 — Adapter Integration (Bọc qua Adapter):** Các thành phần hiện hữu được kết nối vào kiến trúc V2 thông qua các lớp trung gian (Wrapper / Adapter Interface).
3. **Tier 3 — New Component (Xây mới cho V2):** Các thành phần kiến trúc V1 chưa từng có, cần phát triển mới theo chuẩn V2.
4. **Tier 4 — Read-Only Telemetry Reference (Tham chiếu giám sát):** Các module dữ liệu/UI dùng để hiển thị, đối chiếu và kiểm tra trạng thái, không tham gia vào luồng xử lý giao dịch.
5. **Tier 5 — Strictly Prohibited / Air-Gapped (Cách ly an toàn tuyệt đối):** Các cổng giao tiếp Live hoặc các lệnh ghi broker bị phong tỏa fail-closed.

---

## 2. Bảng Phân Loại Toàn Bộ Thành Phần Repository

| Tên File / Module | Phân Loại | Vai Trò trong V1 | Vai Trò & Phương Thức Tái Sử Dụng trong V2 | Ghi Chú An Toàn / Ràng Buộc |
|:---|:---:|:---|:---|:---|
| `continuous_price_producer.py` | **Tier 1** | Stream giá cổ phiếu (Stocks) 1m vào `stock-prices` | Tiếp tục đóng vai trò nguồn cấp dữ liệu thị trường trực tiếp cho V2 Bot | Giữ nguyên pipeline, không đổi format topic |
| `continuous_crypto_producer.py` | **Tier 1** | Stream giá tiền số (Crypto) 1m vào `crypto-bars-1m` | Nguồn cấp dữ liệu nến crypto 1m chuẩn (hỗ trợ `is_final`) cho V2 Bot | Giữ nguyên pipeline và logic nến chốt |
| `ddl_production.sql` / Flink Stocks | **Tier 1** | Flink Continuous Query tính SMA 20/50 cổ phiếu | Hoạt động song song; cung cấp tín hiệu đối chứng cho V2 Strategy Engine | Không sửa đổi DDL đang chạy |
| `ddl_crypto.sql` / Flink Crypto | **Tier 1** | Flink Streaming tính nến 1m và tín hiệu crypto | Hoạt động song song; cung cấp nến 1m tổng hợp và watermark chuẩn | Không sửa đổi DDL đang chạy |
| `libs/mock_trading_broker.py` | **Tier 2** | Mock Broker Engine cho Trading Workbench (GĐ19) | Nhân lõi mô phỏng giao dịch của V2; bọc qua `BotSimulationBrokerAdapter` | V2 sử dụng session/state tách biệt, không ghi đè state manual V1 |
| `libs/alpaca_paper_gate.py` | **Tier 2** | Cổng kiểm soát Alpaca Paper Read-Only & Fail-Closed | Cung cấp tài khoản đối chứng thị trường thực (Read-Only) để so sánh hiệu năng | Khóa chặt `is_gate_open = False`, cấm ghi |
| `signal-handler.py` | **Tier 2** | Consumer tín hiệu Flink cổ phiếu, đẩy qua UI/Slack | Tích hợp qua `V1StrategyAdapter` để bot lắng nghe tín hiệu Flink khi cần | Không làm gián đoạn consumer group hiện hữu |
| `crypto_signal_handler.py` | **Tier 2** | Consumer tín hiệu Flink crypto | Tương tự `signal-handler.py`, cung cấp luồng tín hiệu crypto cho V2 Adapter | Không làm gián đoạn consumer group hiện hữu |
| `libs/bot/domain.py` | **Tier 3** | *Chưa có trong V1* | Định nghĩa 10 thực thể nghiệp vụ chuẩn của V2 Paper Bot | Thuộc tính `environment="SIMULATION"` bắt buộc |
| `libs/bot/interfaces.py` | **Tier 3** | *Chưa có trong V1* | Bộ giao diện trừu tượng chuẩn hóa (Strategy, Data, Portfolio, Order) | Tuân thủ thiết kế hướng đối tượng mở rộng |
| `libs/bot/config.py` | **Tier 3** | *Chưa có trong V1* | Cấu hình tham số bot, quản lý rủi ro, zero-secret storage | Ép buộc `timeframe="1m"`, `dry_run=True` |
| `libs/bot/strategies.py` | **Tier 3** | *Chưa có trong V1* | Bộ chiến lược Python xác định (MA Crossover, RSI, V1 Adapter) | Chạy độc lập hoặc phối hợp với Flink |
| `libs/bot/adapters.py` | **Tier 3** | *Chưa có trong V1* | Các adapter kết nối Redpanda 1m và Mock Broker sandbox | Định tuyến an toàn, bảo vệ offset Kafka |
| `libs/shadow_mode_observer.py` | **Tier 4** | Quan sát và đối chiếu tín hiệu Flink với giá thị trường | Cung cấp số liệu phân tích độ trễ tín hiệu và độ trượt giá cho V2 Bot | Chỉ đọc dữ liệu đối soát |
| `libs/alpaca_order_stream_processor.py`| **Tier 4** | Khử trùng lặp và đồng bộ trạng thái lệnh từ Alpaca | Module tham chiếu logic xử lý trạng thái lệnh và khử trùng lặp | Chỉ đọc |
| `trading-dashboard/backend/main.py` | **Tier 2** | FastAPI backend phục vụ REST & WebSocket cho V1 UI | Mở rộng thêm router `/api/v2/bot/*` để quản lý vòng đời và số liệu V2 Bot | Giữ nguyên các endpoints V1 hiện hữu |
| `trading-dashboard/frontend/` | **Tier 2** | Giao diện Vue 3 Dashboard (Overview, Mock Workbench, ...) | Mở rộng thêm tab/component "Trading Bot V2" phục vụ điều khiển và giám sát | Tái sử dụng Pinia store và theme giao diện |
| `Alpaca Live Trading Endpoints` | **Tier 5** | *Bị cấm trong V1* | **TUYỆT ĐỐI CẤM** trong V2; mọi kết nối đến `api.alpaca.markets` bị chặn | Ném lỗi `LiveTradingProhibitedError` ngay lập tức |

---

## 3. Đánh Giá Khả Năng Tái Sử Dụng Và Khoảng Trống (Gap Analysis)

### 3.1. Thành phần Tái sử dụng Tốt nhất (Strengths)
1. **Hạ tầng Streaming Dữ liệu 1 Phút:**
   V1 đã hoàn thiện hạ tầng Redpanda với topic nến 1m (`crypto-bars-1m`) có trường `is_final` và topic cổ phiếu (`stock-prices`). V2 Paper Bot không cần xây dựng cơ chế lấy dữ liệu từ đầu mà chỉ cần cắm consumer group mới vào.
2. **Mock Broker Simulation Engine:**
   File `libs/mock_trading_broker.py` đã có sẵn logic quản lý số dư \$100,000, tính toán lãi lỗ (Realized/Unrealized PnL), định giá thị trường theo danh mục, và nhật ký hoạt động (Order Activity). V2 chỉ cần đóng gói thành adapter hướng đối tượng.
3. **Cơ chế An toàn Fail-Closed:**
   Bộ thư viện `libs/alpaca_paper_gate.py` đã cung cấp sẵn các ngoại lệ bảo vệ (`PaperExecutionGateClosedError`, `LiveTradingProhibitedError`), giúp V2 kế thừa ngay lập tức cơ chế phòng vệ chống đặt lệnh thật.

### 3.2. Khoảng Trống Nghiệp Vụ Cần Xây Mới (Gaps Solved in V2)
1. **Thiếu Lớp Chiến Lược Python Linh Hoạt:**
   Trong V1, toàn bộ chiến lược nằm ở Flink SQL DDL (`ddl_production.sql`). Người dùng không thể thử nghiệm các chiến lược phức tạp nếu không can thiệp vào Flink job. V2 bổ sung `TradingStrategy(ABC)` giúp định nghĩa các chiến lược Python nhanh chóng.
2. **Thiếu Bộ Quản Lý Vốn & Rủi Ro Tự Động (Portfolio Manager):**
   V1 chỉ cho phép đặt lệnh với số lượng cố định nhập tay. V2 bổ sung `BotPortfolioManager` với công thức tính vị thế theo tỷ lệ rủi ro 2% vốn khả dụng.
3. **Thiếu Bộ Điều Khiển Vòng Đời Bot (Lifecycle State Machine):**
   V1 vận hành dựa trên các tiến trình nền chạy liên tục không có cơ chế Start / Pause / Resume / Stop có kiểm soát từ giao diện. V2 bổ sung máy trạng thái chuẩn mực cho phiên giao dịch bot.
