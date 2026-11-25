# BÁO CÁO NGHIỆM THU ĐỘ CHÍNH XÁC CHIẾN LƯỢC, TÍNH ĐÚNG THỜI GIAN & BACKTEST LỊCH SỬ (GĐ13)

Dự án: **AlgoTrading**  
Đường dẫn: `D:\AlgoTrading`  
Mã giai đoạn: **GĐ13 — Strategy Accuracy, Temporal Correctness & Backtesting**  
Thời gian thực hiện: Tháng 10/2026  
Mã nguồn kiểm thử tự động: `tests/test_gd13_master_acceptance_suite.py`, `tests/test_gd13_numerical_parity.py`, `backtest/run_backtest.py`  
Báo cáo máy đọc được: `data/status/gd13_master_acceptance_report.json`, `data/status/gd13_numerical_parity_report.json`, `data/status/gd13_backtest_results.json`  
Chế độ giao dịch an toàn: `TRADING_MODE=DRY_RUN` (Bảo toàn tuyệt đối, zero live/paper orders phát sinh)

---

## 1. Tóm tắt Kết quả Nghiệm thu (Executive Summary)

Giai đoạn GĐ13 đã thực hiện kiểm toán toàn diện, đối chiếu toán học, kiểm tra tính đúng đắn thời gian và thực hiện backtesting lịch sử cho hệ thống giao dịch tự động của cả hai phân hệ **Stocks** và **Crypto**:

- **Tổng số ca kiểm thử nghiệm thu (Test Cases)**: **16 / 16**
- **Số ca đạt (PASS)**: **16 / 16 (100%)**
- **Số ca thất bại (FAIL)**: **0 / 16 (0%)**
- **Số lượt đánh giá Backtest đa tài sản**: **80 evaluations** (4 tài sản $\times$ 5 chiến lược $\times$ 4 tập phân chia)
- **Tài liệu bàn giao (Deliverables)**: Đầy đủ 5 tài liệu kỹ thuật trong thư mục `docs/`:
  1. `docs/GD13_STRATEGY_SPECIFICATION.md`: Phân tích đặc tả chiến lược, so sánh PDF vs Production, mổ xẻ lỗi Flink SQL.
  2. `docs/GD13_TEMPORAL_AUDIT.md`: Kiểm toán tính đúng đắn thời gian, watermark, out-of-order, late events và look-ahead bias.
  3. `docs/GD13_NATURAL_SIGNAL_RCA.md`: Phân tích nguyên nhân gốc rễ (RCA) vì sao xuất hiện 0 tín hiệu tự nhiên trong GĐ12 kèm phễu chẩn đoán.
  4. `docs/GD13_BACKTEST_REPORT.md`: Báo cáo backtest lịch sử chi tiết, so sánh 5 biến thể chiến lược và phân tích nhật ký giao dịch.
  5. `docs/GD13_ACCEPTANCE.md`: Báo cáo nghiệm thu tổng thể 16 test cases và khuyến nghị kỹ thuật.
- **Trạng thái Nghiệm thu Tổng thể**: **ĐẠT (PASS)**

---

## 2. Ma trận Nghiệm thu Chi tiết 16 Ca Kiểm Thử (16/16 PASS)

Dưới đây là ma trận chi tiết đối chiếu theo đúng yêu cầu đề bài:

