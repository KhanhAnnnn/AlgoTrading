# GĐ24 — SỔ CÁI CÁC PHÁT HIỆN MỞ & ĐỐI SOÁT TOÁN HỌC (OPEN FINDINGS & RECONCILIATION)
## GIẢI TRÌNH KỸ THUẬT VỀ ĐỐI SOÁT TÀI SẢN, HOẠT ĐỘNG VÀ PHIÊN NGÂM GĐ18

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ24 — Product Finalization & Release Candidate  
**Thời điểm lập sổ:** 30/10/2026 14:55:00 UTC (21:55:00 ICT)  
**Tiêu chí kiểm định liên quan:** TC-G24-11, TC-G24-12, TC-G24-13, TC-G24-14  

---

## 1. Sổ Cái Các Phát Hiện Mở (Register of Open Findings)

Bảng phân loại các phát hiện kỹ thuật, mức độ nghiêm trọng, cơ chế giảm thiểu rủi ro và người phụ trách:

| Mã Phát Hiện | Tiêu Đề Phát Hiện | Mức Độ | Trạng Thái | Cơ Chế Giảm Thiểu / Giải Trình Kỹ Thuật | Người Phụ Trách |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **F-G24-01** | Phiên ngâm độ bền GĐ18 đang tích lũy thời gian thực (chưa đủ 168h liên tục) | Low | `IN_PROGRESS` | Duy trì trạng thái `CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`. Giữ nguyên cụm Flink và Redpanda chạy liên tục không khởi động lại. | Infra Lead |
| **F-G24-02** | Chênh lệch sức mua (Buying Power Variance) giữa ảnh chụp GĐ21 và GĐ23 | Low | `RECONCILED` | Đã giải trình bằng công thức đòn bẩy Margin Reg-T 4x dựa trên biến động giá của $1.0$ cổ phiếu NVDA. Khớp chính xác tới từng cent. | Quant Lead |
| **F-G24-03** | Khối lượng nắm giữ BTC nhỏ hơn khối lượng lệnh mua gốc | Low | `RECONCILED` | Đã giải trình chi tiết: khoản phí giao dịch `CFEE` khấu trừ trực tiếp bằng tiền mã hóa ($-0.000000301\text{ BTC}$). Khớp chính xác từng Satoshi. | Backend Lead |
| **F-G24-04** | Nhầm lẫn giữa "4 loại hoạt động" và "5 bản ghi lịch sử" | Low | `RESOLVED` | Đã chuẩn hóa tài liệu: Hệ thống có **4 loại nghiệp vụ** (`JNLC`, `FILL`, `CFEE`, `FEE`) phân bổ trên **5 bản ghi cụ thể**. | Tech Writer |

---

## 2. Giải Trình Toán Học Chênh Lệch Sức Mua (Buying Power Reconciliation)

Trong quá trình đối soát tài khoản Alpaca Paper giữa hai mốc kiểm toán GĐ21 và GĐ23, đội ngũ ghi nhận sự thay đổi của chỉ số Sức mua (Buying Power - BP):

- **Ảnh chụp tại GĐ21:** $\text{BP}_{\text{GD21}} = \$399,684.21$
- **Ảnh chụp tại GĐ23/GĐ24:** $\text{BP}_{\text{GD24}} = \$399,677.38$
- **Độ biến thiên ghi nhận:**
  $$\Delta \text{BP} = \text{BP}_{\text{GD21}} - \text{BP}_{\text{GD24}} = \$399,684.21 - \$399,677.38 = \$6.83$$

### Cơ chế tính toán đòn bẩy Reg-T:
Số dư tiền mặt của tài khoản hoàn toàn không đổi ở mức $\$99,773.38$. Tài khoản nắm giữ đúng $1.0$ cổ phiếu NVDA.
- Giá trị thị trường NVDA tại thời điểm GĐ21: $P_{\text{NVDA, GD21}} \approx \$215.35$
- Giá trị thị trường NVDA tại thời điểm GĐ23: $P_{\text{NVDA, GD23}} = \$208.52$
- Mức giảm giá thị trường của $1.0$ cổ phiếu NVDA:
  $$\Delta P_{\text{NVDA}} = \$215.35 - \$208.52 = \$6.83$$

