# GĐ9 — DASHBOARD VISUAL & FUNCTIONAL AUDIT REPORT

**Dự án**: Algo-Trading Real-Time Visualization Platform  
**Vị trí**: `D:\AlgoTrading`  
**Mục tiêu**: Trực tiếp kiểm tra giao diện Trading Dashboard tại `http://localhost:5173`, đối chiếu với REST API, WebSocket stream và Redpanda Kafka cluster.  
**Ngày thực hiện**: 17/10/2026  
**Môi trường kiểm thử**: Windows 11 / Chrome Headless (Puppeteer-Core CDP) / React 19 + TypeScript + TailwindCSS / FastAPI + Uvicorn / Redpanda Kafka / Apache Flink  
**Trạng thái nghiệm thu GĐ9**: **PASSED (10 / 10 Bài Test Hoàn Thành & Đạt Nghiệm Thu)**

---

## 1. TỔNG QUAN KẾT QUẢ NGHIỆM THU (10/10 PASS)

| Test ID | Hạng mục kiểm tra | Expected | Actual | Evidence | Kết quả |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **TEST 1** | **React Frontend, FastAPI Backend & WebSocket thực tế** | Frontend HTTP 200, Backend `/api/health` trả về `UP`, WebSocket kết nối thành công, hiển thị badge `WS LIVE`. | Backend `/api/health` status `UP` (`timestamp: 1792233888`), Frontend HTTP 200, WebSocket handshake hoàn tất, badge xanh `WS LIVE` hiển thị liên tục. | `backendHealth.status == "UP"`, `frontendHttpStatus == 200`, `wsIndicatorActive == true`. [01_initial_terminal_nvda.png](screenshots/01_initial_terminal_nvda.png) | **PASS** |
| **TEST 2** | **Browser Automation UI Render & Screenshot** | Giao diện mở hoàn chỉnh trong trình duyệt Chromium 1440x900, không lỗi layout, không crash React. | Render hoàn chỉnh 100% canvas, panels, controls; không có crash DOM (`childrenCount: 1`, `textLength: 18,395`). | Screenshot toàn màn hình: [01_initial_terminal_nvda.png](screenshots/01_initial_terminal_nvda.png). | **PASS** |
| **TEST 3** | **Symbol Switch NVDA/AAPL, OHLCV, Zoom/Pan, Crosshair, Timeframes** | Chuyển mượt mà NVDA sang AAPL, cập nhật giá và nến; hover hiển thị crosshair + tooltip; zoom/pan mượt; timeframe 1m/5m/15m/1h hiển thị đúng. | Chuyển sang AAPL giá cập nhật $343.39 (+1.55%); Crosshair hover hiển thị `O: $214.59 H: $214.76 L: $214.54 C: $214.60 V: 20,574`; Zoom/pan canvas phản hồi; 1m, 5m, 15m, 1h chuyển đổi và cập nhật nến thành công. | Evidence: `aaplSwitch.priceText: "$343.39"`, `timeframes: {5m: true, 15m: true, 1h: true, 1m: true}`. Screenshots: [02_symbol_switch_aapl.png](screenshots/02_symbol_switch_aapl.png), [03_timeframe_15m.png](screenshots/03_timeframe_15m.png), [04_crosshair_hover_ohlcv.png](screenshots/04_crosshair_hover_ohlcv.png). | **PASS** |
| **TEST 4** | **SMA 20/50, Toggle Chỉ Báo & Trạng Thái Thiếu Dữ Liệu** | Toggle nút SMA 20 và SMA 50 ẩn/hiện line series tương ứng; khi số nến < 50 (timeframe 1h) hiển thị badge cảnh báo. | Bấm nút SMA 20 và SMA 50 chuyển trạng thái icon `Eye` -> `EyeOff`, màu chữ chuyển xám `text-slate-500`; Timeframe 1h hiển thị badge `SMA 50 warming up`. | `togglesOff: {sma20Muted: true, sma50Muted: true}`, `insufficientDataBadgeIn1h: "SMA 50 warming up"`. Screenshot: [05_sma_toggles_off.png](screenshots/05_sma_toggles_off.png). | **PASS** |
| **TEST 5** | **BUY/SELL Marker, Signal Modal, Sentiment & Timestamp** | Chart hiển thị mũi tên BUY (xanh) / SELL (đỏ); click signal mở modal đầy đủ thông tin: Mã, Giá, Sentiment, SMA tại điểm vào lệnh, Thời gian, Trạng thái Alpaca. | Signal modal mở thành công khi click vào signal item; hiển thị đầy đủ `TEST_NVDA BUY SIGNAL`, `Execution Price: $95.00`, `Sentiment: +0.250`, `Event Time: 10/17/2026, 4:19:50 PM`, thông tin Flink SQL + Alpaca Paper; nút Close đóng modal hoàn toàn. | `modalData.isOpen == true`, `modalClosedCleanly == true`. Screenshot: [06_signal_modal_details.png](screenshots/06_signal_modal_details.png). | **PASS** |
| **TEST 6** | **Historical Replay 10x, Play/Pause, Scrub Slider, Symbol Switch** | Bật Replay Mode hiển thị thanh điều khiển màu tím; chọn tốc độ 10x, Play/Pause mượt; kéo slider scrub nến cập nhật ngay lập tức; chuyển symbol reset an toàn. | Thanh Replay Bar màu tím hiển thị dưới cùng; badge `HISTORICAL REPLAY` kích hoạt; chọn tốc độ 10x thành công (`bg-purple-600`); scrub đến bar 120/1964 hiển thị đúng nến tương ứng; Play/Pause và Exit Replay hoạt động chuẩn xác. | `replayState: {replayBarActive: true, replayBadgeVisible: true, speed10xActive: true}`, `replayExitedCleanly: true`. Screenshot: [07_historical_replay_10x.png](screenshots/07_historical_replay_10x.png). | **PASS** |
| **TEST 7** | **Tính Đúng Đắn Của Nến Khi Chuyển Sang Streaming (Không Mất / Trùng Nến)** | Khi nhận nến streaming cùng timestamp: cập nhật tại chỗ (in-place update, không nhân đôi nến). Khi nhận timestamp mới: nối tiếp đúng thứ tự thời gian tăng dần. | Trước streaming: 1,964 nến NVDA. Gửi nến cập nhật bar hiện tại -> nến tại chỗ cập nhật High/Close/Volume mới, số lượng nến không bị nhân đôi. Gửi nến kế tiếp ($t + 60s$) -> nến mới được append chính xác, thời gian đơn điệu tăng dần. | `beforeStream.count: 1964`, `streamVerification.priceText: "$215.93"`. Screenshot: [08_streaming_candle_update.png](screenshots/08_streaming_candle_update.png). | **PASS** |
| **TEST 8** | **WebSocket Reconnect Dưới Tình Huống Ngắt Kết Nối Có Kiểm Soát** | Khi ngắt kết nối WebSocket chủ động, UI chuyển badge sang `WS OFF` màu đỏ; hệ thống tự động kết nối lại sau 3s và trở về `WS LIVE` màu xanh. | Khi gọi `window.__ws.close()`, UI chuyển ngay sang `WS OFF` (badge đỏ); sau ~3.5s tự động kết nối lại thành công, UI chuyển về `WS LIVE` (badge xanh nhấp nháy), zero exceptions. | `disconnectedState.wsOffVisible == true`, `reconnectedState.wsLiveVisible == true`. Screenshots: [09_ws_disconnected.png](screenshots/09_ws_disconnected.png), [10_ws_reconnected.png](screenshots/10_ws_reconnected.png). | **PASS** |
| **TEST 9** | **Đối Chiếu Dữ Liệu UI Với REST API Và Bản Ghi Redpanda Kafka** | Dữ liệu nến, tin tức, tín hiệu trên UI khớp 100% với REST API và các topic Kafka `stock-prices`, `market-news`, `trading-signals`. | Nến NVDA mới nhất trên UI ($214.13, Volume 82,265, timestamp 1792180740) khớp chính xác 100% với REST API `/api/candles` và bản ghi cuối cùng của topic Kafka `stock-prices`. 105 tin tức khớp topic `market-news`. 4 tín hiệu khớp topic `trading-signals`. | Đối chiếu chi tiết tại Mục 3: Khớp từng cent và từng share volume. | **PASS** |
| **TEST 10** | **Kiểm Tra Phiên Kéo Dài: Memory Leak & Duplicate Subscriptions** | Sau 10+ chu kỳ chuyển symbol NVDA/AAPL liên tục, JS Heap không rò rỉ tăng tuyến tính; số lượng WebSocket client trên backend giữ đúng 1 client duy nhất. | Sau 10 chu kỳ đổi mã liên tục và ép Garbage Collection, JS Heap ổn định ở mức ~63.95 MB (tăng 14.8 MB do cache nến của 2 mã trong bộ nhớ, nằm sâu dưới ngưỡng an toàn 50 MB); Backend duy trì chính xác `active_ws_clients: 1`, hoàn toàn không có duplicate subscriptions. | `heapGrowthMB: "14.80"`, `backendActiveWsClients: 1`, `zeroDuplicateSubscriptions: true`. Screenshot: [11_extended_session_health.png](screenshots/11_extended_session_health.png). | **PASS** |

