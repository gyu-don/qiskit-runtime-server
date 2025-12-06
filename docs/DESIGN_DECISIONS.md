# Design Decisions

This document captures key design decisions made for the Qiskit Runtime Server project, including rationale and alternatives considered.

## 1. Executor Abstraction (Core Architecture)

### Decision
Separate backend metadata (what hardware looks like) from circuit execution (how circuits are run) via a pluggable **Executor interface**.

### Rationale
- **Future-proofing**: Enable GPU simulator replacement without API changes
- **Separation of concerns**: Metadata (topology, noise params) is independent of execution engine
- **Reuse**: FakeProvider backends provide realistic metadata for any executor
- **Testability**: Can mock executor for testing

### Interface
```python
class BaseExecutor(ABC):
    def execute_sampler(self, pubs, options, backend_name) -> PrimitiveResult: ...
    def execute_estimator(self, pubs, options, backend_name) -> PrimitiveResult: ...
```

### Implementations
- `LocalExecutor`: Uses `QiskitRuntimeLocalService` (CPU, current)
- `GPUExecutor`: Will use GPU simulator (future)

### Alternatives Considered
- **Direct QiskitRuntimeLocalService**: Would require code changes for GPU
- **Strategy pattern per-job**: Too fine-grained, adds overhead
- **Plugin system**: More complex than needed for known use cases

---

## 2. Use of `uv` for Package Management

### Decision
Use `uv` instead of pip/poetry/pdm for package management.

### Rationale
- **Speed**: uv is significantly faster than alternatives
- **Lock file**: Deterministic builds with `uv.lock`
- **Modern tooling**: Integrates well with ruff, modern Python ecosystem
- **Simplicity**: Single tool for venv, install, run

### Alternatives Considered
- **pip + requirements.txt**: No lock file, less reproducible
- **Poetry**: Slower, more complex configuration
- **pdm**: Less widespread adoption

---

## 3. In-Memory Storage for Jobs/Sessions

### Decision
Store jobs and sessions in Python dictionaries with threading locks, no persistence.

### Rationale
- **Simplicity**: No database setup required
- **Use case fit**: Designed for development/testing, not production
- **Performance**: No I/O overhead for job operations
- **Stateless restart**: Fresh state is acceptable for local testing

### Alternatives Considered
- **SQLite**: Would add persistence but complicate setup
- **Redis**: Overkill for single-user local testing
- **File-based**: Would add I/O overhead without significant benefit

### Future Consideration
If production use becomes a requirement, database integration would be the first enhancement.

---

## 4. FastAPI for REST API

### Decision
Use FastAPI for the REST API implementation.

### Rationale
- **Automatic documentation**: Swagger/OpenAPI generated from code
- **Type validation**: Pydantic integration for request/response validation
- **Performance**: ASGI-based, async-capable
- **Python ecosystem**: Well-integrated with modern Python tooling

### Alternatives Considered
- **Flask**: Less automatic type validation, no built-in async
- **Django REST Framework**: Heavier, more opinionated
- **Starlette directly**: Less convenient than FastAPI's abstractions

---

## 5. Pydantic v2 for Data Models

### Decision
Use Pydantic v2 for all request/response models.

### Rationale
- **Performance**: Pydantic v2 is significantly faster than v1
- **Type safety**: Runtime type validation
- **Serialization**: Built-in JSON serialization with customization
- **FastAPI integration**: Native support in FastAPI

### Alternatives Considered
- **dataclasses**: No built-in validation or serialization
- **attrs**: Less common in FastAPI ecosystem
- **TypedDict**: No runtime validation

---

## 6. Dependency Injection for Executor

### Decision
Use dependency injection to provide Executor to JobManager via `create_app()`.

### Rationale
- **Swappable**: Easy to replace executor (CPU → GPU)
- **Testable**: Can inject mock executor for testing
- **Configurable**: Different executors for different environments
- **Clean architecture**: Explicit dependencies, no hidden globals

