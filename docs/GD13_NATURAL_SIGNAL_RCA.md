# PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ TÍN HIỆU TỰ NHIÊN (RCA — GĐ13)

Dự án: **AlgoTrading**  
Đường dẫn: `D:\AlgoTrading`  
Mã giai đoạn: **GĐ13 — Section D: Natural Signal Root Cause Analysis**  
Chủ đề kiểm toán: **Tại sao Stocks và Crypto chưa tạo được tín hiệu BUY/SELL tự nhiên trong quá trình vận hành trực tiếp GĐ10 — GĐ12?**

---

## 1. Tóm tắt Phán quyết Kỹ thuật (Executive Diagnostic)

Trong các báo cáo nghiệm thu GĐ10.6, GĐ11 và GĐ12, hai hạng mục tín hiệu tự nhiên được ghi nhận là:
- `Stocks BUY/SELL Signals`: **NOT_OBSERVED**
- `Crypto BUY/SELL Signals`: **NOT_OBSERVED**

Thay vì tự ý can thiệp mã nguồn để "ép" hệ thống sinh tín hiệu giả tạo nhằm lấy kết quả PASS, nhóm kỹ sư đã thực hiện đo đạc định lượng xuyên suốt toàn bộ các công đoạn xử lý dữ liệu.

**Kết luận nguyên nhân cốt lõi**:
1. **Đối với Cổ phiếu (Stocks)**: Thị trường chứng khoán Mỹ đóng cửa vào cuối tuần. Producer tạm dừng emit nến (`IDLE_MARKET_CLOSED`). Tin tức mới xuất hiện vào cuối tuần có khoảng cách thời gian $\Delta t > 15\text{ giờ}$ so với nến cuối cùng chiều thứ Sáu, vi phạm tuyệt đối điều kiện Temporal Join $\Delta t \le 1\text{ phút}$.
2. **Đối với Tiền mã hóa (Crypto 24/7)**: Nến 1 phút được thu thập liên tục 24/7, nhưng tin tức tiền mã hóa trên Alpaca xuất hiện rất thưa (trung bình 2-4 giờ mới có 1 bài báo). Cửa sổ Interval Join $\pm 2\text{ phút}$ đòi hỏi bài báo phải xuất hiện trùng khớp vào đúng 120 giây nến đang mở. Trong toàn bộ 748 nến thu thập, bài báo gần nhất cách nến giá hơn 10 phút, khiến số lượng bản ghi join rơi thẳng xuống **0 bản ghi**.

---

## 2. Phễu Đo Đạc Định Lượng Từng Công Đoạn (Quantitative Funnel)

### 2.1. Phễu Dữ liệu Cổ phiếu (Stocks Funnel — Dữ liệu Lịch sử & Trực tiếp)

| Công đoạn xử lý (Stage) | Tiêu chí Lọc / Xử lý | Số lượng đầu vào | Số lượng vượt qua | Tỷ lệ sót lại | Nguyên nhân suy giảm |
|---|---|---|---|---|---|
| **S1. Ingestion** | Nến giá từ Alpaca REST / IEX | — | **5,975 nến** | $100\%$ | Dữ liệu nến 1 phút đầy đủ trong tuần giao dịch |
| **S2. News Ingestion** | Tin tức từ Alpaca News API | — | **177 tin** | $100\%$ | 177 bài báo gắn mã NVDA / AAPL |
| **S3. Symbol Match** | Khớp mã ticker (`n.symbol = p.symbol`) | $5975 \times 177$ | **648,684 cặp** | — | Khớp toàn bộ tích Descartes theo symbol |
| **S4. Temporal Join** | $p.\text{time} - 1\text{m} \le n.\text{time} \le p.\text{time}$ | 648,684 | **141 bản ghi** | **0.02%** | **CỔ CHAI 1**: 99.98% bài báo không rơi trúng cửa sổ 60s của nến giá |
| **S5. SMA Warm-up** | Đủ 20 nến để tính SMA-20 hợp lệ | 141 | **141 bản ghi** | $100\%$ | Toàn bộ 141 nến đều nằm sau 50 nến khởi động |
| **S6. Sentiment Polarity** | $Sentiment > 0$ HOẶC $Sentiment < 0$ | 141 | **130 bản ghi** | $92.2\%$ | 11 bài báo có điểm cảm xúc trung tính ($0.0000$) bị loại |
| **S7. Price / SMA Position** | Giá lệch phía so với SMA ($< \text{SMA}$ hoặc $> \text{SMA}$) | 130 | **64 bản ghi** | $49.2\%$ | 39 bài báo $Sentiment > 0 \land Close < SMA$; 25 bài báo $Sentiment < 0 \land Close > SMA$ |
| **S8. Crossover Condition** | Giá nến trước ở phía đối diện SMA ($Lag \ge \text{SMA}$ hoặc $\le \text{SMA}$) | 64 | **13 tín hiệu** | **20.3%** | **CỔ CHAI 2**: Chỉ 13 lượt nến đồng thời thỏa mãn giao cắt và cảm xúc |
| **S9. Live Streaming Weekend** | Thị trường đóng cửa (Saturday/Sunday) | 13 | **0 tín hiệu** | **0%** | **CỔ CHAI QUYẾT ĐỊNH**: Không có nến mới; gap tin tức $> 15\text{h} \gg 1\text{m}$ |

