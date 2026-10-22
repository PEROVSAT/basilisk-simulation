"""Wait for Vizard's listener before Basilisk starts its native handshake."""

import socket
import time


def wait_for_vizard(address: str, timeout_s: float) -> None:
    """Probe TCP readiness only; Basilisk still performs the actual handshake."""
    print(
        f"Waiting for Vizard listener at tcp://{address}:5556 "
        f"(up to {timeout_s:g} s).\n"
        "In Vizard select Receive & Reply and Live Display, then Start Visualization.",
        flush=True,
    )
    deadline = time.monotonic() + timeout_s
    last_error = None
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            with socket.create_connection((address, 5556), timeout=min(.2, remaining)):
                pass
        except socket.gaierror as exc:
            raise ConnectionError(f"Cannot resolve Vizard host {address!r}") from exc
        except OSError as exc:
            last_error = exc
            time.sleep(min(.05, max(0.0, deadline - time.monotonic())))
        else:
            print("Vizard TCP listener ready; starting Basilisk handshake.", flush=True)
            return
    raise TimeoutError(
        f"Vizard listener at tcp://{address}:5556 was not reachable within "
        f"{timeout_s:g} s. Check the address, Receive & Reply mode, and network access."
    ) from last_error
