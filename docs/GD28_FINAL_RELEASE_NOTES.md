# THÔNG BÁO PHÁT HÀNH CHÍNH THỨC V1.0 (RELEASE NOTES)

**Sản phẩm:** Nền tảng Giao dịch Thuật toán AlgoTrading  
**Phiên bản:** `v1.0.0` (Final Production Release)  
**Ngày phát hành:** `2026-10-31`  
**Git Revision:** `e4bc3d8b11266835b1b478124e4c97b9ffea4b79`  
**Trạng thái Phạm vi:** **V1.0 SCOPE CLOSED & FROZEN**

---

## 1. Tóm tắt Phiên bản Phát hành V1.0

Bản phát hành chính thức **AlgoTrading v1.0.0** đánh dấu sự hoàn thiện toàn diện của nền tảng giám sát thị trường, phân tích kỹ thuật thời gian thực và mô phỏng giao dịch thuật toán cho hai lớp tài sản Cổ phiếu Mỹ (Stocks) và Tiền mã hóa (Crypto).

Hệ thống được thiết kế theo kiến trúc hướng sự kiện phân tán (Event-Driven Architecture), tích hợp Redpanda message bus, Apache Flink stateful stream processing, FastAPI Backend, và giao diện người dùng React 19 tối ưu hóa phục vụ sản xuất.

---

## 2. Các Tính năng Cốt lõi Trong Bản Phát hành V1.0

### 2.1. Phục vụ Web Sản xuất Độc lập (Production Web Serving)
- Vận hành máy chủ web sản xuất native Node.js trên cổng **`3000`** phục vụ bundle tĩnh tối ưu tại `trading-dashboard/frontend/dist/`.
- Hỗ trợ toàn diện **SPA Routing Fallback**, loại bỏ lỗi 404 khi người dùng refresh hoặc truy cập deep link.
- Tích hợp endpoint giám sát độc lập `http://localhost:3000/healthz` và các headers bảo mật HTTP nghiêm ngặt.

### 2.2. Trí tuệ Thị trường Thời gian thực (Market Intelligence)
- Biểu đồ nến tương tác tốc độ cao hỗ trợ đa khung thời gian (`1m`, `5m`, `15m`, `1h`) trên các mã cổ phiếu công nghệ hàng đầu (`NVDA`, `AAPL`, `MSFT`) và tiền mã hóa (`BTC/USD`, `ETH/USD`, `SOL/USD`).
- Tự động tính toán và hiển thị hai đường trung bình động động **SMA-20** và **SMA-50**.
- Tích hợp luồng phân tích tâm lý tin tức (News Sentiment) và phát hiện tín hiệu giao cắt kỹ thuật.

### 2.3. Bàn Giao dịch Giả lập An toàn (Mock Trading Sandbox)
- Cung cấp môi trường thực nghiệm không rủi ro tài chính với tài khoản vốn ảo **\$100,000.00 Cash**.
- Hỗ trợ đầy đủ vòng đời lệnh: Đặt lệnh Market/Limit, khớp lệnh theo giá thị trường sống, quản lý vị thế, và tính toán lãi/lỗ danh mục.
- Khả năng khôi phục (Reset) tài khoản về trạng thái ban đầu bất cứ lúc nào.

### 2.4. Đối soát Tài khoản Alpaca Paper (Read-Only Synchronization)
- Đồng bộ chỉ đọc thông số tài khoản thật từ Alpaca Paper API qua số tài khoản `PA31BG5IX` (Equity \$99,987.32, Cash \$99,773.38).
- Giám sát vị thế thực tế, danh sách lệnh mở và lịch sử giao dịch với rào cản an toàn `PaperExecutionGate` đóng fail-closed.

### 2.5. Hạ tầng Streaming & Xử lý Dữ liệu Sống
- Cụm Redpanda 2 brokers (`localhost:9092, 9093`) duy trì trạng thái ổn định với **Consumer Lag $= 0$**.
- Cụm Apache Flink thực thi 2 jobs streaming với **hơn 600 checkpoints thành công và 0 checkpoint thất bại**.

### 2.6. Sao lưu Mật mã học & Khôi phục Thảm họa (Disaster Recovery)
- Công cụ sao lưu toàn phần [scripts/disaster_recovery_engine.py](file:///d:/AlgoTrading/scripts/disaster_recovery_engine.py) đóng gói 69 tệp với mã băm SHA-256.
- Thực nghiệm khôi phục trong môi trường cô lập đạt **Zero Data Diff**, **RTO $= 0.0669\text{s}$**, và **RPO delta $= 2,639.78\text{s}$**.

---

## 3. Thành tựu Kiểm thử Tích lũy (Cumulative Testing Milestone)

$$\text{Tổng số Test Cases Tích lũy} = 234\text{ tests}$$
$$\text{Tỷ lệ Vượt qua Tuyệt đối} = \frac{234}{234} = 100.0\%$$
$$\text{Phạm vi Kiểm thử: Toàn bộ 9 giai đoạn (GĐ20 đến GĐ28)}$$

---

## 4. Tuyên bố Đóng Phạm vi Tính năng (Scope Freeze Declaration)

Bản phát hành V1.0 chính thức được niêm phong phạm vi tính năng. Toàn bộ các yêu cầu nâng cấp tính năng mới (ví dụ: mở cổng thực thi Alpaca Paper, tích hợp broker mới, hỗ trợ thêm các chỉ báo RSI/MACD) sẽ được chuyển sang lộ trình phát triển của phiên bản **V1.1** hoặc **V2.0**.

