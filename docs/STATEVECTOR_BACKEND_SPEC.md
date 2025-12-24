# Statevector Backend Specification

**Author**: Investigation based on AerSimulator statevector backend analysis
**Status**: Proposal
**Created**: 2025-12-24

## Table of Contents

1. [Motivation](#motivation)
2. [Background](#background)
3. [Design Overview](#design-overview)
4. [Implementation Specification](#implementation-specification)
5. [API Examples](#api-examples)
6. [Implementation Plan](#implementation-plan)
7. [Alternatives Considered](#alternatives-considered)

---

## Motivation

### Current Limitation

The current system provides 59 virtual backends from `FakeProviderForBackendV2`, all based on **real IBM Quantum hardware topologies**:

- **Hardware constraints**: Fixed qubit count, coupling maps, basis gates
- **Use case**: Realistic noise modeling and transpilation testing
- **Example**: `fake_manila@aer` has 5 qubits with specific coupling map

### Need for Statevector Backends

Many users need **topology-free, ideal simulators** for:

1. **Algorithm development**: Testing quantum algorithms without hardware constraints
2. **Large-scale simulation**: Simulating circuits with arbitrary qubit counts (up to memory limits)
3. **Ideal execution**: No noise, no topology constraints, all gates supported
4. **Performance benchmarking**: Comparing executor performance without noise overhead

### Gap Analysis

| Feature | Current (FakeProvider) | Needed (Statevector) |
|---------|------------------------|---------------------|
| Topology constraints | ✅ Real hardware coupling maps | ❌ No coupling map |
| Qubit count | ✅ Fixed (1-127 qubits) | ✅ Configurable (up to memory) |
| Noise modeling | ✅ Calibration data (T1, T2, errors) | ❌ Ideal simulation |
| Basis gates | ✅ Hardware-specific subset | ✅ All gates supported |
| Use case | Realistic simulation | Algorithm development |

**Solution**: Add statevector backends alongside existing FakeProvider backends.

---

## Background

### AerSimulator Statevector Backend Analysis

Investigation of `qiskit_aer.AerSimulator(method="statevector")` reveals:

```python
from qiskit_aer import AerSimulator

backend = AerSimulator(method="statevector")
```

**Key Properties**:

| Property | Value | Notes |
|----------|-------|-------|
| `backend.name` | `"aer_simulator_statevector"` | Auto-generated name |
| `backend.num_qubits` | `30` | Default max qubits |
| `backend.coupling_map` | `None` | No topology constraints |
| `backend.basis_gates` | 100+ gates | All standard gates + custom |
| `backend.max_shots` | `1000000` | From configuration |
| `backend.properties()` | `None` | No calibration data |
| `backend.configuration()` | `AerBackendConfiguration` | Has configuration object |
| `backend.target` | `Target` | Qiskit Target object |

**Supported Gates** (partial list):
```python
['cx', 'h', 'id', 'measure', 'reset', 'rx', 'ry', 'rz', 's', 'sdg',
 't', 'tdg', 'u', 'u1', 'u2', 'u3', 'x', 'y', 'z', 'swap', 'ccx',
 'initialize', 'unitary', ...]  # 100+ total
```

**Configuration Details**:
```python
{
    'backend_name': 'aer_simulator_statevector',
    'backend_version': '0.17.2',
    'n_qubits': 30,
    'coupling_map': None,
    'max_shots': 1000000,
    'simulator': True,
    'local': True,
    'conditional': True,
    'memory': True,
    'description': 'A C++ statevector simulator with noise'
}
```

### Comparison: AerSimulator vs FakeProvider

| Property | AerSimulator (statevector) | FakeManila (FakeProvider) |
|----------|----------------------------|---------------------------|
| `num_qubits` | 30 (configurable) | 5 (fixed) |
| `coupling_map` | `None` | `[[0,1], [1,0], [1,2], ...]` |
| `basis_gates` | 100+ gates | ~8 gates (`['cx', 'id', 'rz', 'sx', 'x', ...]`) |
| `properties()` | `None` | Calibration data (T1, T2, errors) |
| `configuration()` | ✅ Available | ✅ Available |
| Use case | Ideal simulation | Realistic simulation |

---

## Design Overview

### Hybrid Backend System

Add statevector backends **alongside** existing FakeProvider backends:

```
┌─────────────────────────────────────────────────────────────┐
│              Hybrid Backend System (Proposed)                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. FakeProvider Backends (59 backends):                   │
│     • Real hardware topologies                              │
│     • Fixed qubit counts (1-127)                            │
│     • Hardware-specific coupling maps                       │
│     • Noise calibration data                                │
│     Examples: fake_manila, fake_jakarta, fake_kyoto         │
│                                                             │
│  2. Statevector Backends (NEW):                            │
│     • Topology-free ideal simulators                        │
│     • Configurable qubit counts                             │
│     • No coupling map constraints                           │
│     • No noise (ideal simulation)                           │
│     Examples: statevector_simulator                         │
│                                                             │
│  Virtual Backends = (59 FakeProvider + N Statevector) × M Executors │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Virtual Backend Naming

Extend existing `<metadata>@<executor>` format:

| Backend Type | Virtual Backend Name | Description |
|--------------|---------------------|-------------|
| **FakeProvider** (existing) | `fake_manila@aer` | Manila topology, CPU |
| **FakeProvider** (existing) | `fake_manila@custatevec` | Manila topology, GPU |
| **Statevector** (new) | `statevector_simulator@aer` | Ideal simulator, CPU |
| **Statevector** (new) | `statevector_simulator@custatevec` | Ideal simulator, GPU |

**Key Design Decision**: Use a **reserved backend name** (e.g., `statevector_simulator`) that is not in FakeProvider to avoid naming conflicts.

---

## Implementation Specification

### 1. Backend Metadata Source

#### Option A: GenericBackendV2 (Recommended)

Use `qiskit.providers.fake_provider.GenericBackendV2` for creating statevector backend metadata:

```python
from qiskit.providers.fake_provider import GenericBackendV2

# Create ideal statevector backend metadata
statevector_backend = GenericBackendV2(
    num_qubits=30,  # Configurable
    basis_gates=['cx', 'id', 'rz', 'sx', 'x', 'reset', 'delay', 'measure'],
    coupling_map=None,  # No coupling map = fully connected
    # GenericBackendV2 automatically generates Target with no noise
)
```

**Pros**:
- ✅ Built-in Qiskit class (no external dependencies)
- ✅ Configurable qubit count
- ✅ No coupling map (fully connected)
- ✅ Compatible with BackendV2 interface
- ✅ Has `to_dict()` method for serialization

**Cons**:
- ⚠️ Smaller basis gate set than AerSimulator
- ⚠️ May need to customize basis gates list

#### Option B: AerSimulator Configuration (Alternative)

Extract configuration from `AerSimulator(method="statevector")`:

```python
from qiskit_aer import AerSimulator

# Use AerSimulator configuration as metadata template
aer_backend = AerSimulator(method="statevector")
config = aer_backend.configuration()
target = aer_backend.target
```

**Pros**:
- ✅ Comprehensive basis gate set (100+ gates)
- ✅ Matches actual AerSimulator capabilities
- ✅ Includes all custom Aer instructions

**Cons**:
- ⚠️ Tightly coupled to qiskit-aer
- ⚠️ Configuration contains Aer-specific fields
- ⚠️ May not work with non-Aer executors

**Recommendation**: Use **Option A (GenericBackendV2)** for flexibility and executor-agnostic metadata.

---

### 2. Backend Name Convention

#### Reserved Statevector Backend Names

Define reserved names that trigger statevector backend creation:

```python
STATEVECTOR_BACKEND_NAMES = [
    "statevector_simulator",
    # Future: add variants with different qubit counts?
    # "statevector_10q",
    # "statevector_20q",
    # "statevector_30q",
]
```

#### Naming Pattern

- **Pattern**: `statevector_*` (prefix)
- **Examples**:
  - `statevector_simulator` (default)
  - `statevector_10q` (10 qubits, future)
  - `statevector_30q` (30 qubits, future)

#### Virtual Backend Names

With 2 executors (aer, custatevec):

```
# FakeProvider backends (existing)
fake_manila@aer
fake_manila@custatevec
fake_jakarta@aer
fake_jakarta@custatevec
... (59 × 2 = 118 backends)

# Statevector backends (new)
statevector_simulator@aer
statevector_simulator@custatevec
```

**Total backends**: (59 FakeProvider + 1 Statevector) × 2 executors = **120 backends**

---

### 3. Modified BackendMetadataProvider

Extend `BackendMetadataProvider` to support both FakeProvider and statevector backends:

#### Class Structure

```python
class BackendMetadataProvider:
    """
    Provider for backend metadata from multiple sources:
    1. FakeProviderForBackendV2 (59 real hardware topologies)
    2. GenericBackendV2 (statevector simulators)
    """

    def __init__(
        self,
        available_executors: list[str],
        statevector_config: dict[str, Any] | None = None
    ) -> None:
        """
        Initialize the backend metadata provider.

        Args:
            available_executors: List of executor names (e.g., ["aer", "custatevec"]).
            statevector_config: Optional configuration for statevector backend.
                                Defaults to {"num_qubits": 30}.
        """
        self.available_executors = available_executors
        self.fake_provider = FakeProviderForBackendV2()

        # Statevector backend configuration
        if statevector_config is None:
            statevector_config = {"num_qubits": 30}
        self.statevector_config = statevector_config

        # Create statevector backend
        self._statevector_backend = self._create_statevector_backend()

    def _create_statevector_backend(self) -> GenericBackendV2:
        """Create statevector backend metadata."""
        return GenericBackendV2(
            num_qubits=self.statevector_config.get("num_qubits", 30),
            basis_gates=[
                'cx', 'id', 'rz', 'sx', 'x', 'h', 'y', 'z', 's', 'sdg',
                't', 'tdg', 'swap', 'ccx', 'reset', 'delay', 'measure'
            ],
            coupling_map=None,  # Fully connected
        )

    def _is_statevector_backend(self, metadata_name: str) -> bool:
        """Check if backend name is a statevector backend."""
        return metadata_name in STATEVECTOR_BACKEND_NAMES

    def _backend_exists(self, metadata_name: str) -> bool:
        """Check if a backend with the given metadata name exists."""
        # Check statevector backends
        if self._is_statevector_backend(metadata_name):
            return True

        # Check FakeProvider backends
        try:
            self.fake_provider.backend(metadata_name)
            return True
        except Exception:
            return False

    def get_backend(self, metadata_name: str) -> Any:
        """
        Get backend object by metadata name.

        Args:
            metadata_name: Backend metadata name (without executor suffix).

        Returns:
            Backend object (GenericBackendV2 or FakeProvider backend).

        Raises:
            ValueError: If backend does not exist.
        """
        if self._is_statevector_backend(metadata_name):
            # Return statevector backend with custom name
            backend = self._statevector_backend
            # Override name to match requested name
            backend._name = metadata_name
            return backend
        else:
            # Return FakeProvider backend
            return self.fake_provider.backend(metadata_name)

    def list_backends(self, fields: str | None = None) -> BackendsResponse:
        """
        Generate all virtual backends:
        - FakeProvider backends × executors
        - Statevector backends × executors

        Returns:
            BackendsResponse with virtual backend list.
        """
        virtual_backends = []

        # 1. Add FakeProvider backends
        fake_backends = self.fake_provider.backends()
        for backend in fake_backends:
            for executor_name in self.available_executors:
                virtual_name = f"{backend.name}@{executor_name}"
                backend_dict = self._backend_to_dict(backend)
                backend_dict["name"] = virtual_name
                backend_dict["backend_name"] = virtual_name
                virtual_backends.append(backend_dict)

        # 2. Add Statevector backends
        for statevector_name in STATEVECTOR_BACKEND_NAMES:
            backend = self.get_backend(statevector_name)
            for executor_name in self.available_executors:
                virtual_name = f"{statevector_name}@{executor_name}"
                backend_dict = self._backend_to_dict(backend)
                backend_dict["name"] = virtual_name
                backend_dict["backend_name"] = virtual_name
                # Override description
                backend_dict["description"] = (
                    f"Statevector simulator (ideal, no noise) on {executor_name} executor"
                )
                virtual_backends.append(backend_dict)

        return BackendsResponse(devices=virtual_backends)
```

---

### 4. Configuration Options

#### Server Configuration

Allow users to configure statevector backend parameters:

```python
from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor, CuStateVecExecutor

app = create_app(
    executors={
        "aer": AerExecutor(),
        "custatevec": CuStateVecExecutor(),
    },
    statevector_config={
        "num_qubits": 30,  # Maximum qubits for statevector backend
        "enabled": True,   # Enable/disable statevector backends
    }
)
```

#### Default Configuration

```python
DEFAULT_STATEVECTOR_CONFIG = {
    "num_qubits": 30,      # Match AerSimulator default
    "enabled": True,       # Enabled by default
}
```

---

### 5. Executor Compatibility

All executors must handle statevector backends:

```python
class BaseExecutor(ABC):
    def execute_sampler(self, pubs, options, backend_name):
        """
        Execute sampler primitive.

        Args:
            backend_name: Metadata name (e.g., "fake_manila" or "statevector_simulator")
                         WITHOUT executor suffix.
        """
        # Get backend metadata (FakeProvider or statevector)
        backend = self.get_backend(backend_name)

        # Execute circuit (same logic for both backend types)
        ...
```

**Key Point**: Executors receive `backend_name` without `@executor` suffix. They should handle both FakeProvider backends and statevector backends transparently.

---

## API Examples

### 1. List All Backends

**Request**:
```http
GET /v1/backends HTTP/1.1
```

**Response** (with 2 executors: aer, custatevec):
```json
{
  "devices": [
    {
      "backend_name": "fake_manila@aer",
      "backend_version": "2",
      "num_qubits": 5,
      "coupling_map": [[0, 1], [1, 0], ...],
      "basis_gates": ["cx", "id", "rz", "sx", "x"],
      "description": "5 qubit device"
    },
    {
      "backend_name": "fake_manila@custatevec",
      ...
    },
    ...
    {
      "backend_name": "statevector_simulator@aer",
      "backend_version": "2",
      "num_qubits": 30,
      "coupling_map": null,
      "basis_gates": ["cx", "id", "rz", "sx", "x", "h", "y", "z", ...],
      "description": "Statevector simulator (ideal, no noise) on aer executor"
    },
    {
      "backend_name": "statevector_simulator@custatevec",
      ...
    }
  ]
}
```

### 2. Get Statevector Backend Configuration

**Request**:
```http
GET /v1/backends/statevector_simulator@aer/configuration HTTP/1.1
```

**Response**:
```json
{
  "backend_name": "statevector_simulator@aer",
  "backend_version": "2",
  "num_qubits": 30,
  "coupling_map": null,
  "basis_gates": ["cx", "id", "rz", "sx", "x", "h", "y", "z", ...],
  "max_shots": 1000000,
  "simulator": true,
  "local": true,
  "conditional": true,
  "memory": true,
  "description": "Statevector simulator (ideal, no noise) on aer executor",
  "supported_instructions": ["cx", "id", "rz", ...]
}
```

### 3. Client Usage

#### Example 1: Use Statevector Backend

```python
from qiskit_ibm_runtime import SamplerV2
from qiskit import QuantumCircuit
from local_service_helper import local_service_connection

with local_service_connection("http://localhost:8000") as service:
    # List backends
    backends = service.backends()
    # Returns: ['fake_manila@aer', ..., 'statevector_simulator@aer', ...]

    # Select statevector backend with CPU executor
    backend = service.backend("statevector_simulator@aer")

    # Create circuit (no transpilation needed - all gates supported)
    circuit = QuantumCircuit(10)  # 10 qubits
    circuit.h(0)
    for i in range(9):
        circuit.cx(i, i + 1)
    circuit.measure_all()

    # Run on ideal simulator
    sampler = SamplerV2(mode=backend)
    job = sampler.run([circuit])
    result = job.result()
    print(result[0].data.meas.get_counts())
```

#### Example 2: Compare CPU vs GPU Performance

```python
from qiskit import QuantumCircuit
from qiskit_ibm_runtime import SamplerV2
from local_service_helper import local_service_connection
import time

with local_service_connection("http://localhost:8000") as service:
    # Create large circuit
    circuit = QuantumCircuit(20)
    for i in range(20):
        circuit.h(i)
    for i in range(19):
        circuit.cx(i, i + 1)
    circuit.measure_all()

    # Run on CPU executor
    backend_cpu = service.backend("statevector_simulator@aer")
    sampler_cpu = SamplerV2(mode=backend_cpu)
    start = time.time()
    job_cpu = sampler_cpu.run([circuit])
    result_cpu = job_cpu.result()
    cpu_time = time.time() - start

    # Run on GPU executor
    backend_gpu = service.backend("statevector_simulator@custatevec")
    sampler_gpu = SamplerV2(mode=backend_gpu)
    start = time.time()
    job_gpu = sampler_gpu.run([circuit])
    result_gpu = job_gpu.result()
    gpu_time = time.time() - start

    print(f"CPU time: {cpu_time:.2f}s")
    print(f"GPU time: {gpu_time:.2f}s")
    print(f"Speedup: {cpu_time / gpu_time:.2f}x")
```

#### Example 3: Algorithm Development (No Topology Constraints)

```python
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT
from qiskit_ibm_runtime import SamplerV2
from local_service_helper import local_service_connection

with local_service_connection("http://localhost:8000") as service:
    # Use statevector backend for algorithm development
    backend = service.backend("statevector_simulator@aer")

    # Create QFT circuit (no need to worry about coupling map)
    qft = QFT(num_qubits=15, do_swaps=True)
    circuit = QuantumCircuit(15)
    circuit.compose(qft, inplace=True)
    circuit.measure_all()

    # Run without transpilation (ideal simulator supports all gates)
    sampler = SamplerV2(mode=backend)
    job = sampler.run([circuit])
    result = job.result()
```

---

## Implementation Plan

### Phase 1: Core Implementation

1. **Define statevector backend names** (`STATEVECTOR_BACKEND_NAMES`)
2. **Extend `BackendMetadataProvider`**:
   - Add `_create_statevector_backend()` method
   - Add `_is_statevector_backend()` method
   - Modify `_backend_exists()` to check statevector backends
   - Modify `get_backend()` to return statevector backends
   - Modify `list_backends()` to include statevector × executor combinations
3. **Add configuration parameter** to `create_app()`:
   - `statevector_config: dict[str, Any] | None = None`
4. **Update tests**:
   - Test statevector backend listing
   - Test statevector backend configuration endpoint
   - Test job execution with statevector backends

### Phase 2: Configuration & Documentation

5. **Add configuration options**:
   - `num_qubits`: Maximum qubits (default: 30)
   - `enabled`: Enable/disable statevector backends (default: True)
6. **Update documentation**:
   - `BACKEND_EXECUTOR_CONFIG.md`: Add statevector backend section
   - `ARCHITECTURE.md`: Update backend metadata provider section
   - `README.md`: Add statevector backend examples
7. **Add examples**:
   - `examples/06_statevector_backend.py`
   - `examples/07_cpu_gpu_comparison.py`

### Phase 3: Advanced Features (Future)

8. **Multiple statevector variants** (optional):
   - `statevector_10q`, `statevector_20q`, `statevector_30q`
   - Different qubit counts for different use cases
9. **Custom basis gates** (optional):
   - Allow users to customize basis gate set
   - Match executor capabilities
10. **Noise injection** (optional):
    - Add noise models to statevector backends
    - Use `AerSimulator(method="statevector", noise_model=...)`

---

## Alternatives Considered

### Alternative 1: Separate Statevector Endpoints

Create separate API endpoints for statevector backends:

```
GET /v1/statevector-backends
GET /v1/statevector-backends/{backend_name}/configuration
```

**Pros**:
- Clear separation between FakeProvider and statevector backends
- No naming conflicts

**Cons**:
- ❌ Requires client-side modifications
- ❌ Not compatible with standard `qiskit-ibm-runtime` client
- ❌ More complex API surface

**Decision**: ❌ Not adopted. Use unified `/v1/backends` endpoint with hybrid backend list.

### Alternative 2: Executor-Specific Statevector Backends

Create statevector backends per executor (no virtual backend multiplication):

```
aer_statevector
custatevec_statevector
```

**Pros**:
- Explicit executor in backend name
- No @ suffix needed

**Cons**:
- ❌ Breaks `<metadata>@<executor>` naming convention
- ❌ Less flexible (can't switch executors for same metadata)
- ❌ Inconsistent with existing virtual backend system

**Decision**: ❌ Not adopted. Use consistent `statevector_simulator@executor` format.

### Alternative 3: Use AerSimulator as Default Backend

Add AerSimulator statevector backend directly to FakeProvider:

```python
# Monkey-patch FakeProvider to include AerSimulator
fake_provider.add_backend(AerSimulator(method="statevector"))
```

**Pros**:
- Reuses existing AerSimulator
- No need to create GenericBackendV2

**Cons**:
- ❌ Tightly coupled to qiskit-aer
- ❌ Doesn't work with non-Aer executors
- ❌ Modifies external library behavior

**Decision**: ❌ Not adopted. Use GenericBackendV2 for executor-agnostic metadata.

---

## Summary

### Key Design Decisions

1. ✅ **Hybrid backend system**: FakeProvider (59) + Statevector (1+) backends
2. ✅ **Unified naming**: Use `statevector_simulator@executor` format
3. ✅ **GenericBackendV2**: Use for statevector backend metadata (executor-agnostic)
4. ✅ **Reserved names**: `statevector_*` prefix for statevector backends
5. ✅ **Configuration**: Allow customization via `statevector_config` parameter
6. ✅ **Backward compatibility**: Existing FakeProvider backends unchanged

### Benefits

- ✅ **Topology-free simulation**: No coupling map constraints
- ✅ **Ideal execution**: No noise, all gates supported
- ✅ **Executor flexibility**: Works with any executor (CPU, GPU, custom)
- ✅ **Standard client**: No modifications to `qiskit-ibm-runtime` client
- ✅ **Unified API**: Single `/v1/backends` endpoint for all backends
- ✅ **Backward compatible**: Existing backends and virtual backend system unchanged

### Trade-offs

- ⚠️ **Basis gate set**: GenericBackendV2 has smaller gate set than AerSimulator (can be customized)
- ⚠️ **Backend list growth**: Adds N backends (1 statevector × N executors)

### Total Backend Count

| Backend Type | Base Count | Executors | Total |
|--------------|------------|-----------|-------|
| FakeProvider | 59 | 2 (aer, custatevec) | 118 |
| Statevector | 1 | 2 (aer, custatevec) | 2 |
| **Total** | **60** | **2** | **120** |

**Impact**: +2 backends with 2 executors (minimal increase).

---

## Next Steps

1. ✅ Review this specification
2. ⏳ Implement Phase 1 (core implementation)
3. ⏳ Write tests for statevector backends
4. ⏳ Update documentation
5. ⏳ Add examples
6. ⏳ Consider Phase 3 (advanced features)

---

## References

- **Investigation Script**: `investigate_statevector.py`
- **Current Architecture**: `docs/ARCHITECTURE.md`
- **Backend Executor Config**: `docs/BACKEND_EXECUTOR_CONFIG.md`
- **Design Decisions**: `docs/DESIGN_DECISIONS.md`
- **Qiskit Documentation**: https://docs.quantum.ibm.com/api/qiskit/providers_fake_provider
- **Aer Documentation**: https://qiskit.github.io/qiskit-aer/
