"""QLedger command-line interface.

Provides commands for inspecting databases, listing experiments, viewing
circuit histories, querying benchmark results, and exporting data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _json_out(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def _load_store(args: argparse.Namespace) -> Any:
    from qledger.storage.database import QLedgerStore

    return QLedgerStore(args.db)


# ======================================================================
# Commands
# ======================================================================

def cmd_experiments(args: argparse.Namespace) -> None:
    store = _load_store(args)
    experiments = store.list_experiments(name_like=args.name, limit=args.limit)
    if not experiments:
        print("No experiments found.")
        return
    print(f"{'ID':>5}  {'Name':<30}  {'Circuits':>8}  {'Created':<24}  Tags")
    print("-" * 90)
    for exp in experiments:
        summary = store.get_experiment_summary(exp["id"])
        tags = json.loads(exp["tags"]) if isinstance(exp["tags"], str) else exp["tags"]
        cc = summary["circuit_count"] if summary else 0
        print(f"{exp['id']:>5}  {exp['name']:<30}  {cc:>8}  {exp['created_at']:<24}  {tags}")
    store.close()


def cmd_show(args: argparse.Namespace) -> None:
    store = _load_store(args)
    summary = store.get_experiment_summary(args.id)
    if summary is None:
        print(f"Experiment {args.id} not found.", file=sys.stderr)
        sys.exit(1)
    _json_out(summary)
    store.close()


def cmd_circuits(args: argparse.Namespace) -> None:
    store = _load_store(args)
    circuits = store.list_circuits(args.experiment_id)
    if not circuits:
        print("No circuits found.")
        return
    print(f"{'ID':>5}  {'Name':<20}  {'Qubits':>6}  {'Depth':>5}  {'Gates':>5}  {'2Q':>4}  Hash")
    print("-" * 80)
    for c in circuits:
        print(
            f"{c['id']:>5}  {c['name']:<20}  {c['num_qubits']:>6}  "
            f"{c['depth']:>5}  {c['total_gates']:>5}  {c['two_qubit_gates']:>4}  "
            f"{c['content_hash'][:12]}..."
        )
    store.close()


def cmd_executions(args: argparse.Namespace) -> None:
    store = _load_store(args)
    executions = store.list_executions(
        circuit_id=args.circuit_id,
        backend_name=args.backend,
        framework=args.framework,
        limit=args.limit,
    )
    if not executions:
        print("No executions found.")
        return
    print(
        f"{'ID':>5}  {'Backend':<20}  {'FW':<10}  "
        f"{'Shots':>6}  {'Status':>6}  {'Time':>8}  Top Result"
    )
    print("-" * 95)
    for e in executions:
        status = "OK" if e["success"] else "FAIL"
        counts = json.loads(e["counts"]) if isinstance(e["counts"], str) else e["counts"]
        top = sorted(counts.items(), key=lambda x: -x[1])[:1]
        top_str = f"|{top[0][0]}⟩: {top[0][1]}" if top else "—"
        time_str = f"{e['execution_time_ms']:.1f}ms" if e["execution_time_ms"] else "—"
        print(
            f"{e['id']:>5}  {e['backend_name']:<20}  {e['framework']:<10}  "
            f"{e['shots']:>6}  {status:>6}  {time_str:>8}  {top_str}"
        )
    store.close()


def cmd_history(args: argparse.Namespace) -> None:
    store = _load_store(args)
    rows = store.get_full_history(args.experiment_id)
    if not rows:
        print("No history found.")
        return
    _json_out(rows)
    store.close()


def cmd_versions(args: argparse.Namespace) -> None:
    store = _load_store(args)
    versions = store.get_circuit_versions(args.circuit_id)
    if not versions:
        print("No versions found.")
        return
    print(f"{'Ver':>4}  {'Hash':<14}  {'Parent':<14}  {'Message':<30}  Created")
    print("-" * 90)
    for v in versions:
        parent = v["parent_hash"][:12] + ".." if v["parent_hash"] else "—"
        print(
            f"{v['version']:>4}  {v['content_hash'][:12]}..  {parent:<14}  "
            f"{v['message']:<30}  {v['created_at']}"
        )
    store.close()


def cmd_benchmarks(args: argparse.Namespace) -> None:
    store = _load_store(args)
    results = store.list_benchmarks(
        benchmark_type=args.type,
        backend_name=args.backend,
        limit=args.limit,
    )
    if not results:
        print("No benchmark results found.")
        return
    print(f"{'ID':>5}  {'Type':<20}  {'Backend':<20}  {'Score':>10}  Created")
    print("-" * 80)
    for r in results:
        score_str = f"{r['score']:.4f}" if r["score"] is not None else "—"
        print(
            f"{r['id']:>5}  {r['benchmark_type']:<20}  {r['backend_name']:<20}  "
            f"{score_str:>10}  {r['created_at']}"
        )
    store.close()


def cmd_noise(args: argparse.Namespace) -> None:
    store = _load_store(args)
    snapshots = store.list_noise_snapshots(
        backend_name=args.backend,
        limit=args.limit,
    )
    if not snapshots:
        print("No noise snapshots found.")
        return
    print(
        f"{'ID':>5}  {'Backend':<20}  {'Qubits':>6}  "
        f"{'T1':>8}  {'T2':>8}  {'CX Err':>8}  Captured"
    )
    print("-" * 85)
    for s in snapshots:
        t1 = f"{s['median_t1_us']:.1f}" if s["median_t1_us"] else "—"
        t2 = f"{s['median_t2_us']:.1f}" if s["median_t2_us"] else "—"
        cx = f"{s['avg_cx_error']:.4f}" if s["avg_cx_error"] else "—"
        print(
            f"{s['id']:>5}  {s['backend_name']:<20}  {s['num_qubits']:>6}  "
            f"{t1:>8}  {t2:>8}  {cx:>8}  {s['captured_at']}"
        )
    store.close()


def cmd_export(args: argparse.Namespace) -> None:
    store = _load_store(args)
    data = store.export_experiment(args.experiment_id)
    output = json.dumps(data, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Exported to {args.output}")
    else:
        print(output)
    store.close()


def cmd_adapters(args: argparse.Namespace) -> None:
    import contextlib
    import importlib

    from qledger.adapters.registry import _ADAPTER_MODULES, AdapterRegistry

    # Force adapter discovery — adapters self-register on import.
    for module_path in _ADAPTER_MODULES.values():
        with contextlib.suppress(ImportError):
            importlib.import_module(module_path)

    available = AdapterRegistry.available()
    if not available:
        print("No adapters registered. Install a framework: pip install qledger[qiskit]")
        return
    print("Registered adapters:")
    for name in available:
        try:
            adapter = AdapterRegistry.get(name)
            print(f"  {name:<12} v{adapter.framework_version}")
        except Exception:
            print(f"  {name:<12} (not installed)")


# ======================================================================
# Main
# ======================================================================

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="qledger",
        description="QLedger — inspect experiments, circuits, benchmarks, and noise data.",
    )
    parser.add_argument(
        "--db", default="qledger.sqlite",
        help="Path to the SQLite database file (default: qledger.sqlite).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # experiments
    p = sub.add_parser("experiments", help="List experiments.")
    p.add_argument("--name", help="Filter by name (substring).")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_experiments)

    # show
    p = sub.add_parser("show", help="Show experiment summary.")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_show)

    # circuits
    p = sub.add_parser("circuits", help="List circuits in an experiment.")
    p.add_argument("experiment_id", type=int)
    p.set_defaults(func=cmd_circuits)

    # executions
    p = sub.add_parser("executions", help="List executions.")
    p.add_argument("--circuit-id", type=int)
    p.add_argument("--backend", help="Filter by backend name.")
    p.add_argument("--framework", help="Filter by framework.")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_executions)

    # history
    p = sub.add_parser("history", help="Full execution history for an experiment.")
    p.add_argument("experiment_id", type=int)
    p.set_defaults(func=cmd_history)

    # versions
    p = sub.add_parser("versions", help="Circuit version history.")
    p.add_argument("circuit_id", type=int)
    p.set_defaults(func=cmd_versions)

    # benchmarks
    p = sub.add_parser("benchmarks", help="List benchmark results.")
    p.add_argument("--type", help="Filter by benchmark type.")
    p.add_argument("--backend", help="Filter by backend name.")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_benchmarks)

    # noise
    p = sub.add_parser("noise", help="List noise snapshots.")
    p.add_argument("--backend", help="Filter by backend name.")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_noise)

    # export
    p = sub.add_parser("export", help="Export experiment to JSON.")
    p.add_argument("experiment_id", type=int)
    p.add_argument("-o", "--output", help="Output file path.")
    p.set_defaults(func=cmd_export)

    # adapters
    p = sub.add_parser("adapters", help="List registered framework adapters.")
    p.set_defaults(func=cmd_adapters)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