| ID | Tên Bài Test | Hạng mục / Thành phần | Pre-conditions | Dữ liệu Đầu vào (Input) | Kết quả Kỳ vọng (Expected) | Kết quả Thực tế (Actual) | Bằng chứng Kiểm thử (Evidence) | Trạng thái |
|---|---|---|---|---|---|---|---|---|
| **TC-G13-01** | PDF Baseline Fidelity | Strategy DDL | File PDF gốc và SQL DDLs tồn tại | `ddl_production.sql`, `ddl.sql`, PDF trang 13 | DDL bảo tồn chính xác công thức BUY/SELL và cửa sổ 1-phút join từ PDF | Công thức BUY: `sentiment > 0 AND close < sma_20 AND lag >= sma_20`; SELL: `sentiment < 0 AND close > sma_20`; Join 1m | `ddl_production.sql` dòng 105-116 khớp 100% PDF trang 13 | **PASS** |
| **TC-G13-02** | Stocks Strategy Parity | Flink Streaming Job | Flink cluster UP | REST API `localhost:8081` | Job Flink Stocks đang thực thi topology `ddl_production.sql` với 6 tasks `RUNNING` | Job `69cdeb5713259bdcb8bcdece2b0be065` đang hoạt động, 6/6 tasks `RUNNING` | `GET http://localhost:8081/jobs/overview` trả về state `RUNNING` | **PASS** |
| **TC-G13-03** | Crypto Strategy Parity | Flink Crypto Job | Flink cluster UP | REST API `localhost:8081` | Job Crypto enforce nến đóng `is_final=TRUE` và cú pháp window framing tương thích streaming | Job `91da158edbe9fdb0b53f59d0f416c0e4` đang hoạt động, sử dụng `is_final` và `FIRST_VALUE` | `ddl_crypto.sql` dòng 77, 87, 126-134; Job REST API | **PASS** |
| **TC-G13-04** | SMA20 / SMA50 Numerical Correctness | Analytical Accuracy | Nến lịch sử sạch | 100 nến thực tế từ `stock_prices.csv` | Sai số số học giữa Flink và Python độc lập $< 10^{-4}$ (chuẩn IEEE 754) | Sai số SMA20: `0.0000000000`, Sai số SMA50: `0.0000000000` tại nến 100 | `data/status/gd13_numerical_parity_report.json` | **PASS** |
| **TC-G13-05** | Previous-Close / Crossover Mathematical Correctness | Specification Audit | Nến NVDA lịch sử | 3,928 nến NVDA | Định lượng độ lệch giữa Def A ($SMA20_t$) và Def B ($SMA20_{t-1}$) | Xác định chính xác 79 nến bị lệch tín hiệu (2.01%) do hiện tượng "phantom crossover" | `data/status/gd13_numerical_parity_report.json` mục crossover analysis | **PASS** |
| **TC-G13-06** | Temporal JOIN Window Correctness | Temporal Architecture | DDL SQL definitions | DDL files | Stocks giới hạn $[-1\text{m}, 0]$, Crypto giới hạn $[-2\text{m}, +2\text{m}]$ theo event-time | Cửa sổ tham chiếu thời gian được cấu hình chuẩn xác trong mệnh đề `BETWEEN` của SQL | `ddl_production.sql`: dòng 106, `ddl_crypto.sql`: dòng 113 | **PASS** |
| **TC-G13-07** | Zero Look-Ahead Bias Enforcement | Backtest Simulation | Backtest engine | Chuỗi nến OHLCV | Tín hiệu sinh tại $Close_t$ chỉ được khớp lệnh tại $Open_{t+1}$ | Lệnh được đưa vào `pending_order` và khớp chính xác tại thanh nến tiếp theo ($t+1$) | `backtest/engine.py`: pending_order executed on subsequent bar iteration | **PASS** |
| **TC-G13-08** | Late Events Watermark Handling | Event-Time Processing | Flink DDLs | DDL Watermark syntax | Hai stream định nghĩa watermark trễ tối đa 5 giây; late data bị drop | Watermark được cấu hình `event_time - INTERVAL '5' SECOND` trên cả Prices và News | `ddl_production.sql`: dòng 17, 39; `ddl_crypto.sql`: dòng 22, 42 | **PASS** |
| **TC-G13-09** | Duplicate Candles Suppression Invariant | Data Ingestion | Producers | Code checkpointing | Producer checkpoints lưu `last_candle_ts`, bỏ qua nến trùng timestamp | Tất cả nến có $ts \le ts_{last}$ đều bị loại bỏ trước khi gửi vào Kafka | `continuous_price_producer.py`: dòng 318; `continuous_crypto_producer.py`: dòng 330 | **PASS** |
| **TC-G13-10** | News Freshness & Arrival Sparsity Analysis | Data Characteristics | Historical news CSV | 177 tin tức `market_news.csv` | Định lượng mức độ thưa thớt của tin tức so với dòng nến 1 phút | Khoảng cách trung vị giữa các tin tức là 15.0 phút (lớn gấp 15 lần chu kỳ nến) | Phân tích delta timestamp trong `docs/GD13_TEMPORAL_AUDIT.md` | **PASS** |
| **TC-G13-11** | Natural Signal Root Cause Diagnostics Funnel | Strategy Audit | Dữ liệu E2E GĐ12 | 5,975 nến và 177 tin tức | Phễu chẩn đoán giải thích thỏa đáng vì sao có 0 tín hiệu tự nhiên trong GĐ12 | 5,975 nến $\rightarrow$ 141 join matches $\rightarrow$ 7 BUY / 6 SELL trong quá khứ; 0 trong live do thị trường đóng và tin tức crypto lệch pha | `docs/GD13_NATURAL_SIGNAL_RCA.md` | **PASS** |
| **TC-G13-12** | Backtest Cash & Equity Accounting | Backtest Accounting | Backtest run NVDA | 3,928 nến NVDA | Số dư tiền mặt, giá trị danh mục và tỷ lệ lợi nhuận thỏa mãn phương trình kế toán | Vốn ban đầu: $\$100,000.00$, Vốn cuối kỳ: $\$99,864.47$, Return tính toán: $-0.14\%$, Return báo cáo: $-0.14\%$ | `data/status/gd13_backtest_results.json` | **PASS** |
| **TC-G13-13** | Fee and Slippage Friction Modeling Impact | Execution Realism | Lệnh đã khớp | Bảng giao dịch backtest | Mọi giao dịch đều bị trừ phí thực tế ($5\text{ bps}$ Stocks, $25\text{ bps}$ Crypto) và slippage | Toàn bộ 13 lượt khớp vị thế đều ghi nhận khấu trừ phí chính xác | `data/status/gd13_backtest_trades.csv` cột `fees` và `slippage` | **PASS** |
| **TC-G13-14** | Benchmark Comparison & Alpha Evaluation | Performance Analytics | 80 evaluations | Chuỗi giá đóng cửa | Mọi lượt backtest đều tính toán lợi nhuận Buy & Hold benchmark và Alpha tương đối | Benchmark và Alpha được tính toán đầy đủ cho cả 4 tài sản và 4 phân vùng dữ liệu | `data/status/gd13_strategy_comparison.csv` cột `Benchmark_Return_Pct`, `Alpha_Pct` | **PASS** |
| **TC-G13-15** | Zero Unintended Orders Guardrail | System Safety | Hệ thống vận hành | File cấu hình `.env` | Chế độ `TRADING_MODE=DRY_RUN` được duy trì nghiêm ngặt trong suốt GĐ13 | `TRADING_MODE=DRY_RUN` kích hoạt; zero live/paper orders gửi tới Alpaca | File `.env`: `TRADING_MODE=DRY_RUN` | **PASS** |
| **TC-G13-16** | Stocks & Crypto Strategy Multi-Asset Regression | Regression Safety | Engine & 4 Assets | NVDA, AAPL, BTC/USD, ETH/USD | Backtest engine chạy thành công trên cả 4 tài sản và 5 chiến lược không xảy ra ngoại lệ | Hoàn tất 80 lượt đánh giá, mô phỏng 13 giao dịch trên 4 tài sản sạch lỗi | `data/status/gd13_master_acceptance_report.json` | **PASS** |

