# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)
1. **Hardcoded secrets (dòng 17–18):** `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` được ghi thẳng trong mã nguồn → push lên GitHub sẽ bị lộ ngay lập tức.
2. **Không quản lý cấu hình qua biến môi trường (dòng 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` bị hardcode, không tách cấu hình theo môi trường (dev/staging/prod).
3. **Dùng `print()` thay cho structured logging và in cả secret ra log (dòng 33–34, 38):** `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ API key trong log và không thể parse/tìm kiếm bằng log aggregator (Loki, Datadog…).
4. **Thiếu health check / readiness endpoint (`/health`, `/ready`):** Nền tảng cloud/orchestrator không biết tiến trình có còn sống hay đã sẵn sàng nhận traffic chưa để tự restart hoặc định tuyến.
5. **Cố định `host="localhost"`, `port=8000` và bật `reload=True` (dòng 49–54):** Bind vào `localhost` khiến container không nhận được kết nối từ bên ngoài; không đọc biến `PORT` do platform cấp (Railway/Render); `reload=True` gây tốn tài nguyên và không ổn định trên production.
6. **Không có graceful shutdown & không có input validation chặt:** Khi nhận `SIGTERM` tiến trình tắt đột ngột, dễ cắt ngang request đang xử lý.

### Exercise 1.2: Kết quả chạy bản develop
Lệnh gọi (theo lưu ý K5, bản develop nhận `question` qua query param):
```bash
curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"
```
Output thực tế:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:05:26 GMT
server: uvicorn
content-length: 95
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 1.3: So sánh Develop vs Production (`01-localhost-vs-production/`)
| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode trực tiếp trong code (`OPENAI_API_KEY`, `DATABASE_URL`, `port=8000`, dòng 17–18, 52) | Đọc từ biến môi trường qua `config.settings` (`settings.host`, `settings.port`, `settings.environment`, dòng 24, 196–198) | Tuân thủ 12-Factor App; không lộ secret khi push git; cùng một artifact chạy được ở dev/staging/prod. |
| **Health & Readiness** | Không có | Có `GET /health` (liveness, dòng 135–149) và `GET /ready` (readiness trả 503 khi chưa sẵn sàng, dòng 152–161) | Platform phát hiện container treo để restart (`/health`) và chỉ route traffic khi app đã sẵn sàng (`/ready`). |
| **Logging** | `print("[DEBUG] ...")`, thậm chí in cả `OPENAI_API_KEY` (dòng 33–34) | Structured JSON logging (`logging.basicConfig` + `json.dumps`, không log secret, dòng 28–32, 111–122) | Dễ gom log, lọc lỗi, đo lường trên production và tránh rò rỉ thông tin nhạy cảm. |
| **Shutdown** | Tắt đột ngột, không có lifecycle hook | `lifespan` + xử lý `SIGTERM` (dòng 39–68, 180–189), đặt `is_ready = False` rồi cho request đang chạy hoàn tất | Tránh rơi request (502/connection reset) khi deploy phiên bản mới hoặc scale-in. |
| **Network & CORS** | Bind `localhost`, `reload=True`, không cấu hình CORS (dòng 51–53) | Bind `0.0.0.0`, đọc `PORT`, `reload` chỉ bật khi `DEBUG=true`, có `CORSMiddleware` (dòng 77–82, 196–198) | Container cần `0.0.0.0` và `PORT` động để cloud proxy gọi vào; CORS giới hạn origin hợp lệ. |

---

## Part 2: Docker

### Exercise 2.1: Câu hỏi về `02-docker/develop/Dockerfile`
1. **Base image là gì?** `python:3.11` (bản đầy đủ của Python trên Debian, dung lượng lớn ~1 GB+).
2. **Working directory là gì?** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` đứng trước `COPY app.py`?** Để tận dụng **Docker layer cache**: khi chỉ sửa code ứng dụng (`app.py`) mà không đổi `requirements.txt`, Docker tái sử dụng lại layer `RUN pip install ...` đã cache thay vì cài lại toàn bộ thư viện mỗi lần build.
4. **Lệnh khởi động (`CMD`) là gì?** `CMD ["python", "app.py"]` (exec form).

### Exercise 2.2: Kết quả chạy container `my-agent:develop`
Build từ gốc repo và chạy container:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --rm --name p2-dev-test -p 8000:8000 my-agent:develop
curl -sS -i http://localhost:8000/health
curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"
```
Output thực tế:
```http
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","uptime_seconds":0.4,"container":true}
```
```http
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 2.3: So sánh kích thước image (đo thực tế bằng `docker images`)
```text
REPOSITORY   TAG        SIZE
my-agent     advanced   240MB
my-agent     develop    1.67GB
```
- **Develop (`my-agent:develop`):** `1.67 GB` (~1670 MB)
- **Production (`my-agent:advanced`):** `240 MB`
- **Chênh lệch:** Giảm **~85.6%** (`(1670 - 240) / 1670 ≈ 85.6%`).
- **Lý do giảm dung lượng:** Multi-stage build dùng stage `builder` để cài `gcc`/build tools và `pip install`, sau đó stage `runtime` dùng base image `python:3.11-slim` gọn nhẹ và chỉ copy thư viện đã cài (`/root/.local`) cùng mã nguồn sang, bỏ toàn bộ compiler/headers/cache.

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)
**Sơ đồ các service trong stack:**
```text
Client (HTTP :80)
   │
   ▼
[ nginx ] (reverse proxy / load balancer, expose 80 & 443)
   │  (network: internal)
   ▼
[ agent ] (FastAPI :8000, không expose trực tiếp ra host)
   ├──▶ [ redis ]  (redis:7-alpine :6379 — session cache & rate limit, volume redis_data)
   └──▶ [ qdrant ] (qdrant/qdrant:v1.9.0 :6333 — vector DB cho RAG, volume qdrant_data)
```

**Kết quả test thực tế qua Nginx (`http://localhost`):**
```http
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":0.9,"version":"2.0.0","timestamp":"2026-11-25T08:10:16.613819"}
```
```http
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1: Deploy agent Part 6 lên Railway *(Cập nhật sau khi bạn deploy trên Railway)*
- **Public URL:** `[TODO: Dán URL Railway sau khi deploy 06-lab-complete/]`
- **Screenshots:**
  - `screenshots/dashboard.png`
  - `screenshots/running.png`
  - `screenshots/test.png`

### So sánh `railway.toml` và `render.yaml`
| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
| --- | --- | --- |
| **Định dạng** | TOML ngắn gọn, chia theo section `[build]` và `[deploy]`. | YAML dạng Infrastructure-as-Code (khai báo mảng `services:`). |
| **Phạm vi khai báo** | Tập trung vào cấu hình build & deploy của **1 service** (ví dụ `builder = "DOCKERFILE"`, `healthcheckPath = "/health"`, `restartPolicyType`). Biến môi trường và Redis thường cấu hình trực tiếp trên Dashboard/CLI. | Khai báo được **nhiều service** và cả `envVars` ngay trong cùng 1 Blueprint (có hỗ trợ `generateValue: true` hoặc `sync: false` cho secrets để không lộ giá trị trong git). |
| **Lý do khác nhau** | Railway ưu tiên trải nghiệm nhanh (CLI `railway up` + gắn Redis trực tiếp trên UI project). | Render Blueprint ưu tiên mô tả trọn gói kiến trúc dịch vụ và biến môi trường bằng file YAML để tái tạo đồng bộ từ Git. |

### Exercise 3.3: Phân tích CI/CD Pipeline Google Cloud Run (`03-cloud-deployment/production-cloud-run/`)
Pipeline trong `cloudbuild.yaml` kết hợp `service.yaml` đi qua 4 bước tuần tự (`waitFor`):
1. **`test` (`python:3.11-slim`):** Cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v --tb=short` — nếu test fail sẽ dừng pipeline ngay.
2. **`build` (`gcr.io/cloud-builders/docker`):** Build Docker image gắn tag theo `$COMMIT_SHA` và `latest`, tận dụng `--cache-from` từ image `latest`.
3. **`push` (`gcr.io/cloud-builders/docker`):** Đẩy toàn bộ tag image lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy` (`gcr.io/cloud-builders/gcloud`):** Deploy revision mới lên Cloud Run (`asia-southeast1`) với `min-instances=1`, `max-instances=10`, `512Mi` RAM, 1 CPU, nạp secret (`OPENAI_API_KEY`, `AGENT_API_KEY`) từ Secret Manager (không hardcode), kèm `livenessProbe` (`/health`) và `startupProbe` (`/ready`) định nghĩa trong `service.yaml`.

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop`, `AGENT_API_KEY=secret-key-123`)
**1) Không truyền key → `401 Unauthorized`:**
```http
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```
**2) Sai key → `403 Forbidden`:**
```http
HTTP/1.1 403 Forbidden
content-type: application/json

{"detail":"Invalid API key."}
```
**3) Đúng key (`X-API-Key: [REDACTED]`) → `200 OK`:**
```http
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production`)
Lấy JWT tại `POST /auth/token` với tài khoản `student` / `demo123` (giới hạn 10 request/phút).

