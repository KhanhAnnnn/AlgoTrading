# ĐẶC TẢ CHIẾN LƯỢC GIAO DỊCH & SO SÁNH ĐA TẦNG (GĐ13)

Dự án: **AlgoTrading**  
Đường dẫn: `D:\AlgoTrading`  
Tài liệu gốc tham chiếu: `Real-Time Algorithmic Trading_2025May27.pdf` (21 trang) của tác giả Shijun Ju (Castor / CodeWithYu)  
Mã DDL kiểm toán: `ddl.sql`, `ddl_production.sql`, `ddl_crypto.sql`  
Báo cáo kiểm thử số học: `data/status/gd13_numerical_parity_report.json`

---

## 1. Tổng quan Kiến trúc Đặc tả Chiến lược

Chiến lược giao dịch gốc từ tài liệu PDF được thiết kế nhằm kết hợp hai nguồn dữ liệu thời gian thực:
1. **Dòng giá thị trường (Stock Prices Stream)**: Nến 1 phút với các mức giá Open, High, Low, Close, Volume.
2. **Dòng tin tức tài chính (Market News Stream)**: Tin tức thị trường được tính điểm cảm xúc phân cực (Sentiment Score) thông qua bộ từ điển NLTK VADER.

Mục tiêu chiến lược là phát sinh tín hiệu giao dịch tự động **BUY** hoặc **SELL** khi có sự đồng thuận giữa xu hướng giá kỹ thuật (Price Crossover qua đường trung bình động SMA-20) và tâm lý thị trường (Sentiment $> 0$ hoặc $< 0$).

---

## 2. Bảng Đối chiếu Đặc tả Chiến lược Đa Tầng

| Thành phần Logic | 1. PDF Gốc (`May 27, 2025`) | 2. Stocks Hiện tại (`ddl_production.sql`) | 3. Crypto Hiện tại (`ddl_crypto.sql`) | 4. Đánh giá Khác biệt & Tác động Kỹ thuật |
|---|---|---|---|---|
| **Chỉ báo SMA-20** | `AVG(close) OVER (PARTITION BY symbol ORDER BY event_time ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)` | Giữ nguyên như PDF | Bổ sung điều kiện `WHERE is_final = TRUE` | Crypto lọc nến đã đóng (`is_final`), tránh tính toán trên nến đang hình thành dở dang |
| **Chỉ báo SMA-50** | `ROWS BETWEEN 49 PRECEDING AND CURRENT ROW` | Giữ nguyên như PDF | Bổ sung `WHERE is_final = TRUE` | Được tính toán nhưng **không được sử dụng** trong mệnh đề CASE phát tín hiệu của cả PDF và Stocks |
| **Liên kết SMA (Join)** | `s20.event_time = s50.event_time` | Giữ nguyên như PDF | `s20.event_time = s50.event_time` | Yêu cầu cả 2 view cùng event_time chính xác |
| **Temporal Join** | `n.event_time BETWEEN p.event_time - INTERVAL '1' MINUTE AND p.event_time` | Giữ nguyên như PDF | `n.event_time BETWEEN p.event_time - INTERVAL '2' MINUTE AND p.event_time + INTERVAL '2' MINUTE` | Crypto mở rộng cửa sổ join sang hai phía $\pm 2\text{ phút}$ để tăng khả năng khớp cặp tin tức |
| **Lấy Giá Trước đó (Lag)** | `LAG(close, 1) OVER (PARTITION BY symbol ORDER BY news_time)` | `lag(close, 1) OVER (PARTITION BY symbol ORDER BY news_time)` | `FIRST_VALUE(close) OVER (PARTITION BY symbol ORDER BY news_time ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)` | `FIRST_VALUE` với window framing tương thích 100% với Flink streaming runtime (tránh lỗi cú pháp `LAG` không hỗ trợ streaming) |
| **Điều kiện BUY** | `sentiment > 0 AND close < sma_20 AND lag_close >= sma_20` | `sentiment > 0 AND close < sma_20 AND lag_close >= sma_20` | `sentiment > 0 AND close < sma_20 AND lag_close >= sma_20` | Logic mua khi giá giảm thủng SMA-20 từ trên xuống (Dip-buying / Mean Reversion) |
| **Điều kiện SELL** | `sentiment < 0 AND close > sma_20 AND lag_close <= sma_20` | `sentiment < 0 AND close > sma_20 AND lag_close <= sma_20` | `sentiment < 0 AND close > sma_20 AND lag_close <= sma_20` | Logic bán khi giá tăng vượt SMA-20 từ dưới lên (Fade the rally / Mean Reversion) |
| **Cấu trúc Sink** | `symbol, signal_time, signal` | `symbol, signal_time, signal` | Bổ sung `price, sentiment, sma_20, sma_50` | Crypto sink lưu đầy đủ telemetry phục vụ đối chiếu và audit |

