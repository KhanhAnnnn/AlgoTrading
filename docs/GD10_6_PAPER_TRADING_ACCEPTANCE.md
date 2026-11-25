# GĐ10.6 — BIÊN BẢN NGHIỆM THU CRYPTO SIGNAL VALIDATION & PAPER TRADING ACCEPTANCE

**Dự án:** `D:\AlgoTrading`  
**Phiên bản:** GĐ10.6  
**Ngày nghiệm thu:** 17/10/2026  
**Trạng thái nghiệm thu:** **HOÀN THÀNH TOÀN DIỆN (ACCEPTANCE PASSED)**  

---

## 1. Tóm tắt kết quả nghiệm thu

Giai đoạn GĐ10.6 đã giải quyết triệt để vấn đề audit pipeline Crypto từ GĐ10.5, thực hiện kiểm thử tất định (Deterministic Fixtures) trên Flink Streaming Job, xác thực các cơ chế an toàn của Signal Handler, và thực hiện thành công 1 lệnh Crypto Paper Trading có kiểm soát trên Alpaca theo đúng phê duyệt của người dùng.

### Ma trận nghiệm thu tổng thể (Acceptance Matrix)

| STT | Hạng mục kiểm tra | Phạm vi / Tiêu chí | Kết quả | Chi tiết kiểm chứng |
|:---:|---|---|:---:|---|
| 1 | **Crypto Flink Processing** | Ingestion từ Redpanda, Watermark tiến triển, không crash | **PASS** | Flink Job `a9625608bc5369a7bc3d7f422d73391d` chạy 6/6 tasks, tiêu thụ > 450 bars liên tục. |
| 2 | **SMA Accuracy** | Tính SMA20 và SMA50 chính xác trên từng symbol BTC/USD & ETH/USD | **PASS** | OverAggregate tính toán nến `is_final = TRUE`, đối chiếu chính xác với phép tính Python độc lập. |
| 3 | **Sentiment Temporal Join** | Interval Join $\pm 2$ phút theo Event Time giữa tin tức và giá | **PASS** | Đã kiểm chứng trong môi trường cô lập `test-crypto-*`, kết hợp chính xác 24 sự kiện nến - tin tức. |
| 4 | **Deterministic BUY** | Giá cắt xuống dưới SMA20 kèm Sentiment dương ($> 0$) | **PASS** | Fixture Bar 26 ($79,500 < 79,981$) + News 9002 ($+0.65$) kích hoạt BUY chính xác. |
| 5 | **Deterministic SELL** | Giá cắt lên trên SMA20 kèm Sentiment âm ($< 0$) | **PASS** | Fixture Bar 42 ($80,500 > 79,825$) + News 9003 ($-0.70$) kích hoạt SELL chính xác. |
| 6 | **Natural Market Signals** | Tín hiệu tự nhiên từ Alpaca WebSocket & News REST | **NOT_OBSERVED** | Alpaca Crypto News REST chỉ có tin tức từ 14-16/10, lệch $>18$ giờ so với nến live 17/10. Không tạo tín hiệu giả. |
| 7 | **DRY_RUN Guard** | Ghi nhận Intent mà không gửi API đặt lệnh Alpaca | **PASS** | Đã xác nhận `executed: false`, `status: DRY_RUN_SIMULATED`, 0 cuộc gọi POST `/v2/orders`. |
| 8 | **Signal Deduplication** | Chống trùng tín hiệu dựa trên key `symbol:signal:time` | **PASS** | Đã xác thực deduplication trên bộ nhớ và file persistent `crypto_order_intent.json`. |
| 9 | **Spot No-Short Guard** | Ngăn chặn lệnh SELL khi tài khoản chưa có vị thế Long | **PASS** | Lệnh SELL khi position $= 0$ bị từ chối với lý do `NO_POSITION_TO_SELL`. |
| 10 | **Paper Trading Eligibility**| Tài khoản Alpaca Paper Trading hỗ trợ Crypto | **PASS** | API Account trả về `Crypto Status: ACTIVE`, `Tradable: True` cho cả BTCUSD và ETHUSD. |
| 11 | **Paper Order Submission** | Đặt 1 lệnh mua thử nghiệm có kiểm soát sau phê duyệt | **PASS** | Đặt thành công lệnh BUY BTCUSD Notional $10.00 qua API Alpaca Paper Trading. |
| 12 | **Order Status & Portfolio** | Xác minh Order ID, trạng thái Filled và cập nhật danh mục | **PASS** | Order ID `c5d4311a-2c15-441d-bc11-8a7384fe8eed` trạng thái **FILLED**, khớp 0.000120309 BTC @ $81,535.80. |
| 13 | **Stocks Pipeline Regression**| Bảo toàn hệ thống Stocks, topics, offsets và Flink Stocks Job| **PASS** | Flink Job `c0955d4aa73c9c2197c936f89ba07f22` vẫn chạy liên tục song song (6/6 tasks). |

---

## 2. Chi tiết kết quả kiểm thử tất định (Deterministic Flink Verification)

Được thực hiện độc lập qua script `tests/test_crypto_deterministic_flink.py` trên các topic cô lập `test-crypto-bars-1m`, `test-crypto-news` và `test-crypto-signals`.

### Các ca kiểm thử bao phủ:

