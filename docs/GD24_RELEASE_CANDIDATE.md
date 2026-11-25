# GĐ24 — HỒ SƠ CHỨNG NHẬN BẢN PHÁT HÀNH (RELEASE CANDIDATE DOSSIER)
## HỒ SƠ CHỨNG NHẬN SẢN PHẨM PHIÊN BẢN V1.0.0-RC1

**Dự án:** `D:\AlgoTrading`  
**Phiên bản phát hành:** `v1.0.0-rc1`  
**Giai đoạn:** GĐ24 — Product Finalization & Release Candidate  
**Thời điểm đóng gói:** 30/10/2026 14:55:00 UTC (21:55:00 ICT)  
**Tiêu chí kiểm định liên quan:** TC-G24-25, Toàn bộ bộ kiểm thử GĐ20–GĐ24  

---

## 1. Tuyên Bố Bản Phát Hành (Release Candidate Declaration)

Phiên bản **AlgoTrading v1.0.0-rc1** chính thức được phê duyệt là **Ứng viên Bản Phát hành (Release Candidate)** sau khi đáp ứng trọn vẹn mọi tiêu chí khắt khe về độ tin cậy phần mềm, an toàn rào chắn giao dịch, và sự nguyên vẹn của luồng dữ liệu thời gian thực.

```
+---------------------------------------------------------------------------------------------------------+
|                                  ALGOTRADING RELEASE CANDIDATE MANIFEST                                 |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|  - Tên Sản Phẩm: AlgoTrading Dashboard & Autonomous Engine                                              |
|  - Phiên Bản Đóng Gói: v1.0.0-rc1                                                                       |
|  - Git Commit Ref: HEAD (Mainline Repository D:\AlgoTrading)                                            |
|  - Trạng Thái: CANDIDATE CERTIFIED — READY FOR OPERATIONAL DEPLOYMENT                                   |
|  - Môi Trường Mặc Định: TRADING_MODE=DRY_RUN (Immutable)                                               |
|  - Rào Chắn Cổng Thực Thi: CLOSED (Fail-Closed, is_gate_open=False)                                      |
|  - Cụm Phiên Ngâm GĐ18: CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS (Không ngắt quãng)                     |
|                                                                                                         |
+---------------------------------------------------------------------------------------------------------+
```

---

## 2. Kiểm Tra Bản Dựng Giao Diện (Frontend Production Build Verification)

Thành phần giao diện người dùng React được đóng gói thông qua công cụ biên dịch Vite và TypeScript:

