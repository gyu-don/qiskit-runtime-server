# Development Guide

This guide covers setting up the development environment, running tests, and contributing to the project.

## Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Git

## Initial Setup

### 1. Clone the Repository

```bash
git clone https://github.com/gyu-don/qiskit-runtime-server.git
cd qiskit-runtime-server
```

### 2. Install Dependencies

```bash
# Install all dependencies including dev tools
uv sync --dev
```

This will:
- Create a virtual environment in `.venv/`
- Install all dependencies from `pyproject.toml`
- Generate/update `uv.lock`

### 3. Install Pre-commit Hooks

**This is mandatory before any commits.**

```bash
uv run pre-commit install
```

Pre-commit hooks will run automatically on `git commit`, checking:
- Code formatting (ruff format)
- Linting (ruff check)
- Type checking (mypy)
- Trailing whitespace, YAML syntax, etc.

## Development Workflow

### Running the Server

```bash
# First, create app.py from template (if not already done)
cp app.example.py app.py

# Development mode with auto-reload
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

Server will be available at:
- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/server/test_backends.py

# Run specific test
uv run pytest tests/server/test_backends.py::TestListBackends::test_success

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing

# Generate HTML coverage report
uv run pytest --cov=src --cov-report=html
open htmlcov/index.html
```

### Linting and Formatting

```bash
# Check linting issues
uv run ruff check .

# Auto-fix linting issues
uv run ruff check . --fix

# Check formatting
uv run ruff format --check .

# Apply formatting
uv run ruff format .
```

### Type Checking

```bash
# Run mypy
uv run mypy src

# With verbose output
uv run mypy src --verbose
```

### Running Pre-commit Manually

```bash
# Run all hooks on all files
uv run pre-commit run --all-files

# Run specific hook
uv run pre-commit run ruff --all-files

# Run on staged files only
uv run pre-commit run
```

## Adding Dependencies

**Always use `uv add` - never edit `pyproject.toml` directly.**

```bash
# Add runtime dependency
uv add fastapi

# Add dev dependency
uv add --dev pytest

# Add with version constraint
uv add "pydantic>=2.5.0"

# Remove dependency
uv remove package-name
```

## Code Style Guidelines

### File Organization

```python
# file.py

"""
Module docstring - brief description.

Longer description if needed.
"""

# Standard library imports
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

# Third-party imports
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Local imports
from .models import BackendConfiguration
from .backend_provider import get_backend_provider


# Constants
DEFAULT_SHOTS = 1024
MAX_JOBS = 100


# Classes
class MyClass:
    """Class docstring."""

    def __init__(self) -> None:
        """Initialize the class."""
        pass


# Functions
def my_function(arg1: str, arg2: int = 10) -> Dict[str, Any]:
    """
    Brief description.

    Args:
        arg1: Description of arg1
        arg2: Description of arg2

    Returns:
        Description of return value

    Raises:
        ValueError: When something is wrong
    """
    pass
```

### Type Hints

Always use type hints:

```python
# Good
def get_backend(name: str) -> Optional[BackendInfo]:
    ...

# Bad
def get_backend(name):
    ...
```

### Docstrings

Use Google-style docstrings:

```python
def create_job(
    program_id: str,
    backend_name: str,
    params: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a new runtime job.

    Args:
        program_id: Program identifier ('sampler' or 'estimator')
        backend_name: Name of the backend to run on
        params: Job parameters including 'pubs'
        options: Optional runtime options

    Returns:
        The created job ID

    Raises:
        ValueError: If backend not found or invalid program_id

    Example:
        >>> job_id = create_job("sampler", "fake_manila", {"pubs": []})
        >>> print(job_id)
        'job-abc123'
    """
```

### Error Handling

```python
# Use specific exceptions
from fastapi import HTTPException

def get_backend(name: str) -> BackendInfo:
    backend = provider.get_backend(name)
    if backend is None:
        raise HTTPException(status_code=404, detail=f"Backend not found: {name}")
    return backend
```