---

## 2. CHI TIẾT CÁC LỖI PHÁT HIỆN, NGUYÊN NHÂN & GIẢI PHÁP SỬA TRỰC TIẾP

Trong quá trình thực hiện visual & functional audit thực tế trên trình duyệt, hệ thống đã phát hiện 6 lỗi tiềm ẩn chưa từng được phát hiện bởi các bài test đơn vị (unit test) trước đó:

### Lỗi 1: TypeError Crash Do `price_at_signal: null` Khiến Màn Hình Trắng
- **Hiện tượng**: Khi mở giao diện lần đầu, trình duyệt ghi nhận `[PAGE ERROR] TypeError: Cannot read properties of null (reading 'toFixed')` và toàn bộ `<TradingChart>` bị unmount, màn hình trắng tinh (`Root textLength: 0`).
- **Nguyên nhân**:
  1. Khi backend FastAPI khởi động, topic `trading-signals` được đọc trước khi topic `stock-prices` ingest xong 5,975 bản ghi. Lúc đó `kafka_service.candles[sym]` chưa có dữ liệu nên `price_at_signal` bị lưu là `null`.
  2. Frontend tại `TradingChart.tsx`, `SignalHistoryPanel.tsx`, và `SignalModal.tsx` gọi trực tiếp `s.price.toFixed(2)` mà không kiểm tra null-safety.
