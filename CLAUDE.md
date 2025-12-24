# CLAUDE.md

This file provides guidance for AI assistants (Claude, etc.) working on this codebase.

## Project Overview

This repository contains a self-hosted IBM Qiskit Runtime compatible REST API server for local quantum computing simulation.

## Repository Structure

```
qiskit-runtime-server/
├── pyproject.toml              # Project metadata and dependencies (uv managed)
├── uv.lock                     # Lock file (auto-generated, do not edit)
├── README.md                   # User-facing documentation
├── CLAUDE.md                   # This file - AI assistant guidance
├── CONTRIBUTING.md             # Contribution guidelines
├── LICENSE                     # Apache 2.0 license
├── .pre-commit-config.yaml     # Pre-commit hooks configuration
├── app.example.py              # Application template (copy to app.py)
├── .github/
│   └── workflows/
│       ├── ci.yml              # CI pipeline (lint, type check, test)
│       └── release.yml         # Release automation
├── src/
│   └── qiskit_runtime_server/  # Server package
│       ├── __init__.py
│       ├── app.py              # FastAPI app factory (create_app)
│       ├── models.py           # Pydantic models
│       ├── providers/
│       │   └── backend_metadata.py  # BackendMetadataProvider
│       ├── executors/          # ★ Pluggable execution backends
│       │   ├── __init__.py     # Exports BaseExecutor, AerExecutor, CuStateVecExecutor
│       │   ├── base.py         # BaseExecutor ABC
│       │   ├── aer.py          # AerExecutor (CPU, qiskit-aer)
│       │   └── custatevec.py   # CuStateVecExecutor (GPU, cuQuantum)
│       └── managers/
│           ├── job_manager.py  # Job lifecycle (multi-executor routing)
│           └── session_manager.py
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   ├── server/                 # Server tests
│   │   ├── test_backends.py
│   │   ├── test_jobs.py
│   │   ├── test_sessions.py
│   │   └── test_executors.py   # Executor tests
│   └── integration/            # Integration tests
│       └── test_client_server.py
├── docs/
│   ├── API_SPECIFICATION.md      # Complete REST API reference
│   ├── ARCHITECTURE.md           # System architecture and implementation details
│   ├── BACKEND_EXECUTOR_CONFIG.md # Backend topology and executor configuration options
│   ├── DESIGN_DECISIONS.md       # Key design decisions with rationale and alternatives
│   └── DEVELOPMENT.md            # Development setup and workflow guide
└── examples/
    ├── 01_list_backends.py
    ├── 02_run_sampler.py
    ├── 03_run_estimator.py
    ├── 04_session_mode.py
    └── 05_batch_mode.py
```

## Development Commands

This project uses `uv` for package management. Always use `uv run` to execute scripts.

### Setup

```bash
# Clone and setup
git clone <repo-url>
cd qiskit-runtime-server
uv sync

# Install pre-commit hooks (REQUIRED before any commits)
uv run pre-commit install

# Create application file from template
cp app.example.py app.py
# Edit app.py to customize executor configuration
```

### Common Commands

```bash
# Run the server
uv run uvicorn app:app --host 0.0.0.0 --port 8000

# Or with auto-reload for development
uv run uvicorn app:app --reload

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src --cov-report=term-missing

# Lint and format
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy src

# Run all pre-commit hooks manually
uv run pre-commit run --all-files
```

### Adding Dependencies

```bash
# Add a runtime dependency
uv add <package>

# Add a development dependency
uv add --dev <package>

# NEVER edit pyproject.toml dependencies directly - use uv add
```

## Code Style and Conventions

### Python Style

- Follow PEP 8 with ruff as the linter/formatter
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use double quotes for strings
- Docstrings: Google style

### Type Annotations

**This project targets Python 3.12+, so use modern type hint syntax:**

- `list[str]` instead of `List[str]`
- `dict[str, int]` instead of `Dict[str, int]`
- `int | None` instead of `Optional[int]`
- `str | int` instead of `Union[str, int]`
- `tuple[int, str]` instead of `Tuple[int, str]`

