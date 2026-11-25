# GĐ37 — RESOURCE ISOLATION & CONCURRENCY POLICY

**Dự án:** AlgoTrading V2.0  
**Giai đoạn:** GĐ37  
**Module:** `libs/bot/multibot/resource_policy.py` & `libs/bot/multibot/isolation.py`

---

## 1. Giới hạn Tài nguyên & Chính sách Concurrency

Để đảm bảo hiệu năng và tính ổn định khi chạy nhiều Paper Trading Bot mô phỏng, `ResourcePolicy` áp đặt các hạn mức nghiêm ngặt:

| Tham số | Giá trị Mặc định | Ý nghĩa & Hành vi Khi Vượt Ngưỡng |
| :--- | :--- | :--- |
| `max_concurrent_bots` | 10 | Số lượng bot tối đa được phép ở trạng thái `RUNNING`/`PAUSED`. Khi đạt 10, lệnh start bot thứ 11 sẽ bị từ chối với lỗi `ConcurrencyLimitExceededError`. |
| `max_queue_size_per_bot` | 1000 | Độ sâu tối đa hàng đợi nến 1m của từng bot. Khi đầy, nến mới bị drop mà không làm gián đoạn bot khác. |
| `max_processing_lag_seconds` | 300.0s | Độ trễ xử lý tối đa cho phép trước khi đánh dấu bot bị degraded. |
| `shutdown_timeout_seconds` | 5.0s | Thời gian tối đa chờ bot dừng các lệnh working trước khi hoàn tất dừng hệ thống. |
| `max_memory_budget_mb` | 1024.0 MB | Ngân sách bộ nhớ RAM phân bổ cho toàn bộ runtime mô phỏng. |
| `max_symbols_per_bot` | 20 | Số lượng symbol tối đa một bot có thể đăng ký đồng thời. |

---

## 2. Cô lập Tài nguyên Lưu trữ (Storage Isolation)

Mỗi bot session được cấp phát cây thư mục riêng biệt theo quy chuẩn:

$$\text{Path} = \text{data/paper\_bot/bots/}\{bot\_id\}\text{/sessions/}\{session\_id\}\text{/}$$

```
data/paper_bot/
├── registry/
│   └── bots.json                       <-- Danh mục cấu hình BotDefinition
├── sessions/
│   └── {session_id}.json               <-- Hồ sơ tổng hợp phiên BotSession
└── bots/
    └── {bot_id}/
        └── sessions/
            └── {session_id}/
                ├── orders/             <-- Sổ lệnh OrderStore riêng của bot
                ├── fills/              <-- Sổ khớp lệnh FillStore riêng của bot
                ├── checkpoints/        <-- Checkpoints riêng với mã hash SHA-256
                ├── journal/            <-- Append-only Event Journal riêng
                └── ledger.jsonl        <-- Execution Ledger riêng
```

---

## 3. Cơ chế Khởi tạo Sandbox Độc lập (`BotSandboxFactory`)

Khi supervisor khởi động một bot, `BotSandboxFactory` thực hiện:
1. Tạo định danh duy nhất: `session_id = sess_{bot_id}_{uuid}`.
2. Khởi tạo instance độc lập của:
   - `SimulationPortfolioManager` với ID riêng `port_{bot_id}_{session_id}`.
   - `SimulationBroker` với `OrderStore` và `FillStore` trỏ đến thư mục của bot.
   - `StrategyExecutionEngine` độc lập, tránh chia sẻ bộ nhớ stateful indicators.
   - `SignalDecisionEngine` với cấu hình rủi ro riêng biệt.
   - `BotCheckpointManager` và `BotEventJournal`.
3. Kết nối toàn bộ vào `BotOrchestrator` chuyên biệt cho phiên đó.