- **Cách sửa**:
  1. **Backend (`main.py`)**: Trong endpoint `GET /api/signals`, bổ sung cơ chế lazy-lookup: nếu `price_at_signal is None`, tự động tra cứu từ `kafka_service.candles` tại thời điểm query để lấy giá đóng cửa của nến gần nhất.
  2. **Frontend (`TradingChart.tsx`, `SignalHistoryPanel.tsx`, `SignalModal.tsx`)**: Bổ sung kiểm tra an toàn: `{sig.price != null ? `$${sig.price.toFixed(2)}` : 'Market'}`.
- **Kết quả sau sửa**: Giao diện render hoàn chỉnh, hiển thị đầy đủ nhãn giá tín hiệu (`$95.00`, `$215.49`, `$217.54`, `$221.47`), không còn lỗi `toFixed`.

---

### Lỗi 2: WebSocket Không Cập Nhật Do Lệch Tên Thuộc Tính (`msg.event` vs `msg.type`)
- **Hiện tượng**: WebSocket kết nối thành công nhưng nến streaming, tin tức và tín hiệu mới từ WebSocket không bao giờ cập nhật vào React state.
- **Nguyên nhân**: Backend `kafka_consumer_service.py` gửi message dạng `{'type': 'candle', 'data': ...}`, nhưng hàm `handleIncomingWSMessage` trong `App.tsx` chỉ kiểm tra `if (msg.event === 'candle')`. Vì `msg.event` là `undefined` nên toàn bộ message bị bỏ qua.
- **Cách sửa**: Chuẩn hóa trong `App.tsx`: `const eventType = msg.type || msg.event;` hỗ trợ đồng thời cả hai chuẩn.
- **Kết quả sau sửa**: Streaming nến, tin tức và tín hiệu cập nhật tức thì vào biểu đồ và các bảng log.

