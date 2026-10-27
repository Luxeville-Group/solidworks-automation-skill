"""@brief Query the CAD Studio capability matrix and select the appropriate language backend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .capabilities import (
        backend_route_snapshot,
        load_capabilities,
        operation_route_index,
        resolve_operation_backend,
    )
except ImportError:
    from capabilities import (
        backend_route_snapshot,
        load_capabilities,
        operation_route_index,
        resolve_operation_backend,
    )


def build_parser() -> argparse.ArgumentParser:
    """@brief Construct the command-line argument parser."""
    parser = argparse.ArgumentParser(description="CAD atomik işlemine göre Python, C#, C++ veya headless backend seçin.")
    parser.add_argument("--operation", help="operation_routes içindeki atomik işlem ID.")
    parser.add_argument("--list", action="store_true", help="Tüm işlem rotalarını ve backend özetlerini listeleyin.")
    parser.add_argument("--available", action="append", default=[], help="Yerel kullanılabilir backend ID; birden fazla kez belirtilebilir.")
    parser.add_argument("--requirement", action="append", default=[], help="Sağlanan add-in/lisans koşulları; birden fazla kez belirtilebilir.")
    parser.add_argument("--solidworks-revision", help="SolidWorks Revision, örneğin 34.1.1.")
    parser.add_argument("--exact-api", action="store_true", help="Ham I* arayüz semantiği gerekir; Automation eşdeğer yöntemleri kabul edilmez.")
    parser.add_argument("--manifest", type=Path, help="İsteğe bağlı capability registry yolu.")
    return parser


def route_report(args: argparse.Namespace) -> dict:
    """@brief Return a read-only matrix summary or backend decision for one operation."""
    payload = load_capabilities(args.manifest)
    if args.list:
        return {
            "status": "ready",
            "summary": backend_route_snapshot(payload),
            "routes": [
                {
                    "id": route_id,
                    "label": route.get("label", route_id),
                    "candidate_backends": [item["backend"] for item in route.get("candidates", [])],
                    "blocked_reason": route.get("blocked_reason"),
                    "requires": route.get("requires", []),
                }
                for route_id, route in operation_route_index(payload).items()
            ],
        }
    if not args.operation:
        return {
            "status": "blocked",
            "error_code": "OPERATION_REQUIRED",
            "reason": "--operation belirtin veya kullanılabilir rotalar için --list kullanın",
        }
    return resolve_operation_backend(
        args.operation,
        available_backends=args.available or None,
        available_requirements=args.requirement,
        solidworks_revision=args.solidworks_revision,
        exact_api=args.exact_api,
        payload=payload,
    )


def main() -> int:
    """@brief Command-line entry point."""
    args = build_parser().parse_args()
    report = route_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
