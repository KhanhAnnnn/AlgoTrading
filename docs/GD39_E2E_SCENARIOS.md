# GĐ39 — END-TO-END INTEGRATION SCENARIOS & CAUSATION VERIFICATION

**Dự án:** AlgoTrading V2.0  
**Giai đoạn:** GĐ39 — End-to-End Integration, Short Soak & Reliability Verification  
**Môi trường:** SIMULATION ONLY  
**Trading Mode:** DRY_RUN  

---

## 1. Chuỗi Nhân quả 7 Giai đoạn (7-Stage Causation Chain)

Chuỗi nhân quả từ khi dữ liệu thị trường nến 1m đến khi hoàn tất cập nhật tài khoản mô phỏng được kiểm chứng đầy đủ:

1. **Giai đoạn 1 — Ingestion & Normalization (`PaperBotConsumer`):**
   - Tiếp nhận nến 1m từ Redpanda topic `market.bars.1m`.
   - Kiểm tra `is_final == True`, chuẩn hóa thành `MarketDataEvent`.
2. **Giai đoạn 2 — Strategy Analytical Processing (`StrategyExecutionEngine`):**
   - Cập nhật các chỉ báo kỹ thuật (SMA fast/slow, RSI Wilder/Simple).
   - Phát sinh tín hiệu phân tích `StrategySignal` (BUY/SELL/HOLD).
3. **Giai đoạn 3 — Risk & Portfolio Evaluation (`SignalDecisionEngine`):**
   - Đánh giá tín hiệu với giới hạn vốn, rủi ro tối đa, drawdown limit.
   - Ban hành `SignalDecision` (ACCEPTED hoặc REJECTED kèm reason codes).
4. **Giai đoạn 4 — Simulation Intent Emission (`SignalDecisionEngine`):**
   - Với quyết định ACCEPTED, sinh `SimulationOrderIntent`.
   - Gán `idempotency_key`, `proposed_quantity`, và `proposed_notional`.
5. **Giai đoạn 5 — Order Management & Next-Bar Matching (`SimulationBroker`):**
   - Chuyển `SimulationOrderIntent` thành `SimulatedOrder`.
   - Tuân thủ nghiêm ngặt **Next-Bar Execution Rule**: Khớp lệnh trên nến tiếp theo $T+1$ để loại bỏ hoàn toàn lookahead bias.
6. **Giai đoạn 6 — Execution & Fill Audit (`FillEngine`):**
   - Mô phỏng trượt giá (slippage) và phí giao dịch (commission/fees).
   - Tạo bản ghi khớp lệnh `SimulatedFill`.
7. **Giai đoạn 7 — Portfolio Execution Adapter (`PortfolioExecutionAdapter`):**
   - Khấu trừ tiền mặt mô phỏng, cập nhật vị thế trong `PositionBook`.
   - Ghi nhật ký giao dịch `PortfolioTransactionEvent`, tạo `PortfolioSnapshot`.

---

## 2. Kiểm chứng Correlation ID & Nguồn gốc Dữ liệu (Provenance Tracking)

- Mọi sự kiện dọc theo đường ống đều mang theo mã định danh duy nhất của nến nguồn (`source_bar_key` hoặc `event_id`).
- Lệnh và khớp lệnh phân biệt rõ ràng:
  - `source_bar_key`: Nến phát sinh tín hiệu phân tích ($T$).
  - `execution_bar_key`: Nến thực thi khớp lệnh mô phỏng ($T+1$).
- Khẳng định: $\text{Timestamp}(\text{Execution Bar}) > \text{Timestamp}(\text{Source Bar})$.

---

## 3. Kịch bản E2E Chuẩn (`ReliabilityScenarios.run_e2e_causation_scenario`)

Kịch bản thực thi chuỗi 10 nến 1m liên tiếp với chiến lược `MA_CROSS_1M`:
- Tổng số nến gửi: 10 nến.
- Tín hiệu tạo ra: Được ghi nhận và đánh giá rủi ro đầy đủ.
- Khớp lệnh: Tuân thủ quy tắc Next-Bar.
- Kết quả kiểm toán: `ReconciliationReport.is_balanced == True` (Cân bằng tài chính tuyệt đối).
