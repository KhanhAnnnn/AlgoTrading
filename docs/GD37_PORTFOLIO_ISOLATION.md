# GĐ37 — SIMULATION PORTFOLIO & RISK ISOLATION

**Dự án:** AlgoTrading V2.0  
**Giai đoạn:** GĐ37  
**Module:** `libs/bot/multibot/isolation.py` & `libs/bot/portfolio/manager.py`

---

## 1. Nguyên tắc Bất biến: Vốn Ảo Độc lập, Không Hòa trộn

Tất cả các tài khoản mô phỏng thuộc AlgoTrading V2.0 tuân thủ quy tắc bất biến:

> **TUYÊN BỐ MIỄN TRỪ VỐN MÔ PHỎNG:**  
> `INDEPENDENT_VIRTUAL_SIMULATION_CAPITAL_ONLY` — Mỗi bot sở hữu số dư tiền mặt ảo độc lập, sức mua riêng, và danh mục vị thế riêng. Số dư vốn ảo này không được hòa trộn, không dùng chung để ký quỹ chéo, và không đại diện cho tài khoản live nào.

---

## 2. Kiểm chứng Cô lập Hai Bot Giao dịch Cùng Một Symbol

Trường hợp Bot 1 (`bot_alpha`) và Bot 2 (`bot_beta`) cùng giao dịch mã cổ phiếu `NVDA`:

```
+---------------------------------------------+---------------------------------------------+
| Bot Alpha (bot_id="bot_alpha")              | Bot Beta (bot_id="bot_beta")                |
+---------------------------------------------+---------------------------------------------+
| Vốn khởi đầu: $100,000                      | Vốn khởi đầu: $50,000                       |
| Vị thế NVDA: 10 cổ phiếu @ $140.00         | Vị thế NVDA: 0 cổ phiếu                     |
| Tiền mặt khả dụng: $98,600.00               | Tiền mặt khả dụng: $50,000.00               |
| Giá trị thị trường: $1,400.00               | Giá trị thị trường: $0.00                   |
| Tổng tài sản (Equity): $100,000.00          | Tổng tài sản (Equity): $50,000.00           |
| Sổ lệnh (OrderStore): Sổ lệnh riêng Alpha   | Sổ lệnh (OrderStore): Sổ lệnh riêng Beta    |
| Sổ khớp (FillStore): Sổ khớp riêng Alpha    | Sổ khớp (FillStore): Sổ khớp riêng Beta     |
+---------------------------------------------+---------------------------------------------+
```

### Kết quả Kiểm định Thực tế:
- Khi Bot Alpha gửi lệnh mua 10 NVDA và khớp lệnh, tiền mặt của Bot Alpha bị trừ, vị thế NVDA của Bot Alpha tăng lên 10.
- Số dư tiền mặt, sức mua và sổ vị thế của Bot Beta **hoàn toàn giữ nguyên ở mức $50,000 và 0 NVDA**.
- Không có bất kỳ sự rò rỉ (cross-contamination) trạng thái giao dịch nào giữa hai bot.

---

## 3. Cô lập Hạn mức Rủi ro (Risk Limits Isolation)

Mỗi bot sở hữu `RiskConfig` riêng biệt:
- Bot A (chiến lược Conservative): `max_drawdown_pct = 0.05` (chặn khi sụt giảm 5%).
- Bot B (chiến lược Aggressive): `max_drawdown_pct = 0.30` (chặn khi sụt giảm 30%).

Nếu thị trường biến động mạnh khiến Bot A chạm ngưỡng sụt giảm 5%:
- Chỉ riêng Bot A bị khóa mở vị thế mới hoặc chuyển sang trạng thái dừng bảo vệ.
- Bot B tiếp tục vận hành bình thường mà không bị ảnh hưởng bởi quyết định rủi ro của Bot A.
