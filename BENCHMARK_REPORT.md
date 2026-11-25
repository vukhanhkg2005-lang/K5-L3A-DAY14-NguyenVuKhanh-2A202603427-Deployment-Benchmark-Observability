# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được đo trực tiếp từ report JSON trong `reports/` và CSV trong `benchmark-results/`.

**Họ tên:** Nguyễn Vũ Khanh (`2A202603427`)  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows 11 + WSL2 (`Ubuntu-24.04`), Python 3.12.3, Docker Engine 29.10.1 / Docker Compose v5.8.0

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Với mock LLM cơ bản ~120–180 ms + retrieval ~20 ms, ngưỡng 500 ms đảm bảo 95% người dùng nhận phản hồi mượt (< 0.5s) và phát hiện sớm khi tải cao hoặc tail latency tăng. |
| Error rate `/ask` | `< 2.0 %` | Mock LLM có tỉ lệ lỗi upstream ~1%; đặt SLO < 2% (error budget 2%) giúp chịu được nhiễu ngẫu nhiên nhưng vẫn bắt kịp khi lỗi tăng bất thường. |
| Accuracy trên golden dataset | `≥ 80 %` (mục tiêu sau sửa KB: `100 %`, 0 regression) | Đảm bảo chất lượng câu trả lời của agent v2 luôn cao và không tụt hạng so với baseline trước khi merge/deploy. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 requests/mức)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.17 | 191.1 | 221.7 | 1708.7 | 1.00% | PASS |
| 10 | 38.92 | 188.0 | 221.4 | 1691.4 | 0.67% | PASS |
| 50 | 101.68 | 218.8 | 397.3 | 1756.2 | 1.33% | PASS |
| 100 | 41.83 | 841.8 | 5034.1 | 5351.7 | 1.67% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency.
- Từ concurrency `1 → 10 → 50`, RPS tăng mạnh (`4.17 → 38.92 → 101.68 req/s`) nhờ I/O bất đồng bộ (`async/await`) tận dụng thời gian chờ LLM.
- Tuy nhiên ở concurrency `100`, một tiến trình uvicorn đơn bị quá tải hàng đợi/event loop và contention tài nguyên: RPS **giảm ngược** xuống còn `41.83 req/s` trong khi `p95` vọt lên `5034.1 ms` (vi phạm SLO `< 500 ms`).

### 2.2 Tail latency (agent v2, 300 requests, concurrency=20)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 191.3 | 222.9 | 239.2 |
| 0.03 (mặc định) | 234.0 | 224.8 | 1700.4 |
| 0.1 | 357.0 | 1698.3 | 1715.4 |

