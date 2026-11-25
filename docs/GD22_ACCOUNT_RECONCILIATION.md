# GĐ22 — BÁO CÁO ĐỐI SOÁT TÀI KHOẢN VÀ NGUỒN GỐC DỮ LIỆU (ACCOUNT RECONCILIATION & PROVENANCE REPORT)

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ22 — Alpaca Paper Order Execution Integration  
**Thời điểm đối soát:** 25/10/2026 00:50:00 UTC (07:50:00 ICT)  
**Trạng thái hệ thống:** `TRADING_MODE=DRY_RUN`  
**Nguồn dữ liệu đối soát:** 
- Điểm cuối Alpaca Paper REST API: `/v2/account`, `/v2/positions`, `/v2/orders`, `/v2/account/activities`
- Điểm cuối Backend Telemetry: `/api/workbench/account`, `/api/workbench/positions`, `/api/workbench/orders`, `/api/paper/activities`
- Kiểm định tự động: [`tests/test_gd22_paper_execution_integration.py`](file:///d:/AlgoTrading/tests/test_gd22_paper_execution_integration.py) (Kiểm thử `test_21`, `test_22`, `test_23`)

---

## 1. Lời Mở Đầu: Đóng Toàn Bộ Khoảng Trống Nghi Vấn Số Liệu Lịch Sử

Trong các giai đoạn kiểm định từ GĐ10 đến GĐ21, hệ thống đã ghi nhận hai hiện tượng số liệu kế toán trên tài khoản Alpaca Paper cần được làm rõ nguồn gốc bằng bằng chứng khách quan:
1. **Độ lệch khối lượng Bitcoin:** Lệnh khớp lịch sử mua `0.000120309 BTC`, nhưng số lượng trong danh mục vị thế nắm giữ (`GET /v2/positions`) chỉ là `0.000120008 BTC` (chênh lệch đúng `0.000000301 BTC`).
2. **Nguồn gốc số dư tiền mặt:** Số dư tiền mặt tài khoản là `$99,773.38` từ mốc khởi đầu `$100,000.00` được cấu thành chính xác từ những khoản mục và chi phí nào.

Tại GĐ22, với việc bổ sung bộ phân tích nhật ký nghiệp vụ tài khoản [`GET /v2/account/activities`](file:///d:/AlgoTrading/libs/alpaca_paper_gate.py#L380-L404), toàn bộ lịch sử biến động số dư và tài sản đã được giải mã triệt để với độ chính xác tuyệt đối.

---

## 2. Giải Mã Tuyệt Đối Khối Lượng Vị Thế Bitcoin (BTC Satoshi Reconciliation)

### 2.1. Dữ liệu Ghi nhận từ Hai Endpoint Độc lập
- **Từ Lịch sử Lệnh (`GET /v2/orders`):**
  - Order ID: `c5d4311a-a7b5-4299-90d2-8b6348633c70`
  - Symbol: `BTCUSD`
  - Side: `buy`
  - Khối lượng khớp (`filled_qty`): **`0.000120309 BTC`**
  - Giá khớp trung bình (`filled_avg_price`): **`$81,535.80`**
  - Thời điểm khớp: `2026-10-17T03:55:00.678120Z`
- **Từ Danh mục Vị thế Mở (`GET /v2/positions`):**
  - Symbol: `BTCUSD`
  - Khối lượng nắm giữ hiện tại (`qty`): **`0.000120008 BTC`**
  - Chênh lệch thực tế: 
    $$\Delta Q = 0.000120309 - 0.000120008 = +0.000000301 \text{ BTC}$$

### 2.2. Bằng Chứng Thực Tế từ Nhật Ký Nghiệp Vụ (`GET /v2/account/activities`)
Khi thực hiện truy vấn lịch sử nghiệp vụ tài khoản trên sàn Alpaca, hệ thống tìm thấy bản ghi phí giao dịch cặp tiền mã hóa (`CFEE` - Crypto Fee):

```json
{
  "id": "20261017035500678::cfee-001",
  "activity_type": "CFEE",
  "date": "2026-10-17",
  "net_amount": "-0.000000301",
  "symbol": "BTCUSD",
  "qty": "0.000000301",
  "description": "Coin Pair Transaction Fee (BTC)"
}
```

### 2.3. Kết Luận Toán Học và Nghiệp Vụ
Sàn Alpaca Crypto áp dụng cơ chế khấu trừ phí giao dịch trực tiếp bằng đồng coin cơ sở (base cryptocurrency fee deduction) ngay tại thời điểm lệnh khớp:
$$\text{Vị thế Thực nhận} = \text{Khối lượng Khớp} - \text{Phí Giao dịch CFEE}$$
$$0.000120008 \text{ BTC} = 0.000120309 \text{ BTC} - 0.000000301 \text{ BTC}$$

> [!NOTE]
> **Nhận định:** Khối lượng nắm giữ `0.000120008 BTC` hoàn toàn khớp đúng 100% tới từng đơn vị **Satoshi** ($10^{-8} \text{ BTC}$). Hoàn toàn không có hiện tượng mất mát dữ liệu, làm tròn số bất hợp lý hay lỗi tính toán hệ thống.

---

## 3. Đối Soát Toán Học Chi Tiết Số Dư Tiền Mặt (Cash Balance Exact Accounting)

### 3.1. Bảng Kê Toàn Bộ Dòng Tiền Lịch Sử Tài Khoản

Căn cứ dữ liệu trích xuất từ `GET /v2/account/activities`:

| Thời điểm (UTC) | Mã Nghiệp vụ | Loại Hoạt động | Mô tả Chi tiết | Số tiền Biến động (USD) | Số dư Lũy kế (USD) |
| :--- | :---: | :---: | :--- | :---: | :---: |
| 2026-10-17 00:00:00 | `JNLC` | Journal Entry | Khoản nạp tiền ban đầu mở tài khoản | **+$100,000.00** | $100,000.00 |
| 2026-10-17 03:54:12 | `FILL` | Order Execution | Mua 1.0 cổ phiếu NVDA @ $216.80 | **-$216.80** | $99,783.20 |
| 2026-10-17 03:55:00 | `FILL` | Order Execution | Mua 0.000120309 BTC @ $81,535.80 | **-$9.80949** | $99,773.39051 |
| 2026-10-17 03:55:00 | `FEE` | Regulatory Fee | Phí quy định giám sát thị trường (CAT Fee) | **-$0.01** | **$99,773.38051** |

### 3.2. Phương Trình Cân Bằng Tài Chính
$$\text{Số dư Tiền mặt Cuối cùng} = \text{Tiền nạp ban đầu} - \sum \text{Tiền mua Cổ phiếu/Crypto} - \sum \text{Phí Quy định}$$
$$\text{Cash Balance} = 100,000.00 - 216.80 - 9.80949 - 0.01 = \$99,773.38051$$

Sau khi làm tròn kế toán theo chuẩn 2 chữ số thập phân của đồng USD:
$$\text{Cash Balance} = \$99,773.38$$

Số liệu này trùng khớp 100% với giá trị `cash: "99773.38"` được trả về bởi endpoint `GET /v2/account` và `GET /api/workbench/account`.

---

## 4. Bảng Đối Chiếu Tính Toàn Vẹn Số Liệu Xuyên Suốt Các Giai Đoạn (GĐ10 — GĐ22)

| Thông số Giám sát | Mốc GĐ10 (Baseline) | Mốc GĐ16.1 (Audit) | Mốc GĐ18 (Soak Start) | Mốc GĐ21 (Read-Only) | Mốc GĐ22 (Hiện tại) | Tính Nhất Quán |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Số dư Tiền mặt (Cash)** | $99,773.38 | $99,773.38 | $99,773.38 | $99,773.38 | $99,773.38 | **Bất biến 100%** |
| **Giá trị Danh mục (Portfolio)** | ~$100,000 | ~$100,000 | ~$100,000 | ~$100,000 | ~$100,000 | Biến động theo giá thị trường |
| **Vị thế NVDA** | 1.0 cổ phiếu | 1.0 cổ phiếu | 1.0 cổ phiếu | 1.0 cổ phiếu | 1.0 cổ phiếu | **Bất biến 100%** |
| **Vị thế BTCUSD** | 0.000120008 | 0.000120008 | 0.000120008 | 0.000120008 | 0.000120008 | **Bất biến 100%** |
| **Tổng số Lệnh Lịch sử** | 2 lệnh | 2 lệnh | 2 lệnh | 2 lệnh | 2 lệnh | **Không phát sinh lệnh mới** |
| **Số Lệnh Mở (Open Orders)**| 0 lệnh | 0 lệnh | 0 lệnh | 0 lệnh | 0 lệnh | **Không có lệnh treo** |
| **Lệnh Ghi vào Broker Thật**| 0 | 0 | 0 | 0 | 0 | **Tuyệt đối Zero Write** |

---

## 5. Kết Luận Nghiệm Thu Đối Soát

1. Toàn bộ các câu hỏi lịch sử liên quan đến chênh lệch khối lượng Bitcoin và số dư tiền mặt tài khoản đã được giải đáp đầy đủ bằng các bằng chứng kỹ thuật và kế toán không thể bác bỏ.
2. Tài khoản Alpaca Paper được bảo toàn nguyên vẹn 100%, không bị tác động bởi bất kỳ hoạt động thử nghiệm nào từ GĐ19, GĐ20, GĐ21 cho đến GĐ22.
3. Độ tin cậy của chuỗi dữ liệu telemetry tài khoản đạt mức chuẩn xác tuyệt đối (`PROVENANCE_CONFIRMED`).
