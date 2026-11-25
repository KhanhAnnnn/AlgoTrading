# GĐ27: Production Web Serving Architecture & Hardening

**Repository:** `D:\AlgoTrading`  
**Release:** `v1.0.0`  
**Phase:** GĐ27 — Production Deployment Hardening & Disaster Recovery Validation  
**Status:** `VERIFIED — PRODUCTION_DEPLOYED`  
**Evaluation Timestamp:** `2026-10-31T22:33:00+07:00`

---

## 1. Bối cảnh & Mục tiêu Kiến trúc Phục vụ Web

Trong các giai đoạn phát triển ban đầu, Vite Preview (cổng `4173`) được dùng để tạm thời kiểm tra bản build cục bộ. Theo yêu cầu chuẩn hóa của GĐ27, hệ thống loại bỏ sự phụ thuộc vào Vite Preview cho môi trường sản xuất chính thức, thiết lập một máy chủ phục vụ tĩnh chuẩn mực (Production Static Web Server) tương thích hoàn hảo với môi trường Windows/Node.js, hỗ trợ SPA routing fallback, endpoints kiểm tra sức khỏe độc lập và các tiêu chuẩn bảo mật HTTP nghiêm ngặt.

---

## 2. Ma trận Phân cấp 3 Tầng Máy chủ Web (Three-Tier Web Serving Hierarchy)

| Thuộc tính | Tầng 1: Development Server | Tầng 2: Local Preview Server | Tầng 3: Production Web Server |
| :--- | :--- | :--- | :--- |
| **URL Truy cập** | `http://localhost:5173` | `http://localhost:4173` | `http://localhost:3000` |
| **Công cụ / Daemon** | Vite Dev Server (HMR) | Vite Preview (`vite preview`) | Native Node.js Production HTTP Server |
| **Mục đích Sử dụng** | Lập trình viên phát triển UI | Kiểm tra nhanh bản build cục bộ | **Phục vụ người dùng & vận hành chính thức** |
| **Source Bundle** | TypeScript raw source transpiled | `trading-dashboard/frontend/dist` | `trading-dashboard/frontend/dist` |
| **SPA Fallback** | Vite internal rewrite | Vite internal preview | **Tự động phục vụ `index.html` cho mọi deep route** |
| **Health Check** | Không có (Chỉ có WebSocket) | Không có | **Endpoint `/healthz` & `/api/prod-server/health`** |
| **Security Headers** | Cơ bản | Cơ bản | **`nosniff`, `SAMEORIGIN`, `strict-origin`** |
| **Cơ chế Điều khiển** | `npm run dev` | `npm run preview` | **[scripts/start_prod_web.ps1](file:///d:/AlgoTrading/scripts/start_prod_web.ps1) & [scripts/stop_prod_web.ps1](file:///d:/AlgoTrading/scripts/stop_prod_web.ps1)** |

---

## 3. Kiến trúc Chi tiết Production Web Server (`scripts/prod_web_server.mjs`)

Máy chủ web sản xuất được xây dựng dưới dạng module ES native [scripts/prod_web_server.mjs](file:///d:/AlgoTrading/scripts/prod_web_server.mjs) với các tính năng cốt lõi:

1. **Zero External Dependencies:** Tận dụng thư viện tiêu chuẩn của Node.js (`node:http`, `node:fs`, `node:path`, `node:url`), loại trừ rủi ro lỗ hổng chuỗi cung ứng (supply chain risks).
2. **SPA Routing Fallback:** Khi người dùng truy cập trực tiếp các đường dẫn như `/workbench`, `/analytics`, `/overview`, hoặc làm mới trang (refresh F5), máy chủ tự động trả về `dist/index.html` với mã trạng thái `200 OK` thay vì ném lỗi `404 Not Found`.
3. **MIME Types & Caching Policy:**
   - Các asset có gắn mã băm trong `dist/assets/` (`*.js`, `*.css`): Gán header `Cache-Control: public, max-age=31536000, immutable`.
   - File `index.html`: Gán header `Cache-Control: no-cache, must-revalidate` để đảm bảo client luôn nhận phiên bản mới nhất sau khi cập nhật.
4. **Phòng chống Path Traversal Attacks:** Chuẩn hóa đường dẫn bằng `path.normalize()` và kiểm tra tiền tố `filePath.startsWith(DIST_DIR)`, chặn đứng các request chứa `../` với mã `403 Forbidden`.
5. **Đóng tiến trình có kiểm soát (Graceful Shutdown):** Lắng nghe các tín hiệu `SIGINT` và `SIGTERM`, đóng các kết nối đang mở trước khi thoát.

---

## 4. Kiểm chứng Endpoint Sức khỏe (`GET /healthz`)

Endpoint giám sát độc lập `http://localhost:3000/healthz` cung cấp thông tin trạng thái theo định dạng JSON chuẩn:

```json
{
  "status": "HEALTHY",
  "server": "AlgoTrading Production Web Server",
  "version": "v1.0.0",
  "mode": "PRODUCTION",
  "port": 3000,
  "host": "0.0.0.0",
  "dist_dir": "d:\\AlgoTrading\\trading-dashboard\\frontend\\dist",
  "spa_fallback": true,
  "uptime_seconds": 124,
  "timestamp": "2026-10-31T15:31:25.000Z"
}
```

---

## 5. Quy trình Vận hành Khởi động và Dừng

### Khởi động (Startup):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_prod_web.ps1 -Port 3000 -HostAddress "0.0.0.0"
```
- Tự động kiểm tra xung đột cổng trước khi khởi động.
- Lưu trữ Process ID vào `logs/prod_web_server.pid`.
- Chuyển hướng stdout/stderr sang `logs/prod_web_server.log`.

### Dừng (Shutdown):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop_prod_web.ps1
```
- Đọc PID từ `logs/prod_web_server.pid` và ra lệnh dừng tiến trình có kiểm soát.
- Dọn dẹp PID file an toàn.