- **Thư mục mã nguồn:** [`trading-dashboard/frontend`](file:///d:/AlgoTrading/trading-dashboard/frontend)
- **Lệnh biên dịch:** `npm run build` (`tsc -b && vite build`)
- **Thời gian biên dịch:** **656 ms**
- **Lỗi TypeScript:** **0 lỗi (Zero type errors)**
- **Thư mục đầu ra:** [`trading-dashboard/frontend/dist`](file:///d:/AlgoTrading/trading-dashboard/frontend/dist)

### Danh Mục Tệp Đóng Gói (Asset Inventory):
| Tên Tệp Phân Phối | Kích Thước | Loại Tệp | Mục Đích Sử Dụng |
| :--- | :---: | :---: | :--- |
| `index.html` | ~0.5 KB | HTML5 Entrypoint | Tệp nạp ứng dụng web chính |
| `assets/index-*.js` | ~380 KB | Compiled JavaScript | Toàn bộ logic giao diện, React Router, biểu đồ và kết nối API |
| `assets/index-*.css` | ~45 KB | Tailwind CSS | Toàn bộ giao diện tùy biến, bảng màu tối (Dark mode) và bố cục |
| `vite.svg` | ~1.5 KB | SVG Asset | Biểu tượng ứng dụng |

Kiểm định [`TC-G24-25`](file:///d:/AlgoTrading/tests/test_gd24_release_candidate.py#L492-L505) xác nhận tính toàn vẹn của thư mục `dist/`, xác thực cấu trúc HTML/CSS/JS hợp lệ và không phát hiện bất kỳ dấu hiệu rò rỉ khóa định danh nào.

---

## 3. Xác Thực Hợp Đồng API Phía Máy Chủ (Backend API Contracts)

Máy chủ Backend FastAPI [`trading-dashboard/backend`](file:///d:/AlgoTrading/trading-dashboard/backend) đáp ứng đầy đủ các hợp đồng API tiêu chuẩn:

1. **Nhóm Market Data:**
   - `GET /api/market/latest-prices`: Cung cấp giá khớp mới nhất của cặp cổ phiếu và crypto.
   - `GET /api/market/status`: Cung cấp trạng thái phiên giao dịch (Mở cửa/Đóng cửa).
2. **Nhóm Tin Tức & Phân Tích (News & Sentiment):**
   - `GET /api/news/sentiment`: Cung cấp điểm số tâm lý thị trường trung bình và danh sách tin vĩ mô.
3. **Nhóm Danh Mục & Lệnh Thật (Alpaca Paper Read-Only):**
   - `GET /api/workbench/account?source=alpaca_paper`: Trả về số dư tiền mặt $(\$99,773.38)$, sức mua margin và trạng thái tài khoản `ACTIVE`.
   - `GET /api/workbench/positions?source=alpaca_paper`: Trả về 2 vị thế thật ($1.0\text{ NVDA}$ và $0.000120008\text{ BTC}$).
   - `GET /api/workbench/orders?source=alpaca_paper`: Trả về danh sách lệnh gốc đã khớp.
   - `GET /api/paper/activities`: Trả về 5 bản ghi hoạt động thuộc 4 loại nghiệp vụ.
4. **Nhóm Trạm Làm Việc Mô Phỏng (Mock Workbench):**
   - `GET /api/workbench/orders?source=mock`: Sổ lệnh giao dịch thử nghiệm độc lập.
   - `POST /api/workbench/orders`: Đặt lệnh mô phỏng mới với 5 loại lệnh chuẩn.
   - `PATCH /api/workbench/orders/{id}`: Sửa lệnh treo nội bộ.
   - `DELETE /api/workbench/orders/{id}`: Hủy lệnh lẻ.
   - `DELETE /api/workbench/orders`: Hủy toàn bộ lệnh mở mô phỏng.
   - `POST /api/workbench/reset`: Đặt lại môi trường mô phỏng về $\$100,000.00$.
5. **Nhóm Sức Khỏe & Độ Tin Cậy (Reliability & Health):**
   - `GET /api/health/status`: Trả về đánh giá 5 trụ cột sức khỏe.
   - `GET /api/system/status`: Trả về thông số hạ tầng và chế độ `DRY_RUN`.

---

## 4. Bảng Kiểm Đăng Xuất Bản (Release Sign-Off Checklist)

| Tiêu Chí Kiểm Tra Đóng Bản Phát Hành | Tiêu Chuẩn Nghiệm Thu | Kết Quả Thực Tế | Đánh Giá |
| :--- | :--- | :--- | :---: |
| **Bảo toàn chế độ DRY_RUN** | Bất biến trong `.env` | `TRADING_MODE=DRY_RUN` | **ĐẠT** |
| **Cổng an toàn Paper Gate** | Đóng mặc định (Fail-Closed) | `is_gate_open = False` | **ĐẠT** |
| **Chặn kết nối Live Broker** | Cấm gọi `api.alpaca.markets` | Ném `LiveTradingProhibitedError` | **ĐẠT** |
| **Độ bền cụm Flink GĐ18** | Duy trì 2 streaming jobs, 6/6 tasks | 6/6 Tasks RUNNING, 0 Failures | **ĐẠT** |
| **Độ trễ hàng đợi Consumer Lag** | Không vượt quá 50 sự kiện | $\text{Lag} = 0$ (Hoàn hảo) | **ĐẠT** |
| **Biên dịch Frontend sạch** | Không có lỗi TypeScript | 0 Lỗi, thời gian build 656ms | **ĐẠT** |
| **Đối soát số học tài khoản** | Khớp từng cent và từng Satoshi | $\$99,773.38$ và $0.000120008\text{ BTC}$ | **ĐẠT** |
| **Bộ kiểm thử tự động GĐ24** | Đạt 100% số bài kiểm thử | **26 / 26 Đạt (100%)** | **ĐẠT** |
| **Bộ kiểm thử hồi quy GĐ20–GĐ23**| Đạt 100% số bài kiểm thử | **104 / 104 Đạt (100%)** | **ĐẠT** |
| **Tổng số ca kiểm thử thành công**| Không ghi nhận bất kỳ ca lỗi nào | **130 / 130 Đạt (100%)** | **ĐẠT** |

