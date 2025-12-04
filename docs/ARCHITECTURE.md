# Architecture Design Document

## Overview

This document describes the system architecture of the Qiskit Runtime Server, a self-hosted implementation of the IBM Qiskit Runtime Backend API.

**Key Design Principle**: The execution backend is abstracted behind an **Executor interface**, allowing easy replacement of the simulation engine (e.g., from local CPU simulation to GPU-accelerated simulation).

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
│  │   • Readout errors              │  │   REPLACEABLE:               │  │
│  │                                 │  │   • CPU (current)            │  │
│  │   Source: FakeProvider          │  │   • GPU (future)             │  │
│  │   (59 fake backends)            │  │   • Custom simulator         │  │
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

### Protocol Definition

```python
from typing import Protocol, Any, Dict, List
from abc import abstractmethod

class ExecutorProtocol(Protocol):
    """
    Abstract interface for quantum circuit execution.

    Implementations can use different simulation backends:
    - LocalExecutor: Uses QiskitRuntimeLocalService (CPU)
    - GPUExecutor: Uses GPU-accelerated simulator (future)
    - CustomExecutor: User-defined execution backend
    """

    @abstractmethod
    def execute_sampler(
        self,
        pubs: List[Any],
        options: Dict[str, Any],
        backend_name: str,
    ) -> "PrimitiveResult":
        """
        Execute sampler primitive.

        Args:
            pubs: Primitive Unified Blocks - (circuit, params, shots)
            options: Execution options
            backend_name: Target backend (for noise model/topology)

        Returns:
            SamplerResult with measurement counts
        """
        ...

    @abstractmethod
    def execute_estimator(
        self,
        pubs: List[Any],
        options: Dict[str, Any],
        backend_name: str,
    ) -> "PrimitiveResult":
        """
        Execute estimator primitive.

        Args:
            pubs: Primitive Unified Blocks - (circuit, observable, params)
            options: Execution options
            backend_name: Target backend (for noise model)

        Returns:
            EstimatorResult with expectation values
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Executor implementation name."""
        ...
```

### LocalExecutor (Current Default)

```python
class LocalExecutor(BaseExecutor):
    """
    CPU-based executor using QiskitRuntimeLocalService.

    This is the default implementation that uses Qiskit's
    built-in local simulation.
    """

    def __init__(self):
        from qiskit_ibm_runtime.fake_provider.local_service import (
            QiskitRuntimeLocalService
        )
        self.service = QiskitRuntimeLocalService()
        self.metadata_provider = get_backend_metadata_provider()

    @property
    def name(self) -> str:
        return "local"

    def execute_sampler(
        self,
        pubs: List[Any],
        options: Dict[str, Any],
        backend_name: str,
    ) -> PrimitiveResult:
        backend = self.metadata_provider.get_backend(backend_name)

        return self.service._run(
            program_id="sampler",
            inputs={"pubs": pubs},
            options={"backend": backend, **options}
        )

    def execute_estimator(
        self,
        pubs: List[Any],
        options: Dict[str, Any],
        backend_name: str,
    ) -> PrimitiveResult:
        backend = self.metadata_provider.get_backend(backend_name)

        return self.service._run(
            program_id="estimator",
            inputs={"pubs": pubs},
            options={"backend": backend, **options}
        )
```

### GPUExecutor (Future)

```python
class GPUExecutor(BaseExecutor):
    """
    GPU-accelerated executor.

    Uses backend metadata from FakeProvider for:
    - Coupling map (connectivity constraints for transpilation)
    - Noise model (T1, T2, gate errors for realistic simulation)
    - Basis gates

    Executes circuits on GPU simulator.
    """

    def __init__(
        self,
        device: int = 0,
        use_noise_model: bool = True,
    ):
        self.device = device
        self.use_noise_model = use_noise_model
        self.metadata_provider = get_backend_metadata_provider()
        self._init_gpu()

    @property
    def name(self) -> str:
        return "gpu"

    def _init_gpu(self):
        """Initialize GPU resources."""
        # TODO: Initialize your GPU simulator here
        pass

    def _build_noise_model(self, backend_name: str):
        """
        Build noise model from FakeBackend properties.

        Extracts T1, T2, gate errors, readout errors from
        the fake backend's calibration data.
        """
        properties = self.metadata_provider.get_backend_properties(backend_name)
        if properties is None:
            return None

        # Convert properties to noise model format
        # This depends on your GPU simulator's noise model API
        return self._convert_to_gpu_noise_model(properties)

    def execute_sampler(
        self,
        pubs: List[Any],
        options: Dict[str, Any],
        backend_name: str,
    ) -> PrimitiveResult:
        # Get noise model from backend metadata
        noise_model = None
        if self.use_noise_model:
            noise_model = self._build_noise_model(backend_name)

        # Execute on GPU
        # TODO: Replace with actual GPU simulator call
        results = self._gpu_run_sampler(pubs, options, noise_model)

        return self._format_result(results)

    def _gpu_run_sampler(self, pubs, options, noise_model):
        """
        Core GPU execution method.

        THIS IS THE METHOD TO IMPLEMENT for GPU simulation.
        """
        raise NotImplementedError("GPU executor not yet implemented")
```