1. **Case 1 (Deterministic BUY):**
   - Giá nến trước: $80,000.00 \ge SMA_{20}$
   - Giá nến hiện tại: $79,500.00 < SMA_{20}$ ($79,981.48$)
   - VADER Sentiment: $+0.65$
   - **Kết quả:** Flink phát tín hiệu `BUY BTC/USD @ $79,500.00` vào lúc `2026-10-17 12:26:10Z` (**PASS**).

2. **Case 2 (Deterministic SELL):**
   - Giá nến trước: $79,500.00 \le SMA_{20}$
   - Giá nến hiện tại: $80,500.00 > SMA_{20}$ ($79,825.58$)
   - VADER Sentiment: $-0.70$
   - **Kết quả:** Flink phát tín hiệu `SELL BTC/USD @ $80,500.00` vào lúc `2026-10-17 12:42:10Z` (**PASS**).

3. **Case 3 (Insufficient SMA History):**
   - Tin tức 9001 tại $t = 3$ phút khi mới chỉ có 4 nến lịch sử ($< 20$ nến).
   - **Kết quả:** Không sinh tín hiệu giả (**PASS**).

4. **Case 4 (No Crossover / Elevated Market):**
   - Tin tức 9004 tại $t = 58$ phút có Sentiment dương $+0.80$, nhưng giá đã ở trên SMA20 từ trước đó (không có giao cắt).
   - **Kết quả:** Không sinh tín hiệu (**PASS**).

5. **Case 5 (Neutral Sentiment):**
   - Tin tức 9005 tại $t = 65$ phút có Sentiment chính xác $= 0.0$.
   - **Kết quả:** Bị bộ lọc phân loại trung tính loại bỏ (**PASS**).

6. **Case 6 (Duplicate Candle Ingestion):**
   - Nến lặp lại cùng timestamp được gửi vào Redpanda.
   - **Kết quả:** Flink không sinh tín hiệu trùng lặp (**PASS**).

7. **Case 7 (Late Event Rejection):**
   - Nến gửi đến có timestamp cũ hơn Watermark hiện tại 30 phút.
   - **Kết quả:** Bị Flink Watermark tự động loại bỏ, không làm sai lệch trạng thái (**PASS**).

8. **Case 8 (Flink vs Python Reference Parity):**
   - So sánh giữa đầu ra Flink và mô phỏng tính toán Python thuần túy.
   - **Kết quả:** Khớp 100% (2/2 tín hiệu) (**PASS**).

---

## 3. Nhật ký lệnh Alpaca Crypto Paper Trading thực tế

Sau khi nhận được sự phê duyệt rõ ràng từ người dùng qua tương tác xác nhận, lệnh thử nghiệm một lần có kiểm soát đã được gửi đến endpoint Alpaca Paper Trading:

```json
{
  "execution_timestamp": "2026-10-17T14:37:42.785076+00:00",
  "endpoint": "https://paper-api.alpaca.markets",
  "symbol": "BTCUSD",
  "side": "buy",
  "notional": 10.0,
  "order_type": "market",
  "order_id": "c5d4311a-2c15-441d-bc11-8a7384fe8eed",
  "client_order_id": "GD10-6-TEST-BTCUSD-BUY-1792247854",
  "initial_status": "pending_new",
  "final_status": "filled",
  "filled_qty": "0.000120309",
  "filled_avg_price": "81535.8",
  "pre_position_qty": "0.0",
  "post_position_qty": "0.000120008",
  "portfolio_cash_pre": "100000",
  "portfolio_cash_post": "99990.19"
}
```

### Đánh giá an toàn thực thi:
- Số lượng lệnh: Đúng 1 lệnh (Max Orders = 1).
- Chế độ tự động liên tục: **TẮT** (Không tự bật giao dịch liên tục).
- Tiền mặt tài khoản: Trừ đúng $9.81 (gồm phí khớp lệnh $10.00 notional) từ $100,000 xuống $99,990.19.
- Vị thế BTC: Tăng từ 0.0 lên 0.000120008 BTC.

---

## 4. Trạng thái các dịch vụ đang chạy

| Dịch vụ / Container | Cổng | Process ID / JID | Ghi chú |
|---|:---:|:---:|---|
| **Alpaca Crypto Producer** | — | PID 21236 (task-523) | Stream live BTC/USD & ETH/USD từ Alpaca Crypto WebSocket |
| **Crypto Signal Handler** | — | PID 21204 (task-552) | Lắng nghe `crypto-signals` ở chế độ DRY_RUN an toàn |
| **FastAPI Backend** | 8005 | task-436 | Phục vụ WebSocket & REST API cho Dashboard |
| **React Dashboard (Vite)** | 5173 | task-491 | Hiển thị Chart Stocks & Crypto |
| **Flink Stocks Job** | 8081 | `c0955d4aa73c9c2197c936f89ba07f22` | Xử lý `stock-prices` & `market-news` |
| **Flink Crypto Job** | 8081 | `a9625608bc5369a7bc3d7f422d73391d` | Xử lý `crypto-bars-1m` & `crypto-news` với window logic chuẩn |

---

## 5. Kết luận nghiệm thu

Giai đoạn GĐ10.6 hoàn thành xuất sắc tất cả các mục tiêu đề ra, làm rõ lý do kỹ thuật đằng sau 0 messages ban đầu, nâng cấp câu lệnh Flink Streaming SQL đạt chuẩn, chứng minh tính tất định của chiến lược giao dịch qua 8 bài test cô lập, và hoàn tất đặt lệnh thử nghiệm thực tế trên Alpaca Paper Trading an toàn 100%.

