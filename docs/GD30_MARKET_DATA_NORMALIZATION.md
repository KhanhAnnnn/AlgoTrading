# GĐ30 — Market Data Normalization
**AlgoTrading V2.0 Market Data Standardization**  
**Repository:** `D:\AlgoTrading`  
**Target Entity:** `libs.bot.domain.MarketDataEvent`  
**Mandatory Invariant:** `environment = "SIMULATION"`

---

## 1. Mục Tiêu Chuẩn Hóa Dữ Liệu

Dữ liệu nến 1 phút đến từ hai nguồn streaming khác nhau trong V1:
1. Cổ phiếu (Stocks): Đến từ topic `stock-prices`, do `continuous_price_producer.py` lấy từ Alpaca IEX feed.
2. Tiền số (Crypto): Đến từ topic `crypto-bars-1m`, do `continuous_crypto_producer.py` tổng hợp từ Alpaca Crypto WebSocket.

Bộ chuẩn hóa `libs.bot.normalization.MarketDataNormalizer` có nhiệm vụ chuyển hóa tất cả các cấu trúc bản tin thô không đồng nhất này thành đối tượng nghiệp vụ duy nhất: `MarketDataEvent`.

---

## 2. Bảng Đối Chiếu Schema (Schema Mapping Matrix)

| Trường Chuẩn Hóa (`MarketDataEvent`) | Nguồn Stocks (`stock-prices`) | Nguồn Crypto (`crypto-bars-1m`) | Kiểu Dữ Liệu Chuẩn | Quy Tắc Xử Lý & Ràng Buộc |
|:---|:---|:---|:---:|:---|
| `event_id` | Tự sinh (`mde_[hex]`) | Tự sinh (`mde_[hex]`) | `str` | Mã định danh duy nhất của sự kiện trong V2. |
| `source_event_id` | `id` / `event_id` (nếu có) | `id` / `event_id` (nếu có) | `Optional[str]` | Giữ lại ID gốc từ hệ thống nguồn nếu có. |
| `symbol` | `payload['symbol']` | `payload['symbol']` hoặc `payload['S']` | `str` | Chuẩn hóa: Stocks viết hoa; Crypto có dấu `/` (VD: `BTC/USD`). |
| `asset_class` | Gán cứng `"STOCKS"` | Gán cứng `"CRYPTO"` | `str` | Phân biệt lớp tài sản để áp dụng lịch thị trường phù hợp. |
| `timeframe` | Gán cứng `"1m"` | Gán cứng `"1m"` | `str` | Khung thời gian bắt buộc là 1 phút. |
| `open` | `payload['open']` | `payload['open']` hoặc `payload['o']` | `float` | Kiểm tra bắt buộc, độ chính xác cao qua `Decimal`. |
| `high` | `payload['high']` | `payload['high']` hoặc `payload['h']` | `float` | Kiểm tra bắt buộc, không được nhỏ hơn Open/Close. |
| `low` | `payload['low']` | `payload['low']` hoặc `payload['l']` | `float` | Kiểm tra bắt buộc, không được lớn hơn Open/Close. |
| `close` | `payload['close']` | `payload['close']` hoặc `payload['c']` | `float` | Kiểm tra bắt buộc, giá đóng cửa của nến 1m. |
| `volume` | `payload['volume']` | `payload['volume']` hoặc `payload['v']` | `float` | Khối lượng giao dịch, không được âm ($\ge 0$). |
| `trade_count` | `payload['trade_count']` | `payload['trade_count']` hoặc `payload['n']` | `int` | Số lượng giao dịch trong nến phút. |
| `vwap` | `payload['vwap']` | `payload['vwap']` hoặc `payload['vw']` | `float` | Giá trung bình theo khối lượng; nếu thiếu lấy bằng `close`. |
| `event_time` | `timestamp` (ms) | `timestamp_ms` / `event_time` (s/ms) | `datetime` (UTC) | Chuyển đổi về `datetime` có múi giờ UTC (`tzinfo=timezone.utc`). |
| `ingest_time` | `ingest_time` hoặc lúc nhận | `ingest_time` hoặc lúc nhận | `datetime` (UTC) | Thời điểm bản tin đến tầng hấp thụ của V2. |
| `bar_revision` | Mặc định `0` | `revision` / Mặc định `0` | `int` | Tăng dần khi có bản ghi cập nhật cho cùng `bar_key`. |
| `is_final` | Mặc định `True` (nến IEX) | `payload['is_final']` | `bool` | Xác nhận nến đã chốt phiên phút hay còn đang cập nhật. |
| `source` | `provider` (`"alpaca"`) | `source` (`"alpaca_crypto_ws"`) | `str` | Nguồn cấp dữ liệu gốc. |
| `environment` | Gán cứng `"SIMULATION"` | Gán cứng `"SIMULATION"` | `str` | **Ràng buộc an toàn:** Luôn là `"SIMULATION"`. |
| `provenance` | Nguồn gốc truyền vào | Nguồn gốc truyền vào | `str` | `"NATURAL_RUNTIME"`, `"HISTORICAL_BACKFILL"`, hoặc `"FIXTURE"`. |
| `quality_flags` | Danh sách rỗng ban đầu | Danh sách rỗng ban đầu | `List[str]` | Được gán bởi `DataQualityEngine` trong quá trình thẩm định. |

---

## 3. Quy Định An Toàn Kiểu Dữ Liệu & Độ Chính Xác

1. **Bảo toàn độ chính xác số (Decimal Precision):**
   - Giá cổ phiếu và tiền số được xác thực qua lớp `decimal.Decimal` trước khi chuyển đổi, ngăn chặn hiện tượng làm tròn hoặc lỗi tràn số (floating-point representation error).
   - Tuyệt đối không cho phép giá trị `NaN` hoặc `Infinity`.
2. **Không âm thầm thay thế dữ liệu thiếu (No Silent Coercion):**
   - Nếu bất kỳ trường bắt buộc nào (`open`, `high`, `low`, `close`, `timestamp`) bị thiếu hoặc mang giá trị `None`, hệ thống lập tức ném ngoại lệ `NormalizationError` kèm mã lý do (VD: `ERR_MISSING_OHLC`, `ERR_MISSING_TIMESTAMP`).
   - Tuyệt đối không tự động gán giá trị bằng `0` nếu không có ý nghĩa nghiệp vụ cụ thể.
3. **Phân biệt nguồn gốc (Provenance Labeling):**
   - Mọi bản ghi chuẩn hóa đều mang thuộc tính `provenance`:
     - `NATURAL_RUNTIME`: Thu thập từ luồng streaming thực tế qua Redpanda.
     - `HISTORICAL_BACKFILL`: Đọc từ kho lưu trữ lịch sử hoặc Alpaca Read-Only API.
     - `FIXTURE`: Nạp từ tệp kiểm thử cô lập (mock dataset).
   - Giúp hệ thống tự động nhận diện và ngăn chặn việc ghi dữ liệu backfill vào topic thị trường trực tuyến.