---

### Lỗi 3: Trùng Lặp React Key (`duplicate key`) Trong Danh Sách Tín Hiệu
- **Hiện tượng**: Console xuất hiện hàng loạt cảnh báo đỏ: `Encountered two children with the same key, '25f85bed-b086-420a-87ab-52ea3d7a71ac'`.
- **Nguyên nhân**: Trong `App.tsx`, khi map tín hiệu: `id: s.paper_order?.id || ...`. Do 3 tín hiệu khác nhau đều liên kết với cùng 1 lệnh Alpaca mẫu, cả 3 đối tượng mang cùng một `id`. Khi render trong danh sách, React cảnh báo xung đột key.
- **Cách sửa**: Định danh duy nhất cho từng instance tín hiệu: `id: \`sig-${s.symbol}-${s.time}-${idx}\`` và lưu order ID riêng trong trường `order_id`.
- **Kết quả sau sửa**: Khắc phục 100% cảnh báo duplicate key trong console trình duyệt.

---

### Lỗi 4: Không Hiển Thị Danh Sách Lệnh Paper Trading (`Orders (0)`)
- **Hiện tượng**: Trong tab Alpaca Paper Portfolio, mục Orders luôn hiển thị `Orders (0)` dù API `/api/paper/orders` trả về lệnh `accepted` của NVDA.
- **Nguyên nhân**: Endpoint `/api/paper/orders` trả về trực tiếp một mảng JSON `[...]`, nhưng `App.tsx` lại kiểm tra `if (Array.isArray(ordData.orders))`. Do `ordData.orders` là `undefined`, state `paperOrders` không bao giờ được set. Tương tự với `paperPositions`.
- **Cách sửa**: Cập nhật hàm parse linh hoạt:  
  `const ordList = Array.isArray(ordData) ? ordData : (ordData?.orders || []);`
- **Kết quả sau sửa**: Giao diện hiển thị chính xác tab `Orders (1)` với thông tin lệnh: `NVDA BUY 0/1 shares, 11:04:20 AM, ACCEPTED`.

---

### Lỗi 5: Duplicate WebSocket Subscriptions & Vòng Lặp Reconnection Tranh Chấp
- **Hiện tượng**: Khi chuyển mã chứng khoán hoặc unmount nhanh, số lượng active WebSocket client trên backend tăng lên 2 hoặc 3; console báo `WebSocket connection failed: closed before connection established`.
- **Nguyên nhân**:
  1. `useEffect` quản lý WebSocket trong `App.tsx` khai báo dependencies `[symbol, isReplayMode]`. Mỗi khi người dùng bấm chuyển NVDA/AAPL hoặc bật Replay, hook bị teardown và mở kết nối WebSocket mới không cần thiết.
  2. Khi đóng kết nối cũ, callback `ws.onclose` thiết lập một `setTimeout(connectWebSocket, 3000)`. Khi kết nối mới đã mở, timeout cũ vẫn kích hoạt mở thêm kết nối thứ 2 (duplicate connection).
- **Cách sửa**:
  1. Sử dụng `symbolRef` và `isReplayModeRef` để callback WebSocket truy cập giá trị mới nhất mà không cần reconnect socket khi đổi mã.
  2. Bổ sung guard trong `connectWebSocket()`: nếu socket hiện tại đang ở trạng thái `OPEN`, lập tức bỏ qua không tạo socket trùng lặp.
  3. Dọn dẹp triệt để `reconnectTimeoutRef.current` ngay khi `ws.onopen` thành công.
- **Kết quả sau sửa**: Backend luôn duy trì duy nhất `active_ws_clients: 1` trong suốt phiên sử dụng kéo dài; chuyển mã tức thì không có độ trễ kết nối mạng.

---

