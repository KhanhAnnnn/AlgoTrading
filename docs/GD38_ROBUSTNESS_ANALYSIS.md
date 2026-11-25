# GĐ38 — STRATEGY ROBUSTNESS & TEMPORAL SPLIT ANALYSIS

## 1. Mục tiêu phân tích độ bền vững (Robustness Analysis)
Ngăn chặn hiện tượng tối ưu quá mức (overfitting / data snooping bias) và đảm bảo chiến lược duy trì hiệu quả khi thị trường thay đổi cấu trúc.

## 2. Phân tích độ nhạy tham số (Parameter Sensitivity Analysis)
`StrategyRobustnessAnalyzer.analyze_parameter_sensitivity`:
- Đánh giá phân phối hiệu suất trong lân cận tham số (Neighborhood grid).
- Tính toán giá trị trung bình (mean), độ lệch chuẩn (stdev) và hệ số biến thiên (coefficient of variation - $CV = \frac{\sigma}{|\mu|}$).
- Khi $CV \ge 0.35$ hoặc xuất hiện giá trị âm cực đoan, hệ thống bật cảnh báo giòn tham số (`brittleness_warning = True`).

## 3. Phân chia chuỗi thời gian (Chronological Temporal Split)
- Phương pháp `split_dataset_temporal`:
  - Phân chia tập dữ liệu thành 3 giai đoạn: Train (In-Sample, 60%), Validation (20%), và Test (Out-of-Sample, 20%).
  - Tuân thủ thứ tự thời gian nghiêm ngặt, ngăn chặn triệt để hiện tượng rò rỉ thông tin tương lai (Lookahead Bias / Data Leakage).
- Đánh giá suy thoái hiệu suất (Performance Degradation):
  - Tỷ lệ suy thoái Sharpe: $\text{Degradation Ratio} = \frac{\text{Sharpe}_{\text{OOS}}}{\text{Sharpe}_{\text{IS}}}$.
  - Nếu $\text{Sharpe}_{\text{IS}} > 1.5$ nhưng $\text{Sharpe}_{\text{OOS}} < 0.2$ hoặc $\text{Degradation Ratio} < 0.40$, hệ thống cảnh báo nguy cơ Overfitting ở mức CAO (`overfitting_risk = 'HIGH'`) và khuyến nghị từ chối triển khai.

## 4. Strict Non-Auto-Deployment Invariant
Bất biến an toàn: Kết quả thử nghiệm định lượng chỉ phục vụ mục đích nghiên cứu (Research Only). Nghiêm cấm tự động đẩy (auto-deploy) cấu hình thử nghiệm lên các Paper Bot đang vận hành.
