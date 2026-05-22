"""Exceptions publiques MS-05."""

from __future__ import annotations


class PersistenceError(Exception):
    """Erreur générique couche persistence."""


class EnterpriseNotFoundError(PersistenceError):
    """Entreprise absente du registre."""


class StateTransitionError(PersistenceError):
    """Transition d'état invalide ou conflit de version."""
