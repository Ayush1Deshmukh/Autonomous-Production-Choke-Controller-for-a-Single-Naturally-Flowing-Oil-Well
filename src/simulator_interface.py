"""
The contract between the controller and *any* well simulator.

The whole point of this module is to make one claim provable rather than
merely asserted:

    The controller never touches simulator internals.  It only ever calls

        Q, WHP, FLP, BHP = simulator.step(choke_position)

    so the official Honeywell simulator can be dropped in place of the
    physics stand-in in `well_simulator.py` with ZERO controller changes.

`scripts/04_run_scenarios.py` type-checks the simulator against this Protocol
before every run, and `tests/` exercises the controller against a deliberately
different dummy plant that satisfies the same Protocol.
"""

from __future__ import annotations

from typing import Protocol, Tuple, runtime_checkable


@runtime_checkable
class WellSimulator(Protocol):
    """Minimal interface required of a well simulator."""

    def step(self, choke_position: float) -> Tuple[float, float, float, float]:
        """
        Advance the plant by one control interval (Ts = 1 hour).

        Parameters
        ----------
        choke_position : float
            Commanded production choke opening in percent, 0-100.

        Returns
        -------
        (Q, WHP, FLP, BHP) : tuple of float
            Oil flow rate [bbl/hr], wellhead pressure [psi],
            flowline pressure [psi], bottom hole pressure [psi].
        """
        ...

    def reset(self) -> Tuple[float, float, float, float]:
        """Return the plant to its initial (shut-in) condition."""
        ...
