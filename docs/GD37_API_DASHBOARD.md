# GĐ37 — REST API & DASHBOARD INTEGRATION

**Dự án:** AlgoTrading V2.0  
**Giai đoạn:** GĐ37  
**Module:** `libs/bot/api/routes.py`, `libs/bot/api/service.py`, `PaperBotPanel.tsx`

---

## 1. Danh mục Endpoints Multi-Bot REST API

Các endpoints được gắn dưới tiền tố `/api/v2/bots` và tuân thủ OpenAPI 3.0:

| Phương thức | Endpoint | Chức năng | Phản hồi |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v2/bots/overview` | Lấy telemetry tổng hợp của supervisor, số lượng bot theo trạng thái, utilization, và thông số dispatcher | `200 OK` (JSON) |
| `GET` | `/api/v2/bots` | Danh sách toàn bộ bot (cả active runtimes và persisted definitions) | `200 OK` (Array) |
| `POST` | `/api/v2/bots` | Đăng ký một BotDefinition mới | `201 Created` |
| `GET` | `/api/v2/bots/{bot_id}` | Chi tiết bot theo `bot_id` hoặc `session_id` | `200 OK` / `404` |
| `GET` | `/api/v2/bots/{bot_id}/sessions` | Danh sách lịch sử các phiên của bot | `200 OK` (Array) |
| `POST` | `/api/v2/bots/{bot_id}/start` | Khởi động bot chuyển sang trạng thái `RUNNING` | `200 OK` / `409` |
| `POST` | `/api/v2/bots/{bot_id}/pause` | Tạm dừng nhận nến 1m, bảo lưu lệnh working | `200 OK` |
| `POST` | `/api/v2/bots/{bot_id}/resume` | Tái kích hoạt bot từ trạng thái `PAUSED` | `200 OK` |
| `POST` | `/api/v2/bots/{bot_id}/stop` | Dừng bot an toàn theo `StopPolicy` | `200 OK` |
| `POST` | `/api/v2/bots/{bot_id}/archive` | Soft-archive bot, bảo tồn dữ liệu kiểm toán | `200 OK` |
| `GET` | `/api/v2/bots/{bot_id}/portfolio` | Lấy danh mục, tiền mặt, và vị thế mô phỏng của bot | `200 OK` |
| `GET` | `/api/v2/bots/{bot_id}/orders` | Lấy danh sách lệnh mô phỏng | `200 OK` |
| `GET` | `/api/v2/bots/{bot_id}/fills` | Lấy danh sách khớp lệnh mô phỏng | `200 OK` |
| `GET` | `/api/v2/bots/{bot_id}/performance` | Báo cáo hiệu năng (Win rate, Drawdown, PnL) | `200 OK` |
| `GET` | `/api/v2/bots/{bot_id}/health` | Trạng thái sức khỏe, độ trễ và cảnh báo | `200 OK` |
| `POST` | `/api/v2/bots/dispatch_bar` | Nạp nến 1m vào hệ thống fan-out của supervisor | `200 OK` |

---

## 2. Giao diện Người dùng Multi-Bot Dashboard

Giao diện `PaperBotPanel.tsx` được nâng cấp toàn diện:
1. **Supervisor Overview Banner**:
   - Hiển thị trạng thái hệ thống: `HEALTHY` (xanh) hoặc `DEGRADED` (vàng).
   - Đếm số lượng bot theo trạng thái: `X RUNNING`, `Y PAUSED`, `Z STOPPED`.
   - Báo cáo số lượt nến đã phân phối qua Dispatcher.
   - Huy hiệu tuyên bố miễn trừ: `INDEPENDENT CAPITAL ONLY`.
2. **Bộ chọn Bot Động**:
   - Cho phép chọn nhanh giữa các bot đang chạy hoặc đã dừng.
   - Thể hiện trạng thái thời gian thực thông qua kết nối WebSocket streaming `/ws/v2/bots/{session_id}`.
3. **Thao tác Điều khiển Tập trung**:
   - Nút `Start`, `Pause`, `Resume`, `Stop` có hiệu ứng loading và phản hồi lỗi tức thì.
   - Modal tạo mới bot linh hoạt theo từng chiến lược (`MA_CROSS_1M`, `RSI_1M`, v.v.).
