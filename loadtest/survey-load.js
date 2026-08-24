// Load test for zopyx.surveyjs (Plone 6 + SurveyJS).
//
// Scenario per virtual user:
//   1. Login once per VU (POST login_form; needs the buttons.login field!)
//   2. GET the survey viewer page -> extract auth_token + CSRF from the HTML
//   3. POST @@save-poll with a valid answer set (server-side validation runs)
//
// Default: constant-arrival-rate stress test — 20 submissions/second for 60s
// (~1200 iterations). Override with K6_RATE / K6_DURATION.
//
// NOTE: the session cookie is handled MANUALLY (redirects: 0 + explicit
// Cookie header). The default k6 cookie jar drops the __ac cookie between
// iterations on this k6 build (v2.2.0-dev), which silently logs every VU out
// after its first iteration.
//
// Run:  k6 run loadtest/survey-load.js
// Env overrides:  K6_SURVEY_URL, K6_LOGIN_URL, K6_USER, K6_PASSWORD,
//                 K6_RATE (default 20), K6_DURATION (default 60s)
import http from 'k6/http';
import { check, sleep } from 'k6';

const SURVEY_URL = __ENV.K6_SURVEY_URL || 'http://localhost:8082/demo/demos/multilingual-demo-survey';
const LOGIN_URL = __ENV.K6_LOGIN_URL || 'http://localhost:8082/demo/login_form';
const USER = __ENV.K6_USER || 'forms';
const PASSWORD = __ENV.K6_PASSWORD || 'formsarecool';
const RATE = Number(__ENV.K6_RATE || 3);
const DURATION = __ENV.K6_DURATION || '20s';

const QUESTIONS = {
  service_quality: ['excellent', 'good', 'average', 'poor'],
  product_satisfaction: ['very_satisfied', 'satisfied', 'average', 'dissatisfied'],
  recommendation: ['definitely_yes', 'probably_yes', 'not_sure', 'probably_not', 'definitely_not'],
};

let SESSION = null;

function randomAnswers() {
  const answers = {};
  for (const [q, choices] of Object.entries(QUESTIONS)) {
    answers[q] = choices[Math.floor(Math.random() * choices.length)];
  }
  return answers;
}

export const options = {
  scenarios: {
    load: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: 50,
      maxVUs: 100,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<2000'],
  },
};

export default function () {
  if (__ITER === 0) {
    const login = http.post(
      LOGIN_URL,
      {
        __ac_name: USER,
        __ac_password: PASSWORD,
        came_from: '/demo',
        'buttons.login': 'Log in',
      },
      { redirects: 0 }
    );
    const setCookies = login.headers['set-cookie'] || login.headers['Set-Cookie'] || '';
    const ac = String(setCookies).match(/__ac=([^;]+)/);
    if (!ac) {
      console.log(`login failed; status=${login.status}`);
      return;
    }
    SESSION = { cookie: `__ac=${ac[1]}` };
  }
  if (!SESSION) {
    sleep(1);
    return;
  }

  // Read path: viewer page carries fresh auth_token + CSRF in JSON script tags
  const viewer = http.get(`${SURVEY_URL}/viewer`, { headers: { Cookie: SESSION.cookie } });
  check(viewer, { 'viewer 200': (r) => r.status === 200 });
  const authMatch = viewer.body.match(/id="surveyjs-auth-token">"([^"]+)"</);
  const csrfMatch = viewer.body.match(/id="surveyjs-csrf-token">"([^"]+)"</);
  check(viewer, {
    'tokens extracted': () => !!(authMatch && csrfMatch),
  });
  if (!authMatch || !csrfMatch) {
    return;
  }

  // Write path: submit a valid answer set (single-use auth token)
  const submit = http.post(
    `${SURVEY_URL}/@@save-poll`,
    {
      pollResult: JSON.stringify(randomAnswers()),
      auth_token: authMatch[1],
      _authenticator: csrfMatch[1],
    },
    { headers: { Cookie: SESSION.cookie } }
  );
  check(submit, {
    'submit ok': (r) => r.status === 200 && r.json('isSuccess') === true,
  });

  sleep(1);
}
