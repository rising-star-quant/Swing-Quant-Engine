from __future__ import annotations

import ast
from dataclasses import dataclass, field
import importlib
import json
from pathlib import Path
import sys
import time
import traceback
from typing import Dict, List, Optional, Sequence, Tuple


# =============================================================================
# 1. AUDIT TELEMETRY DATA STRUCTURES
# =============================================================================


@dataclass
class CheckResult:
    """Represents the outcome of a single granular pre-flight verification check."""

    stage_id: int
    check_name: str
    passed: bool
    detail: str = ""


@dataclass
class StageReport:
    """Aggregates all check outcomes for one of the 5 verification stages."""

    stage_id: int
    stage_name: str
    results: List[CheckResult] = field(default_factory=list)
    elapsed_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total_count(self) -> int:
        return len(self.results)


# =============================================================================
# 2. 5-STAGE PRE-FLIGHT SYSTEM AUDITOR
# =============================================================================


class SystemPreFlightAuditor:
    """
    Deterministic 5-Stage Pre-Flight System Audit for the Swing Quant Engine:
    - Stage 1: Repository File Tree & Completeness Audit
    - Stage 2: AST Static Code Integrity & Anti-Truncation Audit
    - Stage 3: Cross-Module Import & Symbol Contract Verification
    - Stage 4: Live Configuration & Registry Schema Validation
    - Stage 5: End-to-End Sandbox Smoke Test
    """

    MANDATORY_FILES: Tuple[str, ...] = (
        "config/index_registry.json",
        "requirements.txt",
        ".github/workflows/daily_quant_pipeline.yml",
        "src/__init__.py",
        "src/schemas.py",
        "src/config.py",
        "src/security.py",
        "src/storage.py",
        "src/data_ingestion.py",
        "src/quant_engine.py",
        "src/notifier.py",
        "src/sandbox_runner.py",
        "src/main.py",
        "tests/__init__.py",
        "tests/test_quant_engine.py",
    )

    MODULE_SYMBOL_CONTRACTS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
        (
            "src.schemas",
            (
                "UserRole",
                "UserIdentitySchema",
                "JWTTokenPayload",
                "IndexTier",
                "IndexConfigSchema",
                "DirectionalSignalSchema",
                "MetaLabeledSignalSchema",
                "ExitReason",
                "TripleBarrierPositionSchema",
                "ClosedTradeAuditSchema",
                "VirtualPortfolioLedgerSchema",
                "MultiTenantStateStoreSchema",
            ),
        ),
        (
            "src.config",
            (
                "SystemSettings",
                "load_index_registry",
                "get_settings",
                "get_active_indices",
            ),
        ),
        (
            "src.security",
            (
                "PasswordManager",
                "JWTManager",
                "TenantSecurityGuard",
            ),
        ),
        (
            "src.storage",
            (
                "ParquetMarketDataRepository",
                "JsonPortfolioStateRepository",
                "CorporateActionSplitDetectedError",
            ),
        ),
        (
            "src.data_ingestion",
            (
                "YFinanceMarketDataProvider",
                "DataIngestionPipeline",
            ),
        ),
        (
            "src.quant_engine",
            (
                "FeatureEngineer",
                "PrimaryScreeningEngine",
                "MetaLabelingBacktestEngine",
                "TenantPortfolioReconciler",
            ),
        ),
        (
            "src.notifier",
            (
                "TelegramHTMLFormatter",
                "TelegramNotifier",
                "TenantDailyReportPayload",
            ),
        ),
        (
            "src.sandbox_runner",
            (
                "SyntheticMarketDataProvider",
                "SandboxDryRunHarness",
            ),
        ),
        (
            "src.main",
            (
                "QuantPipelineOrchestrator",
                "main",
            ),
        ),
    )

    FORBIDDEN_LINE_MARKERS: Tuple[str, ...] = (
        "# " + "TODO",
        "FIX" + "ME",
        "NotImplemented" + "Error",
    )

    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root: Path = (
            repo_root.resolve()
            if repo_root is not None
            else Path(__file__).resolve().parent.parent
        )
        if str(self.repo_root) not in sys.path:
            sys.path.insert(0, str(self.repo_root))
        self.stage_reports: List[StageReport] = []

    # -------------------------------------------------------------------------
    # Stage 1 — Repository File Tree & Completeness Audit
    # -------------------------------------------------------------------------

    def run_stage_1_file_tree_audit(self) -> StageReport:
        t0 = time.monotonic()
        stage = StageReport(
            stage_id=1,
            stage_name="Stage 1 — Repository File Tree & Completeness Audit",
        )

        for rel_path_str in self.MANDATORY_FILES:
            full_path = self.repo_root / rel_path_str
            if not full_path.exists() or not full_path.is_file():
                stage.results.append(
                    CheckResult(
                        stage_id=1,
                        check_name=f"File Exists: {rel_path_str}",
                        passed=False,
                        detail=f"Missing required file at '{full_path}'.",
                    )
                )
                continue

            size_bytes = full_path.stat().st_size
            if size_bytes <= 0:
                stage.results.append(
                    CheckResult(
                        stage_id=1,
                        check_name=f"File Non-Empty: {rel_path_str}",
                        passed=False,
                        detail=f"File '{rel_path_str}' is 0 bytes (empty).",
                    )
                )
            else:
                stage.results.append(
                    CheckResult(
                        stage_id=1,
                        check_name=f"File Verified: {rel_path_str}",
                        passed=True,
                        detail=f"{size_bytes:,} bytes",
                    )
                )

        registry_path = self.repo_root / "config/index_registry.json"
        if registry_path.is_file():
            try:
                raw_json = registry_path.read_text(encoding="utf-8")
                parsed_json = json.loads(raw_json)
                if not isinstance(parsed_json, dict) or not parsed_json:
                    stage.results.append(
                        CheckResult(
                            stage_id=1,
                            check_name="JSON Syntax: config/index_registry.json",
                            passed=False,
                            detail="Parsed JSON must be a non-empty dictionary object.",
                        )
                    )
                else:
                    stage.results.append(
                        CheckResult(
                            stage_id=1,
                            check_name="JSON Syntax: config/index_registry.json",
                            passed=True,
                            detail=f"Valid JSON with {len(parsed_json)} index entries.",
                        )
                    )
            except Exception as exc:
                stage.results.append(
                    CheckResult(
                        stage_id=1,
                        check_name="JSON Syntax: config/index_registry.json",
                        passed=False,
                        detail=f"Invalid JSON syntax: {exc}",
                    )
                )

        stage.elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
        return stage

    # -------------------------------------------------------------------------
    # Stage 2 — AST Static Code Integrity & Anti-Truncation Audit
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_abstractmethod(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for dec in func_node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "abstractmethod":
                return True
            if isinstance(dec, ast.Attribute) and dec.attr == "abstractmethod":
                return True
        return False

    @staticmethod
    def _is_stub_function_body(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> Optional[str]:
        """
        Inspects a function/method AST body and returns a failure reason if the body
        consists solely of `pass` or `Ellipsis` (`...`), even if preceded by a docstring.
        """
        effective_stmts: List[ast.stmt] = []
        for idx, stmt in enumerate(func_node.body):
            # Ignore leading docstring expression
            if (
                idx == 0
                and isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                continue
            effective_stmts.append(stmt)

        if not effective_stmts:
            return None

        if len(effective_stmts) == 1:
            only_stmt = effective_stmts[0]
            if isinstance(only_stmt, ast.Pass):
                return f"Function '{func_node.name}' at line {func_node.lineno} contains only 'pass'."
            if (
                isinstance(only_stmt, ast.Expr)
                and isinstance(only_stmt.value, ast.Constant)
                and only_stmt.value.value is Ellipsis
            ):
                return f"Function '{func_node.name}' at line {func_node.lineno} contains only Ellipsis ('...')."

        return None

    def run_stage_2_ast_static_audit(self) -> StageReport:
        t0 = time.monotonic()
        stage = StageReport(
            stage_id=2,
            stage_name="Stage 2 — AST Static Code Integrity & Anti-Truncation Audit",
        )

        target_dirs = [self.repo_root / "src", self.repo_root / "tests"]
        py_files: List[Path] = []
        for d in target_dirs:
            if d.is_dir():
                py_files.extend(sorted(d.rglob("*.py")))

        if not py_files:
            stage.results.append(
                CheckResult(
                    stage_id=2,
                    check_name="Python Source Discovery",
                    passed=False,
                    detail="No Python (.py) files found under src/ or tests/.",
                )
            )
            stage.elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
            return stage

        for py_file in py_files:
            rel_name = str(py_file.relative_to(self.repo_root))
            try:
                source_text = py_file.read_text(encoding="utf-8")
            except Exception as exc:
                stage.results.append(
                    CheckResult(
                        stage_id=2,
                        check_name=f"Read Source: {rel_name}",
                        passed=False,
                        detail=f"Failed to read file: {exc}",
                    )
                )
                continue

            # 1. AST Parse Check (catches mid-file copy-paste truncation or syntax errors)
            try:
                tree = ast.parse(source_text, filename=rel_name)
            except SyntaxError as syn_err:
                stage.results.append(
                    CheckResult(
                        stage_id=2,
                        check_name=f"AST Syntax & Completeness: {rel_name}",
                        passed=False,
                        detail=(
                            f"SyntaxError at line {syn_err.lineno}, col {syn_err.offset}: "
                            f"{syn_err.msg} (possible file truncation)."
                        ),
                    )
                )
                continue

            # 2. Walk AST to flag stub functions/methods (`pass` or `...`)
            stub_violations: List[str] = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if self._is_abstractmethod(node):
                        continue
                    violation = self._is_stub_function_body(node)
                    if violation is not None:
                        stub_violations.append(violation)

            # 3. Scan raw source lines for forbidden placeholder markers
            marker_violations: List[str] = []
            for line_no, raw_line in enumerate(source_text.splitlines(), start=1):
                for marker in self.FORBIDDEN_LINE_MARKERS:
                    if marker in raw_line:
                        marker_violations.append(
                            f"Line {line_no} contains forbidden marker '{marker}': {raw_line.strip()}"
                        )

            all_violations = stub_violations + marker_violations
            if all_violations:
                stage.results.append(
                    CheckResult(
                        stage_id=2,
                        check_name=f"AST & Zero-Placeholder Audit: {rel_name}",
                        passed=False,
                        detail="; ".join(all_violations),
                    )
                )
            else:
                stage.results.append(
                    CheckResult(
                        stage_id=2,
                        check_name=f"AST & Zero-Placeholder Audit: {rel_name}",
                        passed=True,
                        detail="Valid Python 3.11+ AST, zero stubs or placeholders.",
                    )
                )

        stage.elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
        return stage

    # -------------------------------------------------------------------------
    # Stage 3 — Cross-Module Import & Symbol Contract Verification
    # -------------------------------------------------------------------------

    def run_stage_3_import_contract_audit(self) -> StageReport:
        t0 = time.monotonic()
        stage = StageReport(
            stage_id=3,
            stage_name="Stage 3 — Cross-Module Import & Symbol Contract Verification",
        )

        for module_name, expected_symbols in self.MODULE_SYMBOL_CONTRACTS:
            try:
                mod = importlib.import_module(module_name)
                stage.results.append(
                    CheckResult(
                        stage_id=3,
                        check_name=f"Import Module: {module_name}",
                        passed=True,
                        detail="Imported cleanly",
                    )
                )
            except Exception as exc:
                stage.results.append(
                    CheckResult(
                        stage_id=3,
                        check_name=f"Import Module: {module_name}",
                        passed=False,
                        detail=f"Import failed: {exc}",
                    )
                )
                continue

            missing_symbols = [sym for sym in expected_symbols if not hasattr(mod, sym)]
            if missing_symbols:
                stage.results.append(
                    CheckResult(
                        stage_id=3,
                        check_name=f"Symbol Contracts: {module_name}",
                        passed=False,
                        detail=f"Missing required public symbols: {missing_symbols}",
                    )
                )
            else:
                stage.results.append(
                    CheckResult(
                        stage_id=3,
                        check_name=f"Symbol Contracts: {module_name}",
                        passed=True,
                        detail=f"Verified {len(expected_symbols)} exported symbols.",
                    )
                )

        stage.elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
        return stage

    # -------------------------------------------------------------------------
    # Stage 4 — Live Configuration & Registry Schema Validation
    # -------------------------------------------------------------------------

    def run_stage_4_config_and_registry_audit(self) -> StageReport:
        t0 = time.monotonic()
        stage = StageReport(
            stage_id=4,
            stage_name="Stage 4 — Live Configuration & Registry Schema Validation",
        )

        try:
            config_mod = importlib.import_module("src.config")
            get_settings_fn = getattr(config_mod, "get_settings")
            load_index_registry_fn = getattr(config_mod, "load_index_registry")
            get_active_indices_fn = getattr(config_mod, "get_active_indices")

            settings = get_settings_fn()
            stage.results.append(
                CheckResult(
                    stage_id=4,
                    check_name="Instantiate SystemSettings",
                    passed=True,
                    detail=(
                        f"env={settings.environment}, lookback={settings.backtest_lookback_days}d, "
                        f"max_heat={settings.default_max_portfolio_heat_pct:.1%}"
                    ),
                )
            )

            registry = load_index_registry_fn(settings.index_registry_path)
            if not registry:
                stage.results.append(
                    CheckResult(
                        stage_id=4,
                        check_name="Load Index Registry",
                        passed=False,
                        detail="Index registry returned empty dictionary.",
                    )
                )
            else:
                stage.results.append(
                    CheckResult(
                        stage_id=4,
                        check_name="Load Index Registry",
                        passed=True,
                        detail=f"Loaded {len(registry)} validated IndexConfigSchema entries.",
                    )
                )

            active_indices = get_active_indices_fn(settings)
            if not active_indices:
                stage.results.append(
                    CheckResult(
                        stage_id=4,
                        check_name="Active Index Gate",
                        passed=False,
                        detail="Zero active indices (is_active=True) configured in index_registry.json.",
                    )
                )
            else:
                stage.results.append(
                    CheckResult(
                        stage_id=4,
                        check_name="Active Index Gate",
                        passed=True,
                        detail=f"Active indices: {list(active_indices.keys())}",
                    )
                )

            for idx_id, cfg in registry.items():
                rr_ok = cfg.k_profit_atr >= 2.0 * cfg.k_stop_atr
                weight_sum = cfg.weight_momentum + cfg.weight_volume + cfg.weight_rs
                weights_ok = abs(weight_sum - 1.0) <= 1e-6

                if rr_ok and weights_ok:
                    stage.results.append(
                        CheckResult(
                            stage_id=4,
                            check_name=f"Index Invariants [{idx_id}]",
                            passed=True,
                            detail=(
                                f"tier={cfg.tier.value}, R:R={cfg.k_profit_atr / cfg.k_stop_atr:.2f}:1, "
                                f"weights_sum={weight_sum:.4f}"
                            ),
                        )
                    )
                else:
                    stage.results.append(
                        CheckResult(
                            stage_id=4,
                            check_name=f"Index Invariants [{idx_id}]",
                            passed=False,
                            detail=(
                                f"Invariant breach: k_stop={cfg.k_stop_atr}, k_profit={cfg.k_profit_atr}, "
                                f"weights_sum={weight_sum:.6f}"
                            ),
                        )
                    )

        except Exception as exc:
            stage.results.append(
                CheckResult(
                    stage_id=4,
                    check_name="Configuration & Registry Validation",
                    passed=False,
                    detail=f"Exception during configuration validation: {exc}",
                )
            )

        stage.elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
        return stage

    # -------------------------------------------------------------------------
    # Stage 5 — End-to-End Sandbox Smoke Test
    # -------------------------------------------------------------------------

    def _snapshot_tracked_files_mtimes(self) -> Dict[str, Tuple[int, int]]:
        snapshot: Dict[str, Tuple[int, int]] = {}
        for rel_path_str in self.MANDATORY_FILES:
            p = self.repo_root / rel_path_str
            if p.is_file():
                st = p.stat()
                snapshot[rel_path_str] = (st.st_size, st.st_mtime_ns)
        return snapshot

    def run_stage_5_sandbox_smoke_test(self) -> StageReport:
        t0 = time.monotonic()
        stage = StageReport(
            stage_id=5,
            stage_name="Stage 5 — End-to-End Sandbox Smoke Test",
        )

        before_snapshot = self._snapshot_tracked_files_mtimes()

        try:
            sandbox_mod = importlib.import_module("src.sandbox_runner")
            harness_cls = getattr(sandbox_mod, "SandboxDryRunHarness")
            harness = harness_cls(seed=42)
            smoke_ok = bool(harness.run())

            if smoke_ok:
                stage.results.append(
                    CheckResult(
                        stage_id=5,
                        check_name="SandboxDryRunHarness().run()",
                        passed=True,
                        detail="3-day multi-tenant walk-forward simulation succeeded.",
                    )
                )
            else:
                stage.results.append(
                    CheckResult(
                        stage_id=5,
                        check_name="SandboxDryRunHarness().run()",
                        passed=False,
                        detail="SandboxDryRunHarness().run() returned False.",
                    )
                )
        except Exception as exc:
            tb_summary = traceback.format_exc(limit=3).strip().replace("\n", " | ")
            stage.results.append(
                CheckResult(
                    stage_id=5,
                    check_name="SandboxDryRunHarness().run()",
                    passed=False,
                    detail=f"Unhandled exception: {exc} ({tb_summary})",
                )
            )

        after_snapshot = self._snapshot_tracked_files_mtimes()
        mutated_files = [
            rel_p
            for rel_p, before_meta in before_snapshot.items()
            if after_snapshot.get(rel_p) != before_meta
        ]
        if mutated_files:
            stage.results.append(
                CheckResult(
                    stage_id=5,
                    check_name="Zero Repository Mutation Guarantee",
                    passed=False,
                    detail=f"Sandbox smoke test modified tracked files: {mutated_files}",
                )
            )
        else:
            stage.results.append(
                CheckResult(
                    stage_id=5,
                    check_name="Zero Repository Mutation Guarantee",
                    passed=True,
                    detail="Zero tracked repository files modified during sandbox run.",
                )
            )

        stage.elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
        return stage

    # -------------------------------------------------------------------------
    # Full Execution & ASCII Diagnostic Report Formatting
    # -------------------------------------------------------------------------

    def run_all_stages(self) -> bool:
        self.stage_reports = [
            self.run_stage_1_file_tree_audit(),
            self.run_stage_2_ast_static_audit(),
            self.run_stage_3_import_contract_audit(),
            self.run_stage_4_config_and_registry_audit(),
            self.run_stage_5_sandbox_smoke_test(),
        ]
        self.print_diagnostic_report()
        return all(stage.passed for stage in self.stage_reports)

    def print_diagnostic_report(self) -> None:
        banner_line = "=" * 96
        sub_line = "-" * 96
        print(f"\n{banner_line}")
        print(" SWING QUANT ENGINE — 5-STAGE PRE-FLIGHT SYSTEM READINESS AUDIT REPORT")
        print(f"{banner_line}")
        print(f"{'STATUS':<10} | {'STAGE DESCRIPTION':<56} | {'CHECKS':<10} | {'DURATION':<10}")
        print(sub_line)

        total_checks = 0
        total_passed = 0
        failed_checks: List[CheckResult] = []

        for stage in self.stage_reports:
            status_tag = "[PASS]" if stage.passed else "[FAIL]"
            checks_str = f"{stage.passed_count}/{stage.total_count}"
            dur_str = f"{stage.elapsed_ms:.1f} ms"
            print(f"{status_tag:<10} | {stage.stage_name:<56} | {checks_str:<10} | {dur_str:<10}")

            total_checks += stage.total_count
            total_passed += stage.passed_count
            for res in stage.results:
                if not res.passed:
                    failed_checks.append(res)

        print(sub_line)
        overall_passed = len(failed_checks) == 0 and total_checks > 0
        overall_badge = "[PASS] ALL PRE-FLIGHT GATES VERIFIED" if overall_passed else "[FAIL] PRE-FLIGHT AUDIT FAILED"
        print(f"OVERALL VERDICT: {overall_badge} ({total_passed}/{total_checks} checks passed)")
        print(f"{banner_line}")

        if failed_checks:
            print("\nCRITICAL FAILURE DIAGNOSTICS (ACTION REQUIRED):")
            print(sub_line)
            for idx, failure in enumerate(failed_checks, start=1):
                print(
                    f"  {idx}. [Stage {failure.stage_id}] {failure.check_name}\n"
                    f"     -> {failure.detail}"
                )
            print(f"{banner_line}\n")
        else:
            print("System is 100% ready for autonomous GitHub Actions EOD execution.\n")


# =============================================================================
# 3. CLI ENTRYPOINT
# =============================================================================


def main(argv: Optional[Sequence[str]] = None) -> int:
    _ = argv
    auditor = SystemPreFlightAuditor()
    all_passed = auditor.run_all_stages()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