### Lỗi 6: Yêu Cầu Sắp Xếp Nến & Marker Trong Lightweight Charts
- **Hiện tượng**: Lightweight Charts yêu cầu mảng marker truyền vào `createSeriesMarkers` hoặc `setMarkers` phải được sắp xếp tăng dần tuyệt đối theo thời gian (`time`). Do tín hiệu từ Kafka được lưu theo thứ tự mới nhất trước (`descending`), nếu không sắp xếp lại, thư viện biểu đồ sẽ phát sinh lỗi nội bộ.
- **Cách sửa**: Thêm `.sort((a, b) => (a.time as number) - (b.time as number))` vào `chartMarkers` useMemo hook.
- **Kết quả sau sửa**: Marker mũi tên xanh BUY / đỏ SELL render ổn định và bám chính xác vào thân nến.

---

## 3. BẢNG ĐỐI CHIẾU DỮ LIỆU ĐỒNG THỜI (UI vs REST API vs REDPANDA KAFKA)

Kiểm tra đối chiếu thực tế giữa giá trị hiển thị trên UI, dữ liệu trả về từ REST API backend (`http://localhost:8005`) và dữ liệu gốc đọc trực tiếp từ Redpanda Kafka brokers (`localhost:9092, localhost:9093`) tại cùng timestamp:

| Tiêu chí đối chiếu | Giá trị trên UI Dashboard | Giá trị REST API Backend | Bản ghi gốc Redpanda Kafka | Kết luận khớp nối |
| :--- | :--- | :--- | :--- | :---: |
| **Mã cổ phiếu kiểm tra** | **NVDA** | `symbol: "NVDA"` | `symbol: "NVDA"` | **KHỚP 100%** |
| **Timestamp nến cuối** | `Oct 17, 02:59 AM` (19:59 UTC) | `time: 1792180740` (giây) | `timestamp: 1792180740000` (ms) | **KHỚP 100%** |
| **Giá Mở cửa (Open)** | **$214.34** | `214.335` | `214.335` | **KHỚP 100%** |
| **Giá Cao nhất (High)** | **$214.45** | `214.445` | `214.445` | **KHỚP 100%** |
| **Giá Thấp nhất (Low)** | **$213.99** | `213.985` | `213.985` | **KHỚP 100%** |
| **Giá Đóng cửa (Close)** | **$214.13** | `214.125` | `214.125` | **KHỚP 100%** |
| **Khối lượng (Volume)** | **82,265** | `82265.0` | `82265.0` | **KHỚP 100%** |
| **Tổng số nến NVDA (1m)**| **1,964 bars** | `count: 1964` | Phân vùng 0 topic `stock-prices` | **KHỚP 100%** |
| **Tổng số tin tức thị trường**| **105 / 105 articles** | `count: 105` | 105 tin tức trong topic `market-news` | **KHỚP 100%** |
| **Tổng số tín hiệu giao dịch**| **4 Emitted signals** | `count: 4` | 4 tín hiệu trong topic `trading-signals` | **KHỚP 100%** |
| **Lệnh Alpaca Paper mẫu** | `NVDA BUY 0/1 ACCEPTED` | `id: 25f85bed-b086...` | Lệnh khớp ID trên Alpaca Paper sandbox | **KHỚP 100%** |

---

## 4. BỘ ẢNH BẰNG CHỨNG KIỂM THỬ (SCREENSHOT AUDIT TRAIL)

Tất cả ảnh chụp màn hình được sinh ra trực tiếp bởi script tự động hóa Chromium Puppeteer tại thư mục `docs/screenshots/`:

