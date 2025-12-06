# Qiskit Runtime Server

A self-hosted IBM Qiskit Runtime compatible REST API server with multi-executor support (CPU/GPU) for local quantum computing simulation and testing.

**Current Status**: GPU support is not yet.

## Overview

This project provides a FastAPI-based REST API server that implements the IBM Qiskit Runtime Backend API specification, enabling local simulation using Qiskit's fake backends with pluggable execution backends (CPU/GPU).

## Features

- **Multi-Executor Support**: Run CPU (Aer) and GPU (cuStateVec) executors simultaneously
- **Virtual Backends**: 59 fake backends × N executors (e.g., `fake_manila@aer`, `fake_manila@custatevec`)
- **Full API Compatibility**: IBM Qiskit Runtime Backend API (v2025-05-01)
- **Sampler & Estimator**: Support for both V2 primitives
- **Session Mode**: Dedicated/batch job grouping
- **Async Job Execution**: Non-blocking job submission with FIFO queue
- **Auto-Documentation**: Swagger UI and ReDoc
- **Zero Client Changes**: Works with standard `qiskit-ibm-runtime` client using `channel="local"`

## Quick Start

### Server

```bash
# Install
uv add qiskit-runtime-server

# Or install from source
git clone https://github.com/gyu-don/qiskit-runtime-server.git
cd qiskit-runtime-server
uv sync

# Run the server
uv run qiskit-runtime-server
# Server runs at http://localhost:8000
```

### Client

```python
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit.circuit.random import random_circuit

# Connect to local server
service = QiskitRuntimeService(
    channel="local",  # REQUIRED for localhost
    token="test-token",
    url="http://localhost:8000",
    instance="crn:v1:bluemix:public:quantum-computing:us-east:a/local::local",
    verify=False
)

# List available backends (default: 59 backends with @aer)
backends = service.backends()
# Returns: ['fake_manila@aer', 'fake_quantum_sim@aer', ...]

# Select backend with executor
backend = service.backend("fake_manila@aer")  # CPU executor

# Run circuit
sampler = SamplerV2(mode=backend)
circuit = random_circuit(5, 2)
job = sampler.run([circuit])
result = job.result()
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/backends` | List all available backends |
| GET | `/v1/backends/{id}/configuration` | Get backend configuration |
| GET | `/v1/backends/{id}/properties` | Get calibration properties |
| GET | `/v1/backends/{id}/status` | Get operational status |
| GET | `/v1/backends/{id}/defaults` | Get pulse defaults |
| POST | `/v1/jobs` | Create and execute job |
| GET | `/v1/jobs/{id}` | Get job status |
| GET | `/v1/jobs/{id}/results` | Get job results |
| DELETE | `/v1/jobs/{id}` | Cancel job |
| POST | `/v1/sessions` | Create session |
| GET | `/v1/sessions/{id}` | Get session details |
| PATCH | `/v1/sessions/{id}` | Update session |
| DELETE | `/v1/sessions/{id}/close` | Cancel session |

## Multi-Executor Configuration

### Default Setup (CPU only)

```bash
# Server startup with default Aer executor
uv run qiskit-runtime-server

# Available backends: fake_manila@aer, fake_quantum_sim@aer, ... (59 total)
```

### Multi-Executor Setup (CPU + GPU)

```bash
# Install with GPU support
uv sync --extra custatevec  # Requires CUDA 12.x
```

```python
# Server configuration
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor, CuStateVecExecutor

app = create_app(executors={
    "aer": AerExecutor(),                # CPU
    "custatevec": CuStateVecExecutor(),  # GPU
})

# Creates: 59 × 2 = 118 virtual backends
# - fake_manila@aer (CPU)
# - fake_manila@custatevec (GPU)
# - ... (all combinations)
```

```python
# Client usage
backend_cpu = service.backend("fake_manila@aer")       # Use CPU
backend_gpu = service.backend("fake_manila@custatevec")  # Use GPU
```

### Virtual Backend System

The server uses `<metadata>@<executor>` naming to provide explicit executor selection:

- **Metadata**: 59 fake backends from `FakeProviderForBackendV2` (topology, noise parameters)
- **Executor**: Simulation engine (CPU via Aer, GPU via cuStateVec, or custom)
- **Result**: Dynamic virtual backend generation (metadata × executor combinations)

See [docs/BACKEND_EXECUTOR_CONFIG.md](docs/BACKEND_EXECUTOR_CONFIG.md) for details.

## Use Cases

- **Local Development**: Develop and test quantum algorithms without IBM Cloud access
- **GPU Acceleration**: Run large-scale quantum simulations with GPU support
- **CI/CD Testing**: Run quantum circuit tests in automated pipelines
- **Education**: Learn Qiskit without requiring IBM Quantum account
- **Offline Development**: Work on quantum applications without internet connectivity
- **Executor Comparison**: Benchmark CPU vs GPU performance on same circuits

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** - Multi-executor system architecture
- **[Backend & Executor Configuration](docs/BACKEND_EXECUTOR_CONFIG.md)** - Virtual backend system and executor setup
- **[API Specification](docs/API_SPECIFICATION.md)** - Complete REST API reference
- **[Design Decisions](docs/DESIGN_DECISIONS.md)** - Design rationale and alternatives
- **[Development Guide](docs/DEVELOPMENT.md)** - Development workflow and testing
- **[Implementation Status](IMPLEMENTATION_STATUS.md)** - Phase 3 completion status

## Requirements

- Python 3.12+
- qiskit-ibm-runtime >= 0.43.1
- qiskit-aer >= 0.17.2
- FastAPI >= 0.123.8

**Optional** (GPU support):
- CUDA 12.x
- cuquantum-python >= 25.11.0 (install via `uv sync --extra custatevec`)

## License

Apache License 2.0

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.