Only import from `typing` for special types:
- `Any`, `Literal`, `TypeVar`, `Protocol`, `TypeAlias`, etc.

**Example:**
```python
# Good (Python 3.12+)
from typing import Any

def process(items: list[dict[str, Any]], key: str | None = None) -> tuple[int, str]:
    ...

# Bad (old style)
from typing import Any, Dict, List, Optional, Tuple

def process(items: List[Dict[str, Any]], key: Optional[str] = None) -> Tuple[int, str]:
    ...
```

### Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: prefix with `_`

### Import Order

```python
# Standard library
import json
from datetime import datetime
from typing import Any

# Third-party
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Local
from .models import BackendConfiguration
from .backend_provider import get_backend_provider
```

## Architecture Notes

### Key Design: Separation of Metadata and Execution

The architecture separates two concerns:

1. **Backend Metadata** (from FakeProvider)
   - Qubit count, coupling map, basis gates
   - Calibration data: T1, T2, gate errors
   - Read-only, used for transpilation and noise modeling

2. **Circuit Execution** (via Executor interface)
   - Pluggable: LocalExecutor (CPU), GPUExecutor (future)
   - Uses metadata for noise model construction
   - Swappable without changing API

### Server Components

1. **FastAPI App (`app.py`)**: Application factory `create_app(executors: dict[str, BaseExecutor])`
2. **BackendMetadataProvider (`providers/backend_metadata.py`)**:
   - Parses `<metadata>@<executor>` backend names
   - Lists virtual backends (metadata × executor combinations)
   - Wraps `FakeProviderForBackendV2` (59 fake backends)
3. **Executor (`executors/`)**: Abstract interface for circuit execution
   - `BaseExecutor`: Abstract base class with `execute_sampler()`, `execute_estimator()`
   - `AerExecutor`: CPU execution using qiskit-aer (default)
   - `CuStateVecExecutor`: GPU execution using cuQuantum cuStateVec
4. **JobManager (`managers/job_manager.py`)**: Routes jobs to correct executor based on backend name
5. **SessionManager (`managers/session_manager.py`)**: Manages session/batch modes (not yet implemented)

### Key Design Decisions

For detailed design rationale and alternatives considered, see [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md).

Key decisions:
- **Multi-executor abstraction**: Server hosts multiple executors simultaneously (CPU, GPU, custom)
- **Virtual backend naming**: `<metadata>@<executor>` format (e.g., `fake_manila@aer`)
- **Dynamic backend list**: Metadata × executors combinations (59 × N backends)
- **uv for package management**: Fast, modern, with lock file for reproducibility
- **In-memory storage**: Jobs and sessions stored in memory (designed for local testing)
- **FastAPI + Pydantic v2**: Auto-docs, type validation, performance
- **Dependency injection**: Executors dict injected into JobManager via `create_app()`
- **Background threads**: Non-blocking job execution with daemon threads
- **Strict type checking**: mypy strict mode + pre-commit hooks for code quality
- **Optional dependencies**: GPU support via `--extra custatevec` (CUDA 12.x required)

### Creating a Custom Executor

```python
from qiskit_runtime_server.executors.base import BaseExecutor

class MyCustomExecutor(BaseExecutor):
    @property
    def name(self) -> str:
        return "custom"

    def execute_sampler(self, pubs, options, backend_name):
        # backend_name is the metadata name (e.g., "fake_manila")
        # NOT the full virtual backend name

        # Get backend metadata from FakeProvider
        backend = self.get_backend(backend_name)

        # Implement your custom execution logic
        # Use backend.coupling_map, backend.num_qubits, etc.
        result = self.custom_simulation(pubs, options, backend)
        return result

    def execute_estimator(self, pubs, options, backend_name):
        # Similar implementation
        ...

# Use custom executor
from qiskit_runtime_server import create_app

app = create_app(executors={
    "aer": AerExecutor(),           # CPU
    "custom": MyCustomExecutor(),   # Your executor
})

# Creates virtual backends:
# - fake_manila@aer
# - fake_manila@custom
# - ... (59 × 2 = 118 total)
```