---

## 3. Phân tích Chuyên sâu Lỗi Thuật toán Crossover (Crossover Logic Flaws)

Kiểm toán kỹ thuật phát hiện **hai sai số toán học và kiến trúc nghiêm trọng** trong cách Flink SQL của tác giả PDF triển khai crossover:

### 3.1. Sai số 1: So sánh Giá Trước đó với SMA Hiện tại (Current SMA vs Lagged SMA)
Trong tài liệu PDF (trang 13) và mã nguồn Flink SQL:
```sql
CASE
    WHEN sentiment > 0 AND `close` < sma_20 
         AND LAG(`close`, 1) OVER (PARTITION BY symbol ORDER BY news_time) >= sma_20 THEN 'BUY'
    ...
```
- Giá hiện tại là $Close_t$.
- Đường trung bình động hiện tại là $SMA20_t$.
- Giá trước đó là $Close_{t-1}$.

Trong biểu thức trên, điều kiện crossover là:
$$Close_t < SMA20_t \quad \land \quad Close_{t-1} \ge SMA20_t$$

**Hệ quả sai lệch**:
Biểu thức sử dụng $SMA20_t$ cho cả hai thời điểm!  
Trong phân tích kỹ thuật chuẩn mực, giao cắt cắt xuống (downward crossover) đòi hỏi:
$$Close_{t-1} \ge SMA20_{t-1} \quad \land \quad Close_t < SMA20_t$$

Nếu tại thời điểm $t$, đường SMA20 sụt giảm đột ngột (do một mức giá cao từ 20 kỳ trước rớt khỏi cửa sổ tính toán), $SMA20_t$ sẽ tụt xuống dưới $SMA20_{t-1}$. Khi đó, có thể xảy ra trường hợp:
$$Close_{t-1} < SMA20_{t-1} \quad \text{nhưng} \quad Close_{t-1} \ge SMA20_t$$
Hệ thống sẽ phát ra **tín hiệu giao cắt ảo (Phantom Crossover)**, mặc dù tại thời điểm $t-1$, giá vốn dĩ đã nằm dưới đường SMA20!

**Bằng chứng số học từ dữ liệu thực tế (Kiểm thử `tests/test_gd13_numerical_parity.py`)**:
- Trên 3,928 nến lịch sử của NVDA:
  - Crossover theo Định nghĩa A (PDF/Flink): 171 lượt cắt xuống, 179 lượt cắt lên.
  - Crossover theo Định nghĩa B (Chuẩn toán học $SMA_{t-1}$): 177 lượt cắt xuống, 176 lượt cắt lên.
  - **Số nến xảy ra sai lệch: 79 nến (chiếm 2.01% tổng số nến)**.
  - Sai số này làm sai lệch thời điểm vào lệnh từ 1 đến 5 phút trên biểu đồ!

```
Định nghĩa A (PDF): Close[t-1] so với SMA20[t]    --> 79 nến sai lệch (2.01%)
Định nghĩa B (Chuẩn): Close[t-1] so với SMA20[t-1] --> Khớp bản chất giao cắt kỹ thuật
```

### 3.2. Sai số 2: Phân vùng LAG() theo Dòng Tin tức thay vì Dòng Nến Giá
Trong biểu thức SQL:
```sql
LAG(`close`, 1) OVER (PARTITION BY symbol ORDER BY news_time)
```
Mệnh đề `OVER` được đặt trên view `news_and_prices`.  
Bảng `news_and_prices` chỉ có bản ghi khi **có một bài báo khớp thời gian với nến giá**.

