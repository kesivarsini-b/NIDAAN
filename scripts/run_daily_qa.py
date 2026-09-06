# ============================================================================
# NIDAAN - daily 15-scenario QA sweep
# ----------------------------------------------------------------------------
# Boots the full stack (REST + WebSocket), runs every calibrated scenario,
# verifies the fused tier matches its labeled expected_risk, and writes a
# dated report. Intended to be scheduled daily (Task Scheduler / cron).
#
# Usage:
#   python scripts/run_daily_qa.py                 # against running server
#   NIDAAN_URL=http://127.0.0.1:8000 python scripts/run_daily_qa.py
#
# Exit code 0 = all tiers match, 1 = regressions found, 2 = stack/unavailable.
# ============================================================================

import datetime as dt
import json
import os
import sys

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS_JSON = os.path.join(ROOT, "data", "synthetic_scenarios.json")
REPORTS_DIR = os.path.join(ROOT, "reports")
BASE_URL = os.environ.get("NIDAAN_URL", "http://127.0.0.1:8000").rstrip("/")

HEALTH_TIMEOUT, CALL_TIMEOUT = 10.0, 30.0


def load_scenarios():
    with open(SCENARIOS_JSON, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload.get("scenarios", [])


def main():
    print(f"[daily-qa] base URL: {BASE_URL}")
    try:
        with httpx.Client(base_url=BASE_URL, timeout=HEALTH_TIMEOUT) as client:
            health = client.get("/api/v1/health").json()
    except Exception as exc:
        print(f"[daily-qa] FATAL: stack unreachable at {BASE_URL}: {exc}")
        return 2

    scenarios = load_scenarios()
    plan_check = {}
    results = []
    failures = 0
    today = dt.date.today().isoformat()

    with httpx.Client(base_url=BASE_URL, timeout=CALL_TIMEOUT) as client:
        try:
            plans = client.get("/api/v1/action-plans").json()
            plan_check = plans if isinstance(plans, dict) else {}
        except Exception as exc:
            print(f"[daily-qa] WARN: action-plans fetch failed: {exc}")

        for sc in scenarios:
            sid = sc.get("id")
            expected = str(sc.get("expected_risk", "")).upper()
            try:
                resp = client.post("/api/v1/analyze-text", json={"text": sc.get("transcript", "")})
                resp.raise_for_status()
                body = resp.json()
                analysis = body.get("analysis", {})
                got = str(analysis.get("risk_category", "")).upper()
                score = analysis.get("semantic_trauma_score")
                plan = body.get("action_plan", {})
            except Exception as exc:
                got, score, plan = "ERROR", None, {}
                print(f"[daily-qa] ERROR {sid}: {exc}")

            match = got == expected
            if not match:
                failures += 1
            results.append({
                "id": sid,
                "title": sc.get("title"),
                "expected_risk": expected,
                "got_tier": got,
                "semantic_trauma_score": score,
                "match": match,
                "plan_steps": len(plan.get("steps", [])),
            })
            flag = "OK " if match else "FAIL"
            print(f"[daily-qa] {flag} {sid} expected={expected:<9} got={got:<9} score={score}")

    report = {
        "date": today,
        "base_url": BASE_URL,
        "health": health,
        "total": len(scenarios),
        "passed": len(scenarios) - failures,
        "failed": failures,
        "action_plan_tiers_available": sorted(
            k for k in plan_check if isinstance(k, str)
        ),
        "results": results,
    }

    os.makedirs(REPORTS_DIR, exist_ok=True)
    out_path = os.path.join(REPORTS_DIR, f"daily_qa_{today}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"[daily-qa] SUMMARY {report['passed']}/{report['total']} match | "
          f"report -> {os.path.abspath(out_path)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())