"""Stratégie Tor KBO — passes direct → tor1 → tor2 → tor3 (+ boucle optionnelle)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from packages.acquisition.config import AcquisitionConfig

logger = logging.getLogger(__name__)

IP_CHECK_URL = "https://api.ipify.org?format=json"


@dataclass(frozen=True)
class KboEgressLane:
    name: str
    proxy_url: str | None  # None = connexion directe


def build_kbo_lanes(config: AcquisitionConfig) -> list[KboEgressLane]:
    lanes: list[KboEgressLane] = []
    if config.kbo_direct_first:
        lanes.append(KboEgressLane("direct", None))
    for index, proxy in enumerate(config.tor_proxies, start=1):
        lanes.append(KboEgressLane(f"tor{index}", proxy))
    if not lanes:
        lanes.append(KboEgressLane("direct", None))
    return lanes


def is_kbo_rate_or_captcha(reason_code: str) -> bool:
    """Captcha / rate-limit — déclenche bascule Tor (KBO, statuts, …)."""
    return reason_code in ("CAPTCHA_SUSPECT", "HTTP_4XX")


def is_tor_escalation_reason(reason_code: str) -> bool:
    return is_kbo_rate_or_captcha(reason_code)


def wait_tor_loop_cycle_interval(
    *,
    min_interval_s: float,
    last_cycle_completed_at: float | None,
) -> float:
    """
    Pause entre deux cycles Tor complets (direct → torN).

    Retourne l'horodatage monotonic de fin d'attente (pour le cycle suivant).
    """
    if min_interval_s <= 0 or last_cycle_completed_at is None:
        return time.monotonic()
    elapsed = time.monotonic() - last_cycle_completed_at
    remaining = min_interval_s - elapsed
    if remaining > 0:
        logger.info(
            "KBO Tor — attente %.0f s avant nouveau cycle (minimum %.0f s entre cycles)",
            remaining,
            min_interval_s,
        )
        time.sleep(remaining)
    return time.monotonic()


@dataclass
class KboTorScheduler:
    """Gère la lane courante et le nombre de cycles Tor."""

    lanes: list[KboEgressLane]
    tor_loop: bool
    lane_index: int = 0
    loop_cycles: int = 1

    def current_lane(self) -> KboEgressLane:
        return self.lanes[self.lane_index]

    def advance_lane(self) -> bool:
        """Passe à la lane suivante. Retourne False si cycle terminé."""
        if self.lane_index + 1 < len(self.lanes):
            self.lane_index += 1
            logger.info(
                "KBO Tor — rotation vers lane %s (%s)",
                self.current_lane().name,
                self.current_lane().proxy_url or "direct",
            )
            return True
        return False

    def reset_cycle(self) -> None:
        self.lane_index = 0
        self.loop_cycles += 1
        logger.info("KBO Tor — nouveau cycle %d (tor_loop)", self.loop_cycles)

    def can_loop_again(self) -> bool:
        return self.tor_loop and self.loop_cycles < 50

    def lanes_summary(self) -> list[str]:
        return [lane.name for lane in self.lanes]


class KboTorLaneCoordinator:
    """
    Lane partagée pour tout le run KBO.

    Dès qu'une requête voit un captcha / 403 / 429 sur la lane courante,
    on passe immédiatement à la suivante (direct → tor1 → tor2 → tor3)
    pour toutes les entreprises encore en file.
    """

    def __init__(
        self,
        *,
        lanes: list[KboEgressLane],
        tor_loop: bool,
        tor_loop_min_interval_s: float,
    ) -> None:
        self._scheduler = KboTorScheduler(lanes=lanes, tor_loop=tor_loop)
        self._tor_loop_min_interval_s = tor_loop_min_interval_s
        self._lock = threading.Lock()
        self._lanes_used: set[str] = set()
        self._last_cycle_completed_at: float | None = None

    @property
    def loop_cycles(self) -> int:
        return self._scheduler.loop_cycles

    def lanes_used(self) -> list[str]:
        with self._lock:
            return sorted(self._lanes_used)

    def current_lane(self) -> KboEgressLane:
        with self._lock:
            lane = self._scheduler.current_lane()
            self._lanes_used.add(lane.name)
            return lane

    def escalate_on_captcha(self) -> bool:
        """Brûle la lane courante et passe à la suivante. False = plus de lane."""
        with self._lock:
            burned = self._scheduler.current_lane().name
            if self._scheduler.advance_lane():
                nxt = self._scheduler.current_lane().name
                logger.warning(
                    "KBO Tor — captcha sur %s → bascule immédiate vers %s (tout le run)",
                    burned,
                    nxt,
                )
                self._lanes_used.add(nxt)
                return True
            return False

    def restart_loop_cycle(self) -> bool:
        """Nouveau cycle direct→torN après pause (tor_loop)."""
        with self._lock:
            if not self._scheduler.can_loop_again():
                return False
            self._last_cycle_completed_at = wait_tor_loop_cycle_interval(
                min_interval_s=self._tor_loop_min_interval_s,
                last_cycle_completed_at=self._last_cycle_completed_at,
            )
            self._scheduler.reset_cycle()
            self._lanes_used.add(self._scheduler.current_lane().name)
            return True


@dataclass
class KboEnterpriseLaneState:
    """Suivi par entreprise sur la lane courante."""

    blocked_on_lane: bool = False


@dataclass
class KboTorRunState:
    pending: set[str] = field(default_factory=set)
    outcomes: dict[str, dict] = field(default_factory=dict)
    lane_state: dict[str, KboEnterpriseLaneState] = field(default_factory=dict)

    def mark_blocked(self, number: str) -> None:
        self.lane_state.setdefault(number, KboEnterpriseLaneState()).blocked_on_lane = True

    def clear_lane_flags(self) -> None:
        self.lane_state.clear()

    def pending_for_lane_retry(self) -> list[str]:
        return sorted(
            n for n in self.pending if self.lane_state.get(n, KboEnterpriseLaneState()).blocked_on_lane
        )

    def all_pending_blocked_on_current_lane(self) -> bool:
        if not self.pending:
            return False
        return all(
            self.lane_state.get(n, KboEnterpriseLaneState()).blocked_on_lane for n in self.pending
        )
