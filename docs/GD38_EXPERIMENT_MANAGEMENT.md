# GĐ38 — BACKTEST EXPERIMENT MANAGEMENT & LIFECYCLE

## 1. Mục tiêu kiến trúc
Quản lý các nghiên cứu tham số định lượng có hệ thống (Grid Search, Sensitivity Analysis, Calibration) theo mô hình:
$$\text{Experiment} \longrightarrow \text{Variants (Configurations)} \longrightarrow \text{Independent BacktestRuns} \longrightarrow \text{Comparative Evaluation}$$

## 2. Cấu trúc thực thể Experiment (`libs/bot/experiments/manager.py`)
- `BacktestExperiment`:
  - `experiment_id`: Định danh duy nhất của thử nghiệm (`exp_*`).
  - `name`: Tên thử nghiệm.
  - `base_strategy_id`: Chiến lược nền tảng (`MA_CROSS_1M`, `RSI_1M`).
  - `dataset_version`: Phiên bản dữ liệu nến chuẩn dùng làm benchmark.
  - `date_range`: Khoảng thời gian kiểm thử (`start_time`, `end_time`).
  - `variants`: Danh sách các biến thể tham số (`ExperimentVariant`).
  - `status`: Vòng đời thử nghiệm (`PENDING` $\rightarrow$ `RUNNING` $\rightarrow$ `COMPLETED` / `FAILED` / `CANCELLED`).
  - `max_concurrency`: Giới hạn tài nguyên song song (mặc định 4).
  - `comparison_summary`: Bảng tổng hợp KPI và so sánh tương đối.

## 3. Điều phối thực thi & Quản lý Hủy bỏ (Cancellation)
- `run_experiment(experiment_id)`:
  - Khởi chạy các biến thể độc lập sử dụng `BacktestRunner` của GĐ36.
  - Mỗi biến thể nhận một `run_id` riêng biệt, ghi nhận `EconomicSequenceFingerprint`, đường cong equity và chỉ số hiệu suất.
- `cancel_experiment(experiment_id)`:
  - Cho phép hủy bỏ an toàn thử nghiệm đang thực thi, đưa các biến thể chưa hoàn tất về trạng thái `CANCELLED`.
