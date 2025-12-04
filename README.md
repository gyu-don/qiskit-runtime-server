# Qiskit Runtime Server

A self-hosted IBM Qiskit Runtime compatible REST API server using Qiskit's fake backends for local quantum computing simulation and testing.

## Overview

This project provides a FastAPI-based REST API server that implements the IBM Qiskit Runtime Backend API specification, enabling local simulation using Qiskit's built-in fake backends.

## Features

- Full REST API compatibility with IBM Qiskit Runtime Backend API (v2025-05-01)
- 59 fake quantum backends from `qiskit_ibm_runtime.fake_provider`
- Support for Sampler and Estimator primitives
- Session mode (dedicated/batch) for job grouping
- Job management with async execution
- Swagger UI and ReDoc documentation
- Works with standard qiskit-ibm-runtime client using `channel="local"`

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
from qiskit_ibm_runtime import QiskitRuntimeService

# Connect to local server
service = QiskitRuntimeService(
    channel="local",  # SET THIS!!!!!!!!!
    token="test-token",
    url="http://localhost:8000",
    instance="crn:v1:bluemix:public:quantum-computing:us-east:a/local::local",
    verify=False
)

# Use like normal IBM Quantum service
backends = service.backends()  # Returns 59 fake backends
backend = service.backend("fake_manila")
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

## Configuration

### Executor Selection

The server supports pluggable executors for circuit simulation:

```bash
# Default: CPU simulation (QiskitRuntimeLocalService)
qiskit-runtime-server

# GPU simulation (when available)
QRS_EXECUTOR=gpu qiskit-runtime-server

# Or programmatically
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import GPUExecutor

app = create_app(executor=GPUExecutor(device=0))
```

### Backend Topology

Backends provide topology (coupling map) and noise parameters (T1, T2, gate errors). The executor uses this metadata for realistic simulation:

```python
# Client selects backend for topology/noise
backend = service.backend("fake_manila")  # 5-qubit Falcon r4T

# The server's executor (CPU or GPU) uses FakeManila's:
# - Coupling map: [(0,1), (1,2), (1,3), (3,4)]
# - T1, T2 relaxation times
# - Gate error rates
# - Readout errors
```

See [Backend & Executor Configuration](docs/BACKEND_EXECUTOR_CONFIG.md) for advanced options.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QRS_HOST` | `0.0.0.0` | Server host |
| `QRS_PORT` | `8000` | Server port |
| `QRS_EXECUTOR` | `local` | Executor: `local` or `gpu` |
| `QRS_LOG_LEVEL` | `INFO` | Logging level |
| `QRS_GPU_DEVICE` | `0` | GPU device ID (when executor=gpu) |

## Use Cases

- **Local Development**: Develop and test quantum algorithms without IBM Cloud access
- **CI/CD Testing**: Run quantum circuit tests in automated pipelines
- **Education**: Learn Qiskit without requiring IBM Quantum account
- **Offline Development**: Work on quantum applications without internet connectivity
- **Benchmarking**: Test circuit compilation and execution locally

## Documentation

- [API Specification](docs/API_SPECIFICATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Backend & Executor Configuration](docs/BACKEND_EXECUTOR_CONFIG.md)
- [Development Guide](docs/DEVELOPMENT.md)

## Requirements

- Python 3.10+
- qiskit-ibm-runtime >= 0.20.0

## License

Apache License 2.0

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.
