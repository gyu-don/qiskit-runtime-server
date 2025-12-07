# Architecture Design Document

## Overview

This document describes the system architecture of the Qiskit Runtime Server, a self-hosted implementation of the IBM Qiskit Runtime Backend API.

**Key Design Principles**:
1. **Executor abstraction**: Multiple simulation backends (CPU via Aer, GPU via cuStateVec) are abstracted behind a unified `BaseExecutor` interface
2. **Virtual backends**: Backend naming follows `<metadata>@<executor>` format (e.g., `fake_manila@aer`), allowing users to explicitly select topology and execution backend
3. **Multiple executor support**: Server can host multiple executors simultaneously, with dynamic virtual backend generation (metadata × executor combinations)

## Core Concept: Separation of Metadata and Execution

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Two Distinct Concerns                            │
│                                                                         │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────┐  │
│  │   Backend Metadata              │  │   Circuit Execution          │  │
│  │   (What the hardware looks like)│  │   (How circuits are run)     │  │
│  │                                 │  │                              │  │
│  │   • Qubit count                 │  │   • Sampler primitive        │  │
│  │   • Coupling map (topology)     │  │   • Estimator primitive      │  │
│  │   • Basis gates                 │  │   • Noise simulation         │  │
│  │   • T1, T2 times                │  │   • Shot execution           │  │
│  │   • Gate errors                 │  │                              │  │
│  │   • Readout errors              │  │   AVAILABLE EXECUTORS:       │  │
│  │                                 │  │   • AerExecutor (CPU)        │  │
│  │   Source: FakeProvider          │  │   • CuStateVecExecutor (GPU) │  │
│  │   (59 fake backends)            │  │   • Custom executors         │  │
│  └─────────────────────────────────┘  └─────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User Application                               │
│                                                                         │
│   from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2        │
│   service = QiskitRuntimeService(channel="local",                       │
│       url="http://localhost:8000", ...)                                 │
│   sampler = SamplerV2(mode=backend)                                     │
│   job = sampler.run([circuit])                                          │
│                                                                         │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ HTTP/REST
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Qiskit Runtime Server                             │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                       REST API Layer (FastAPI)                     │  │
│  │                                                                    │  │
│  │   GET /v1/backends                    POST /v1/jobs                │  │
│  │   GET /v1/backends/{id}/configuration GET /v1/jobs/{id}/results    │  │
│  │   GET /v1/backends/{id}/properties    POST /v1/sessions            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                          │                        │                      │
│                          ▼                        ▼                      │
│  ┌────────────────────────────────┐  ┌────────────────────────────────┐ │
│  │   BackendMetadataProvider      │  │        JobManager              │ │
│  │                                │  │                                │ │
│  │   • list_backends()            │  │   • create_job()               │ │
│  │   • get_configuration()        │  │   • get_status()               │ │
│  │   • get_properties()           │  │   • get_result()               │ │
│  │   • get_status()               │  │                                │ │
│  │                                │  │   Uses Executor ───────┐       │ │
│  │   Source: FakeProvider         │  │                        │       │ │
│  │   (read-only metadata)         │  │                        ▼       │ │
│  └────────────────────────────────┘  │   ┌────────────────────────┐   │ │
│                                      │   │   Executor Interface   │   │ │
│                                      │   │                        │   │ │
│                                      │   │   execute_sampler()    │   │ │
│                                      │   │   execute_estimator()  │   │ │
│                                      │   └───────────┬────────────┘   │ │
│                                      │               │                │ │
│                                      │   ┌───────────┴────────────┐   │ │
│                                      │   │                        │   │ │
│                                      │   ▼                        ▼   │ │
│                                      │ ┌──────────┐  ┌──────────────┐ │ │
│                                      │ │ Local    │  │ GPU Executor │ │ │
│                                      │ │ Executor │  │   (future)   │ │ │
│                                      │ │ (CPU)    │  │              │ │ │
│                                      │ └──────────┘  └──────────────┘ │ │
│                                      └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

## Executor Interface

The **Executor** is the abstraction that enables pluggable simulation backends.