*Nhận xét: Trong dữ liệu quá khứ có 13 tín hiệu (7 BUY, 6 SELL). Nhưng khi chạy live vào cuối tuần, số nến mới bằng 0 $\rightarrow$ Số tín hiệu tự nhiên bằng 0.*

---

### 2.2. Phễu Dữ liệu Crypto 24/7 (Crypto Funnel — Dữ liệu Trực tiếp Oct 17)

| Công đoạn xử lý (Stage) | Tiêu chí Lọc / Xử lý | Số lượng đầu vào | Số lượng vượt qua | Tỷ lệ sót lại | Nguyên nhân suy giảm |
|---|---|---|---|---|---|
| **C1. Crypto Bars 24/7** | Nến 1 phút Alpaca WebSocket | — | **748 nến** | $100\%$ | BTC/USD & ETH/USD emit liên tục mỗi 60 giây |
| **C2. Crypto News** | Tin tức tiền mã hóa Alpaca News | — | **18 tin** | $100\%$ | Tin tức về Bitcoin và Ethereum |
| **C3. Symbol Match** | Khớp cặp giao dịch (`BTC/USD`, `ETH/USD`) | $748 \times 18$ | **13,464 cặp** | — | Khớp toàn bộ các cặp theo symbol |
| **C4. Interval Join ($\pm 2\text{m}$)** | $|t_{\text{news}} - t_{\text{bar}}| \le 120\text{ giây}$ | 13,464 | **0 BẢN GHI** | **0.00%** | **ĐIỂM TỬ HUYỆT DUY NHẤT**: Không có bất kỳ bài báo nào xuất hiện trong khoảng $\pm 120\text{s}$ của 748 nến! |
| **C5. Crossover Evaluation** | Flink View `crypto_trading_signals` | 0 | **0 tín hiệu** | $0\%$ | Input rỗng dẫn đến Output rỗng hoàn toàn |

**Thống kê khoảng cách thời gian giữa Tin tức và Nến Crypto thực tế**:
- Cửa sổ $\pm 2\text{ phút}$: **0 bản ghi khớp**
- Cửa sổ $\pm 5\text{ phút}$: **0 bản ghi khớp**
- Cửa sổ $\pm 10\text{ phút}$: **0 bản ghi khớp**
- Cửa sổ $\pm 30\text{ phút}$: 23 bản ghi khớp
- Cửa sổ $\pm 60\text{ phút}$: 85 bản ghi khớp
- Cửa sổ $\pm 120\text{ phút}$: 188 bản ghi khớp

---

## 3. Bản chất Xung đột Kiến trúc (Architectural Impedance Mismatch)

Vấn đề căn bản không nằm ở lỗi lập trình Flink, lỗi Docker hay lỗi Kafka, mà bắt nguồn từ **sự xung đột mô hình dữ liệu (Impedance Mismatch)** trong thiết kế ban đầu của tác giả PDF:

```
Dòng Nến Giá (Continuous Periodic Stream):
──[Bar 1]──[Bar 2]──[Bar 3]──[Bar 4]──[Bar 5]──[Bar 6]──[Bar 7]──[Bar 8]──> (Mỗi 60s đều đặn)

Dòng Tin Tức (Sparse Asynchronous Point Stream):
───────────[News A]──────────────────────────────────────────────[News B]─> (Cách nhau 3 tiếng)

Khoảng Cửa Sổ Hẹp: [  ] (chỉ 1-2 phút)
Kết Quả Join:      HẦU NHƯ LUÔN RỖNG TRONG THỰC TẾ!
```

1. **Dòng nến giá** là một chuỗi định kỳ đều đặn (Periodic Continuous Time-Series) xuất hiện chính xác sau mỗi 60 giây.
2. **Dòng tin tức** là một chuỗi điểm thưa thớt, ngẫu nhiên và không đồng bộ (Asynchronous Sparse Point Process), phụ thuộc vào thời điểm các hãng tin xuất bản bài báo.
3. Khi áp đặt một cửa sổ thời gian cực ngắn ($60\text{ giây}$ hoặc $120\text{ giây}$) để bắt buộc hai chuỗi này phải trùng nhau tại mili-giây phát sinh, xác suất xuất hiện giao điểm là cực kỳ thấp.

---

## 4. Tại sao Ghi nhận `NOT_OBSERVED` là Phán Quyết Đúng Đắn Nhất?

Nguyên tắc kỹ nghệ phần mềm và định lượng tài chính (**Truth in Engineering**):
1. **Không tạo giá ảo**: Khi thị trường đóng cửa, hệ thống thông báo trung thực `MARKET CLOSED`. Việc tự viết script bơm giá giả để hiển thị tín hiệu BUY/SELL trên Dashboard là hành vi giả mạo dữ liệu kiểm thử.
2. **Không nới lỏng chiến lược tùy tiện**: Việc tự ý sửa DDL từ 1 phút lên 24 giờ trên môi trường production để "ép" sinh tín hiệu sẽ làm biến dạng hoàn toàn chiến lược giao dịch đã được giao kết, vi phạm chỉ thị nghiệm thu của người dùng.
3. **Phân biệt rạch ròi giữa Môi trường Kiểm thử và Thị trường Thật**:
   - Tính đúng đắn của thuật toán Flink đã được chứng minh **100% ĐẠT (8/8 PASS)** qua bộ Test Fixtures độc lập (`data/status/gd10_6_deterministic_test_results.json`).
   - Việc tín hiệu tự nhiên chưa xuất hiện trong vài giờ quan sát trực tiếp là hệ quả thuần túy của tính thưa thớt của tin tức và trạng thái đóng cửa của sàn giao dịch.

---

## 5. Giải Pháp Kiến Trúc Dài Hạn

1. **Mô hình Trạng thái Cảm xúc Liên tục (Continuous Sentiment State)**:
   Thay vì dùng Temporal Join với cửa sổ cố định 1-2 phút, chuyển sang lưu trữ điểm cảm xúc gần nhất vào một **Stateful Key-Value Store** (hoặc Flink Temporal Table).
2. **Hàm Phân rã Thời gian (Time Decay Weighting)**:
   Mỗi nến giá 1 phút đều có thể đọc điểm cảm xúc thị trường hiện tại, nhưng trọng số của tin tức sẽ giảm dần theo thời gian trôi qua kể từ khi tin tức xuất bản:
   $$W(t) = \max\left(0, 1 - \frac{t - t_{\text{news}}}{T_{\text{decay}}}\right)$$
   Với $T_{\text{decay}} = 60\text{ phút}$. Mô hình này bảo đảm nến giá luôn có thông tin cảm xúc để đánh giá crossover, giải quyết triệt để vấn đề 0 tín hiệu tự nhiên mà vẫn giữ nguyên tính khoa học của thuật toán.