## Component Details

### 1. BackendMetadataProvider

**Purpose**: Provide backend metadata (NOT execution)

```python
class BackendMetadataProvider:
    """
    Provides backend metadata from FakeProviderForBackendV2.

    This component is READ-ONLY - it does not execute circuits.
    It provides:
    - Backend list with basic info
    - Configuration (topology, gates, constraints)
    - Properties (calibration data: T1, T2, errors)
    - Status information

    The Executor uses this metadata for:
    - Noise model construction
    - Topology-aware transpilation
    """

    def __init__(self):
        from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2
        self._provider = FakeProviderForBackendV2()
        self._backends_cache = None

    def list_backends(self) -> List[BackendInfo]:
        """List all available backends."""
        ...

    def get_backend(self, name: str) -> FakeBackendV2:
        """Get backend instance (for LocalExecutor)."""
        return self._provider.backend(name)

    def get_backend_configuration(self, name: str) -> Dict[str, Any]:
        """Get backend configuration (topology, gates, etc.)."""
        ...

    def get_backend_properties(self, name: str) -> BackendProperties:
        """Get calibration properties (T1, T2, errors)."""
        ...
```

### 2. JobManager

**Purpose**: Job lifecycle management with pluggable Executor

```python
class JobManager:
    """
    Manages job lifecycle.

    Key change from original: Uses injected Executor instead of
    hardcoded QiskitRuntimeLocalService.
    """

    def __init__(self, executor: BaseExecutor):
        self.executor = executor  # ← Injected, swappable
        self.jobs: Dict[str, JobInfo] = {}
        self._lock = threading.Lock()

    def create_job(
        self,
        program_id: str,
        backend_name: str,
        params: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        job_id = f"job-{uuid.uuid4()}"

        # Start background execution
        thread = threading.Thread(
            target=self._execute_job,
            args=(job_id, program_id, backend_name, params, options or {})
        )
        thread.start()

        return job_id

    def _execute_job(self, job_id, program_id, backend_name, params, options):
        """Execute job using the configured Executor."""
        try:
            if program_id == "sampler":
                result = self.executor.execute_sampler(
                    pubs=params.get("pubs", []),
                    options=options,
                    backend_name=backend_name,
                )
            elif program_id == "estimator":
                result = self.executor.execute_estimator(
                    pubs=params.get("pubs", []),
                    options=options,
                    backend_name=backend_name,
                )

            self._set_job_completed(job_id, result)
        except Exception as e:
            self._set_job_failed(job_id, str(e))
```

### 3. Application Factory

**Purpose**: Create app with configurable Executor

```python
def create_app(executor: Optional[BaseExecutor] = None) -> FastAPI:
    """
    Create FastAPI application with configurable executor.

    Args:
        executor: Executor implementation. Defaults to LocalExecutor.

    Returns:
        Configured FastAPI application

    Examples:
        # Default (CPU)
        app = create_app()

        # With GPU executor
        app = create_app(executor=GPUExecutor(device=0))

        # With custom executor
        app = create_app(executor=MyCustomExecutor())
    """
    if executor is None:
        executor = LocalExecutor()

    # Create managers with executor
    job_manager = JobManager(executor=executor)
    session_manager = SessionManager()
    metadata_provider = BackendMetadataProvider()

    # Create FastAPI app
    app = FastAPI(title="Qiskit Runtime Server")

    # Register routes with dependencies
    register_backend_routes(app, metadata_provider)
    register_job_routes(app, job_manager)
    register_session_routes(app, session_manager)

    return app
```

## Data Flow

### Job Execution with Executor Abstraction

```
Client                    Server                         Executor
  │                         │                               │
  │  POST /v1/jobs          │                               │
  │  {program_id: sampler,  │                               │
  │   backend: fake_manila} │                               │
  │────────────────────────►│                               │
  │                         │                               │
  │                         │  1. JobManager.create_job()   │
  │                         │                               │
  │                         │  2. executor.execute_sampler( │
  │                         │       pubs,                   │
  │                         │       options,                │
  │                         │       backend_name            │
  │                         │     )                         │
  │                         │──────────────────────────────►│
  │                         │                               │
  │                         │     LocalExecutor:            │
  │                         │       Uses QiskitRuntime      │
  │                         │       LocalService            │
  │                         │                               │
  │                         │     GPUExecutor (future):     │
  │                         │       Gets noise model from   │
  │                         │       BackendMetadataProvider │
  │                         │       Executes on GPU         │
  │                         │                               │
  │                         │  PrimitiveResult              │
  │                         │◄──────────────────────────────│
  │                         │                               │
  │  JobResponse            │                               │
  │◄────────────────────────│                               │
```