## Testing Guidelines

### Test Structure

```python
# tests/server/test_backends.py

import pytest
from fastapi.testclient import TestClient

from qiskit_runtime_server.app import app


client = TestClient(app)


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Provide valid authentication headers."""
    return {
        "Authorization": "Bearer test-token",
        "Service-CRN": "crn:v1:test",
        "IBM-API-Version": "2025-05-01",
    }


class TestListBackends:
    """Tests for GET /v1/backends endpoint."""

    def test_success(self, auth_headers: Dict[str, str]) -> None:
        """Test successful backend listing."""
        response = client.get("/v1/backends", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert len(data["devices"]) > 0

    def test_missing_auth(self) -> None:
        """Test request without authorization."""
        response = client.get("/v1/backends")
        assert response.status_code == 422

    def test_invalid_api_version(self, auth_headers: Dict[str, str]) -> None:
        """Test request with invalid API version."""
        headers = auth_headers.copy()
        headers["IBM-API-Version"] = "1999-01-01"

        response = client.get("/v1/backends", headers=headers)
        assert response.status_code == 400
```

### Test Categories

1. **Unit Tests**: Test individual functions/methods
2. **API Tests**: Test HTTP endpoints
3. **Integration Tests**: Test client-server interaction

### Fixtures

Define reusable fixtures in `conftest.py`:

```python
# tests/conftest.py

import pytest
from fastapi.testclient import TestClient

from qiskit_runtime_server.app import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Valid auth headers."""
    return {
        "Authorization": "Bearer test-token",
        "Service-CRN": "crn:v1:test",
        "IBM-API-Version": "2025-05-01",
    }
```

## Debugging

### Enable Debug Logging

```python
# app.py
import logging

logging.basicConfig(level=logging.DEBUG)

from qiskit_runtime_server import create_app
# ... rest of configuration
```

Then run the server:

```bash
uvicorn app:app --log-level debug
```

### Using Python Debugger

```python
# Add breakpoint in code
breakpoint()

# Or use pdb
import pdb; pdb.set_trace()
```

### VS Code Configuration

`.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Run Server",
            "type": "python",
            "request": "launch",
            "module": "uvicorn",
            "args": ["app:app", "--reload"],
            "cwd": "${workspaceFolder}"
        },
        {
            "name": "Run Tests",
            "type": "python",
            "request": "launch",
            "module": "pytest",
            "args": ["-v"]
        }
    ]
}
```

## Common Development Tasks

### Adding a New Endpoint

1. **Define models** in `models.py`:
   ```python
   class NewRequest(BaseModel):
       field1: str
       field2: int

   class NewResponse(BaseModel):
       result: str
   ```

2. **Add endpoint** in `app.py`:
   ```python
   @app.post("/v1/new-endpoint", response_model=NewResponse)
   async def new_endpoint(
       request: NewRequest,
       api_version: str = Depends(verify_api_version),
       auth: dict = Depends(verify_authorization),
   ) -> NewResponse:
       """Endpoint description."""
       # Implementation
       return NewResponse(result="success")
   ```

3. **Add tests** in `tests/server/test_new.py`:
   ```python
   def test_new_endpoint(auth_headers):
       response = client.post(
           "/v1/new-endpoint",
           json={"field1": "test", "field2": 42},
           headers=auth_headers,
       )
       assert response.status_code == 200
   ```

4. **Update documentation** in `docs/API_SPECIFICATION.md`

### Modifying Pydantic Models

When changing models, ensure:
1. Backward compatibility (if possible)
2. Tests pass
3. API documentation is updated
4. Examples still work


## Release Process

1. **Update version** in `pyproject.toml`
2. **Update CHANGELOG.md**
3. **Create PR** with changes
4. **After merge**, create GitHub release with tag
5. GitHub Actions publishes to PyPI

## Getting Help

- Check existing issues on GitHub
- Review documentation in `docs/`
- Ask in project discussions