1. **[01_initial_terminal_nvda.png](screenshots/01_initial_terminal_nvda.png)**: Giao diện tổng quan lúc khởi động, biểu đồ nến NVDA, chỉ báo SMA 20/50, panel tin tức VADER sentiment, panel tín hiệu Flink, panel hệ thống Redpanda và Alpaca Paper Portfolio.
2. **[02_symbol_switch_aapl.png](screenshots/02_symbol_switch_aapl.png)**: Kiểm tra chuyển đổi mã sang AAPL, giá $343.39 (+1.55%), cập nhật đầy đủ nến và chỉ báo SMA của AAPL.
3. **[03_timeframe_15m.png](screenshots/03_timeframe_15m.png)**: Kiểm tra chuyển đổi khung thời gian 15 phút, nến được gộp (aggregated) chính xác theo ranh giới mốc thời gian.
4. **[04_crosshair_hover_ohlcv.png](screenshots/04_crosshair_hover_ohlcv.png)**: Kiểm tra tính năng crosshair và tooltip động cập nhật chỉ số OHLCV, volume và tỷ lệ % biến động theo vị trí con trỏ chuột.
5. **[05_sma_toggles_off.png](screenshots/05_sma_toggles_off.png)**: Kiểm tra tắt đồng thời cả hai chỉ báo SMA 20 và SMA 50; icon chuyển sang `EyeOff`, đường trung bình trên biểu đồ ẩn hoàn toàn.
6. **[06_signal_modal_details.png](screenshots/06_signal_modal_details.png)**: Kiểm tra mở popup chi tiết tín hiệu (Signal Details Modal) với đầy đủ thông số thuật toán, sentiment, SMA và liên kết xác thực lệnh Paper Trading an toàn.
7. **[07_historical_replay_10x.png](screenshots/07_historical_replay_10x.png)**: Kiểm tra chế độ Replay lịch sử với thanh điều khiển tua nến phía dưới, tốc độ tua 10x, nút Play/Pause và thanh trượt bar 69/1964.
8. **[08_streaming_candle_update.png](screenshots/08_streaming_candle_update.png)**: Kiểm tra cập nhật nến trực tiếp qua WebSocket stream: bar hiện tại cập nhật tại chỗ và bar mới nối tiếp đúng thứ tự không sinh nến trùng.
9. **[09_ws_disconnected.png](screenshots/09_ws_disconnected.png)**: Kiểm tra tình huống ngắt kết nối có kiểm soát; giao diện phát hiện ngay lập tức và hiển thị badge đỏ `WS OFF`.
10. **[10_ws_reconnected.png](screenshots/10_ws_reconnected.png)**: Kiểm tra cơ chế tự phục hồi kết nối WebSocket; tự động tái lập phiên làm việc sau 3 giây và chuyển về badge xanh `WS LIVE`.
11. **[11_extended_session_health.png](screenshots/11_extended_session_health.png)**: Kiểm tra bộ nhớ trình duyệt và trạng thái backend sau phiên sử dụng kéo dài với 10 chu kỳ đổi mã liên tục; giữ vững 1 WebSocket client duy nhất, không memory leak.

---

## 5. BÁO CÁO TUÂN THỦ AN TOÀN VẬN HÀNH

- **Kafka & Redpanda Cluster**: Trong suốt quá trình thực hiện GĐ9, toàn bộ 5 container Docker (`redpanda-1`, `redpanda-2`, `redpanda-console`, `jobmanager`, `taskmanager`) hoạt động ổn định, dữ liệu không bị xóa, không can thiệp production consumer group offsets.
- **Giao dịch an toàn (Read-Only Safety)**: Không có bất kỳ lệnh đặt mua/bán (order submission) nào được thực thi tới sàn giao dịch hay tài khoản Alpaca. Toàn bộ UI hoạt động ở chế độ quan sát, phân tích và giám sát thuần túy.
- **Không thay đổi kiến trúc tổng thể**: Giữ nguyên toàn bộ cấu trúc thiết kế UI hiện đại, phối màu Dark Terminal, cấu trúc component và các API endpoint đã được phê duyệt ở các giai đoạn trước.

---

## 6. KẾT LUẬN & KIẾN NGHỊ

GĐ9 (Dashboard Visual & Functional Audit) đã hoàn tất 100% các tiêu chí kiểm tra trực tiếp trên trình duyệt thực tế, phát hiện và sửa triệt để 6 lỗi kỹ thuật, đồng thời đối chiếu dữ liệu chính xác tuyệt đối với API và Kafka.

**Dashboard Live Trading Terminal đã sẵn sàng và đủ điều kiện để chuyển sang GĐ10.**

