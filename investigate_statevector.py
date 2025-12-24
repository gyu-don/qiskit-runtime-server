"""Investigate AerSimulator statevector backend metadata."""

from qiskit_aer import AerSimulator
from qiskit.providers.fake_provider import GenericBackendV2
import json


def investigate_aer_statevector():
    """Investigate AerSimulator with statevector method."""
    print("=" * 80)
    print("AerSimulator (statevector method)")
    print("=" * 80)

    # Create AerSimulator with statevector method
    backend = AerSimulator(method="statevector")

    print(f"\nBackend name: {backend.name}")
    print(f"Backend version: {backend.backend_version}")
    print(f"Number of qubits: {backend.num_qubits}")
    print(f"Coupling map: {backend.coupling_map}")
    print(f"Basis gates: {backend.operation_names}")
    if hasattr(backend, "max_shots"):
        print(f"Max shots: {backend.max_shots}")
    else:
        print("Max shots: N/A (attribute not available)")

    # Get configuration
    if hasattr(backend, "configuration"):
        config = backend.configuration()
        print(f"\nConfiguration type: {type(config)}")
        print(f"Configuration dict keys: {list(config.__dict__.keys())}")
        print(f"\nFull configuration:")
        for key, value in config.__dict__.items():
            print(f"  {key}: {value}")

    # Get properties (calibration data)
    if hasattr(backend, "properties"):
        props = backend.properties()
        print(f"\nProperties: {props}")

    # Get target
    if hasattr(backend, "target"):
        target = backend.target
        print(f"\nTarget type: {type(target)}")
        print(f"Target num_qubits: {target.num_qubits}")
        print(f"Target operations: {list(target.operations)[:10]}...")  # First 10
        print(f"Target qargs (first op): {list(target.qargs)[0] if target.qargs else None}")

    # Get options
    print(f"\nOptions: {backend.options}")

    return backend


def investigate_generic_backend():
    """Investigate GenericBackendV2 for comparison."""
    print("\n\n" + "=" * 80)
    print("GenericBackendV2 (5 qubits)")
    print("=" * 80)

    backend = GenericBackendV2(num_qubits=5)

    print(f"\nBackend name: {backend.name}")
    print(f"Backend version: {backend.backend_version}")
    print(f"Number of qubits: {backend.num_qubits}")
    print(f"Coupling map: {backend.coupling_map}")
    print(f"Basis gates: {backend.operation_names}")

    if hasattr(backend, "target"):
        target = backend.target
        print(f"\nTarget type: {type(target)}")
        print(f"Target num_qubits: {target.num_qubits}")
        print(f"Target operations: {list(target.operations)[:10]}...")

    return backend


def compare_backends():
    """Compare different backend types."""
    print("\n\n" + "=" * 80)
    print("COMPARISON: AerSimulator vs GenericBackendV2")
    print("=" * 80)

    aer = AerSimulator(method="statevector")
    generic = GenericBackendV2(num_qubits=5)

    print("\n| Property | AerSimulator | GenericBackendV2 |")
    print("|----------|--------------|------------------|")
    print(f"| name | {aer.name} | {generic.name} |")
    print(f"| num_qubits | {aer.num_qubits} | {generic.num_qubits} |")
    print(f"| coupling_map | {aer.coupling_map} | {generic.coupling_map} |")
    print(f"| Has properties() | {hasattr(aer, 'properties')} | {hasattr(generic, 'properties')} |")
    print(f"| Has configuration() | {hasattr(aer, 'configuration')} | {hasattr(generic, 'configuration')} |")
    print(f"| Has target | {hasattr(aer, 'target')} | {hasattr(generic, 'target')} |")


if __name__ == "__main__":
    aer_backend = investigate_aer_statevector()
    generic_backend = investigate_generic_backend()
    compare_backends()
