# Backend Topology and Executor Configuration

This document describes the virtual backend system that allows users to configure backend topology (for metadata) independently from the executor (CPU/GPU simulation engine).

## Overview

Two independent concerns:

1. **Backend Topology (Metadata)**: Defines the simulated hardware characteristics
   - Qubit count and connectivity (coupling map)
   - Noise parameters (T1, T2, gate errors, readout errors)
   - Basis gates
   - **Source**: `FakeProviderForBackendV2` (59 fake backends)
   - **Purpose**: Metadata reference for client-side transpilation

2. **Executor**: The simulation engine that runs circuits
   - `AerExecutor` (CPU) - qiskit-aer based simulation
   - `CuStateVecExecutor` (GPU) - cuQuantum cuStateVec based simulation
   - Custom implementations via `BaseExecutor`
   - **Purpose**: Circuit execution (no topology validation)

**Virtual Backend Naming**: `<metadata>@<executor>` format (e.g., `fake_manila@aer`)

---

## Current Implementation: Virtual Backends ✅

The server uses **virtual backends** with `<metadata>@<executor>` naming to provide explicit executor selection.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Virtual Backend System                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Base Metadata (59 FakeProvider backends):                 │
│    • fake_manila, fake_quantum_sim, fake_jakarta, ...       │
│                                                             │
│  Executors (configurable):                                 │
│    • aer (CPU)                                              │
│    • custatevec (GPU)                                       │
│    • custom (user-defined)                                  │
│                                                             │
│  Virtual Backends (metadata × executors):                  │
│    • fake_manila@aer                                        │
│    • fake_manila@custatevec                                 │
│    • fake_quantum_sim@aer                                   │
│    • fake_quantum_sim@custatevec                            │
│    • ... (59 × N total)                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Server Setup

#### Default Setup (Single Executor - CPU only)

```python
from qiskit_runtime_server import create_app

# Default: Aer executor only
app = create_app()

# Available backends: fake_manila@aer, fake_quantum_sim@aer, ... (59 total)
```

#### Multi-Executor Setup (CPU + GPU)

```python
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor, CuStateVecExecutor

# Multiple executors
app = create_app(executors={
    "aer": AerExecutor(),
    "custatevec": CuStateVecExecutor(),
})

# Available backends: 59 × 2 = 118 virtual backends
# fake_manila@aer, fake_manila@custatevec, fake_quantum_sim@aer, ...
```

#### Custom Executor Setup

