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

## 7. Background Threads for Job Execution

### Decision
Execute jobs in daemon background threads.

### Rationale
- **Non-blocking**: API returns immediately with job ID
- **Simple implementation**: Threading is simpler than async for CPU-bound quantum simulation
- **Resource management**: Daemon threads auto-cleanup on server shutdown
- **Familiar pattern**: Matches how IBM Quantum jobs work (submit then poll)

### Alternatives Considered
- **Async/await**: Quantum simulation is CPU-bound, not I/O-bound
- **Process pool**: Overkill for single-user local testing
- **Celery/RQ**: External dependency, complexity not justified

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

## Summary Table

| Decision | Choice | Key Reason |
|----------|--------|------------|
| **Executor abstraction** | **Pluggable interface** | **Enable GPU replacement** |
| Package manager | uv | Speed and simplicity |
| Storage | In-memory | Designed for local testing |
| Web framework | FastAPI | Auto docs, type validation |
| Data models | Pydantic v2 | Performance, validation |
| Dependency injection | Executor → JobManager | Swappable, testable |
| Job execution | Background threads | Non-blocking, simple |
| API versioning | Header validation | IBM compatibility |
| Serialization | Runtime encoder/decoder | Qiskit object support |
| Code quality | Pre-commit + strict mypy | Consistency, safety |
