import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const p99Latency = new Trend('custom_p99', true);
const errorRate = new Rate('error_rate');

export const options = {
  stages: [
    { duration: '1m', target: 100 },   // 0 → 100 RPS 램프업
    { duration: '2m', target: 100 },   // 100 RPS 유지
    { duration: '1m', target: 500 },   // 100 → 500 RPS 램프업
    { duration: '2m', target: 500 },   // 500 RPS 유지
    { duration: '30s', target: 0 },    // 램프다운
  ],
  thresholds: {
    http_req_duration: ['p(99)<500', 'p(95)<300'],  // SLO 기준
    error_rate: ['rate<0.001'],
  },
  // 기본 summaryTrendStats는 p(95)까지만 포함해 p(99)가 리포트에서 항상 0으로 나오는 버그가 있었음.
  // handleSummary()가 p(99)를 읽을 수 있도록 명시적으로 포함시킨다.
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  // 시나리오 1: 헬스체크
  const health = http.get(`${BASE_URL}/api/v1/health`);
  check(health, { 'health 200': (r) => r.status === 200 });
  errorRate.add(health.status !== 200);
  p99Latency.add(health.timings.duration);

  sleep(0.1);

  // 시나리오 2: 플랜 목록 조회 (캐시 대상 엔드포인트)
  const plans = http.get(`${BASE_URL}/api/v1/plans`);
  check(plans, { 'plans 200': (r) => r.status === 200 });
  errorRate.add(plans.status !== 200);
  p99Latency.add(plans.timings.duration);

  sleep(0.1);
}

export function handleSummary(data) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  return {
    [`load-tests/reports/phase1-${timestamp}.html`]: htmlReport(data),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}

function textSummary(data, opts) {
  const p95 = data.metrics.http_req_duration?.values?.['p(95)'] || 0;
  const p99 = data.metrics.http_req_duration?.values?.['p(99)'] || 0;
  const errRate = data.metrics.error_rate?.values?.rate || 0;
  return `
📊 Phase 1 결과 (베이스라인)
  P95: ${p95.toFixed(1)}ms  (SLO: ≤300ms) ${p95 <= 300 ? '✅' : '❌'}
  P99: ${p99.toFixed(1)}ms  (SLO: ≤500ms) ${p99 <= 500 ? '✅' : '❌'}
  에러율: ${(errRate * 100).toFixed(3)}%  (SLO: ≤0.1%) ${errRate <= 0.001 ? '✅' : '❌'}
`;
}

function htmlReport(data) {
  const p95 = data.metrics.http_req_duration?.values?.['p(95)'] || 0;
  const p99 = data.metrics.http_req_duration?.values?.['p(99)'] || 0;
  return `<!DOCTYPE html>
<html><head><title>Phase 1 리포트</title></head>
<body>
<h1>Phase 1 — 베이스라인 (0→500 RPS)</h1>
<table border="1">
  <tr><th>지표</th><th>측정값</th><th>SLO 기준</th><th>결과</th></tr>
  <tr><td>P95</td><td>${p95.toFixed(1)}ms</td><td>≤300ms</td><td>${p95 <= 300 ? '✅ PASS' : '❌ FAIL'}</td></tr>
  <tr><td>P99</td><td>${p99.toFixed(1)}ms</td><td>≤500ms</td><td>${p99 <= 500 ? '✅ PASS' : '❌ FAIL'}</td></tr>
</table>
</body></html>`;
}