### How GPU Executor Uses Backend Metadata

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     GPU Executor Workflow                                │
│                                                                         │
│   1. Job arrives: {backend: "fake_manila", pubs: [...]}                 │
│                                                                         │
│   2. GPUExecutor queries BackendMetadataProvider:                       │
│      ┌─────────────────────────────────────────────────────────────┐   │
│      │  properties = metadata_provider.get_properties("fake_manila") │   │
│      │                                                               │   │
│      │  Returns:                                                     │   │
│      │  {                                                            │   │
│      │    qubits: [                                                  │   │
│      │      [{name: "T1", value: 125.3, unit: "us"}, ...],          │   │
│      │      ...                                                      │   │
│      │    ],                                                         │   │
│      │    gates: [                                                   │   │
│      │      {gate: "cx", qubits: [0,1], error: 0.0043}, ...         │   │
│      │    ]                                                          │   │
│      │  }                                                            │   │
│      └─────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   3. GPUExecutor builds noise model from properties                     │
│                                                                         │
│   4. GPUExecutor runs circuit on GPU with noise model                   │
│                                                                         │
│   5. Returns PrimitiveResult                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

```bash
# Select executor implementation
QRS_EXECUTOR=local          # Default: QiskitRuntimeLocalService
QRS_EXECUTOR=gpu            # Future: GPU simulator

# GPU-specific options
QRS_GPU_DEVICE=0            # GPU device ID
QRS_GPU_MEMORY_LIMIT=8G     # Memory limit
QRS_GPU_USE_NOISE=true      # Enable noise modeling

# Server options
QRS_HOST=0.0.0.0
QRS_PORT=8000
QRS_LOG_LEVEL=INFO
```

### Programmatic Configuration

```python
# main.py or __main__.py

from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import LocalExecutor, GPUExecutor

# Option 1: Environment-based (default)
app = create_app()

# Option 2: Explicit local executor
app = create_app(executor=LocalExecutor())

# Option 3: GPU executor
app = create_app(executor=GPUExecutor(
    device=0,
    use_noise_model=True,
))

# Option 4: Custom executor
class MySimulator(BaseExecutor):
    def execute_sampler(self, pubs, options, backend_name):
        # Your implementation here
        pass

app = create_app(executor=MySimulator())
```

## Project Structure

```
src/qiskit_runtime_server/
├── __init__.py
├── __main__.py                 # Entry point
├── app.py                      # create_app() factory
├── config.py                   # Configuration
├── models.py                   # Pydantic models
│
├── providers/
│   ├── __init__.py
│   └── backend_metadata.py     # BackendMetadataProvider
│
├── executors/                  # ★ Executor abstraction
│   ├── __init__.py             # Exports: BaseExecutor, LocalExecutor
│   ├── base.py                 # BaseExecutor ABC
│   ├── local.py                # LocalExecutor (CPU, default)
│   └── gpu.py                  # GPUExecutor (future, placeholder)
│
├── managers/
│   ├── __init__.py
│   ├── job_manager.py          # JobManager (uses Executor)
│   └── session_manager.py      # SessionManager
│
├── routes/
│   ├── __init__.py
│   ├── backends.py             # Backend endpoints
│   ├── jobs.py                 # Job endpoints
│   └── sessions.py             # Session endpoints
│
└── utils/
    ├── __init__.py
    └── serialization.py        # RuntimeEncoder/Decoder
```

## Migration Path to GPU

### Phase 1: Current State
- `LocalExecutor` using `QiskitRuntimeLocalService`
- All execution happens on CPU
- Full API compatibility

### Phase 2: Implement GPUExecutor
1. Create `GPUExecutor` class implementing `BaseExecutor`
2. Implement `_gpu_run_sampler()` and `_gpu_run_estimator()`
3. Add noise model conversion from `BackendProperties`
4. Test with same API, different executor

### Phase 3: Configuration
1. Add `QRS_EXECUTOR=gpu` environment variable support
2. Document GPU setup requirements
3. Add GPU-specific configuration options

### Phase 4: Optimization
1. Add `HybridExecutor` for automatic CPU/GPU routing
2. Batch multiple circuits for GPU efficiency
3. Memory management for large circuits

## Summary

| Component | Responsibility | Replaceable? |
|-----------|----------------|--------------|
| BackendMetadataProvider | Backend info (topology, noise params) | No (uses FakeProvider) |
| **Executor** | **Circuit execution** | **Yes (core abstraction)** |
| JobManager | Job lifecycle | No (uses Executor) |
| SessionManager | Session/batch management | No |

The **Executor interface** is the key abstraction that enables:
- Current: CPU-based simulation via QiskitRuntimeLocalService
- Future: GPU-accelerated simulation
- Extensible: Any custom simulation backend

Backend metadata (coupling maps, T1/T2 times, gate errors) comes from FakeProvider and is reused across all Executor implementations for consistent noise modeling.