### Executor Design Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Executor Abstraction                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                      BaseExecutor (ABC)                       │  │
│  │                                                               │  │
│  │  Abstract Methods:                                            │  │
│  │  • execute_sampler(pubs, options, backend_name) → Result     │  │
│  │  • execute_estimator(pubs, options, backend_name) → Result   │  │
│  │  • name: str (property)                                       │  │
│  │                                                               │  │
│  │  Helper Methods:                                              │  │
│  │  • get_backend(backend_name) → FakeBackendV2                 │  │
│  │    ↳ Query FakeProvider for metadata                         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                  │                                  │
│                                  │                                  │
│         ┌────────────────────────┴────────────────────────┐         │
│         │                                                  │         │
│         ▼                                                  ▼         │
│  ┌──────────────────┐                           ┌─────────────────┐ │
│  │  AerExecutor     │                           │ CuStateVec      │ │
│  │  (CPU)           │                           │ Executor (GPU)  │ │
│  │                  │                           │                 │ │
│  │  • Uses Aer's    │                           │ • Uses cuQuantum│ │
│  │    QiskitRuntime │                           │   cuStateVec    │ │
│  │    LocalService  │                           │ • GPU-accelerated│ │
│  │  • Default       │                           │ • Optional dep  │ │
│  │    executor      │                           │                 │ │
│  └──────────────────┘                           └─────────────────┘ │
│                                                                     │
│         Custom Executors (User-Defined):                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │ NoiseExecutor    │  │ HybridExecutor   │  │ MyCustomExecutor│  │
│  │ (Future)         │  │ (Future)         │  │                 │  │
│  └──────────────────┘  └──────────────────┘  └─────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

Data Flow: Job Execution
────────────────────────────────────────────────────────────────────

Client Request:
  POST /v1/jobs {backend: "fake_manila@aer", ...}
           │
           ▼
  ┌─────────────────────┐
  │  JobManager         │
  │                     │
  │  1. Parse backend   │──► backend_name.split("@")
  │     name            │    → ("fake_manila", "aer")
  │                     │
  │  2. Route to        │──► executors["aer"]
  │     executor        │
  └─────────────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  AerExecutor        │
  │                     │
  │  1. Receive params  │──► execute_sampler(pubs, options, "fake_manila")
  │                     │    (Note: receives "fake_manila", NOT "fake_manila@aer")
  │  2. Get metadata    │──► self.get_backend("fake_manila")
  │     (optional)      │    → FakeManila backend object
  │                     │
  │  3. Execute circuit │──► QiskitRuntimeLocalService + Aer
  │                     │
  │  4. Return result   │──► PrimitiveResult
  └─────────────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  JobManager         │
  │                     │
  │  Store result       │──► job.status = "COMPLETED"
  │                     │    job.result = result
  └─────────────────────┘
```

### Protocol Definition

See [src/qiskit_runtime_server/executors/base.py](../src/qiskit_runtime_server/executors/base.py) for the complete interface definition.

**Key methods**:
- `execute_sampler(pubs, options, backend_name)`: Execute sampler primitive (measurement counts)
- `execute_estimator(pubs, options, backend_name)`: Execute estimator primitive (expectation values)
- `name` property: Executor implementation name (e.g., "aer", "custatevec")

**Design principle**: Executors receive the metadata name only (e.g., "fake_manila"), not the full virtual backend name. This allows executors to query backend properties independently.

### AerExecutor (Default - CPU) ✅

**Implementation**: [src/qiskit_runtime_server/executors/aer.py](../src/qiskit_runtime_server/executors/aer.py)

CPU-based executor using qiskit-aer's `QiskitRuntimeLocalService`.

**Key features**:
- Default executor (automatically used if no executors specified)
- Uses Aer's high-performance CPU simulation
- Supports both sampler and estimator primitives
- Ideal simulation (no noise model applied)

**Design notes**:
- Circuits are assumed to be pre-transpiled by the client
- No topology validation or basis gate checking
- Backend name used for metadata reference only

**Usage**:
```python
from qiskit_runtime_server import create_app

# Default (Aer is used automatically)
app = create_app()
```

### CuStateVecExecutor (GPU) ✅

**Implementation**: [src/qiskit_runtime_server/executors/custatevec.py](../src/qiskit_runtime_server/executors/custatevec.py)

GPU-accelerated executor using NVIDIA cuQuantum cuStateVec.

**Requirements**:
- CUDA 12.x
- Install with: `uv sync --extra custatevec`

**Key features**:
- GPU-accelerated quantum simulation
- Supports both sampler and estimator primitives
- Validates cuquantum installation at initialization

**Current status**: Uses `QiskitRuntimeLocalService` as foundation. Direct cuStateVec integration planned for future optimization.

**Usage**:
```bash
# Install with GPU support
uv sync --extra custatevec
```

```python
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor, CuStateVecExecutor

