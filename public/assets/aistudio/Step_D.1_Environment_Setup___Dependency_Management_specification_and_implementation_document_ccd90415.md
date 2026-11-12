# Step D.1: Environment Setup & Dependency Management Specification

## 1. Architectural Overview & Deterministic Reproducibility

In alignment with **Dr. Marcos López de Prado's** reproducibility mandates (*Advances in Financial Machine Learning*) and **Jim Simons'** deterministic execution standards (*Renaissance Technologies*), the **Swing Quant Engine** enforces strict environment locking and atomic state persistence.

Floating package versions (`pip install pandas`) are prohibited in production quant systems, as minor upstream updates to numerical libraries (`numpy`, `pandas`, `pyarrow`) can alter floating-point rounding in $\text{ATR}_{14}$ or cross-sectional Z-score calculations.

### Core Infrastructure Guarantees:
1. **Strict Version Pinning (`requirements.txt`):** Every runtime and verification dependency is locked to an exact, tested release compatible with Python 3.11+ on Linux (`ubuntu-latest` in GitHub Actions and GitHub Codespaces).
2. **Externalized Index Strategy Registry (`config/index_registry.json`):** Decouples index-tailored parameters (`RUT_2000`, `SP_400`, `SP_500`) from application code, validated at boot via `IndexConfigSchema`.
3. **Crash-Safe Atomic State Persistence (`src/storage.py` & `src/main.py`):** State updates to `virtual_portfolio.json` are written to a temporary staging file, flushed to disk (`os.fsync`), validated via Pydantic v2, and atomically swapped via POSIX `os.replace()`. This guarantees zero state corruption even if a runner terminates mid-execution.

```
swing-quant-engine/
├── .github/
│   └── workflows/
│       └── daily_quant_pipeline.yml   # Step D.2 Automated CI/CD & Cron Runner
├── config/
│   ├── index_registry.json            # Externalized Index Parameters (RUT_2000, SP_400)
│   └── constituents/                  # Curated Index Ticker Rosters (RUT_2000.csv, SP_400.csv)
├── data/
│   ├── cache/
│   │   └── market_data_window.parquet # 500-Bar Smart Sliding Window Cache
│   └── state/
│       └── virtual_portfolio.json     # Multi-Tenant Isolated Portfolio State Store
├── docs/                              # Engineering Specifications (Phases A, B, C, D, E)
├── src/
│   ├── __init__.py
│   ├── schemas.py                     # Step B.3 Pydantic v2 Data Contracts
│   ├── data_ingestion.py              # Step C.1 Smart Sliding Window & Split Guard
│   ├── quant_engine.py                # Step C.2 Vectorized Features, Meta-Labeling & Barriers
│   ├── storage.py                     # Atomic JSON / Relational DB Repository Layer
│   ├── notifier.py                    # Step E.1 Telegram Dispatch Integration
│   └── main.py                        # Headless Zero-Override CLI Orchestrator
├── tests/
│   └── test_quant_engine.py           # Step C.3 Deterministic Pytest Verification Suite
├── .env.example                       # Environment Variable Template
├── .gitignore                         # Repository Hygiene & Secret Protection Rules
├── pyproject.toml                     # Build System, Pytest & Ruff Linter Configuration
└── requirements.txt                   # Strictly Pinned Production Dependencies
```

---

## 2. Locked Dependency Manifest (`requirements.txt`)

```text
# =========================================================================
# Swing Quant Engine - Strictly Pinned Production & Verification Manifest
# Target Runtime: Python 3.11+ (Ubuntu / Debian / GitHub Codespaces)
# =========================================================================

# Core Numerical & Vectorized Time-Series Engine
numpy==2.1.2
pandas==2.2.3
pyarrow==17.0.0

# Market Data Ingestion & Network Resilience
yfinance==0.2.48
requests==2.32.3
urllib3==2.2.3

# Strict Data Contracts & Runtime Schema Validation
pydantic==2.9.2
pydantic-settings==2.6.0

# Automated Verification & Code Quality Gatekeepers
pytest==8.3.3
pytest-cov==5.0.0
ruff==0.7.1
```

---

## 3. Project & Test Runner Configuration (`pyproject.toml`)

Configuring `pyproject.toml` ensures that `pytest` automatically resolves imports from `src/` without requiring manual `PYTHONPATH` hacks in local terminals or GitHub Actions runners.

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "swing-quant-engine"
version = "2.0.0"
description = "Autonomous Multi-Index Swing Quant Engine (López de Prado & Simons Architecture)"
readme = "README.md"
requires-python = ">=3.11"

[tool.pytest.ini_options]
minversion = "8.0"
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-v --tb=short --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["E501"]
```

---

## 4. Repository Hygiene & Secret Protection (`.gitignore` & `.env.example`)

### A. `.gitignore`
```text
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/