### Pattern
```python
def create_app(executor: BaseExecutor = None) -> FastAPI:
    executor = executor or LocalExecutor()
    job_manager = JobManager(executor=executor)
    ...
```

### Alternatives Considered
- **Global singleton**: Less flexible, harder to test
- **Factory per request**: Wasteful for stateless executor
- **Plugin system**: Over-engineered for known use cases

---

## 7. Async Queue Architecture with Single Worker Thread

### Decision
Use an async job queue with a single worker thread for sequential job execution.

### Rationale
- **Non-blocking API**: API returns immediately with job ID (202 Accepted)
- **Sequential execution**: Only one job runs at a time, preventing resource contention
- **Simple implementation**: Single worker thread is easier to debug than parallel execution
- **Resource management**: Prevents GPU/CPU memory conflicts
- **Predictable behavior**: FIFO queue ensures fair scheduling and predictable execution order
- **Future extensible**: Easy to scale to multiple workers when needed

### Architecture
```
Client → POST /v1/jobs → JobManager.create_job()
                              ↓
                         Jobs added to queue.Queue (FIFO)
                              ↓
                         Worker thread picks jobs one at a time
                              ↓
                         Executor.execute_sampler/estimator()
                              ↓
                         Results stored in JobInfo
```

### Job Status Flow
```
POST /v1/jobs (202 Accepted)
     ↓
  QUEUED → RUNNING → COMPLETED
     │        │           ↑
     │        └─→ FAILED ─┘
     └───────→ CANCELLED
```

### Implementation Details
- **queue.Queue**: Thread-safe FIFO queue with automatic locking
- **Single worker thread**: Daemon thread that continuously polls the queue
- **Graceful shutdown**: `shutdown()` method stops worker thread cleanly
- **Job cancellation**: Only QUEUED jobs can be cancelled (RUNNING jobs continue)

### Alternatives Considered
- **Direct threading per job**: Would allow parallel execution but risk resource contention
- **Async/await**: Quantum simulation is CPU-bound, not I/O-bound; threading is more appropriate
- **Process pool**: Overkill for single-user local testing, adds complexity
- **Celery/RQ**: External dependency not justified for local development server
- **Multiple workers immediately**: Decided to start simple with single worker, add parallelization later if needed

### Future Enhancements
- **Multiple workers**: Add worker pool for parallel execution when resource management is implemented
- **Resource-aware scheduling**: Separate CPU and GPU queues with dedicated workers
- **Priority queue**: Support job priorities for advanced scheduling

### Why Single Worker?
1. **Resource contention prevention**: GPU simulators need exclusive memory access
2. **Debugging simplicity**: Predictable execution order makes debugging easier
3. **Implementation simplicity**: No need for complex synchronization or resource locking
4. **Good enough for local testing**: Single-user development doesn't need parallelization

### Reference
- Implementation: `src/qiskit_runtime_server/managers/job_manager.py`
- Design document: `tmp/design-phase3-async-queue.md`

---

## 8. API Version Header Validation

### Decision
Require `IBM-API-Version` header and validate against supported versions.

### Rationale
- **IBM compatibility**: Matches real IBM Quantum API behavior
- **Future-proofing**: Can handle version-specific behavior
- **Client validation**: Ensures clients explicitly specify version

### Supported Versions
- `2024-01-01`
- `2025-01-01`
- `2025-05-01` (current)

---

## 9. RuntimeEncoder/RuntimeDecoder for Serialization

### Decision
Use qiskit-ibm-runtime's RuntimeEncoder/RuntimeDecoder for job params and results.

### Rationale
- **Qiskit object handling**: Properly serializes QuantumCircuit, SparsePauliOp, etc.
- **Client compatibility**: Same serialization as IBM Quantum uses
- **Round-trip fidelity**: Objects serialize and deserialize correctly

### Implementation
- Job params: Deserialized on server with RuntimeDecoder
- Job results: Serialized on server with RuntimeEncoder, deserialized by client

---

## 10. Pre-commit Hooks as Mandatory

### Decision
Require pre-commit hooks installation for all contributors.