# Multi-executor setup
app = create_app(executors={
    "aer": AerExecutor(),                # CPU
    "custatevec": CuStateVecExecutor(),  # GPU
})
# Creates: 59 × 2 = 118 virtual backends
```

## Component Details

### 1. BackendMetadataProvider

**Implementation**: [src/qiskit_runtime_server/providers/backend_metadata.py](../src/qiskit_runtime_server/providers/backend_metadata.py)

**Purpose**: Provide virtual backend metadata with executor-aware naming

**Key features**:
- Parses `<metadata>@<executor>` backend names
- Lists all virtual backends (metadata × executor combinations)
- Validates executor availability
- Read-only (does not execute circuits)

**Core methods**:
- `parse_backend_name(backend_name)`: Parse virtual backend name into (metadata, executor) tuple
- `list_backends()`: Generate all metadata × executor combinations
- `get_configuration(backend_name)`: Get backend configuration
- `get_properties(backend_name)`: Get backend properties (T1/T2, gate errors, etc.)

**Example**:
```python
provider = BackendMetadataProvider(["aer", "custatevec"])

# Parse backend name
metadata, executor = provider.parse_backend_name("fake_manila@aer")
# Returns: ("fake_manila", "aer")

# List all virtual backends
response = provider.list_backends()
# Returns: 59 × 2 = 118 virtual backends
```

### 2. JobManager

**Implementation**: [src/qiskit_runtime_server/managers/job_manager.py](../src/qiskit_runtime_server/managers/job_manager.py)

**Purpose**: Job lifecycle management with async queueing and multi-executor routing

**Architecture**: Async queue with single worker thread (FIFO execution)

```
┌─────────────────────────────────────────────────────────────┐
│                      JobManager                              │
│                                                              │
│  Job Queue (FIFO) → Worker Thread → Executor Selection      │
│  [QUEUED jobs]       [RUNNING job]   [Route to executor]    │
│                                       ↓                      │
│                                    Result Storage            │
│                                    [COMPLETED/FAILED]        │
└─────────────────────────────────────────────────────────────┘
```

**Job Status Transitions**:
```
POST /v1/jobs → QUEUED → RUNNING → COMPLETED/FAILED
                   ↓
                CANCELLED (only if not RUNNING)
```

**Key features**:
- FIFO job queue with automatic executor routing
- Single worker thread (prevents resource contention)
- Thread-safe job state management
- Non-blocking job submission (returns job ID immediately)
- Backend name parsing: `fake_manila@aer` → routes to `executors["aer"]`

**Core methods**:
- `create_job(program_id, backend_name, params, options)`: Add job to queue (non-blocking)
- `get_job(job_id)`: Get job status and result
- `cancel_job(job_id)`: Cancel queued job
- `shutdown()`: Gracefully shutdown worker thread

**Design rationale**:
- **Single worker**: Prevents GPU/CPU memory contention, predictable execution order
- **Daemon thread**: Automatic cleanup on server shutdown
- **FIFO queue**: Fair scheduling, simple debugging

### 3. Application Factory

**Implementation**: [src/qiskit_runtime_server/app.py](../src/qiskit_runtime_server/app.py)

**Function**: `create_app(executors: dict[str, BaseExecutor] | None = None) -> FastAPI`

**Purpose**: Create FastAPI application with configurable executors

**Parameters**:
- `executors`: Mapping of executor name to instance (defaults to `{"aer": AerExecutor()}`)

**Examples**:
```python
# Default (Aer only)
app = create_app()
# Creates: 59 virtual backends (fake_manila@aer, ...)

# Multiple executors
app = create_app(executors={
    "aer": AerExecutor(),
    "custatevec": CuStateVecExecutor(),
})
# Creates: 59 × 2 = 118 virtual backends

