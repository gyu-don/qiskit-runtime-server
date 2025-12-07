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

# Create and run the server
cp app.example.py app.py
uv run uvicorn app:app --host 0.0.0.0 --port 8000
# Server runs at http://localhost:8000
```

### Client

**Option 1: Using local_service_helper.py (Recommended)**

```bash
# Download the helper script
wget https://raw.githubusercontent.com/gyu-don/qiskit-runtime-server/main/examples/local_service_helper.py

# Or copy from examples/ directory if cloned
cp qiskit-runtime-server/examples/local_service_helper.py .
```

```python
from qiskit_ibm_runtime import SamplerV2
from qiskit.circuit.random import random_circuit
from local_service_helper import local_service_connection

# Connect to local server with context manager
with local_service_connection("http://localhost:8000") as service:
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

**Option 2: Using channel="local" (Limited compatibility)**

```python
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit.circuit.random import random_circuit

# Connect to local server
# NOTE: This may not work with all qiskit-ibm-runtime versions
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

> **Why use local_service_helper.py?**
> The official `qiskit-ibm-runtime` client is designed for IBM Cloud and may have authentication issues with local servers. The helper script patches these authentication flows to enable seamless local server connection.

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
