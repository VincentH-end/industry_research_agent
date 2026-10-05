import argparse
import asyncio
import json

from app.benchmarks import BenchmarkRequest, run_benchmark
from app.config import get_settings
from app.telemetry import configure_logging


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate real orchestration with output and trace rubrics")
    parser.add_argument("--mode", choices=["fixture", "demo", "live"], default="fixture")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--timeout", type=int, default=120, help="Per-case seconds, including agent workflow")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings)
    result = asyncio.run(run_benchmark(settings, BenchmarkRequest(mode=args.mode, case_ids=args.case, judge=args.judge, timeout_seconds=args.timeout)))
    print(json.dumps({"run_id": result["run_id"], "pass_rate": result["pass_rate"], "artifact": result["artifact"], "disclaimer": result["disclaimer"]}, ensure_ascii=False, indent=2))