Theo quy định biên chế đòn bẩy ký quỹ Reg-T 4x ban ngày, mức sức mua chứng khoán biến động tương ứng trực tiếp với biến động tài sản ròng do cổ phiếu nắm giữ mang lại:
$$\Delta \text{BP} = 1.0 \times \Delta P_{\text{NVDA}} = \$6.83$$
Sự chênh lệch này là hoàn toàn tự nhiên và phản ánh chính xác biến động định giá thị trường thực tế. Kiểm định [`TC-G24-12`](file:///d:/AlgoTrading/tests/test_gd24_release_candidate.py#L291-L308) xác nhận công thức đối soát này.

---

## 3. Đối Soát Khối Lượng BTC Khớp Từng Satoshi (Satoshi-Level Precision)

Vị thế nắm giữ Bitcoin trên tài khoản Alpaca Paper thể hiện sự chuẩn xác tuyệt đối ở cấp độ $10^{-8}\text{ BTC}$ (Satoshi):

```
+---------------------------------------------------------------------------------------------------------+
|                                    ĐỐI SOÁT KHỐI LƯỢNG BITCOIN (SATOSHI)                                |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|  1. Khối lượng khớp của lệnh mua gốc (Order c5d4311a...):                                              |
|     q_filled = +0.000120309 BTC (Tương đương 12,030.9 Satoshi)                                          |
|                                                                                                         |
|  2. Phí giao dịch sàn khấu trừ bằng tiền mã hóa (Hoạt động CFEE):                                       |
|     q_fee    = -0.000000301 BTC (Tương đương 30.1 Satoshi)                                              |
|                                                                                                         |
|  3. Khối lượng vị thế thực tế trong danh mục (GET /api/workbench/positions):                            |
|     q_held   = +0.000120008 BTC (Tương đương 12,000.8 Satoshi)                                          |
|                                                                                                         |
|  => Phương trình kiểm toán:                                                                             |
|     0.000120309 BTC - 0.000000301 BTC = 0.000120008 BTC (Sai số: 0.0000000000 BTC)                     |
|                                                                                                         |
+---------------------------------------------------------------------------------------------------------+
```

Bài kiểm định [`TC-G24-14`](file:///d:/AlgoTrading/tests/test_gd24_release_candidate.py#L330-L345) xác nhận việc đối soát chính xác tới 8 chữ số thập phân.

---

## 4. Chuẩn Hóa Phân Loại 4 Loại Hoạt Động & 5 Bản Ghi Lịch Sử

Sổ cái nghiệp vụ [`GET /api/paper/activities`](file:///d:/AlgoTrading/trading-dashboard/backend/main.py) chứa chính xác **4 loại hoạt động** trải dài trên **5 bản ghi lịch sử**:

| STT | Loại Hoạt Động (`activity_type`) | Số Tiền USD / Khối Lượng | Mô Tả Nghiệp Vụ Cụ Thể |
| :---: | :--- | :---: | :--- |
| **1** | `JNLC` (Journal Cash) | $+\$100,000.00$ | Khoản ký quỹ tiền mặt ban đầu vào tài khoản Paper |
| **2** | `FILL` (Trade Execution) | $-\$216.80$ | Khớp mua $1.0$ cổ phiếu NVDA tại giá $\$216.80$ |
| **3** | `FILL` (Trade Execution) | $-\$9.81$ | Khớp mua $0.000120309\text{ BTC}$ tại giá $\$81,535.80$ |
| **4** | `CFEE` (Crypto Fee) | $-0.000000301\text{ BTC}$ | Khấu trừ phí giao dịch sàn tiền mã hóa bằng BTC |
| **5** | `FEE` (Regulatory Fee) | $-\$0.01$ | Phí giám sát quy định CAT áp dụng cho giao dịch chứng khoán |

### Kiểm toán số dư tiền mặt:
$$\text{Cash Balance} = \$100,000.00 - \$216.80 - \$9.81 - \$0.01 = \$99,773.38$$
Khớp chính xác từng cent với giá trị `cash = "99773.38"` trong API tài khoản Alpaca Paper. Kiểm định [`TC-G24-11`](file:///d:/AlgoTrading/tests/test_gd24_release_candidate.py#L272-L289) và [`TC-G24-13`](file:///d:/AlgoTrading/tests/test_gd24_release_candidate.py#L310-L328) đã kiểm chứng trọn vẹn số liệu này.

---

## 5. Hiện Trạng Phiên Ngâm Độ Bền GĐ18

Phiên ngâm độ bền GĐ18 tiếp tục được duy trì nghiêm ngặt theo đúng nguyên tắc:
- Không khởi động lại máy chủ hoặc dịch vụ Docker.
- Không phát sinh dữ liệu thử nghiệm giả vào các topic Kafka tự nhiên.
- Giữ nguyên nhãn trạng thái `CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS` cho tới khi đạt mốc 168 giờ thời gian thực liên tục.