Giả sử:
- Bài báo 1 xuất hiện lúc `09:30:00`: Giá khớp $Close_{09:30} = 120.0$, $SMA20_{09:30} = 118.0$.
- Trong suốt 3 tiếng tiếp theo không có tin tức nào về mã cổ phiếu này.
- Bài báo 2 xuất hiện lúc `12:45:00`: Giá khớp $Close_{12:45} = 115.0$, $SMA20_{12:45} = 116.0$.

Khi Flink tính toán tại thời điểm `12:45:00`:
- `close` = $Close_{12:45} = 115.0$
- `LAG(close, 1) OVER (ORDER BY news_time)` **CHÍNH LÀ $Close_{09:30} = 120.0$**!
- Nó **KHÔNG PHẢI** là giá của nến 1 phút trước đó ($Close_{12:44}$)!

Biểu thức trên thực chất đang kiểm tra xem: *"Giá tại thời điểm tin tức 3 tiếng trước có lớn hơn SMA hiện tại hay không"*, chứ hoàn toàn không phải kiểm tra nến giá vừa mới cắt qua đường SMA trong phút vừa qua! Đây là một lỗ hổng kiến trúc cơ bản trong mã nguồn mẫu ban đầu của tác giả.

---

## 4. Bản chất Chiến lược: Dip-Buying (Mean Reversion) vs Trend-Following (Momentum)

Trong tài liệu PDF (trang 13), tác giả viết rõ:
> *"BUY: Positive sentiment and the price crosses below the 20-minute SMA from above, indicating a potential reversal."*  
> *"SELL: Negative sentiment and the price crosses above the 20-minute SMA from below."*

1. **Triết lý Bắt đáy Đảo chiều (Mean Reversion / Dip Buying)**:
   - Tác giả định nghĩa: Khi tin tức tích cực ($Sentiment > 0$), nhưng giá cổ phiếu vừa bị đạp xuống dưới đường trung bình 20 phút ($Close < SMA20$), đó là hiện tượng "bán tháo quá đà / rũ bỏ", tạo cơ hội mua bắt đáy đón sóng hồi phục (Buy the Dip).
   - Ngược lại, khi tin tức tiêu cực ($Sentiment < 0$), nhưng giá hồi phục vượt trên SMA20, đó là cơ hội bán khống đón sóng giảm (Fade the Rally).
2. **Triết lý Bám theo Xu hướng (Trend-Following Momentum)**:
   - Trong giao dịch định lượng truyền thống:
     - Giá vượt lên trên SMA20 + Tin tức tốt $\rightarrow$ Mua theo đà tăng (Breakout BUY).
     - Giá thủng xuống dưới SMA20 + Tin tức xấu $\rightarrow$ Bán theo đà giảm (Breakdown SELL).
3. **Đánh giá Hiệu quả Thực tế**:
   - Trong thị trường có xu hướng mạnh (Trending Market), chiến lược Dip-Buying của PDF có thể bắt trúng dao rơi nếu xu hướng giảm tiếp tục kéo dài.
   - Do đó, trong phần Backtesting (GĐ13.E & F), hệ thống giữ nguyên Chiến lược PDF làm Baseline chuẩn, đồng thời đánh giá song song biến thể Trend-Following để cung cấp cái nhìn định lượng đa chiều.

---

## 5. Kết luận & Đề xuất Kỹ thuật

1. **Về tính nguyên bản**: Giữ nguyên logic DDL hiện tại trên môi trường production để bảo toàn tính tương thích và bảo đảm quy tắc không sửa đổi cấu trúc hệ thống khi chưa có phê duyệt.
2. **Về thuật toán chuẩn**: Trong mô hình Backtesting độc lập, triển khai cả hai dạng crossover (Current SMA và Lagged SMA) để người dùng thấy rõ độ nhạy của tín hiệu.
3. **Về kiến trúc tin tức**: Đề xuất nâng cấp kiến trúc tương lai sang mô hình **Stateful Sentiment Decay (Phân rã cảm xúc có trạng thái)**: Duy trì trạng thái cảm xúc mới nhất với chu kỳ bán rã (Half-life = 60 phút), giúp kết hợp mượt mà giữa dòng tin tức không đồng bộ và dòng nến 1 phút định kỳ.

