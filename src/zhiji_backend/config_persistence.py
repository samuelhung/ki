from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import CONFIG_PATH


@dataclass(frozen=True)
class ConfigFileSnapshot:
    exists: bool
    data: bytes
    mode: int


_ConfigFileSnapshot = ConfigFileSnapshot


@dataclass(frozen=True)
class PersistenceDependencies:
    config_path: Path
    os_module: Any
    logger: Any


DefaultDependencyFactory = Callable[[], PersistenceDependencies]


@dataclass(frozen=True)
class _DefaultFactoryRegistration:
    owner: str
    identity: tuple[str, str]
    factory: DefaultDependencyFactory


_SCOPED_DEPENDENCIES: ContextVar[PersistenceDependencies | None] = ContextVar(
    "zhiji_config_persistence_dependencies", default=None
)
_DEFAULT_FACTORY_LOCK = threading.Lock()
_DEFAULT_FACTORY_REGISTRATION: _DefaultFactoryRegistration | None = None


def _local_dependencies() -> PersistenceDependencies:
    return PersistenceDependencies(
        config_path=CONFIG_PATH,
        os_module=os,
        logger=logging.getLogger("zhiji_backend.config_manager"),
    )


def register_default_dependency_factory(
    factory: DefaultDependencyFactory,
    *,
    owner: str,
) -> None:
    """Register one application resolver; same-owner reloads may refresh it."""
    if not callable(factory):
        raise TypeError("default dependency factory must be callable")
    if not isinstance(owner, str) or not owner:
        raise ValueError("default dependency factory owner must be a non-empty string")
    module = getattr(factory, "__module__", None)
    qualname = getattr(factory, "__qualname__", None)
    if not isinstance(module, str) or not isinstance(qualname, str):
        raise TypeError("default dependency factory must be a named callable")

    registration = _DefaultFactoryRegistration(
        owner=owner,
        identity=(module, qualname),
        factory=factory,
    )
    global _DEFAULT_FACTORY_REGISTRATION
    with _DEFAULT_FACTORY_LOCK:
        current = _DEFAULT_FACTORY_REGISTRATION
        if current is None:
            _DEFAULT_FACTORY_REGISTRATION = registration
        elif current.factory is factory:
            return
        elif current.owner == owner and current.identity == registration.identity:
            _DEFAULT_FACTORY_REGISTRATION = registration
        else:
            raise RuntimeError(
                f"default dependency factory already registered by {current.owner}"
            )


def _current_dependencies() -> PersistenceDependencies:
    # Context-local overrides always win; the registered resolver is the app default.
    scoped = _SCOPED_DEPENDENCIES.get()
    if scoped is not None:
        return scoped
    with _DEFAULT_FACTORY_LOCK:
        registration = _DEFAULT_FACTORY_REGISTRATION
    dependencies = (
        registration.factory() if registration is not None else _local_dependencies()
    )
    if not isinstance(dependencies, PersistenceDependencies):
        raise TypeError("default dependency factory must return PersistenceDependencies")
    return dependencies


@contextmanager
def persistence_scope(dependencies: PersistenceDependencies) -> Iterator[None]:
    token = _SCOPED_DEPENDENCIES.set(dependencies)
    try:
        yield
    finally:
        _SCOPED_DEPENDENCIES.reset(token)


def _without_plaintext_provider_credential(config: dict) -> dict:
    general = config.get("general")
    if not isinstance(general, dict) or "api_key" not in general:
        return config
    storage_config = dict(config)
    storage_general = dict(general)
    storage_general.pop("api_key")
    storage_config["general"] = storage_general
    return storage_config


def write_config(config: dict) -> None:
    """Atomically write a config payload without changing in-memory state."""
    dependencies = _current_dependencies()
    config_path = dependencies.config_path
    os_module = dependencies.os_module
    reject_config_symlink()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            os_module.fchmod(temp_file.fileno(), 0o600)
            storage_config = _without_plaintext_provider_credential(config)
            json.dump(storage_config, temp_file, ensure_ascii=False, indent=2)
            temp_file.flush()
            os_module.fsync(temp_file.fileno())
        os_module.chmod(temp_path, 0o600)
        os_module.replace(temp_path, config_path)
        temp_path = None
        fsync_parent_directory()
        dependencies.logger.info("Saved system config to %s", config_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def snapshot_config_file() -> ConfigFileSnapshot:
    dependencies = _current_dependencies()
    config_path = dependencies.config_path
    reject_config_symlink()
    exists = config_path.exists()
    return ConfigFileSnapshot(
        exists=exists,
        data=config_path.read_bytes() if exists else b"",
        mode=stat.S_IMODE(config_path.stat().st_mode) if exists else 0o600,
    )


def config_file_matches(snapshot: ConfigFileSnapshot) -> bool:
    dependencies = _current_dependencies()
    config_path = dependencies.config_path
    reject_config_symlink()
    exists = config_path.exists()
    if exists != snapshot.exists:
        return False
    if not exists:
        return True
    return (
        config_path.read_bytes() == snapshot.data
        and stat.S_IMODE(config_path.stat().st_mode) == snapshot.mode
    )


def restore_config_file(snapshot: ConfigFileSnapshot) -> None:
    dependencies = _current_dependencies()
    config_path = dependencies.config_path
    os_module = dependencies.os_module
    reject_config_symlink()
    if not snapshot.exists:
        config_path.unlink(missing_ok=True)
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=config_path.parent,
            prefix=f".{config_path.name}.rollback.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            os_module.fchmod(temp_file.fileno(), snapshot.mode)
            temp_file.write(snapshot.data)
            temp_file.flush()
            os_module.fsync(temp_file.fileno())
        os_module.replace(temp_path, config_path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def reject_config_symlink() -> None:
    dependencies = _current_dependencies()
    config_path = dependencies.config_path
    try:
        mode = dependencies.os_module.lstat(config_path).st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise OSError(f"refusing to use symlink system config: {config_path}")


def fsync_parent_directory() -> None:
    """Durably record an atomic rename when directory fsync is supported."""
    dependencies = _current_dependencies()
    config_path = dependencies.config_path
    os_module = dependencies.os_module
    directory_fd: int | None = None
    try:
        flags = os_module.O_RDONLY | getattr(os_module, "O_DIRECTORY", 0)
        directory_fd = os_module.open(config_path.parent, flags)
        os_module.fsync(directory_fd)
    except OSError:
        dependencies.logger.debug(
            "Parent directory fsync is unavailable for %s",
            config_path.parent,
            exc_info=True,
        )
    finally:
        if directory_fd is not None:
            try:
                os_module.close(directory_fd)
            except OSError:
                dependencies.logger.debug(
                    "Failed to close config directory fd", exc_info=True
                )
