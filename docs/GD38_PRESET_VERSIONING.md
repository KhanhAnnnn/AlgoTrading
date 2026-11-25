# GĐ38 — IMMUTABLE PRESET MANAGEMENT & CONFIGURATION VERSIONING

## 1. Overview
Hệ thống preset chiến lược bất biến (`StrategyPreset`) đảm bảo tính tái lập (reproducibility) tuyệt đối cho các nghiên cứu định lượng và các phiên giao dịch mô phỏng bot.

## 2. Canonical JSON Serialization & SHA-256 Hashing (`versioning.py`)
- Mọi cấu hình trước khi băm được chuẩn hóa thông qua `canonical_serialize(data)`:
  - Sắp xếp đệ quy toàn bộ các khóa từ điển (`sort_keys=True`).
  - Định dạng số thực tránh sai lệch dấu phẩy động IEEE 754.
  - Loại bỏ khoảng trắng không có nghĩa (`separators=(',', ':')`).
- `compute_configuration_hash(data)` tạo mã băm SHA-256 64 ký tự hex đại diện cho dấu vân tay bất biến của cấu hình.

## 3. Preset Immutability & Run-Locking Policy (`presets.py`)
- **Immutability Invariant**: Khi một preset đã được lưu với `is_immutable=True`, mọi yêu cầu ghi đè (overwrite) hoặc sửa đổi trực tiếp đều bị từ chối bằng `PresetImmutableError`.
- **Run-Locking**: Khi một preset được tham chiếu bởi một `BacktestRun` hoặc `BotSession`, phương thức `lock_preset(preset_id, run_id)` khóa vĩnh viễn preset đó.
- **Cloning Paradigm**: Muốn tinh chỉnh tham số, người dùng bắt buộc phải tạo bản sao thông qua `clone_preset()`, tạo ra `preset_id` mới và `configuration_hash` mới.

## 4. Persistent Storage
- Toàn bộ preset được lưu trữ tại `data/paper_bot/presets/{preset_id}.json`.
- Định dạng JSON lưu trữ đầy đủ `configuration_hash`, `schema_version`, `environment='SIMULATION'`, `created_at`, và `parameters`.