**Nhận xét:**
- **p99** nhạy sớm nhất (ngay ở `MOCK_SLOW_RATE=0.03`, `p99` nhảy từ `239.2 ms` lên `1700.4 ms` — gấp > 7 lần, trong khi `avg` chỉ tăng nhẹ từ `191.3 ms` lên `234.0 ms`). Khi `MOCK_SLOW_RATE=0.1` (10% request chậm), cả **p95** (`1698.3 ms`) lẫn **p99** (`1715.4 ms`) đều tăng vọt, còn `avg` vẫn chỉ `357.0 ms` (trông vẫn dưới ngưỡng 500 ms!).
- Vì vậy **không nên đặt SLO theo average**: giá trị trung bình che giấu hoàn toàn trải nghiệm tệ của nhóm người dùng gặp tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 (`eval_v1.json`) | Agent v2 (`eval_v2.json`) | Agent v2 sau khi sửa KB (`eval_v2_fixed.json`) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | **100.0% (23/23)** |
| Avg tokens / câu | 57.6 | 109.0 | 114.6 |
| Tổng cost (USD) | $0.000411 | $0.000759 | $0.000799 |
| Cost / câu đúng (USD) | $0.00041115 | $0.00003616 | **$0.00003472** |
| Quality gate | FAIL | PASS (so với v1) | **PASS** (100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách đã sửa (`utils/mock_llm.py`, không sửa `golden_dataset.jsonl`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry vào `KNOWLEDGE_BASE` với từ khóa `["jwt", "xác thực"]` giải thích JWT là token có chữ ký số và thời gian hết hạn (exp) dùng xác thực stateless, khác với API key cố định. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry vào `KNOWLEDGE_BASE` với từ khóa `["hpa", "kubernetes"]` giải thích Kubernetes HPA tự động scale pod dựa trên CPU, memory và custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- **Chất lượng:** v2 dùng retrieval (RAG) giúp accuracy tăng vọt từ `4.35%` lên `91.30%` (và `100%` sau khi bổ sung KB).
- **Latency & Token/Cost:** v2 tốn thêm bước retrieval (~20 ms, p50 tăng từ `156.0 ms` lên `182.2–193.8 ms`) và prompt dài hơn nên số token/câu tăng gần gấp đôi (`57.6 → 109.0–114.6`).
- **Hiệu quả thực tế (`cost / câu đúng`):** Dù tổng chi phí tăng gần gấp đôi, **chi phí cho mỗi câu trả lời đúng của v2 rẻ hơn ~11.8 lần** (`$0.00003472` so với `$0.00041115` của v1) → đánh đổi rất xứng đáng.

**Dùng exit code của `run_eval.py` để chặn merge trong CI:**
- Khi chạy thử hồi quy `python eval/run_eval.py --url http://localhost:8001 --baseline reports/eval_v2.json`, script phát hiện **20 câu bị regression**, in `Quality gate: ❌ FAIL` và trả về **exit code `1`**.
- Trong GitHub Actions, bất kỳ bước nào trả về exit code khác `0` sẽ làm job fail và chặn merge PR:
```yaml
- name: Run agent quality gate
  run: |
    python eval/run_eval.py \
      --url http://localhost:8002 \
      --min-accuracy 0.9 \
      --baseline reports/eval_v2.json
```

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] [Dashboard Grafana khi đang có tải](screenshots/grafana-dashboard.png)
- [x] [Một trace chậm trong Jaeger](screenshots/jaeger-slow-trace.png)
- [x] [Một trace lỗi trong Jaeger](screenshots/jaeger-error-trace.png)
- [x] [Trang Alerts của Prometheus có ≥ 2 alert đang firing](screenshots/prometheus-alert-firing.png)

*(Đã kiểm tra unit test alert rules bằng `promtool test rules /p/alert_rules_test.yml` → `SUCCESS`.)*

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | ~86 giây (`for: 1m` + chu kỳ scrape/đánh giá) | Golden Signals → **Error rate** (chuyển đỏ > 5%) & **LLM calls ok/error** |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | ~154 giây (`for: 2m` + chu kỳ scrape/đánh giá) | Golden Signals → **p95 latency** (đỏ > 1s) & **Latency p50/p95/p99/avg** |
| C | `LLM_MODEL=mock-llm-large` (và lưu lượng tải cao) | `LLMCostBurnRateHigh` | ~17 giây sau khi chuyển cấu hình (tích luỹ burn rate > `$2/giờ`, `for: 2m`) | Golden Signals → **Cost 1h** & **LLM cost USD/giờ** |
| D | `docker pause` 1 instance (`agent-3`) | `AgentInstanceDown` (`pending` sau ~22s; cần giữ pause > 30s để `firing`) | ~22s tới `pending` (~50s tới `firing` theo rule `for: 30s`) | **Instances up** giảm & **Requests/s theo instance** mất 1 dòng |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | N/A | **Retrieval hit ratio** giảm về 0, **Tokens/s** giảm, bảng **Agent Version** đổi sang `v1` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**
- Các metric hạ tầng (HTTP 200, latency, CPU/RAM) vẫn xanh vì agent v1 trả lời nhanh và không lỗi 5xx. Để phát hiện lỗi giảm chất lượng trong production cần kết hợp: (1) chạy **eval quality gate** tự động trên golden dataset trong CI/CD trước khi deploy; (2) theo dõi **domain/RAG metrics** (như `retrieval_hit_ratio` tụt bất thường, hoặc alert khi `agent_info{version="v1"}` xuất hiện); và (3) **online evaluation** (LLM-as-a-judge sampling + phản hồi thumbs up/down của người dùng).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger / agent logs:

- `trace_id`: `a5b11e6aac6e5b35554e3a9d2a666ae8` *(trace lỗi kèm theo: `42c27ddf8f6e7b198bd283555f1e23ec`)*
- Tổng thời gian: `1821.6 ms`
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1645.8 ms`, chiếm **90.3%** tổng thời gian request — nguyên nhân là tail latency từ upstream LLM, không phải bước retrieval hay code xử lý của agent)
- Dòng log JSON tương ứng (grep theo `trace_id` `a5b11e6aac6e5b35554e3a9d2a666ae8`):

```json
{"ts": "2026-11-25T09:11:19.709936+00:00", "level": "INFO", "service": "observable-agent", "instance": "b7aaea5640b4", "event": "llm_call", "trace_id": "a5b11e6aac6e5b35554e3a9d2a666ae8", "span_id": "1d8891ebfb87d960", "request_id": "76207dd5e1c7", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 78, "output_tokens": 40, "cost_usd": 3.6e-05, "llm_ms": 1645.8}
{"ts": "2026-11-25T09:11:19.810338+00:00", "level": "INFO", "service": "observable-agent", "instance": "b7aaea5640b4", "event": "http_request", "trace_id": "a5b11e6aac6e5b35554e3a9d2a666ae8", "span_id": "1d8891ebfb87d960", "request_id": "76207dd5e1c7", "method": "POST", "route": "/ask", "status": 200, "ms": 1821.6}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu trích trực tiếp từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `Aggregated` / `POST /ask`):