### Client Connection

To connect to the local server, use the `local_service_helper.py` script (located in `examples/`) that patches IBM Cloud authentication:

```python
from qiskit_ibm_runtime import SamplerV2
from qiskit import QuantumCircuit, transpile
from local_service_helper import local_service_connection

# Connect to local server with context manager
with local_service_connection("http://localhost:8000") as service:
    # List available backends
    backends = service.backends()
    # Returns: ['fake_manila@aer', 'fake_manila@custatevec', ...]

    # Select backend with explicit executor
    backend = service.backend("fake_manila@aer")  # CPU executor
    # backend = service.backend("fake_manila@custatevec")  # GPU executor

    # Create and transpile circuit
    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure_all()
    circuit = transpile(circuit, backend=backend)

    # Run circuit
    sampler = SamplerV2(mode=backend)
    job = sampler.run([circuit])
    result = job.result()
```

**Why use `local_service_helper.py`?**
- The official `qiskit-ibm-runtime` client expects IBM Cloud IAM authentication
- The helper script patches authentication flows to work with localhost or custom domains
- Works without forking or modifying the `qiskit-ibm-runtime` package
- Uses `channel="ibm_cloud"` internally with patched authentication methods

## Testing Guidelines

- **Unit tests**: Test individual components in isolation (`tests/server/`)
- **Integration tests**: Test client-server interaction (`tests/integration/`)
- Use `TestClient` for API endpoint testing
- Run tests with `uv run pytest` or `uv run pytest --cov=src` for coverage

## Documentation Guide

This project has comprehensive documentation organized by purpose:

- **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)**: ✅ **Current implementation status** (Phase 3 complete). Read this first for overview.
- **[DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md)**: Explains *why* architectural choices were made, alternatives considered, and trade-offs.
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)**: ✅ Explains *how* the system works, with detailed component descriptions, data flow diagrams, and implementation patterns.
- **[BACKEND_EXECUTOR_CONFIG.md](docs/BACKEND_EXECUTOR_CONFIG.md)**: ✅ Explains virtual backend system and `<metadata>@<executor>` naming.
- **[API_SPECIFICATION.md](docs/API_SPECIFICATION.md)**: Complete REST API reference with all endpoints, parameters, and response formats.
- **[DEVELOPMENT.md](docs/DEVELOPMENT.md)**: Developer workflow guide (setup, testing, linting, debugging).

## Common Tasks

- **Adding a new endpoint**: Define Pydantic models in `models.py`, add endpoint in `app.py`, add tests, update API docs
- **Creating a custom executor**: Extend `BaseExecutor`, implement `execute_sampler()` and `execute_estimator()` methods
- **Modifying backend provider**: Update `providers/backend_metadata.py`, ensure compatibility with `FakeProviderForBackendV2`


## Troubleshooting

- **"Module not found" errors**: Always use `uv run python script.py`, not `python script.py`
- **Type checking errors**: Run `uv run mypy src --install-types` to regenerate stubs
- **Pre-commit failing**: Run `uv run ruff format . && uv run ruff check . --fix`

## API Compatibility

This server targets IBM Qiskit Runtime Backend API version `2025-05-01`. When updating:

1. Check IBM API changelog for breaking changes
2. Update models in `models.py`
3. Update endpoint signatures in `app.py`
4. Bump API version in responses

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create PR with changes
4. After merge, create GitHub release
5. GitHub Actions publishes to PyPI

## Important Notes

- **Do not modify** `uv.lock` directly - it's auto-generated
- **Always run** `uv run pre-commit run --all-files` before committing
- **Test with** actual qiskit-ibm-runtime client before releasing
- **Keep** backward compatibility with older qiskit-ibm-runtime versions

### Working with Temporary Files

- Use `tmp/` directory for temporary files and scratch work (not `/tmp`)
- The `tmp/` directory is **not** in `.gitignore` to allow Claude to search and access files
- Never commit files from `tmp/` to the repository (exclude manually from commits)
- This directory is for development/debugging purposes only