**Gọi `/ask` với `Authorization: Bearer <REDACTED_JWT>` → `200 OK`:**
```http
HTTP/1.1 200 OK
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"what is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```

**Vòng lặp gửi liên tiếp vượt 10 req/phút → Request thứ 11 trả `429 Too Many Requests`:**
```text
Request 2 -> HTTP 200
Request 3 -> HTTP 200
Request 4 -> HTTP 200
Request 5 -> HTTP 200
Request 6 -> HTTP 200
Request 7 -> HTTP 200
Request 8 -> HTTP 200
Request 9 -> HTTP 200
Request 10 -> HTTP 200
Request 11 -> HTTP 429
```
```http
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795593996
retry-after: 59
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cách làm Cost Guard & tại sao cần cả Rate Limit và Cost Guard
- **Cách triển khai Cost Guard (`04-api-gateway/production/cost_guard.py` & Part 6):**
  1. **Trước khi gọi LLM (`check_budget`):** Đọc tổng chi phí đã dùng trong ngày/tháng (lưu trong Redis trên production để chia sẻ giữa mọi worker/instance). Nếu vượt `DAILY_BUDGET_USD` hoặc `MONTHLY_BUDGET_USD` thì chặn ngay và trả **`HTTP 402 Payment Required`**.
  2. **Sau khi gọi LLM (`record_cost`):** Quy đổi số `input_tokens` và `output_tokens` sang USD theo đơn giá model (ví dụ GPT-4o-mini: `$0.00015/1K input`, `$0.0006/1K output`), cộng dồn vào Redis bằng `INCRBYFLOAT` kèm TTL hết hạn theo ngày/tháng.
  3. **Cảnh báo sớm:** Ghi log `WARNING` khi chi phí chạm ngưỡng (ví dụ 80% budget).
- **Tại sao cần cả hai:** Rate limit bảo vệ **tốc độ/lưu lượng request** (chống spam/DDoS làm quá tải CPU/RAM), còn Cost guard bảo vệ **ngân sách tiền API LLM** (tránh trường hợp ít request nhưng mỗi prompt/response cực dài hoặc chạy đều cả ngày làm phát sinh hóa đơn ngoài kiểm soát).

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.3: Liveness (`/health`) vs Readiness (`/ready`) và thiết kế Stateless
- **Liveness (`/health`):** Trả lời *"Process còn sống không?"* — luôn trả `200` miễn là ứng dụng chưa bị treo/deadlock (kể cả khi Redis tạm mất kết nối). Nếu `/health` fail, orchestrator sẽ restart container.
- **Readiness (`/ready`):** Trả lời *"Instance có sẵn sàng nhận traffic ngay lúc này không?"* — kiểm tra các dependency cốt lõi (như ping Redis). Nếu Redis mất kết nối, `/ready` trả `503` để load balancer ngừng định tuyến request mới vào instance đó mà không restart oan container.
- **Tại sao state trong RAM bị hỏng khi scale nhiều instance:** Khi chạy 3 instance sau Nginx load balancer, request 1 có thể vào `instance-A` (lưu session/counter vào RAM của A), nhưng request 2 lại vào `instance-B` (RAM của B không có dữ liệu đó) → mất lịch sử hội thoại và rate limit bị sai lệch. Chuyển toàn bộ state sang **Redis dùng chung** giúp mọi instance đều stateless và thay thế/scale ngang an toàn.

### Exercise 5.4 & 5.5: Kết quả chạy `test_stateless.py` với 3 instance (`-p k5-day14-scaling --scale agent=3`, cổng `8080`, endpoint `POST /chat`)
```text
{"status":"ok","instance_id":"instance-72a6ef","uptime_seconds":17.8,"storage":"redis","redis_connected":true}
============================================================
Stateless Scaling Demo
============================================================

Session ID: f7aa547c-0b00-4181-8571-aa6a29443279

Request 1: [instance-72a6ef]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-fbafb9]
  Q: Why do we need containers?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 3: [instance-72a6ef]
  Q: What is Kubernetes?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 4: [instance-fbace7]
  Q: How does load balancing work?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 5: [instance-fbafb9]
  Q: What is Redis used for?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-fbace7', 'instance-fbafb9', 'instance-72a6ef'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Kubernetes?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: How does load balancing work?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Redis used for?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...

✅ Session history preserved across all instances via Redis!
```
**Giải thích kết quả:** 5 request trong cùng một `session_id` được Nginx phân tải luân phiên tới cả 3 container khác nhau (`instance-72a6ef`, `instance-fbafb9`, `instance-fbace7`), nhưng khi truy vấn `/chat/{session_id}/history` vẫn còn nguyên đủ 10 tin nhắn (5 câu hỏi + 5 câu trả lời) vì toàn bộ lịch sử được lưu tập trung trong Redis.

---

## Part 6: Final Project — Kết quả `check_production_ready.py`

Chạy đầy đủ có Docker trong WSL2 (`Ubuntu-24.04`) tại `06-lab-complete/`:

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Một số chỉ số đo được khi chấm:
- **Docker image size:** `238 MB` (< 500 MB), multi-stage trên `python:3.11-slim`, user non-root `appuser`.
- **Graceful shutdown:** nhận `SIGTERM` trong lúc có request đang chạy vẫn trả `200` và thoát `exit code 0`; `docker stop` hoàn tất trong `1.1s` (< 10s).
- **Stateless Redis:** vượt `RATE_LIMIT_PER_MINUTE=5` trả `429`, restart agent vẫn giữ state trong Redis và tiếp tục trả `429`.

---

## AI Log
- **Công cụ sử dụng:** Antigravity AI Assistant.
- **Nội dung hỏi & nhận:**
  1. Kiểm tra môi trường Docker/WSL2, hướng dẫn cài đặt Docker Engine trong `Ubuntu-24.04`.
  2. Đọc đề bài (`README.md`, `CHECKPOINTS.md`, `RUBRIC.md`, `06-lab-complete/check_production_ready.py`) để hiểu rõ lộ trình K5 và 12 tiêu chí chấm.
  3. Hỗ trợ triển khai các module `TODO` trong `06-lab-complete/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) và chạy thực tế các ví dụ Part 1, 2, 4, 5 trong WSL2.
- **Tự kiểm tra & xác nhận:**
  - Chạy trực tiếp `python check_production_ready.py` (không sửa script chấm) trong WSL2 với Docker, đạt `PASS 12/12` (43/43 checks).
  - Mọi số liệu (kích thước image `1.67GB` vs `240MB`, output `curl -i` 200/401/403/429, output `test_stateless.py` với 3 instance) đều được chạy thật trên máy, không ước lượng.
  - Tự rà soát để hiểu từng file trong `06-lab-complete/app/` trước khi deploy lên Railway và trả lời Lab Coach.
