from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

KI_HANDLER_OWNER = "zhiji"
KI_HANDLER_OWNER_ATTR = "_zhiji_handler_owner"
KI_HANDLER_ROLE_ATTR = "_zhiji_handler_role"


@dataclass(frozen=True)
class LoggerLevelMutation:
    logger: Any
    previous: int
    applied: int


@dataclass(frozen=True)
class EnvironmentMutation:
    name: str
    previous: str | None
    applied: str | None


@dataclass(frozen=True)
class RuntimeResources:
    handlers: tuple[Any, ...] = ()
    level_mutations: tuple[LoggerLevelMutation, ...] = ()
    environment: MutableMapping[str, str] | None = None
    environment_mutations: tuple[EnvironmentMutation, ...] = ()

    def __iter__(self):
        return iter(self.handlers)


def restore_module_state(namespace: dict[str, Any], state: dict[str, Any]) -> None:
    for name in tuple(namespace):
        if name not in state:
            del namespace[name]
    namespace.update(state)


def _environment_mutations(
    environment: MutableMapping[str, str], before: dict[str, str]
) -> tuple[EnvironmentMutation, ...]:
    names = before.keys() | environment.keys()
    return tuple(
        EnvironmentMutation(name, before.get(name), environment.get(name))
        for name in names
        if before.get(name) != environment.get(name)
        or (name in before) != (name in environment)
    )


def rollback_environment(
    environment: MutableMapping[str, str],
    mutations: tuple[EnvironmentMutation, ...],
) -> None:
    for mutation in reversed(mutations):
        current = environment.get(mutation.name)
        if current != mutation.applied or (mutation.name in environment) != (
            mutation.applied is not None
        ):
            continue
        if mutation.previous is None:
            environment.pop(mutation.name, None)
        else:
            environment[mutation.name] = mutation.previous


def prepare_environment(
    environment: MutableMapping[str, str], load: Any
) -> tuple[EnvironmentMutation, ...]:
    before = dict(environment)
    try:
        load()
    except BaseException:
        rollback_environment(environment, _environment_mutations(environment, before))
        raise
    return _environment_mutations(environment, before)


def rollback_runtime(resources: RuntimeResources, *, root_logger: Any | None) -> None:
    for handler in resources.handlers:
        try:
            if root_logger is not None and handler in root_logger.handlers:
                root_logger.removeHandler(handler)
        except BaseException:
            pass
        try:
            handler.close()
        except BaseException:
            pass
    for mutation in reversed(resources.level_mutations):
        try:
            if mutation.logger.level == mutation.applied:
                mutation.logger.setLevel(mutation.previous)
        except BaseException:
            pass
    if resources.environment is not None:
        rollback_environment(resources.environment, resources.environment_mutations)


def prepare_logging(
    *,
    logging_module: Any,
    root_logger: Any,
    create_console_handler: Any,
    create_file_handler: Any,
) -> RuntimeResources:
    logger_targets = (
        (root_logger, logging_module.DEBUG),
        (logging_module.getLogger("httpx"), logging_module.WARNING),
        (logging_module.getLogger("httpcore"), logging_module.WARNING),
        (logging_module.getLogger("urllib3"), logging_module.WARNING),
    )
    level_mutations = tuple(
        LoggerLevelMutation(logger, logger.level, target)
        for logger, target in logger_targets
    )
    installed: list[Any] = []
    resources = RuntimeResources((), level_mutations)
    try:
        for mutation in level_mutations:
            mutation.logger.setLevel(mutation.applied)
        for role, create_handler in (
            ("console", create_console_handler),
            ("file", create_file_handler),
        ):
            if any(
                getattr(handler, KI_HANDLER_OWNER_ATTR, None) == KI_HANDLER_OWNER
                and getattr(handler, KI_HANDLER_ROLE_ATTR, None) == role
                for handler in root_logger.handlers
            ):
                continue
            handler = create_handler()
            setattr(handler, KI_HANDLER_OWNER_ATTR, KI_HANDLER_OWNER)
            setattr(handler, KI_HANDLER_ROLE_ATTR, role)
            installed.append(handler)
            root_logger.addHandler(handler)
        return RuntimeResources(tuple(installed), level_mutations)
    except BaseException:
        resources = RuntimeResources(tuple(installed), level_mutations)
        rollback_runtime(resources, root_logger=root_logger)
        raise


def create_console_handler(logging_module: Any, formatter_type: Any) -> Any:
    handler = logging_module.StreamHandler()
    handler.setLevel(logging_module.INFO)
    handler.setFormatter(
        formatter_type(
            "%(asctime)s [%(levelname)-7s] %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler


def create_file_handler(
    logging_module: Any, handler_type: Any, formatter_type: Any, log_dir: Any
) -> Any:
    handler = handler_type(
        str(log_dir / "ki.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    handler.setLevel(logging_module.DEBUG)
    handler.setFormatter(
        formatter_type(
            "%(asctime)s [%(levelname)-7s] %(name)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler
