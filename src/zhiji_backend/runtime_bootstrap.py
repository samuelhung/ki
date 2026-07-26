from __future__ import annotations

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
class RuntimeResources:
    handlers: tuple[Any, ...] = ()
    level_mutations: tuple[LoggerLevelMutation, ...] = ()

    def __iter__(self):
        return iter(self.handlers)


def restore_module_state(namespace: dict[str, Any], state: dict[str, Any]) -> None:
    for name in tuple(namespace):
        if name not in state:
            del namespace[name]
    namespace.update(state)


def rollback_runtime(resources: RuntimeResources, *, root_logger: Any) -> None:
    for handler in resources.handlers:
        try:
            if handler in root_logger.handlers:
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