| Số instance | RPS (Aggregated / `/ask`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 (`scale_1_stats.csv`) | 61.80 / 56.08 | 200 | 380 (410 trên `/ask`) | 1700 | 78 / 7782 (1.00%) |
| 3 (`scale_3_stats.csv`) | 62.33 / 56.65 | 190 | 290 (290 trên `/ask`) | 1700 | 55 / 7830 (0.70%) |

**Giải thích kết quả:**
- Khi scale từ **1 → 3 instance**, **p95 cải thiện rõ rệt** (`380 ms → 290 ms` tổng hợp, và `410 ms → 290 ms` riêng `/ask`, giảm ~29%) nhờ giảm hàng đợi xử lý cục bộ trên từng container.
- Tuy nhiên **RPS gần như giữ nguyên** (~62 req/s, do tải sinh ra bởi 100 Locust users có thời gian nghỉ cố định) và **p99 vẫn ở mức `1700 ms`**. Lý do là **nút thắt nằm ở upstream LLM latency** (`MOCK_SLOW_MS = 1500 ms` ở ~3% request), nên thêm bản sao agent không thể rút ngắn thời gian chờ phản hồi từ LLM — để giảm p99 cần tối ưu tầng LLM (caching, streaming, fallback model nhanh hơn hoặc timeout/hedged request).

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **Tail latency (p95/p99) mới phản ánh đúng trải nghiệm người dùng**, còn latency trung bình dễ che giấu sự cố (như khi `MOCK_SLOW_RATE=0.1`, `avg` vẫn 357ms nhưng `p95` đã vọt lên 1698ms).
  2. **Benchmark hiệu năng và benchmark chất lượng bổ trợ cho nhau:** Load test kiểm tra khả năng chịu tải (RPS/SLO), còn Eval trên golden dataset + `cost / câu đúng` giúp đánh giá trade-off RAG và chặn regression tự động bằng exit code trong CI.
  3. **Liên kết 3 trụ cột Metrics – Traces – Logs** giúp thu hẹp nguyên nhân gốc rễ nhanh: metric báo bất thường → trace chỉ ra span chậm/lỗi → `trace_id` giúp tra ngay dòng log JSON tương ứng.
- Nếu đưa agent này lên production thật, sẽ thêm các metric/alert:
  - Metric & alert cho **tầng Load Balancer / Synthetic Check bên ngoài** (để bắt lỗi `502`/`504` khi agent treo mà metric nội bộ của agent không ghi nhận được).
  - Alert cho **RAG quality / Retrieval hit ratio** giảm đột ngột và **Token/Cost per user** tăng bất thường.