### Rationale
- **Consistency**: All code follows same formatting/linting rules
- **Early detection**: Catch issues before CI
- **Developer experience**: Auto-fix most issues locally
- **CI time savings**: Fewer failing PRs due to formatting

### Hooks Used
- ruff (lint + format)
- mypy (type check)
- trailing whitespace, YAML check, etc.

---

## 11. Strict Type Checking

### Decision
Enable strict mode in mypy configuration.

### Rationale
- **Bug prevention**: Catch type errors before runtime
- **Documentation**: Types serve as documentation
- **IDE support**: Better autocomplete and error detection
- **Code quality**: Forces explicit handling of optional types

### Configuration
```toml
[tool.mypy]
strict = true
```

---

## 12. Executor backend_name Parameter: Frontend-Only Checking

### Decision
The `backend_name` parameter passed to executors is for **frontend metadata reference only**. Executors do **not** validate topology constraints or basis gates.

### Rationale
- **Client responsibility**: Transpilation (circuit optimization for topology) is the client's responsibility
- **Pre-transpiled circuits**: Circuits submitted to the server are assumed to be already transpiled
- **Executor simplicity**: Executors focus on execution, not validation
- **Ideal simulation**: Current executors perform ideal (noiseless) simulation without topology constraints
- **Performance**: Skipping validation reduces server overhead
- **Flexibility**: Allows circuits to use any gates, not limited to backend basis gates

### What backend_name IS Used For
- **Metadata lookup**: Retrieve backend properties for client-side transpilation
- **Future noise modeling**: Reserved for future implementations that may apply noise models
- **Logging**: Track which backend metadata was requested
- **API compatibility**: Maintain IBM Quantum API compatibility

### What backend_name IS NOT Used For
- ❌ **Topology validation**: No checking if circuit respects coupling map
- ❌ **Basis gate validation**: No checking if gates match backend basis gates
- ❌ **Noise modeling**: Current implementation performs ideal simulation
- ❌ **Circuit rejection**: Executors never reject circuits based on backend_name

### Implementation
```python
class AerExecutor(BaseExecutor):
    def execute_sampler(self, pubs, options, backend_name: str):
        """
        Args:
            backend_name: Metadata name (e.g., "fake_manila")
                         Used for frontend metadata reference only
                         Executors don't validate topology/basis gates
        """
        # backend_name accepted but not used for validation
        # Circuits executed as-is (no topology checking)
        backend = self.get_backend(backend_name)  # For metadata only
        result = self.service._run(...)
        return result
```

### Design Philosophy
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

### Alternatives Considered
- **Server-side validation**: Would duplicate client-side transpilation logic, adds complexity
- **Reject invalid circuits**: Would break compatibility with pre-transpiled circuits
- **Automatic transpilation**: Would require maintaining transpiler state, adds dependencies
- **Noise model enforcement**: Would require noise simulation, not needed for ideal simulation

### Future Considerations
If noise modeling is implemented:
- backend_name could be used to construct noise models from FakeProvider properties
- Still no topology validation (client transpiles circuits first, then noise is applied)

### Reference
- Implementation: `src/qiskit_runtime_server/executors/aer.py`
- User-selected code: Lines 20-23 in `aer.py`

---

## Summary Table

| Decision | Choice | Key Reason |
|----------|--------|------------|
| **Executor abstraction** | **Pluggable interface** | **Enable GPU replacement** |
| **Async queue architecture** | **Single worker thread** | **Prevent resource contention** |
| **backend_name parameter** | **Frontend-only reference** | **Client transpilation responsibility** |
| Package manager | uv | Speed and simplicity |
| Storage | In-memory | Designed for local testing |
| Web framework | FastAPI | Auto docs, type validation |
| Data models | Pydantic v2 | Performance, validation |
| Dependency injection | Executor → JobManager | Swappable, testable |
| API versioning | Header validation | IBM compatibility |
| Serialization | Runtime encoder/decoder | Qiskit object support |
| Code quality | Pre-commit + strict mypy | Consistency, safety |
