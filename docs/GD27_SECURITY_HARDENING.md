# GĐ27: Security & Access Hardening Verification

**Repository:** `D:\AlgoTrading`  
**Release:** `v1.0.0`  
**Phase:** GĐ27 — Production Deployment Hardening & Disaster Recovery Validation  
**Status:** `VERIFIED — SECURITY_HARDENED`  
**Evaluation Timestamp:** `2026-10-31T22:33:00+07:00`

---

## 1. Mục tiêu Tăng cường Bảo mật & Kiểm soát Truy cập

Báo cáo này xác minh toàn diện các chốt bảo vệ an toàn (security guardrails), kiểm soát quyền truy cập API, vệ sinh nhật ký và cấu hình ràng buộc mạng của phiên bản phát hành v1.0.0 nhằm triệt tiêu mọi nguy cơ tấn công hoặc rò rỉ dữ liệu ngoài ý muốn.

---

## 2. Kiểm soát Ranh giới Mạng & Ràng buộc Hostname (Network Binding)

1. **Ràng buộc Mạng Nội bộ (Internal Network Binding):**
   - Website và API được cấu hình phục vụ trong mạng cục bộ nội bộ (`localhost` / mạng LAN nội bộ an toàn).
   - Tuyệt đối không mở các cổng điều khiển (port 8005, 3000, 8081, 9092) ra mạng Internet công cộng.
   - Không kích hoạt bất kỳ giải pháp public tunnel nào (như `ngrok`, `localtunnel`).
2. **Chính sách CORS Phân vùng Nghiêm ngặt:**
   - Backend FastAPI cấu hình middleware CORS cho phép kết nối từ Production Web Server (`http://localhost:3000`), Dev Server (`http://localhost:5173`), và Preview (`http://localhost:4173`).
   - Các yêu cầu HTTP Options preflight được xác thực và gán header hợp lệ.

---

## 3. Rà soát Rò rỉ Bí mật (Secret Leak Prevention)

| Khu vực Rà soát | Phương pháp Kiểm định | Kết quả Rà soát | Đánh giá |
| :--- | :--- | :--- | :---: |
| **Frontend Production Assets (`dist/assets/*.js`)** | Quét tự động bằng biểu thức chính quy tìm kiếm `ALPACA_SECRET_KEY`, `BROKER_SECRET_KEY`, JWTs | **Zero secrets found** (Không phát hiện bất kỳ token nào) | **PASS** |
| **Nhật ký Hoạt động (`logs/*.log`)** | Quét toàn bộ tệp log tìm kiếm API keys, Bearer tokens, passwords | **Zero credentials in logs** (Tất cả log sạch và được vệ sinh) | **PASS** |
| **Bản sao lưu Khôi phục (`configs/sanitized_env.json`)** | Hàm `sanitize_env_content()` tự động gắn mặt nạ `***REDACTED***` | **100% tokens masked** (Không lưu plaintext secret) | **PASS** |
| **Mã nguồn Git (`.env` vs `.env.example`)** | Kiểm tra `.gitignore` bảo vệ `.env` không bị commit vào git repository | **`.env` được bỏ qua hoàn toàn** | **PASS** |

---

## 4. Kiểm soát Quyền Ghi Broker & Cơ chế Fail-Closed

1. **Thẩm quyền Phía Máy chủ (Server-Side Authority Assertion):**
   - Bất kể giao diện client gửi payload gì, hàm xử lý tại `trading-dashboard/backend/main.py` luôn kiểm tra:
     ```python
     if order_req.target_broker and order_req.target_broker.upper() == "ALPACA_PAPER":
         if not paper_gate.is_gate_open:
             raise HTTPException(
                 status_code=status.HTTP_403_FORBIDDEN,
                 detail="PaperExecutionGate is LOCKED. Order execution via Alpaca Paper is strictly disabled."
             )
     ```
   - Kết quả: Khi gửi lệnh với `target_broker: "ALPACA_PAPER"`, máy chủ luôn phản hồi ngay lập tức bằng mã **HTTP 403 Forbidden**, chặn đứng ở tầng backend.
2. **Cổng An toàn PaperExecutionGate:**
   - `paper_gate.is_gate_open = False`
   - Phương thức `submit_paper_order` lập tức ném ngoại lệ `PaperExecutionGateClosedError`.
3. **Cấm Tuyệt đối Live Trading:**
   - Bất kỳ nỗ lực khởi tạo SDK kết nối tới URL `api.alpaca.markets` sẽ kích hoạt ngay `LiveTradingProhibitedError`.

