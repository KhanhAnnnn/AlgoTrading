# GĐ38 — STRATEGY CONFIGURATION & SCHEMA VALIDATION

## 1. Executive Summary
Giai đoạn GĐ38 triển khai hệ thống quản trị cấu hình chiến lược định lượng có phiên bản, kiểm soát chặt chẽ kiểu dữ liệu, giới hạn biên và ràng buộc quan hệ giữa các tham số (cross-parameter constraints) cho AlgoTrading V2.0.

## 2. Parameter Schema Architecture (`libs/bot/strategy_config/schemas.py`)
Mỗi tham số chiến lược được định nghĩa thông qua `ParameterSchema`:
- `name`: Tên tham số định danh duy nhất.
- `data_type`: Kiểu dữ liệu (`int`, `float`, `str`, `bool`, `list`).
- `required`: Bắt buộc hay tùy chọn.
- `default`: Giá trị mặc định an toàn.
- `minimum` / `maximum`: Ngưỡng chặn dưới và chặn trên hợp lệ.
- `permitted_values`: Danh sách giá trị phân loại cho phép (enums).
- `units`: Đơn vị đo lường (`bars`, `index`, `percent`, `bps`).
- `description`: Mô tả ngữ nghĩa định lượng.

## 3. Strict Parameter Validation & Cross-Parameter Rules
`StrategySchemaValidator` thực hiện xác thực nghiêm ngặt:
1. **Từ chối tham số không khai báo (Reject Undeclared Parameters)**: Ngăn chặn triệt để tham số thừa hoặc gõ nhầm gây ra hành vi không lường trước.
2. **MA_CROSS_1M Constraints**:
   - `fast_window < slow_window`: Bắt buộc đường trung bình nhanh phải có chu kỳ nhỏ hơn đường trung bình chậm.
   - `indicator_type` $\in$ `["SMA", "EMA"]`.
   - `fast_window` $\ge 1$, `slow_window` $\ge 2$.
3. **RSI_1M Constraints**:
   - $0.0 \le \text{oversold\_threshold} < \text{overbought\_threshold} \le 100.0$.
   - `period` $\ge 2$, `period` $\le 200$.
   - `method` $\in$ `["WILDER", "SIMPLE_ROLLING"]`.

## 4. Strategy Registry (`libs/bot/strategy_config/registry.py`)
`StrategyConfigurationRegistry` quản lý danh mục `StrategyDefinition`:
- Hỗ trợ tra cứu định nghĩa, liệt kê danh sách chiến lược đang kích hoạt.
- Cung cấp phương thức `validate_parameters(strategy_id, params)` tích hợp vào API và lifecycle.
