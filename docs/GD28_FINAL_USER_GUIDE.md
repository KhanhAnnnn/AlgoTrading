# HƯỚNG DẪN SỬ DỤNG HỆ THỐNG ALGOTRADING V1.0 (USER GUIDE)

**Dự án:** `D:\AlgoTrading`  
**Phiên bản phát hành:** `v1.0.0`  
**Giai đoạn:** GĐ28 — V1.0 Final Acceptance & Project Closure  
**Đối tượng:** Người dùng cuối (Trader / Nhà phân tích / Quản trị viên)

---

## 1. Giới thiệu Nền tảng AlgoTrading

**AlgoTrading Platform v1.0.0** là hệ thống bảng điều khiển thời gian thực kết hợp phân tích kỹ thuật và mô phỏng giao dịch dành cho hai lớp tài sản: **Cổ phiếu Mỹ (Stocks)** và **Tiền mã hóa (Crypto)**.

Hệ thống cung cấp:
1. **Market Intelligence:** Biểu đồ nến tương tác thời gian thực với chỉ báo SMA-20 và SMA-50.
2. **Strategy Analytics & News Sentiment:** Cảnh báo tín hiệu giao dịch và điểm số tâm lý tin tức từ thị trường.
3. **Simulated Trading Workbench:** Bàn giao dịch giả lập an toàn với vốn ảo \$100,000.
4. **Alpaca Paper Read-Only Sync:** Giám sát danh mục tài khoản Alpaca Paper thực tế ở chế độ chỉ đọc.

---

## 2. Cách thức Truy cập Giao diện Web

Sau khi hệ thống được khởi động theo Runbook, mở trình duyệt web hiện đại (Google Chrome, Microsoft Edge, Brave) và truy cập:

```
http://localhost:3000
```

> [!TIP]
> Máy chủ phục vụ tĩnh sản xuất (cổng 3000) hỗ trợ cơ chế SPA Fallback, cho phép người dùng thoải mái refresh (F5) hoặc chia sẻ đường dẫn trực tiếp (ví dụ `/workbench`) mà không bị lỗi trang.

---

## 3. Hướng dẫn Sử dụng Biểu đồ Kỹ thuật (Market Overview)

1. **Chọn Tài sản Theo dõi:**
   - Tại thanh công cụ trên cùng, chọn mã cổ phiếu (`NVDA`, `AAPL`, `MSFT`) hoặc mã tiền mã hóa (`BTC/USD`, `ETH/USD`, `SOL/USD`).
2. **Chọn Khung thời gian (Timeframe):**
   - Hỗ trợ các khung: `1m` (1 phút), `5m`, `15m`, và `1h`.
3. **Đọc Chỉ báo Trung bình Động:**
   - **Đường SMA-20 (Màu Vàng):** Xu hướng giá ngắn hạn (20 nến gần nhất).
   - **Đường SMA-50 (Màu Xanh lam):** Xu hướng giá trung hạn (50 nến gần nhất).
   - Tín hiệu giao cắt vàng (Golden Cross) khi SMA-20 cắt lên trên SMA-50, báo hiệu đà tăng trưởng.

---

## 4. Hướng dẫn Sử dụng Bàn Giao dịch Mô phỏng (Mock Workbench)

Bàn giao dịch mô phỏng cho phép thử nghiệm các chiến lược vào lệnh mà không có bất kỳ rủi ro tài chính nào:

1. **Chuyển sang Chế độ Mock Broker:**
   - Tại Trading Workbench Panel, bấm chọn tab **`MOCK BROKER`**.
   - Kiểm tra nhãn trạng thái hiển thị: `[SIMULATED MOCK BROKER]`.
2. **Kiểm tra Số dư Vốn Ảo:**
   - Tài khoản khởi điểm được cấp: **\$100,000.00 Cash**.
3. **Đặt Lệnh Mô phỏng:**
   - Nhập mã chứng khoán (ví dụ: `AAPL` hoặc `BTC/USD`).
   - Nhập khối lượng (Quantity, ví dụ `5.0`).
   - Chọn loại lệnh: **Market** (Lệnh thị trường khớp tức thì) hoặc **Limit** (Lệnh giới hạn giá).
   - Bấm **"Submit Simulated Order"**.
4. **Theo dõi Trạng thái Lệnh:**
   - Tab **Open Orders:** Hiển thị các lệnh đang chờ khớp.
   - Tab **Order History:** Hiển thị lịch sử các lệnh đã khớp (`FILLED`) hoặc đã hủy (`CANCELED`).
   - Tab **Positions:** Hiển thị số lượng cổ phiếu đang nắm giữ, giá vốn bình quân và lãi/lỗ tạm tính (Unrealized P&L).
5. **Khôi phục Tài khoản Về Trạng thái Ban đầu:**
   - Nếu muốn thiết lập lại số dư về \$100,000 và xóa sạch các vị thế mô phỏng, bấm nút **"Reset Simulated Account"** và xác nhận.

---

## 5. Hướng dẫn Xem Tài khoản Alpaca Paper (Read-Only)

1. **Chuyển sang Chế độ Alpaca Paper:**
   - Bấm chọn tab **`ALPACA PAPER`**.
   - Nhãn trạng thái hiển thị: `[ALPACA PAPER (READ-ONLY SYNC)]`.
2. **Xem Số dư Thật:**
   - Giao diện đồng bộ trực tiếp từ Alpaca Paper API qua số tài khoản `PA31BG5IX`.
   - Hiển thị chính xác: Portfolio Value, Cash, Equity, và Buying Power.
3. **Ranh giới Bảo vệ An toàn:**
   - Nút đặt lệnh bị vô hiệu hóa kèm cảnh báo `"EXECUTION GATE CLOSED (DRY-RUN)"`.
   - Đây là tính năng bảo vệ an toàn chủ động, ngăn chặn việc vô tình đặt lệnh lên broker thật khi chưa được cấp phép.

---

## 6. Xử lý Sự cố Thường gặp (Troubleshooting)

| Hiện tượng | Nguyên nhân Khả dĩ | Cách Khắc phục |
| :--- | :--- | :--- |
| Không mở được trang web `http://localhost:3000` | Máy chủ web sản xuất chưa chạy | Chạy lệnh `powershell -File scripts/start_prod_web.ps1` |
| Biểu đồ không tải dữ liệu nến | Backend API (cổng 8005) chưa khởi động | Kiểm tra trạng thái backend tại `http://127.0.0.1:8005/api/health` |
| Dòng chữ "MARKET CLOSED" trên biểu đồ Stocks | Ngoài giờ giao dịch của sàn chứng khoán Mỹ | Đây là hiện tượng bình thường; chuyển sang tab Crypto để xem dữ liệu 24/7 |
| Báo lỗi "PaperExecutionGate is LOCKED" khi gửi lệnh Alpaca | Cổng thực thi bị khóa theo thiết kế bảo mật | Chuyển sang tab `MOCK BROKER` để thực hiện giao dịch thử nghiệm |

