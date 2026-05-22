"""Erreurs actionnables MS-03."""

from __future__ import annotations


class StorageError(Exception):
    """Base pour le module storage."""


class HdfsConnectionError(StorageError):
    """Namenode / backend injoignable."""


class HdfsPermissionError(StorageError):
    """Droits insuffisants sur le chemin HDFS."""


class HdfsQuotaError(StorageError):
    """Quota ou espace disque dépassé."""


class RawBundleNotFoundError(StorageError):
    """Répertoire ou fichiers raw introuvables."""


class InvalidRawContentError(StorageError):
    """Contenu rejeté à la frontière stockage (page d'erreur, vide, etc.)."""


class MetadataValidationError(StorageError):
    """Sidecar metadata.json invalide ou incomplet."""
