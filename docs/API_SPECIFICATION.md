# API Specification

Complete REST API reference for Qiskit Runtime Server.

**API Version**: 2025-05-01
**Base URL**: `http://localhost:8000/v1`

## Table of Contents

- [Authentication](#authentication)
- [Backend Endpoints](#backend-endpoints)
- [Job Endpoints](#job-endpoints)
- [Session Endpoints](#session-endpoints)
- [System Endpoints](#system-endpoints)
- [Error Handling](#error-handling)
- [Data Models](#data-models)

---

## Authentication

All `/v1/*` endpoints require authentication headers.

### Required Headers

| Header | Description | Example |
|--------|-------------|---------|
| `Authorization` | Bearer token | `Bearer test-token` |
| `Service-CRN` | Service instance CRN | `crn:v1:bluemix:public:quantum-computing:us-east:a/local::local` |
| `IBM-API-Version` | API version | `2025-05-01` |

### Supported API Versions

- `2024-01-01`
- `2025-01-01`
- `2025-05-01` (recommended)

### Example Request

```bash
curl -X GET "http://localhost:8000/v1/backends" \
  -H "Authorization: Bearer test-token" \
  -H "Service-CRN: crn:v1:bluemix:public:quantum-computing:us-east:a/local::local" \
  -H "IBM-API-Version: 2025-05-01"
```

---

## Backend Endpoints

### List Backends

List all available quantum backends.

**Endpoint**: `GET /v1/backends`

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `fields` | string | Additional fields (e.g., `wait_time_seconds`) |

**Response**: `200 OK`

```json
{
  "devices": [
    {
      "name": "fake_manila",
      "backend_version": "1.0.0",
      "operational": true,
      "simulator": false,
      "n_qubits": 5,
      "processor_type": {
        "family": "Falcon",
        "revision": 1.0
      },
      "quantum_volume": 32,
      "clops_h": null
    }
  ]
}
```

---

### Get Backend Configuration

Get detailed configuration for a specific backend.

**Endpoint**: `GET /v1/backends/{id}/configuration`

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Backend identifier (e.g., `fake_manila`) |

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `calibration_id` | string | Optional calibration ID |

**Response**: `200 OK`

```json
{
  "backend_name": "fake_manila",
  "backend_version": "1.0.0",
  "n_qubits": 5,
  "basis_gates": ["id", "rz", "sx", "x", "cx", "reset"],
  "gates": [...],
  "coupling_map": [[0, 1], [1, 0], [1, 2], ...],
  "simulator": false,
  "local": false,
  "conditional": true,
  "open_pulse": true,
  "memory": true,
  "max_shots": 100000,
  "processor_type": {
    "family": "Falcon",
    "revision": 1.0
  },
  "dt": 2.2222222222222221e-10,
  "quantum_volume": 32
}
```

**Errors**:
- `404 Not Found`: Backend does not exist

---

### Get Backend Properties

Get calibration properties (T1, T2, gate errors, etc.).

**Endpoint**: `GET /v1/backends/{id}/properties`

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Backend identifier |

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `calibration_id` | string | Optional calibration ID |
| `updated_before` | datetime | Get properties before timestamp |

**Response**: `200 OK`

```json
{
  "backend_name": "fake_manila",
  "backend_version": "1.0.0",
  "last_update_date": "2024-01-15T10:30:00Z",
  "qubits": [
    [
      {"date": "2024-01-15T10:30:00Z", "name": "T1", "unit": "us", "value": 125.3},
      {"date": "2024-01-15T10:30:00Z", "name": "T2", "unit": "us", "value": 89.2},
      {"date": "2024-01-15T10:30:00Z", "name": "frequency", "unit": "GHz", "value": 4.971}
    ]
  ],
  "gates": [
    {
      "qubits": [0, 1],
      "gate": "cx",
      "parameters": [
        {"date": "2024-01-15T10:30:00Z", "name": "gate_error", "unit": "", "value": 0.0043}
      ]
    }
  ],
  "general": []
}
```

**Errors**:
- `404 Not Found`: Backend does not exist or has no properties

---

### Get Backend Status

Get real-time operational status.

**Endpoint**: `GET /v1/backends/{id}/status`

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Backend identifier |

**Response**: `200 OK`

```json
{
  "backend_name": "fake_manila",
  "backend_version": "1.0.0",
  "state": true,
  "status": "active",
  "length_queue": 0
}
```

**Errors**:
- `404 Not Found`: Backend does not exist

---

### Get Backend Defaults

Get default pulse calibrations (OpenPulse backends only).

**Endpoint**: `GET /v1/backends/{id}/defaults`

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Backend identifier |

**Response**: `200 OK`

```json
{
  "qubit_freq_est": [4.971, 4.823, 5.102, ...],
  "meas_freq_est": [6.523, 6.789, 6.456, ...],
  "buffer": 10,
  "pulse_library": [...],
  "cmd_def": [...]
}
```

**Errors**:
- `404 Not Found`: Backend does not exist or does not support pulse defaults

---

## Job Endpoints

### Create Job

Create and execute a runtime job.

**Endpoint**: `POST /v1/jobs`

**Request Body**:

```json
{
  "program_id": "sampler",
  "backend": "fake_manila",
  "params": {
    "pubs": [...]
  },
  "options": {
    "default_shots": 1024
  },
  "session_id": "session-abc123"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `program_id` | string | Yes | `sampler` or `estimator` |
| `backend` | string | Yes | Backend name |
| `params` | object | Yes | Job parameters with `pubs` |
| `options` | object | No | Runtime options |
| `session_id` | string | No | Associated session ID |

**Response**: `201 Created`

```json
{
  "id": "job-abc123",
  "program": {"id": "sampler"},
  "backend": "fake_manila",
  "state": {
    "status": "QUEUED",
    "reason": null
  },
  "created": "2024-01-15T10:30:00Z",
  "session_id": "job-abc123"
}
```

**Errors**:
- `400 Bad Request`: Invalid parameters or backend mismatch
- `404 Not Found`: Backend or session not found

---

### Get Job Status

Get the current status of a job.

**Endpoint**: `GET /v1/jobs/{job_id}`

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string | Job identifier |

**Response**: `200 OK`

```json
{
  "id": "job-abc123",
  "program": {"id": "sampler"},
  "backend": "fake_manila",
  "state": {
    "status": "COMPLETED",
    "reason": null
  },
  "created": "2024-01-15T10:30:00Z",
  "session_id": "job-abc123"
}
```

**Job Status Values**:
- `QUEUED`: Job waiting to execute
- `RUNNING`: Job currently executing
- `COMPLETED`: Job finished successfully
- `FAILED`: Job encountered an error
- `CANCELLED`: Job was cancelled

**Errors**:
- `404 Not Found`: Job does not exist

---

### Get Job Results

Get the results of a completed job.

**Endpoint**: `GET /v1/jobs/{job_id}/results`

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string | Job identifier |

**Response**: `200 OK`

Returns `PrimitiveResult` serialized via `RuntimeEncoder`:

```json
{
  "__type__": "PrimitiveResult",
  "__value__": {
    "pub_results": [...],
    "metadata": {...}
  }
}
```

**Errors**:
- `400 Bad Request`: Job not completed
- `404 Not Found`: Job does not exist

---

### Cancel Job

Cancel a running or queued job.

**Endpoint**: `DELETE /v1/jobs/{job_id}`

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string | Job identifier |

**Response**: `204 No Content`

**Errors**:
- `404 Not Found`: Job does not exist or already completed

---

### List Jobs

List jobs with optional filters.

**Endpoint**: `GET /v1/jobs`

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max results (1-100, default: 10) |
| `skip` | integer | Skip count (default: 0) |
| `backend` | string | Filter by backend |
| `program` | string | Filter by program_id |
| `state` | string | Filter by status |

**Response**: `200 OK`

```json
{
  "jobs": [...],
  "count": 5
}
```

---

## Session Endpoints

### Create Session

Create a new session for grouping jobs.

**Endpoint**: `POST /v1/sessions`

**Request Body**:

```json
{
  "mode": "dedicated",
  "backend": "fake_manila",
  "instance": "crn:v1:...",
  "max_ttl": 28800
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mode` | string | Yes | `dedicated` (sequential) or `batch` (parallel) |
| `backend` | string | Yes | Backend name |
| `instance` | string | No | IBM Cloud instance CRN |
| `max_ttl` | integer | No | Max time-to-live in seconds |

**Response**: `201 Created`

```json
{
  "id": "session-abc123",
  "mode": "dedicated",
  "backend": "fake_manila",
  "instance": "crn:v1:...",
  "max_ttl": 28800,
  "created_at": "2024-01-15T10:30:00Z",
  "accepting_jobs": true,
  "active": true,
  "elapsed_time": 0,
  "jobs": []
}
```

---

### Get Session Details

Get session information.

**Endpoint**: `GET /v1/sessions/{session_id}`

**Response**: `200 OK`

```json
{
  "id": "session-abc123",
  "mode": "dedicated",
  "backend": "fake_manila",
  "instance": "crn:v1:...",
  "max_ttl": 28800,
  "created_at": "2024-01-15T10:30:00Z",
  "accepting_jobs": true,
  "active": true,
  "elapsed_time": 150,
  "jobs": ["job-1", "job-2", "job-3"]
}
```

**Errors**:
- `404 Not Found`: Session does not exist

---

### Update Session

Update session settings (e.g., stop accepting jobs).

**Endpoint**: `PATCH /v1/sessions/{session_id}`

**Request Body**:

```json
{
  "accepting_jobs": false
}
```

**Response**: `200 OK`

Returns updated session details.

**Errors**:
- `404 Not Found`: Session does not exist

---

### Cancel Session

Cancel session and all queued jobs.

**Endpoint**: `DELETE /v1/sessions/{session_id}/close`

**Response**: `204 No Content`

**Errors**:
- `404 Not Found`: Session does not exist

---

## System Endpoints

### Health Check

**Endpoint**: `GET /health`

**Response**: `200 OK`

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "2025-05-01"
}
```

### API Information

**Endpoint**: `GET /`

**Response**: `200 OK`

```json
{
  "name": "Qiskit Runtime Backend API",
  "version": "2025-05-01",
  "documentation": "/docs",
  "endpoints": {
    "backends": "/v1/backends",
    "health": "/health"
  }
}
```

---

## Error Handling

### Error Response Format

```json
{
  "errors": [
    {
      "message": "Backend not found: invalid_backend",
      "code": "BACKEND_NOT_FOUND"
    }
  ],
  "trace": "abc123",
  "status_code": 404
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 204 | No Content |
| 400 | Bad Request |
| 401 | Unauthorized |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |

---

## Data Models

### BackendDevice

```json
{
  "name": "string",
  "backend_version": "string",
  "operational": true,
  "simulator": false,
  "n_qubits": 5,
  "processor_type": {
    "family": "string",
    "revision": 1.0
  },
  "quantum_volume": 32,
  "clops_h": null,
  "queue_length": 0,
  "wait_time_seconds": 0.0
}
```

### JobState

```json
{
  "status": "QUEUED|RUNNING|COMPLETED|FAILED|CANCELLED",
  "reason": "string or null"
}
```

### SessionResponse

```json
{
  "id": "string",
  "mode": "dedicated|batch",
  "backend": "string",
  "instance": "string or null",
  "max_ttl": 28800,
  "created_at": "datetime",
  "accepting_jobs": true,
  "active": true,
  "elapsed_time": 0,
  "jobs": ["job-id-1", "job-id-2"]
}
```

### Nduv (Name-Date-Unit-Value)

```json
{
  "date": "datetime",
  "name": "string",
  "unit": "string",
  "value": 125.3
}
```