# Custom executor
app = create_app(executors={
    "custom": MyCustomExecutor(),
})
```

**What it does**:
1. Initializes executors (defaults to Aer if none provided)
2. Creates JobManager with executor routing
3. Creates BackendMetadataProvider with virtual backend generation
4. Registers REST API endpoints
5. Returns configured FastAPI app

## Data Flow

### Job Execution with Multi-Executor Routing

```
Client                         Server                      Executor
  │                              │                            │
  │  POST /v1/jobs               │                            │
  │  backend: "fake_manila@aer"  │                            │
  │─────────────────────────────►│                            │
  │                              │                            │
  │                              │  1. Parse backend name:    │
  │                              │     "fake_manila@aer" →    │
  │                              │     metadata="fake_manila" │
  │                              │     executor="aer"         │
  │                              │                            │
  │                              │  2. Route to executor      │
  │                              │     executors["aer"]       │
  │                              │     .execute_sampler(      │
  │                              │       pubs,                │
  │                              │       options,             │
  │                              │       "fake_manila")       │
  │                              │───────────────────────────►│
  │                              │                            │
  │                              │  3. Execute & return       │
  │                              │◄───────────────────────────│
  │                              │                            │
  │  JobResponse {id: "job-123"} │                            │
  │◄─────────────────────────────│                            │
```

**Key Points**:
- Client specifies **full virtual backend name**: `fake_manila@aer`
- Server parses to extract **metadata** (`fake_manila`) and **executor** (`aer`)
- JobManager routes to the correct executor: `executors["aer"]`
- Executor receives **metadata name only** (not `@executor` suffix)

### How Executors Use Backend Metadata

**Workflow**:
1. Job arrives with metadata name (e.g., `"fake_manila"`)
2. Executor calls `self.get_backend(backend_name)` to retrieve metadata from FakeProvider
3. Backend metadata includes:
   - Qubit count, coupling map, basis gates
   - T1/T2 times, gate errors, readout errors
4. Executor optionally builds noise model from properties
5. Executor runs circuit and returns PrimitiveResult

**Note**: Current executors use ideal simulation (no noise model). Noise modeling can be added in future executor implementations.

## Configuration

### Installation Options

```bash
# CPU only (default)
uv sync

# With GPU support (requires CUDA 12.x)
uv sync --extra custatevec
```

### Application Configuration

See [Application Factory](#3-application-factory) section for `create_app()` examples.

**Summary**:
- Default: Aer executor only (59 virtual backends)
- Multi-executor: Pass `executors` dict to `create_app()`
- Custom executors: Extend `BaseExecutor` class

### Environment Variables

Not yet implemented. Use programmatic configuration via `create_app(executors={...})`.

## Project Structure (Current Implementation) ✅

```
src/qiskit_runtime_server/
├── __init__.py                 # Exports: create_app
├── app.py                      # create_app() factory (multi-executor)
├── models.py                   # Pydantic models
│
├── providers/
│   ├── __init__.py
│   └── backend_metadata.py     # BackendMetadataProvider (virtual backends)
│
├── executors/                  # ★ Multi-executor abstraction
│   ├── __init__.py             # Exports: BaseExecutor, AerExecutor, CuStateVecExecutor
│   ├── base.py                 # BaseExecutor ABC
│   ├── aer.py                  # AerExecutor (CPU, default)
│   └── custatevec.py           # CuStateVecExecutor (GPU)
│
└── managers/
    ├── __init__.py
    ├── job_manager.py          # JobManager (multi-executor routing)
    └── session_manager.py      # SessionManager (stub)
```

**Not yet implemented**:
- `routes/` - Route separation (optional, low priority)

## Implementation Status

**Current**: Production-ready multi-executor system (Phase 1-3 complete)

**Completed features**:
- Multi-executor abstraction (`BaseExecutor`, `AerExecutor`, `CuStateVecExecutor`)
- Virtual backend naming: `<metadata>@<executor>`
- Dynamic backend list generation (59 × N executors)
- Automatic executor routing in JobManager

**Future optimizations**:
- Direct cuStateVec integration (replace QiskitRuntimeLocalService fallback)
- HybridExecutor (automatic CPU/GPU routing based on circuit size)
- Environment-based configuration
- CLI entry point

## Summary

### Core Design Principles

1. **Separation of Concerns**:
   - **Metadata** (topology, noise) → FakeProvider (read-only, 59 backends)
   - **Execution** (simulation) → Executor interface (swappable: CPU/GPU/custom)
   - **Routing** → JobManager parses `<metadata>@<executor>` and routes to executor

2. **Multi-Executor System**: Single server hosts multiple executors
   - Virtual backends: 59 metadata × N executors
   - Client selects executor via backend name: `fake_manila@aer` (CPU) or `fake_manila@custatevec` (GPU)
   - No client-side modifications required

3. **Flexibility**: Mix-and-match any topology with any executor
   - Add new executors by extending `BaseExecutor`
   - Dynamic backend list generation
   - Explicit executor selection without API changes