See [ARCHITECTURE.md](ARCHITECTURE.md#executor-interface) for details on implementing custom executors.

```python
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor

# Use custom executor
app = create_app(executors={
    "aer": AerExecutor(),
    "custom": MyCustomExecutor(),  # Your BaseExecutor subclass
})

# Available backends: fake_manila@aer, fake_manila@custom, ... (59 × 2)
```

### Client Usage

```python
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit.circuit.random import random_circuit

service = QiskitRuntimeService(
    channel="local",
    url="http://localhost:8000",
    token="test-token",
    instance="crn:v1:bluemix:public:quantum-computing:us-east:a/local::local",
    verify=False
)

# List all available backends
backends = service.backends()
# Returns: ['fake_manila@aer', 'fake_manila@custatevec', ...]

# Select backend with explicit executor
backend_cpu = service.backend("fake_manila@aer")  # CPU executor
backend_gpu = service.backend("fake_manila@custatevec")  # GPU executor

# Use CPU executor
sampler_cpu = SamplerV2(mode=backend_cpu)
circuit = random_circuit(5, 2)
job_cpu = sampler_cpu.run([circuit])
result_cpu = job_cpu.result()

# Use GPU executor
sampler_gpu = SamplerV2(mode=backend_gpu)
job_gpu = sampler_gpu.run([circuit])
result_gpu = job_gpu.result()
```

### Benefits

✅ **Simple client API**: Standard `qiskit-ibm-runtime` client works as-is
✅ **Explicit executor selection**: Users specify executor in backend name
✅ **No client modifications**: No custom patches or forks required
✅ **Single server instance**: Can host multiple executors simultaneously
✅ **Dynamic backend list**: Automatically generated (metadata × executors)
✅ **Flexible deployment**: Easy to add/remove executors

### Trade-offs

⚠️ **Backend list grows linearly**: 59 base backends × N executors
⚠️ **Executor specification required**: Backend name must include `@executor` suffix

---

## Backend Metadata vs. Execution

**Important Design Principle**: The `backend_name` parameter passed to executors is for **metadata reference only**. Executors do **not** validate topology constraints or basis gates.

### Separation of Concerns

```
┌─────────────────────────────────────────────────────────────┐
│                  Separation of Concerns                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CLIENT-SIDE (qiskit-ibm-runtime):                          │
│    • Fetch backend metadata (topology, basis gates)         │
│    • Transpile circuits for target backend                  │
│    • Submit pre-transpiled circuits                         │
│                                                             │
│  SERVER-SIDE (qiskit-runtime-server):                       │
│    • Provide backend metadata                               │
│    • Execute circuits as-is (no validation)                 │
│    • Return results                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### What backend_name IS Used For

- ✅ **Metadata lookup**: Retrieve backend properties for client-side transpilation
- ✅ **Future noise modeling**: Reserved for future implementations
- ✅ **Logging**: Track which backend metadata was requested
- ✅ **API compatibility**: Maintain IBM Quantum API compatibility

### What backend_name IS NOT Used For

- ❌ **Topology validation**: No checking if circuit respects coupling map
- ❌ **Basis gate validation**: No checking if gates match backend basis gates
- ❌ **Noise modeling**: Current implementation performs ideal simulation
- ❌ **Circuit rejection**: Executors never reject circuits based on backend_name

**See Also**: [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md#12-executor-backend_name-parameter-frontend-only-checking) for detailed rationale.

---

## Virtual Backend Naming Convention

### Format

```
<metadata>@<executor>
```

### Examples

| Virtual Backend Name | Metadata Source | Executor | Description |
|---------------------|-----------------|----------|-------------|
| `fake_manila@aer` | FakeManila | AerExecutor | Manila topology, CPU simulation |
| `fake_manila@custatevec` | FakeManila | CuStateVecExecutor | Manila topology, GPU simulation |
| `fake_quantum_sim@aer` | FakeQuantumSim | AerExecutor | QuantumSim topology, CPU |
| `fake_jakarta@custom` | FakeJakarta | Custom executor | Jakarta topology, custom |

### Parsing

Server-side parsing logic:

```python
backend_name = "fake_manila@aer"
metadata_name, executor_name = backend_name.split("@", 1)

# metadata_name = "fake_manila"
# executor_name = "aer"
```

Client-side usage:

```python
# Standard qiskit-ibm-runtime client
backend = service.backend("fake_manila@aer")

# Backend name is opaque to client - it just passes the string
# Server parses and routes to correct executor
```

---

## Available Base Backends

The server provides 59 base backends from `FakeProviderForBackendV2`:

### IBM Quantum System Backends (Real Hardware Topologies)

```
fake_almaden, fake_armonk, fake_athens, fake_auckland, fake_belem,
fake_boeblingen, fake_bogota, fake_brooklyn, fake_burlington, fake_cairo,
fake_cambridge, fake_casablanca, fake_cusco, fake_essex, fake_geneva,
fake_guadalupe, fake_hanoi, fake_jakarta, fake_johannesburg, fake_kawasaki,
fake_kolkata, fake_kyiv, fake_kyoto, fake_lagos, fake_lima, fake_london,
fake_manhattan, fake_manila, fake_melbourne, fake_montreal, fake_mumbai,
fake_nairobi, fake_oracle, fake_oslo, fake_ourense, fake_paris, fake_peekskill,
fake_perth, fake_prague, fake_poughkeepsie, fake_quito, fake_rochester,
fake_rome, fake_rueschlikon, fake_santiago, fake_sherbrooke, fake_singapore,
fake_sydney, fake_tenerife, fake_tokyo, fake_toronto, fake_valencia,
fake_vigo, fake_washington, fake_yorktown
```

### Simulators

```
fake_5q, fake_7q, fake_20q, fake_27q, fake_127q, fake_quantum_sim
```

**Total**: 59 base backends × N executors = 59N virtual backends

---

## API Endpoints

### GET /v1/backends

Returns all virtual backends (metadata × executor combinations).

**Response example** (with 2 executors: aer, custatevec):

```json
{
  "devices": [
    {
      "backend_name": "fake_manila@aer",
      "backend_version": "2",
      "num_qubits": 5,
      ...
    },
    {
      "backend_name": "fake_manila@custatevec",
      "backend_version": "2",
      "num_qubits": 5,
      ...
    },
    ...
  ]
}
```

### GET /v1/backends/{backend_name}/configuration

Returns backend configuration (topology, basis gates, etc.).

**Example**: `GET /v1/backends/fake_manila@aer/configuration`

Returns the same metadata as `fake_manila` (executor is ignored for metadata).

### GET /v1/backends/{backend_name}/properties

Returns backend properties (noise parameters).

**Example**: `GET /v1/backends/fake_manila@custatevec/properties`

Returns the same properties as `fake_manila` (executor is ignored for metadata).

---

## Alternatives Considered (Not Implemented)

The following alternatives were considered but **not implemented**. Only virtual backends (`<metadata>@<executor>`) are supported.

### Option 1: Server-Level Executor Configuration

**Concept**: Server configured with single executor at startup. All jobs use the same executor.

```python
# Not implemented
app = create_app(executor=GPUExecutor())
```

**Why not implemented**:
- No per-job executor selection
- Requires multiple server instances for CPU + GPU
- Less flexible than virtual backends

### Option 3: Execution Options in Job Request

**Concept**: Users specify executor in job options.

```python
# Not implemented
job = sampler.run([circuit], executor="gpu")
```

**Why not implemented**:
- Requires client-side modifications
- May not work with standard `qiskit-ibm-runtime` client
- More complex than virtual backend naming

### Option 5: Multiple Server Endpoints

**Concept**: Run separate server instances for different executors.

```bash
# Not implemented
QRS_PORT=8000 QRS_EXECUTOR=local qiskit-runtime-server  # CPU
QRS_PORT=8001 QRS_EXECUTOR=gpu qiskit-runtime-server    # GPU
```

**Why not implemented**:
- Requires multiple processes
- More complex deployment
- Virtual backends provide same functionality in single instance

---

## Summary Table

| Method | Complexity | Flexibility | Client Changes | Status |
|--------|------------|-------------|----------------|--------|
| **Virtual backends (`<metadata>@<executor>`)** | **Medium** | **High** | **None** | ✅ **Implemented** |
| Server-level executor | Low | Low | None | ❌ Not implemented |
| Multiple servers | Low | Medium | URL change only | ❌ Not implemented |
| Job options | High | High | May not work | ❌ Not implemented |
| Custom backends (YAML/JSON config) | High | High | None | ❌ Not implemented |

**Current Implementation**: Virtual backends with `<metadata>@<executor>` naming provides the best balance of flexibility and simplicity. Users can explicitly select executors via backend names without any client-side modifications.

---

## See Also

- **[ARCHITECTURE.md](ARCHITECTURE.md)**: System architecture and component details
- **[DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)**: Design rationale and alternatives
- **[IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md)**: Current implementation status
- **[API_SPECIFICATION.md](API_SPECIFICATION.md)**: Complete REST API reference