---

## 3. Các Phát hiện Kỹ thuật Trọng yếu (Key Engineering Insights)

Qua quá trình kiểm toán toàn diện tại GĐ13, ba kết luận quan trọng đã được chứng minh bằng thực nghiệm:

### 3.1. Hai Sai số Toán học trong Câu lệnh Flink SQL Gốc (PDF Baseline)
1. **Sai số Crossover**: Biểu thức Flink SQL sử dụng $SMA20_t$ hiện tại cho cả $Close_t$ và $Close_{t-1}$, dẫn đến **79 nến bị lệch tín hiệu (2.01%)** trên chuỗi dữ liệu NVDA. Khi SMA giảm dốc, tín hiệu giao cắt ảo (phantom crossover) bị kích hoạt dù giá không thực sự cắt qua đường trung bình động.
2. **Sai số Lấy Giá Quá khứ (Partition by News Time)**: Mệnh đề `LAG(close, 1) OVER (PARTITION BY symbol ORDER BY news_time)` làm cho hàm `LAG` lấy giá của **tin tức liền trước** (có thể cách hàng giờ hoặc hàng ngày) thay vì lấy giá của **nến 1 phút liền trước**! Điều này vi phạm nguyên tắc cơ bản của phân tích kỹ thuật.

### 3.2. Bản chất Hiện tượng "0 Tín hiệu Tự nhiên" trong GĐ12
- Hệ thống Flink và Kafka không bị lỗi.
- Hiện tượng 0 tín hiệu trong lúc stream trực tiếp bắt nguồn từ sự không tương thích giữa:
  - **Dòng nến định kỳ 1 phút liên tục (Periodic Stream)**.
  - **Dòng tin tức xuất hiện ngẫu nhiên, thưa thớt (Sparse Point Events)** với khoảng cách trung vị lên tới **15 phút**.
  - **Cửa sổ Temporal Join quá hẹp (1 đến 2 phút)**.
