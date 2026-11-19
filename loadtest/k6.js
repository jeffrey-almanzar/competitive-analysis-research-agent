// Load test for the read paths of the API.
//
// It deliberately does NOT call POST /research: every POST queues a real research run
// that spends Claude and Exa credits (roughly $0.35-1 per report). To test the enqueue
// path, run against a stack with stubbed Claude/Exa, never against real API keys.
//
//   RUN_ID=<an existing run id> k6 run loadtest/k6.js
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const RUN_ID = __ENV.RUN_ID;

export const options = {
  thresholds: {
    http_req_duration: ['p(95)<200', 'p(99)<300'],
    http_req_failed: ['rate<0.01'],
  },
  stages: [
    { duration: '1m', target: 100 },
    { duration: '5m', target: 100 },
  ],
};

export default function () {
  check(http.get(`${BASE}/health`), { 'health 200': (r) => r.status === 200 });
  check(http.get(`${BASE}/research?limit=20`), { 'list 200': (r) => r.status === 200 });
  if (RUN_ID) {
    check(http.get(`${BASE}/research/${RUN_ID}`), { 'run 200': (r) => r.status === 200 });
  }
}
