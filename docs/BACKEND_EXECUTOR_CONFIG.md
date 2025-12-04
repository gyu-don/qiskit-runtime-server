# Backend Topology and Executor Configuration

This document describes how users can configure backend topology (for noise/connectivity) independently from the executor (CPU/GPU simulation engine).

## Overview

Two independent concerns:

1. **Backend Topology**: Defines the simulated hardware characteristics
   - Qubit count and connectivity (coupling map)
   - Noise parameters (T1, T2, gate errors, readout errors)
   - Basis gates

2. **Executor**: The simulation engine that runs circuits
   - LocalExecutor (CPU)
   - GPUExecutor (GPU)
   - Custom implementations

## User Configuration Options

### Option 1: Server-Level Executor (Default)

The server administrator configures the executor at startup. All jobs use the same executor.

```bash
# Start server with GPU executor
QRS_EXECUTOR=gpu qiskit-runtime-server

# Or programmatically
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import GPUExecutor

app = create_app(executor=GPUExecutor(device=0))
```

Users submit jobs normally - they don't need to know which executor is used:

```python
# Client code
service = QiskitRuntimeService(
    channel="local",
    token="test-token",
    url="http://localhost:8000",
    instance="crn:v1:bluemix:public:quantum-computing:us-east:a/local::local",
    verify=False
)
backend = service.backend("fake_manila")  # Topology from FakeManila
sampler = SamplerV2(mode=backend)
job = sampler.run([circuit])
```

**Pros**: Simple client code, centralized control
**Cons**: No per-job executor selection

---

### Option 2: Backend Name Encodes Both Topology and Executor

Server provides virtual backends that combine topology + executor:

```
Available backends:
- fake_manila           → FakeManila topology + default executor
- fake_manila_gpu       → FakeManila topology + GPU executor
- fake_sherbrooke       → FakeSherbrooke topology + default executor
- fake_sherbrooke_gpu   → FakeSherbrooke topology + GPU executor
- ideal_20q             → 20-qubit ideal (no noise) + default executor
- ideal_20q_gpu         → 20-qubit ideal (no noise) + GPU executor
```

```python
# Client selects backend (implicitly selects executor)
backend = service.backend("fake_manila_gpu")  # GPU execution
sampler = SamplerV2(mode=backend)
```

**Pros**: Simple client API, explicit selection
**Cons**: Combinatorial explosion of backend names

---

### Option 3: Execution Options in Job Request

Users specify executor preference in job options:

```python
# Client code
sampler = SamplerV2(mode=backend)
job = sampler.run(
    [circuit],
    executor="gpu",  # New option
)
```

Server-side handling:
```python
# In job creation endpoint
executor_name = request.options.get("executor", "default")
executor = get_executor(executor_name)  # Returns GPU or CPU executor
```

**Pros**: Flexible per-job selection
**Cons**: Requires client-side awareness, may not work with standard qiskit-ibm-runtime client

---

---

### Option 5: Multiple Server Endpoints (Recommended for Simplicity)

Run separate server instances for different executors:

```bash
# Terminal 1: CPU server
QRS_PORT=8000 QRS_EXECUTOR=local qiskit-runtime-server

# Terminal 2: GPU server
QRS_PORT=8001 QRS_EXECUTOR=gpu qiskit-runtime-server
```

Users connect to the appropriate server:

```python
# For CPU simulation
service_cpu = QiskitRuntimeService(
    channel="local",
    token="test-token",
    url="http://localhost:8000",
    instance="crn:v1:bluemix:public:quantum-computing:us-east:a/local::local",
    verify=False
)

# For GPU simulation
service_gpu = QiskitRuntimeService(
    channel="local",
    token="test-token",
    url="http://localhost:8001",
    instance="crn:v1:bluemix:public:quantum-computing:us-east:a/local::local",
    verify=False
)
```

**Pros**: Clear separation, no API changes, standard client works
**Cons**: Multiple server processes

---

## Recommended Approach

### Primary: Server-Level Configuration (Option 1)

For most use cases, configure the executor at server startup:

```bash
# Environment variable
export QRS_EXECUTOR=gpu
export QRS_GPU_DEVICE=0
qiskit-runtime-server
```

