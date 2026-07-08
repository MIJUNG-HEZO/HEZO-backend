import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// 오토스케일링 데모용 안전 버전 (팀원 phase1.js를 100 RPS로 캡).
// 500 RPS까지 안 올려서 프로덕션 부담·실사용자 영향을 최소화 —
// 100 RPS면 태스크당 200요청/분 목표를 넘겨 스케일아웃 유발엔 충분하다.
const errorRate = new Rate('error_rate');

export const options = {
  scenarios: {
    demo_ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 400,
      // iteration 1회당 요청 2건(health+plans) → iteration 50/s = 요청 100/s
      stages: [
        { duration: '1m', target: 25 },   // 0 → 50 req/s 램프업
        { duration: '4m', target: 50 },   // 100 req/s 유지 (스케일아웃 관찰 구간)
        { duration: '30s', target: 0 },   // 램프다운
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(99)<500', 'p(95)<300'],
    error_rate: ['rate<0.001'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const BASE_URL = __ENV.BASE_URL || 'https://api.hezo.asia';

export default function () {
  const health = http.get(`${BASE_URL}/api/v1/health`);
  check(health, { 'health 200': (r) => r.status === 200 });
  errorRate.add(health.status !== 200);
  sleep(0.1);

  const plans = http.get(`${BASE_URL}/api/v1/plans`);
  check(plans, { 'plans 200': (r) => r.status === 200 });
  errorRate.add(plans.status !== 200);
  sleep(0.1);
}
