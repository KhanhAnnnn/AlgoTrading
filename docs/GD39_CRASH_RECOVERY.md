# GĐ39 — CONTROLLED CRASH & CHECKPOINT RECOVERY

**Dự án:** AlgoTrading V2.0  
**Giai đoạn:** GĐ39 — End-to-End Integration, Short Soak & Reliability Verification  
**Môi trường:** SIMULATION ONLY  

---

## 1. Động cơ Bơm Lỗi Có Kiểm soát (Fault Injection Engine)

Để kiểm chứng tính bền vững trước sự cố đột ngột của hệ thống mô phỏng, GĐ39 phát triển module `FaultInjectionEngine` cho phép giả lập dừng đột ngột (Simulated Crash) tại 8 điểm can thiệp then chốt trong chu kỳ xử lý:

| STT | Điểm Can thiệp (`FailurePoint`) | Vị trí Trong Chu kỳ Xử lý | Rủi ro Tiềm ẩn Nếu Không Phục hồi Đúng |
| :---: | :--- | :--- | :--- |
| 1 | `AFTER_BAR_RECEIVE` | Ngay sau khi nhận nến 1m | Mất nến, lệch chuỗi chỉ báo |
| 2 | `AFTER_SIGNAL_GENERATE` | Ngay sau khi sinh StrategySignal | Tín hiệu mồ côi (orphaned signal) |
| 3 | `AFTER_INTENT_GENERATE` | Ngay sau khi sinh SimulationOrderIntent | Intent chưa gửi broker |
| 4 | `AFTER_ORDER_CREATE` | Ngay sau khi tạo SimulatedOrder | Lệnh chưa đưa vào sổ lệnh |
| 5 | `AFTER_FILL_SIMULATE` | Ngay sau khi FillEngine tạo SimulatedFill | Khớp lệnh nhưng chưa cập nhật ví |
| 6 | `AFTER_TRANSACTION_APPLY`| Ngay sau khi ghi sổ cái giao dịch | Lệch giữa sổ cái và số dư ví |
| 7 | `BEFORE_CHECKPOINT` | Trước khi ghi Checkpoint nguyên tử | Checkpoint bị thiếu trạng thái mới |
| 8 | `AFTER_CHECKPOINT_BEFORE_COMMIT` | Sau khi lưu Checkpoint nhưng trước commit | Checkpoint dư thừa hoặc sai offset |

---

## 2. Quy trình Khôi phục Trạng thái từ Checkpoint

Khi xảy ra sự cố đột ngột tại bất kỳ điểm nào trong 8 điểm trên:
1. `BotCheckpointManager` tải checkpoint nguyên tử gần nhất được xác thực bằng mã băm SHA-256.
2. `SimulationPortfolioManager` khôi phục số dư tiền mặt, các vị thế mở và nhật ký giao dịch về thời điểm checkpoint.
3. `SimulationBroker` loại bỏ các lệnh chưa hoàn tất hoặc xác thực lại trạng thái khớp lệnh qua `idempotency_key`.
4. `PaperBotConsumer` đặt lại offset tiêu thụ dữ liệu tương ứng với `last_processed_event_id`.

---

## 3. Kết quả Kiểm toán Tính Bền vững

- **Zero Duplicate Fills:** Không có bất kỳ fill trùng lặp nào được tạo ra sau khi bot khởi động lại từ checkpoint.
- **Zero Duplicate Transactions:** Sổ cái giao dịch duy trì tính duy nhất tuyệt đối của các mã định danh giao dịch.
- **Financial Balance Equation Verified:**
  $$\text{Cash} + \text{Cost Basis} + \text{Reserved Cash} = \text{Initial Cash} + \text{Realized PnL} - \text{Total Fees}$$
  Đẳng thức luôn đạt trạng thái `BALANCED` với sai số $\le 10^{-4}$ USD trên toàn bộ 8 kịch bản crash.
