# GĐ39 — SATURDAY 28/11/2026 DEMO READINESS & RUNBOOK

**Dự án:** AlgoTrading V2.0  
**Giai đoạn:** GĐ39 — End-to-End Integration, Short Soak & Reliability Verification  
**Thời hạn phục vụ báo cáo:** Thứ Bảy, 28/11/2026  
**Trạng thái Sẵn sàng:** **100% READY FOR LIVE DEMONSTRATION**  

---

## 1. Kịch bản Trình diễn Trực tiếp (Live Demo Script)

Kịch bản được thiết kế để trình bày trực quan và thuyết phục trong buổi báo cáo Thứ Bảy, 28/11/2026:

### Phần 1: Bằng chứng Hồi quy Toàn diện (623/623 Tests Pass) — Thời lượng: 1 phút
Mục tiêu: Chứng minh tính nguyên vẹn của toàn bộ kiến trúc từ GĐ29 đến GĐ39.
```powershell
python -m unittest tests.test_gd29_contracts tests.test_gd30_data_layer tests.test_gd31_strategy_engine tests.test_gd32_portfolio_risk tests.test_gd33_execution_broker tests.test_gd34_orchestrator tests.test_gd35_api_dashboard tests.test_gd36_backtesting tests.test_gd37_multibot tests.test_gd38_strategy_configuration tests.test_gd39_reliability
```
*Kết quả kỳ vọng:* Toàn bộ 623 bài kiểm thử vượt qua trong ~12 giây, khẳng định không có lỗi hồi quy (zero regression).

---

### Phần 2: Trình diễn Khả năng Vận hành Ngâm Ngắn Thực tế (Short Soak Demo) — Thời lượng: 1 phút
Mục tiêu: Cho thấy 3 bot giao dịch độc lập nhận dữ liệu thời gian thực, cập nhật nhịp tim và cân bằng tài chính.
```powershell
python scripts/run_gd39_short_soak.py
```
*Kết quả kỳ vọng:* Tiến trình chạy 30 giây thời gian thực, xử lý ~150 nến 1m, ghi nhận nhịp tim đầy đủ, p95 latency ~4.5ms, kết luận `PASS` và báo cáo kiểm toán tài chính `BALANCED`.

---

### Phần 3: Trình diễn REST API & Dashboard Trực quan — Thời lượng: 2 phút
Mục tiêu: Minh họa hệ thống điều khiển API `/api/v2/bots` và giao diện Web Dashboard.
1. Khởi động Backend API:
   ```powershell
   uvicorn trading_dashboard.backend.main:app --port 8000
   ```
2. Truy vấn Tổng quan Đa Bot (Overview API):
   ```powershell
   curl -H "X-API-KEY: simulation_token_v2" http://localhost:8000/api/v2/bots/overview
   ```
3. Mở Dashboard Frontend:
   Mở trình duyệt truy cập `http://localhost:5173` hoặc mở bản build tĩnh tại `trading-dashboard/frontend/dist/index.html`.

---

### Phần 4: Trình diễn Chặn An toàn Tuyệt đối (Fail-Closed Safety Demo) — Thời lượng: 1 phút
Mục tiêu: Chứng minh bất biến an toàn không thể bị vượt qua.
- Thử nghiệm gửi lệnh có cờ vi phạm: Hệ thống kích hoạt `CriticalSafetyViolationError` và chặn 100% cuộc gọi ra ngoài.
- Khẳng định: `TRADING_MODE=DRY_RUN`, `PaperExecutionGate.is_gate_open=False`.

---

## 2. Danh mục Bằng chứng Số liệu Sẵn sàng

Toàn bộ tài liệu số và file json chứng thực được chuẩn bị sẵn sàng trong repository:
- `data/status/gd39_acceptance.json`: Quyết định nghiệm thu chính thức.
- `data/status/gd39_test_inventory.json`: Kiểm toán chi tiết 623 bài test.
- `data/status/gd39_soak_evidence.json`: Bằng chứng đo lường thực tế đợt soak.
- `data/status/gd39_performance_evidence.json`: Hồ sơ độ trễ p50, p95, p99 và RAM/CPU.
- `data/status/gd39_safety_evidence.json`: Bằng chứng tuân thủ bất biến an toàn.
