# Deployment Information

## Public URL
https://k5-l3a-day14-nguyenvukhanh-2a202603427-deploymen-production.up.railway.app

## Platform
Railway (deploy từ thư mục `06-lab-complete/` sử dụng `Dockerfile` và `railway.toml`, kết nối kèm dịch vụ Redis trên Railway)

## Test Commands

Đặt biến môi trường trước khi chạy (không commit key thật vào repo):
```bash
export BASE="https://k5-l3a-day14-nguyenvukhanh-2a202603427-deploymen-production.up.railway.app"
export AGENT_API_KEY="<YOUR_AGENT_API_KEY>"
```

### 1. Health Check (Expected: `200`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
```

### 2. Readiness Check — có Redis (Expected: `200`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
```

### 3. API Test không có API key (Expected: `401`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
```

### 4. API Test có API key hợp lệ (Expected: `200`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

## Environment Variables Set (trên Railway Dashboard, không ghi trong code)
- `PORT` (Railway tự cấp hoặc `8000`)
- `ENVIRONMENT=production`
- `REDIS_URL` (trỏ tới service Redis trên Railway, ví dụ `${{Redis.REDIS_URL}}`)
- `AGENT_API_KEY` (secret đặt trên Railway Variables)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`
- `LOG_LEVEL=INFO`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