# Virtual Environments
.venv/
venv/
ENV/

# Secrets & Local Environment Overrides (NEVER COMMIT)
.env
*.pem
*.key

# Ephemeral Staging Files
*.tmp
data/cache/*.tmp
```

### B. `.env.example`
```ini
# =========================================================================
# Swing Quant Engine - Environment Configuration Template
# Copy to .env for local development or configure in GitHub Actions Secrets
# =========================================================================

QUANT_ENV=production
LOG_LEVEL=INFO

# File Paths
STATE_STORE_PATH=data/state/virtual_portfolio.json
PARQUET_CACHE_PATH=data/cache/market_data_window.parquet
CONSTITUENTS_DIR=config/constituents

# Telegram Dispatch Credentials (Injected via GitHub Secrets in Step D.3 / E.1)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# Future Phase 2 Cloud Database Connection (Supabase / PostgreSQL with RLS)
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/swing_quant_db
```

---

## 5. Externalized Dynamic Index Registry (`config/index_registry.json`)

This configuration file initializes the default index pipelines (`RUT_2000` and `SP_400` active by default, with `SP_500` pre-configured and toggleable via `"is_active": true`).

```json
{
  "RUT_2000": {
    "index_id": "RUT_2000",
    "display_name": "Russell 2000 Small-Cap",
    "benchmark_ticker": "IWM",
    "tier": "SMALL_CAP",
    "is_active": true,
    "min_price": 5.0,
    "min_adv_30d": 500000,
    "max_relative_spread": 0.005,
    "volume_surge_multiplier": 1.8,
    "k_stop_atr": 2.5,
    "k_profit_atr": 5.0,
    "max_holding_bars": 14
  },
  "SP_400": {
    "index_id": "SP_400",
    "display_name": "S&P MidCap 400",
    "benchmark_ticker": "MDY",
    "tier": "MID_CAP",
    "is_active": true,
    "min_price": 5.0,
    "min_adv_30d": 500000,
    "max_relative_spread": 0.004,
    "volume_surge_multiplier": 1.4,
    "k_stop_atr": 2.0,
    "k_profit_atr": 4.5,
    "max_holding_bars": 14
  },
  "SP_500": {
    "index_id": "SP_500",
    "display_name": "S&P 500 Large-Cap",
    "benchmark_ticker": "SPY",
    "tier": "LARGE_CAP",
    "is_active": false,
    "min_price": 10.0,
    "min_adv_30d": 1000000,
    "max_relative_spread": 0.002,
    "volume_surge_multiplier": 1.25,
    "k_stop_atr": 1.8,
    "k_profit_atr": 4.0,
    "max_holding_bars": 14
  }
}
```

---

## 6. Atomic State Repository & Headless CLI Entrypoint (`src/storage.py` & `src/main.py`)

### A. Atomic State Repository (`src/storage.py`)
Implements the Repository Pattern so the engine can read/write `virtual_portfolio.json` atomically in Phase 1 and swap cleanly to PostgreSQL in Phase 2.

```python
from datetime import date, datetime
import json
import logging
import os
from pathlib import Path
from typing import Dict
from uuid import UUID

from schemas import (
    IndexConfigSchema,
    MultiTenantStateStoreSchema,
    VirtualPortfolioLedgerSchema,
)

logger = logging.getLogger("SwingQuantEngine.Storage")

DEFAULT_ADMIN_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
DEFAULT_ADMIN_PORTFOLIO_ID = UUID("00000000-0000-4000-8000-000000000101")


class AtomicStateRepository:
    """
    Provides crash-safe, atomic read/write persistence for the Multi-Tenant State Store
    and enforces Pydantic v2 schema validation on every load and save operation.
    """

    def __init__(
        self,
        state_path: Path = Path("data/state/virtual_portfolio.json"),
        index_registry_path: Path = Path("config/index_registry.json"),
    ) -> None:
        self.state_path = state_path
        self.index_registry_path = index_registry_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load_index_registry(self) -> Dict[str, IndexConfigSchema]:
        if not self.index_registry_path.exists():
            raise FileNotFoundError(f"Index registry missing at {self.index_registry_path}")
        raw_data = json.loads(self.index_registry_path.read_text(encoding="utf-8"))
        return {k: IndexConfigSchema.model_validate(v) for k, v in raw_data.items()}

    def load_or_initialize_state(self, as_of_date: date) -> MultiTenantStateStoreSchema:
        index_registry = self.load_index_registry()

        if not self.state_path.exists():
            logger.info(f"Initializing new Multi-Tenant State Store at {self.state_path}")
            default_portfolio = VirtualPortfolioLedgerSchema(
                portfolio_id=DEFAULT_ADMIN_PORTFOLIO_ID,
                user_id=DEFAULT_ADMIN_USER_ID,
                portfolio_name="Primary Swing Shadow Portfolio",
                as_of_date=as_of_date,
                cash_balance=100_000.0,
                total_equity=100_000.0,
                max_portfolio_heat_pct=0.06,
                max_concurrent_positions=10,
                subscribed_indices=["RUT_2000", "SP_400"],
            )
            initial_state = MultiTenantStateStoreSchema(
                index_registry=index_registry,
                tenant_portfolios={DEFAULT_ADMIN_PORTFOLIO_ID: default_portfolio},
            )
            self.save_state_atomically(initial_state)
            return initial_state

        raw_json = json.loads(self.state_path.read_text(encoding="utf-8"))
        state = MultiTenantStateStoreSchema.model_validate(raw_json)
        # Always synchronize index_registry with the latest config/index_registry.json
        state.index_registry = index_registry
        return state

    def save_state_atomically(self, state: MultiTenantStateStoreSchema) -> None:
        """
        Writes state to a staging `.tmp` file, flushes OS buffers to physical storage,
        and executes an atomic POSIX rename to prevent corrupt JSON on unexpected termination.
        """
        state.last_updated_utc = datetime.utcnow()
        # Re-validate entire state tree prior to serialization
        validated_state = MultiTenantStateStoreSchema.model_validate(state.model_dump())
        payload = validated_state.model_dump_json(indent=2)

        staging_path = self.state_path.with_suffix(".json.tmp")
        with open(staging_path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        os.replace(staging_path, self.state_path)
        logger.info(f"Successfully committed atomic state update to {self.state_path}")
```

### B. Headless Zero-Override CLI Orchestrator (`src/main.py`)
```python
import argparse
from datetime import date, datetime
import logging
import os
from pathlib import Path
import sys
from typing import Dict, List

from data_ingestion import SmartSlidingWindowOrchestrator, YFinanceDataProvider
from quant_engine import SwingQuantEngineOrchestrator
from storage import AtomicStateRepository


def configure_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Swing Quant Engine - Autonomous EOD Execution Worker"
    )
    parser.add_argument(
        "--as-of-date",
        type=str,
        default=None,
        help="Target EOD market date in YYYY-MM-DD format (defaults to today UTC).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full pipeline and validation without overwriting virtual_portfolio.json.",
    )
    return parser.parse_args()


def main() -> int:
    configure_logging()
    logger = logging.getLogger("SwingQuantEngine.Main")
    args = parse_args()

    target_date = (
        date.fromisoformat(args.as_of_date)
        if args.as_of_date
        else datetime.utcnow().date()
    )
    logger.info(f"=== Starting Autonomous Swing Quant Engine Cycle (as_of_date={target_date}) ===")

    state_path = Path(os.getenv("STATE_STORE_PATH", "data/state/virtual_portfolio.json"))
    cache_path = Path(os.getenv("PARQUET_CACHE_PATH", "data/cache/market_data_window.parquet"))
    constituents_dir = Path(os.getenv("CONSTITUENTS_DIR", "config/constituents"))

    # 1. Load & Validate Multi-Tenant Portfolio State and Index Registry
    repo = AtomicStateRepository(state_path=state_path)
    state_store = repo.load_or_initialize_state(as_of_date=target_date)

    # 2. Initialize Market Data Provider & Smart Sliding Window Orchestrator
    provider = YFinanceDataProvider(constituent_Lists_dir=constituents_dir)
    window_manager = SmartSlidingWindowOrchestrator(
        provider=provider,
        cache_path=cache_path,
        max_window_bars=500,
        min_required_bars=250,
    )

    # 3. Synchronize Rolling 500-Day Window (Incremental 2-Day Delta + Split Guard)
    market_df, _ = window_manager.sync_daily_market_window(
        state_store=state_store,
        as_of_date=target_date,
    )

    # Load constituent lists for active indices
    index_constituents_map: Dict[str, List[str]] = {
        idx_id: provider.fetch_index_constituents(idx_id)
        for idx_id, cfg in state_store.index_registry.items()
        if cfg.is_active
    }

    # 4. Execute Vectorized Screening, 500d Meta-Labeling & Triple-Barrier Reconciliation
    quant_orchestrator = SwingQuantEngineOrchestrator()
    dispatch_telemetry = quant_orchestrator.execute_daily_quant_cycle(
        market_df=market_df,
        state_store=state_store,
        index_constituents_map=index_constituents_map,
        as_of_date=target_date,
    )

    # 5. Commit Updated Portfolio Ledger Atomically
    if args.dry_run:
        logger.info("Dry-run mode enabled: skipping state persistence to disk.")
    else:
        repo.save_state_atomically(state_store)

    logger.info(
        f"=== Completed Swing Quant Engine Cycle for {len(dispatch_telemetry)} tenant portfolio(s) ==="
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```