# Qiskit Runtime Server

A self-hosted IBM Qiskit Runtime compatible REST API server with multi-executor support (CPU/GPU) for local quantum computing simulation and testing.

**Current Status**: GPU support is not yet.

## Overview

This project provides a FastAPI-based REST API server that implements the IBM Qiskit Runtime Backend API specification, enabling local simulation using Qiskit's fake backends with pluggable execution backends (CPU/GPU).

## Features

- **Multi-Executor Support**: Run CPU (Aer) and GPU (cuStateVec) executors simultaneously
- **Virtual Backends**: Explicit executor selection via `<metadata>@<executor>` naming (e.g., `fake_manila@aer`, `fake_manila@custatevec`)
- **Full API Compatibility**: IBM Qiskit Runtime Backend API (v2025-05-01)
- **Sampler & Estimator**: Support for both V2 primitives
- **Session Mode**: Dedicated/batch job grouping
- **Async Job Execution**: Non-blocking job submission with FIFO queue
- **Auto-Documentation**: Swagger UI and ReDoc
- **Simple Client Setup**: Works with standard `qiskit-ibm-runtime` client via authentication patch helper

## Quick Start

### Server

```bash
# Install
uv add qiskit-runtime-server

# Or install from source
git clone https://github.com/gyu-don/qiskit-runtime-server.git
cd qiskit-runtime-server
uv sync

# Create and run the server
cp app.example.py app.py
uv run uvicorn app:app --host 0.0.0.0 --port 8000
# Server runs at http://localhost:8000
```

### Client

**Using local_service_helper.py**

The official `qiskit-ibm-runtime` client is designed for IBM Cloud and uses IBM Cloud authentication (IAM tokens). To connect to a local server without modifying the client library, use the provided helper script that patches the authentication flow.

```bash
# Download the helper script
wget https://raw.githubusercontent.com/gyu-don/qiskit-runtime-server/main/examples/local_service_helper.py

# Or copy from examples/ directory if cloned
cp qiskit-runtime-server/examples/local_service_helper.py .
```

```python
from qiskit_ibm_runtime import SamplerV2
from qiskit import QuantumCircuit, transpile
from local_service_helper import local_service_connection

# Connect to local server with context manager
with local_service_connection("http://localhost:8000") as service:
    # List available backends (default: 59 backends with @aer)
    backends = service.backends()
    # Returns: ['fake_manila@aer', 'fake_quantum_sim@aer', ...]

    # Select backend with executor
    backend = service.backend("fake_manila@aer")  # CPU executor

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

> **Why is patching needed?**
> - The client library attempts to authenticate with IBM Cloud IAM servers
> - It validates instance CRNs against IBM Cloud services
> - The helper script patches these authentication and validation flows to work with localhost or custom domains
> - This approach works without forking or modifying the `qiskit-ibm-runtime` package

**Alternative: Direct connection (not recommended)**

You can try connecting directly with `channel="local"` (deprecated since qiskit-ibm-runtime 0.15.0) or `channel="ibm_cloud"` (requires manual patching). However, these methods may not work reliably across different client library versions. **Always prefer using `local_service_helper.py`**.

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

## Server Configuration

### Quick Start

```bash
# Create application file
cp app.example.py app.py

# Run server
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

### Default Setup (CPU only)

```python
# app.py
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor

executors = {
    "aer": AerExecutor(shots=1024),
}

app = create_app(executors=executors)
```

Available backends: `fake_manila@aer`, `fake_quantum_sim@aer`, ... (59 total)

### Multi-Executor Setup (CPU + GPU)

```bash
# Install GPU support
uv sync --extra custatevec  # Requires CUDA 12.x
```

```python
# app.py
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor, CuStateVecExecutor
import os

executors = {
    "aer": AerExecutor(shots=1024),
}

# Add GPU executor if available
if os.path.exists("/dev/nvidia0"):
    executors["custatevec"] = CuStateVecExecutor(device_id=0, shots=2048)

app = create_app(executors=executors)

# Creates: 59 × 2 = 118 virtual backends
# - fake_manila@aer (CPU)
# - fake_manila@custatevec (GPU)
# - ... (all combinations)
```

### Custom Executors

```python
# app.py
from qiskit_runtime_server import create_app
from my_custom_executor import MyCustomExecutor

app = create_app(executors={
    "aer": AerExecutor(),
    "custom": MyCustomExecutor(param1="value"),
})
```

```python
# Client usage
backend_cpu = service.backend("fake_manila@aer")       # Use CPU
backend_gpu = service.backend("fake_manila@custatevec")  # Use GPU
```

### Virtual Backend Naming: `<metadata>@<executor>`

The server uses **virtual backends** with explicit executor selection through naming convention:

**Format**: `<metadata>@<executor>`

**Examples**:
- `fake_manila@aer` - Manila topology (5 qubits), CPU execution (Aer)
- `fake_manila@custatevec` - Manila topology (5 qubits), GPU execution (cuStateVec)
- `fake_quantum_sim@aer` - Generic simulator, CPU execution

**Components**:
- **Metadata** (59 fake backends from `FakeProviderForBackendV2`):
  - Backend topology (qubit count, coupling map)
  - Noise parameters (T1/T2 times, gate errors, readout errors)
  - Basis gates
  - Used by client for transpilation and noise modeling
- **Executor** (pluggable simulation engine):
  - `aer` - CPU-based simulation (qiskit-aer)
  - `custatevec` - GPU-accelerated simulation (cuQuantum)
  - Custom executors via `BaseExecutor` interface

**How it works**:
1. Client requests `fake_manila@aer` backend
2. Server provides Manila topology metadata (for client-side transpilation)
3. Client transpiles circuit to Manila topology constraints
4. Client submits job with `backend: "fake_manila@aer"`
5. Server parses backend name → routes to `aer` executor
6. Executor runs the pre-transpiled circuit

**Result**: 59 base backends × N executors = 59N total virtual backends

See [docs/BACKEND_EXECUTOR_CONFIG.md](docs/BACKEND_EXECUTOR_CONFIG.md) for complete details.

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
