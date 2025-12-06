"""Example application configuration for qiskit-runtime-server.

To use this configuration:
    cp app.example.py app.py

Then edit app.py to customize executor settings.

To run the server:
    uvicorn app:app --host 0.0.0.0 --port 8000

For development with auto-reload:
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload
"""

from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor

# ==============================================================================
# Executor Configuration
# ==============================================================================

# Default: CPU executor (Aer)
executors = {
    "aer": AerExecutor(
        shots=1024,
        seed_simulator=None,  # Set to int for deterministic results
        max_parallel_threads=0,  # 0 = auto-detect (use all CPUs)
    ),
}

# ==============================================================================
# Optional: GPU Executor (cuStateVec)
# ==============================================================================

# Uncomment the following to enable GPU executor if you have NVIDIA GPU with CUDA:
#
# try:
#     from qiskit_runtime_server.executors import CuStateVecExecutor
#
#     # Auto-detect GPU
#     if os.path.exists("/dev/nvidia0"):
#         executors["custatevec"] = CuStateVecExecutor(
#             device_id=0,  # GPU device ID
#             shots=2048,
#             seed_simulator=None,
#         )
# except ImportError:
#     pass  # cuStateVec not installed

# ==============================================================================
# Optional: Custom Executor
# ==============================================================================

# from my_custom_executor import MyCustomExecutor
#
# executors["custom"] = MyCustomExecutor(
#     param1="value1",
#     param2=42,
# )

# ==============================================================================
# Advanced: Dynamic Configuration
# ==============================================================================

# Example: Use environment variable to select GPU device
# gpu_device = os.getenv("CUDA_VISIBLE_DEVICES")
# if gpu_device is not None:
#     executors["custatevec"] = CuStateVecExecutor(
#         device_id=int(gpu_device),
#         shots=2048,
#     )

# Example: Adjust thread count based on CPU count
# cpu_count = os.cpu_count() or 1
# executors["aer"] = AerExecutor(
#     shots=1024,
#     max_parallel_threads=max(1, cpu_count - 2),
# )

# ==============================================================================
# Create Application
# ==============================================================================

app = create_app(executors=executors)

# The 'app' object is used by uvicorn:
#   uvicorn app:app --host 0.0.0.0 --port 8000
