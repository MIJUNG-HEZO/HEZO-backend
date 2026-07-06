import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const p99Latency = new Trend('custom_p99', true);
const errorRate = new Rate('error_rate');

export const options = {
  // 세션 112 발견: 기존 `stages`(VU 램프) 방식은 "가상유저(VU) 수"만 고정할 뿐 실제
  // 초당 요청수(RPS)는 응답 지연에 따라 크게 출렁인다 — 단일 태스크로 응답이 5~10초씩
  // 걸릴 때는 실제 RPS가 150~184에 그쳤고, ECS Auto Scaling 적용 후 응답이 빨라지자 같은
  // "500 VU" 스크립트가 분당 21만 건(초당 3,500건 이상, 사실상 Phase 3 스케일)까지
  // 치솟아 Auto Scaling 전/후를 공정하게 비교할 수 없었다.
  // → `ramping-arrival-rate` executor로 전환해 응답 속도와 무관하게 실제 초당
  //   요청수(iteration/s)를 목표치에 고정한다. preAllocatedVUs/maxVUs는 응답이
  //   가장 느렸던 조건(단일 태스크, P99 최대 ~10.8s)에서도 목표 RPS를 최대한
  //   유지할 수 있도록 넉넉히 잡았다 — 그래도 못 버티면 `dropped_iterations`
  //   지표로 "목표 RPS를 못 채웠다"는 사실 자체가 드러난다(이것도 유의미한 결과).
  scenarios: {
    phase1_ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 300,
      maxVUs: 2000,
      // target 단위는 "iteration/s"다. 반복 1회당 HTTP 요청 2건(health+plans)이므로
      // 실제 요청수(req/s) 기준 "100 RPS"/"500 RPS"에 맞추려면 iteration 목표를 절반(50/250)으로 잡는다.
      stages: [
        { duration: '1m', target: 50 },    // 0 → 100 req/s 램프업 (iteration 50/s = 요청 100/s)
        { duration: '2m', target: 50 },    // 100 req/s 유지
        { duration: '1m', target: 250 },   // 100 → 500 req/s 램프업 (iteration 250/s = 요청 500/s)
        { duration: '2m', target: 250 },   // 500 req/s 유지
        { duration: '30s', target: 0 },    // 램프다운
      ],
    },
  },
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
  const dropped = data.metrics.dropped_iterations?.values?.count || 0;
  const totalReqs = data.metrics.http_reqs?.values?.count || 0;
  return `
📊 Phase 1 결과 (베이스라인, 고정 arrival-rate)
  P95: ${p95.toFixed(1)}ms  (SLO: ≤300ms) ${p95 <= 300 ? '✅' : '❌'}
  P99: ${p99.toFixed(1)}ms  (SLO: ≤500ms) ${p99 <= 500 ? '✅' : '❌'}
  에러율: ${(errRate * 100).toFixed(3)}%  (SLO: ≤0.1%) ${errRate <= 0.001 ? '✅' : '❌'}
  총 요청수: ${totalReqs}건 / dropped_iterations: ${dropped}건 (${dropped > 0 ? '⚠️ 목표 RPS를 못 채움 — 응답 지연으로 VU 소진' : '✅ 목표 RPS 정상 달성'})
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
