"""Compatibility facade for thematic series domain services."""

from __future__ import annotations

import difflib as difflib
import json as json
import sqlite3
import uuid as uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol

from fastapi import HTTPException

from . import series_mutation_service, series_query_service
from .db import connect, init_db

type Identifier = str
type IdentifierList = list[Identifier]
type ConnectFn = Callable[[], AbstractContextManager[sqlite3.Connection]]
type InitDbFn = Callable[[], None]


class SeriesCreateData(Protocol):
    name: str
    member_ids: IdentifierList
    description: str


class SeriesOrderData(Protocol):
    member_ids: IdentifierList


class SeriesMembersData(Protocol):
    event_ids: IdentifierList


class SeriesMergeData(Protocol):
    source_id: Identifier
    target_id: Identifier


def name_similarity(a: str, b: str) -> float:
    return series_query_service.name_similarity(a, b)


def member_overlap_score(ids_a: IdentifierList, ids_b: IdentifierList) -> float:
    return series_query_service.member_overlap_score(ids_a, ids_b)


def list_series(
    include_candidates: bool = False,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    return series_query_service.list_series(
        include_candidates, connect_fn=connect_fn, init_db_fn=init_db_fn
    )


def list_candidates(
    *, connect_fn: ConnectFn = connect, init_db_fn: InitDbFn = init_db
) -> dict[str, Any]:
    return series_query_service.list_candidates(
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
        name_similarity_fn=name_similarity,
        member_overlap_score_fn=member_overlap_score,
    )


def create_series(
    data: SeriesCreateData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    try:
        return series_mutation_service.create_series(
            data,
            connect_fn=connect_fn,
            init_db_fn=init_db_fn,
            datetime_cls=datetime,
            uuid_fn=uuid.uuid4,
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def delete_series(
    series_id: Identifier,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    try:
        return series_mutation_service.delete_series(
            series_id, connect_fn=connect_fn, init_db_fn=init_db_fn
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def update_series(
    series_id: Identifier,
    data: dict[str, Any],
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    try:
        return series_mutation_service.update_series(
            series_id, data, connect_fn=connect_fn, init_db_fn=init_db_fn
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def merge_series(
    data: SeriesMergeData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    try:
        return series_mutation_service.merge_series(
            data,
            connect_fn=connect_fn,
            init_db_fn=init_db_fn,
            datetime_cls=datetime,
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_series_detail(
    series_id: Identifier,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    try:
        return series_query_service.get_series_detail(
            series_id, connect_fn=connect_fn, init_db_fn=init_db_fn
        )
    except series_query_service.SeriesQueryError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from None


def reorder_series(
    series_id: Identifier,
    data: SeriesOrderData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    try:
        return series_mutation_service.reorder_series(
            series_id, data, connect_fn=connect_fn, init_db_fn=init_db_fn
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_series_suggestions(
    series_id: Identifier,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    try:
        return series_query_service.get_series_suggestions(
            series_id, connect_fn=connect_fn, init_db_fn=init_db_fn
        )
    except series_query_service.SeriesQueryError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from None


def add_series_members(
    series_id: Identifier,
    data: SeriesMembersData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    try:
        return series_mutation_service.add_series_members(
            series_id, data, connect_fn=connect_fn, init_db_fn=init_db_fn
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