Or in Python:

```python
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import GPUExecutor

executor = GPUExecutor(
    device=0,
    use_noise_model=True,  # Use noise from backend metadata
)
app = create_app(executor=executor)
```

### Secondary: Virtual Backends (Option 2)

For advanced users who need per-job executor selection, configure virtual backends:

```python
# config.py or server startup
VIRTUAL_BACKENDS = {
    # Standard backends (default executor)
    "fake_manila": {"topology": "fake_manila", "executor": "default"},
    "fake_sherbrooke": {"topology": "fake_sherbrooke", "executor": "default"},

    # GPU backends
    "fake_manila_gpu": {"topology": "fake_manila", "executor": "gpu"},
    "fake_sherbrooke_gpu": {"topology": "fake_sherbrooke", "executor": "gpu"},

    # Ideal (no noise)
    "ideal_20q": {"topology": "linear_20", "executor": "default", "noise": False},
    "ideal_127q_gpu": {"topology": "heavy_hex_127", "executor": "gpu", "noise": False},
}
```

---

## Custom Topology Configuration

Beyond FakeProvider backends, users may want custom topologies.

### Server-Side Custom Backends

```python
# custom_backends.py
from qiskit_runtime_server.providers import CustomBackend

# Define custom backend with specific topology
my_backend = CustomBackend(
    name="my_custom_chip",
    num_qubits=20,
    coupling_map=[(0,1), (1,2), (2,3), ...],  # Custom connectivity
    basis_gates=["cx", "rz", "sx", "x"],
    t1=[100e-6] * 20,  # T1 times in seconds
    t2=[80e-6] * 20,   # T2 times
    gate_errors={"cx": 0.01, "sx": 0.001},
)

# Register with server
app = create_app(
    executor=GPUExecutor(),
    custom_backends=[my_backend]
)
```

### Configuration File

```yaml
# backends.yaml
backends:
  - name: my_research_chip
    num_qubits: 50
    topology: heavy_hex  # Predefined topology pattern
    noise:
      t1_us: 100
      t2_us: 80
      cx_error: 0.01
      readout_error: 0.02

  - name: ideal_100q
    num_qubits: 100
    topology: all_to_all
    noise: none
```

```bash
# Start server with custom backends
qiskit-runtime-server --backends backends.yaml --executor gpu
```

---

## API Changes

### GET /v1/backends Response

Include executor information in backend listing:

```json
{
  "devices": [
    {
      "backend_name": "fake_manila",
      "num_qubits": 5,
      "executor": "local",
      "features": ["noise_model", "coupling_map"]
    },
    {
      "backend_name": "fake_manila_gpu",
      "num_qubits": 5,
      "executor": "gpu",
      "features": ["noise_model", "coupling_map"]
    },
    {
      "backend_name": "ideal_20q",
      "num_qubits": 20,
      "executor": "local",
      "features": ["coupling_map"]
    }
  ]
}
```

### GET /v1/server/info (New Endpoint)

```json
{
  "version": "0.1.0",
  "default_executor": "gpu",
  "available_executors": ["local", "gpu"],
  "gpu_devices": [
    {"id": 0, "name": "NVIDIA A100", "memory_gb": 40}
  ]
}
```

---

## Implementation Phases

### Phase 1: Server-Level Executor (Current Plan)
- Executor configured at server startup
- All jobs use same executor
- Backend = topology only

### Phase 2: Virtual Backends
- Backend name can include executor suffix (`_gpu`)
- Server maps to topology + executor combination

### Phase 3: Custom Backends
- YAML/JSON configuration for custom topologies
- Register custom backends at startup

### Phase 4: Runtime Executor Selection
- HTTP header or job option for per-job executor
- Requires client patch updates

---

## Summary

| Method | Complexity | Flexibility | Client Changes |
|--------|------------|-------------|----------------|
| Server-level config | Low | Low | None |
| Virtual backends | Medium | Medium | None |
| Multiple servers | Low | Medium | URL change only |
| Job options | High | High | May not work |

**Recommendation**: Start with server-level configuration (Phase 1). Add virtual backends (Phase 2) if users need per-job executor selection without running multiple servers.
