# GĐ38 — FAIR COMPARISON RULES & COMPARATIVE METRICS

## 1. Nguyên tắc So sánh Công bằng (Fair Comparison Rules)
Để ngăn ngừa ngụy biện định lượng (research bias) và so sánh khập khiễng, `ComparabilityEngine` bắt buộc các backtest runs phải thỏa mãn các điều kiện tương thích:
1. **Dataset Version / Hash**: Cùng phiên bản dữ liệu nến 1m (`DATASET_MISMATCH`).
2. **Date Range**: Cùng mốc thời gian bắt đầu và kết thúc (`DATE_RANGE_MISMATCH`).
3. **Asset Universe**: Cùng tập hợp danh mục cổ phiếu / tiền mã hóa (`UNIVERSE_MISMATCH`).
4. **Timeframe**: Cùng khung thời gian chuẩn 1 phút (`TIMEFRAME_MISMATCH`).
5. **Fee Model & Slippage Model**: Cùng giả định chi phí giao dịch và trượt giá (`FEE_MODEL_MISMATCH`, `SLIPPAGE_MODEL_MISMATCH`).
6. **Initial Capital**: Cùng số vốn ban đầu mô phỏng (`CAPITAL_MISMATCH`).

Khi một trong các điều kiện trên vi phạm, hệ thống đánh dấu cờ `NOT_DIRECTLY_COMPARABLE` kèm danh sách mã nguyên nhân, cảnh báo nhà định lượng trên bảng so sánh.

## 2. Comparative KPI Table & Deltas (`libs/bot/experiments/comparison.py`)
Hệ thống tính toán các chỉ số tương đối so với biến thể cơ sở (Baseline Variant):
- $\Delta \text{Sharpe} = \text{Sharpe}_{\text{variant}} - \text{Sharpe}_{\text{baseline}}$
- $\Delta \text{Return} = \text{Return}_{\text{variant}} - \text{Return}_{\text{baseline}}$
- $\Delta \text{MaxDrawdown} = \text{MDD}_{\text{variant}} - \text{MDD}_{\text{baseline}}$
- $\Delta \text{WinRate} = \text{WinRate}_{\text{variant}} - \text{WinRate}_{\text{baseline}}$
- $\Delta \text{ProfitFactor} = \text{PF}_{\text{variant}} - \text{PF}_{\text{baseline}}$

## 3. Zero-Denominator Safeguards
Xử lý an toàn khi số lượng giao dịch = 0, phương sai lợi nhuận = 0, hoặc drawdown = 0, không bao giờ phát sinh `ZeroDivisionError`, `NaN` hay `Infinity`.
