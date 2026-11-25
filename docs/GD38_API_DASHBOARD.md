# GĐ38 — REST API & DASHBOARD INTEGRATION

## 1. REST API Specification (`libs/bot/api/experiment_routes.py`)
Được gắn tại `/api/v2`, bổ sung các tài nguyên:

### Strategy Definitions
- `GET /api/v2/strategies`: Danh sách định nghĩa chiến lược, phân loại và schema tham số.
- `GET /api/v2/strategies/{strategy_id}`: Chi tiết schema và giới hạn tham số của một chiến lược.

### Strategy Presets
- `GET /api/v2/strategy-presets`: Liệt kê tất cả presets (hỗ trợ lọc theo `strategy_id`).
- `POST /api/v2/strategy-presets`: Tạo preset bất biến mới (xác thực schema trước khi lưu).
- `GET /api/v2/strategy-presets/{preset_id}`: Xem chi tiết cấu hình và mã băm SHA-256 của preset.
- `POST /api/v2/strategy-presets/{preset_id}/clone`: Sao chép và tạo biến thể mới với `preset_id` mới.

### Backtest Experiments & Comparison
- `GET /api/v2/experiments`: Liệt kê các thử nghiệm tham số.
- `POST /api/v2/experiments`: Khởi tạo thử nghiệm với danh sách biến thể tham số.
- `GET /api/v2/experiments/{experiment_id}`: Trạng thái tiến độ thực thi của thử nghiệm.
- `POST /api/v2/experiments/{experiment_id}/run`: Kích hoạt chạy các biến thể trong thử nghiệm.
- `GET /api/v2/experiments/{experiment_id}/comparison`: Bảng so sánh KPI đa biến thể, độ lệch delta và cờ xác thực so sánh công bằng.
- `POST /api/v2/experiments/{experiment_id}/cancel`: Hủy bỏ thử nghiệm đang chạy.

## 2. React Dashboard Integration
- Bổ sung tab **Experiments & Comparison** trong `BacktestPanel.tsx`.
- Giao diện hỗ trợ chọn thử nghiệm, xem bảng so sánh KPI đa biến thể, nhãn trạng thái `DIRECTLY_COMPARABLE` / `NOT_DIRECTLY_COMPARABLE`, và chênh lệch $\Delta$ Sharpe, $\Delta$ Return.
- Tương thích 100% với Vite, TypeScript và Tailwind CSS (`npm run build` thành công trong 548ms).