- Khi kiểm thử trên toàn bộ dữ liệu lịch sử kết hợp (5,975 nến), hệ thống ghi nhận **141 lần khớp cửa sổ** và sinh ra **7 tín hiệu BUY, 6 tín hiệu SELL** hợp lệ.

### 3.3. Hiệu quả Bảo toàn Vốn (Capital Preservation) & Ma sát Phí
- Trong thị trường giảm mạnh (NVDA giảm $-6.15\%$, ETH giảm $-1.29\%$, BTC giảm $-0.43\%$), các thuật toán kết hợp Sentiment đều giữ phần lớn tài sản ở tiền mặt, mang lại **Alpha dương từ $+0.34\%$ đến $+6.01\%$** so với việc nắm giữ thụ động (Buy & Hold).
- Tuy nhiên, mức phí giao dịch Crypto ($25\text{ bps}$ mỗi chiều $\rightarrow 0.5\%$ trọn vòng) tạo ra áp lực ma sát rất lớn đối với chiến lược nến 1 phút nếu tần suất giao dịch quá dày.

---

## 4. Khuyến nghị Kỹ thuật: Quyết định Đối với Chiến lược Baseline

Dựa trên các bằng chứng thực nghiệm và kiểm toán số học:

| Câu hỏi Kỹ thuật | Khuyến nghị của Kỹ sư Hệ thống |
|---|---|
| **Có nên giữ Chiến lược Baseline PDF cho Live Trading không?** | **TUYỆT ĐỐI KHÔNG**. Chiến lược gốc chứa lỗi logic crossover, lỗi lag tin tức, tần suất tín hiệu quá hiếm và không có cơ chế Take-Profit / Stop-Loss độc lập. |
| **Có nên giữ Chiến lược Baseline trong mã nguồn hiện tại không?** | **NÊN GIỮ Ở TRẠNG THÁI DRY_RUN**. Giữ nguyên `ddl_production.sql` và `ddl_crypto.sql` để bảo toàn tính tương thích với đặc tả PDF gốc và các bài test nghiệm thu hồi quy. |
| **Đề xuất Kiến trúc cho Giai đoạn Kế tiếp (GĐ14+)** | 1. **Chuyển sang Stateful Decaying Sentiment (Strategy 5)**: Lưu trữ điểm tin tức trong state Flink và suy giảm theo thời gian (half-life = 60m), tách rời ràng buộc join 1 phút cứng.<br/>2. **Khắc phục triệt để logic Crossover**: Sử dụng $SMA20_{t-1}$ cho giá đóng cửa trước đó.<br/>3. **Bổ sung Quản trị Rủi ro Tự động**: Bổ sung ngưỡng Chốt lời (+2.0%), Cắt lỗ (-1.0%) và Time-Stop (60 phút) thay vì chờ đợi tin tức tiêu cực đối ứng. |

---

## 5. Kết luận Nghiệm thu GĐ13

Giai đoạn **GĐ13 — Strategy Accuracy, Temporal Correctness & Backtesting** chính thức **HOÀN THÀNH TOÀN DIỆN VÀ ĐẠT 100% CÁC TIÊU CHÍ NGHIỆM THU (16/16 PASS)**.

Hệ thống được bảo toàn nguyên vẹn:
- Cụm Docker, Redpanda, Flink Streaming Jobs đang hoạt động ổn định.
- Chế độ an toàn `TRADING_MODE=DRY_RUN` được duy trì tuyệt đối.
- Không có bất kỳ lệnh Alpaca nào bị gửi ra ngoài.
- Toàn bộ artifacts, báo cáo và mã nguồn đã được lưu trữ an toàn trong kho lưu trữ của dự án.
- **Sẵn sàng chuyển giao hoặc tiến hành giai đoạn tiếp theo (GĐ14) theo yêu cầu.**

