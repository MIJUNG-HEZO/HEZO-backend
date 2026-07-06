import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('error_rate');

export const options = {
  // Phase 1(load-tests/phase1.js)에서 발견한 것과 같은 이유로 처음부터
  // ramping-arrival-rate executor로 작성한다: VU 램프(stages) 방식은 응답
  // 속도에 따라 실제 요청률이 크게 출렁여 "0→5,000 RPS"라는 목표 자체가
  // 지켜지지 않는다. 이 스크립트는 반복(iteration)당 요청 1건(GET /plans)
  // 이므로 target(iteration/s) == 실제 요청수(req/s)로 1:1 대응한다.
  scenarios: {
    phase2_ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 500,
      maxVUs: 6000,
      stages: [
        { duration: '2m', target: 300 },   // 캐시 워밍업
        { duration: '2m', target: 1000 },
        { duration: '2m', target: 3000 },
        { duration: '2m', target: 5000 },
        { duration: '1m', target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(99)<500', 'p(95)<300'],
    error_rate: ['rate<0.001'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  const plans = http.get(`${BASE_URL}/api/v1/plans`);
  check(plans, { 'plans 200': (r) => r.status === 200 });
  errorRate.add(plans.status !== 200);
}

export function handleSummary(data) {
  const p95 = data.metrics.http_req_duration?.values?.['p(95)'] || 0;
  const p99 = data.metrics.http_req_duration?.values?.['p(99)'] || 0;
  const errRate = data.metrics.error_rate?.values?.rate || 0;
  const dropped = data.metrics.dropped_iterations?.values?.count || 0;
  const totalReqs = data.metrics.http_reqs?.values?.count || 0;
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  return {
    [`load-tests/reports/phase2-${timestamp}.html`]: `<!DOCTYPE html>
<html><head><title>Phase 2 리포트</title></head><body>
<h1>Phase 2 — Redis 캐싱 + Auto Scaling 적용 (0→5,000 req/s, 고정 arrival-rate)</h1>
<table border="1">
  <tr><th>지표</th><th>측정값</th><th>SLO</th><th>결과</th></tr>
  <tr><td>P95</td><td>${p95.toFixed(1)}ms</td><td>≤300ms</td><td>${p95 <= 300 ? '✅' : '❌'}</td></tr>
  <tr><td>P99</td><td>${p99.toFixed(1)}ms</td><td>≤500ms</td><td>${p99 <= 500 ? '✅' : '❌'}</td></tr>
  <tr><td>에러율</td><td>${(errRate * 100).toFixed(3)}%</td><td>≤0.1%</td><td>${errRate <= 0.001 ? '✅' : '❌'}</td></tr>
  <tr><td>총 요청수</td><td>${totalReqs}</td><td>-</td><td>dropped_iterations: ${dropped}</td></tr>
</table>
<p>Phase 1/Task 7 베이스라인과 비교: P99 개선량을 기록하세요</p>
</body></html>`,
    stdout: `\n📊 Phase 2 결과 (고정 arrival-rate, 0→5,000 req/s)\n  P95: ${p95.toFixed(1)}ms ${p95 <= 300 ? '✅' : '❌'}\n  P99: ${p99.toFixed(1)}ms ${p99 <= 500 ? '✅' : '❌'}\n  에러율: ${(errRate * 100).toFixed(3)}% ${errRate <= 0.001 ? '✅' : '❌'}\n  총 요청수: ${totalReqs}건 / dropped_iterations: ${dropped}건 (${dropped > 0 ? '⚠️ 목표 RPS를 못 채움' : '✅ 목표 RPS 정상 달성'})\n`,
  };
}
