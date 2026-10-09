"""Diagnostic command-line interface for repository and registry checks."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from geo_research import __version__
from geo_research.adapters.serp.google import GoogleOrganicAdapter
from geo_research.config.paths import RepositoryPaths
from geo_research.config.settings import Settings
from geo_research.connectors.dataforseo.auth import DataForSEOCredentials
from geo_research.connectors.dataforseo.client import DataForSEOClient
from geo_research.connectors.dataforseo.errors import DataForSEOError
from geo_research.domain.serp import Query, SearchTarget
from geo_research.exceptions import ConfigurationError, ReleaseIncompleteError
from geo_research.registries.validators import (
    RegistryValidationError,
    load_comparisons,
    validate_registries,
)
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.raw_registration import register_verified_raw_evidence
from geo_research.storage.raw_store import RawStore
from geo_research.storage.releases import ReleaseRepository
from geo_research.storage.repositories import RawEvidenceRepository
from geo_research.transforms.llm_raw import transform_llm_raw_file
from geo_research.transforms.silver import transform_bronze_to_silver

if TYPE_CHECKING:
    from geo_research.collection.llm_collector import LLMCollectionAssignment
    from geo_research.collection.standard_serp import StandardSERPAssignment


def _total_estimated_cost(count: int, per_task_cost: float | None) -> float:
    """Return the displayed total estimate after CLI preflight validated its inputs."""
    if per_task_cost is None:
        raise ValueError("estimated task cost is required")
    return count * per_task_cost


def _filter_standard_serp_assignments(
    assignments: Sequence[StandardSERPAssignment],
    *,
    query_id: str | None,
    target_ids: Sequence[str] | None,
    search_engine: str | None,
) -> list[StandardSERPAssignment]:
    """Return only assignments selected by explicit Standard SERP CLI filters."""
    selected_target_ids = set(target_ids or ())
    selected_engine = search_engine.casefold() if search_engine else None
    return [
        assignment
        for assignment in assignments
        if (query_id is None or str(assignment.query.query_id) == query_id)
        and (
            not selected_target_ids
            or str(assignment.target.search_target_id) in selected_target_ids
        )
        and (
            selected_engine is None
            or assignment.target.search_engine.casefold() == selected_engine
        )
    ]


def _filter_llm_assignments(
    assignments: Sequence[LLMCollectionAssignment],
    *,
    prompt_id: str | None,
    target_ids: Sequence[str] | None,
    platform: str | None,
) -> list[LLMCollectionAssignment]:
    """Return only assignments selected by explicit LLM CLI filters."""
    selected_target_ids = set(target_ids or ())
    selected_platform = platform.casefold() if platform else None
    return [
        assignment
        for assignment in assignments
        if (prompt_id is None or str(assignment.prompt.prompt_id) == prompt_id)
        and (
            not selected_target_ids
            or str(assignment.target.llm_target_id) in selected_target_ids
        )
        and (
            selected_platform is None
            or assignment.target.platform.casefold() == selected_platform
        )
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the non-collecting diagnostic command parser."""
    parser = argparse.ArgumentParser(prog="geo-research")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version")
    config_check = subparsers.add_parser("config-check")
    config_check.add_argument("--config", type=Path)
    subparsers.add_parser("paths")
    registry = subparsers.add_parser("registry")
    registry_subparsers = registry.add_subparsers(
        dest="registry_command", required=True
    )
    for command in ("validate", "summary"):
        registry_command = registry_subparsers.add_parser(command)
        registry_command.add_argument("--directory", type=Path)
    storage = subparsers.add_parser("storage")
    storage_subparsers = storage.add_subparsers(dest="storage_command", required=True)
    for command in ("init", "verify", "status"):
        storage_command = storage_subparsers.add_parser(command)
        storage_command.add_argument("--database", type=Path)
        storage_command.add_argument("--raw-directory", type=Path)
    register_raw = storage_subparsers.add_parser("register-raw")
    register_raw.add_argument("--database", type=Path)
    register_raw.add_argument("--raw-directory", type=Path)
    collect = subparsers.add_parser("collect")
    collect_subparsers = collect.add_subparsers(
        dest="collection_category", required=True
    )
    for category in ("serp", "llm", "all"):
        collection = collect_subparsers.add_parser(category)
        collection.add_argument("--query-id")
        collection.add_argument("--prompt-id")
        collection.add_argument("--target-id", action="append")
        collection.add_argument("--search-engine")
        collection.add_argument("--platform")
        collection.add_argument("--collection-window", default="default")
        collection.add_argument("--dry-run", action="store_true")
        collection.add_argument("--max-cost-usd", type=float)
        collection.add_argument("--allow-real-api", action="store_true")
        collection.add_argument("--database", type=Path)
        collection.add_argument("--raw-directory", type=Path)
        collection.add_argument("--registries-directory", type=Path)
        collection.add_argument("--estimated-cost-usd", type=float)
    retrieve = subparsers.add_parser("retrieve")
    retrieve_subparsers = retrieve.add_subparsers(
        dest="retrieval_category", required=True
    )
    retrieve_serp = retrieve_subparsers.add_parser("serp")
    retrieve_serp.add_argument("--dry-run", action="store_true")
    retrieve_serp.add_argument("--max-cost-usd", type=float)
    retrieve_serp.add_argument("--allow-real-api", action="store_true")
    retrieve_serp.add_argument("--database", type=Path)
    retrieve_serp.add_argument("--raw-directory", type=Path)
    retrieve_llm = retrieve_subparsers.add_parser("llm")
    retrieve_llm.add_argument("--dry-run", action="store_true")
    retrieve_llm.add_argument("--max-cost-usd", type=float)
    retrieve_llm.add_argument("--allow-real-api", action="store_true")
    retrieve_llm.add_argument("--database", type=Path)
    retrieve_llm.add_argument("--raw-directory", type=Path)
    transform = subparsers.add_parser("transform")
    transform_subparsers = transform.add_subparsers(
        dest="transform_command", required=True
    )
    llm_raw = transform_subparsers.add_parser("llm-raw")
    llm_raw.add_argument("--input", type=Path, required=True)
    llm_raw.add_argument("--output", type=Path)
    llm_raw.add_argument("--database", type=Path)
    llm_raw.add_argument("--raw-directory", type=Path)
    serp_raw = transform_subparsers.add_parser("serp-raw")
    serp_raw.add_argument("--database", type=Path)
    serp_raw.add_argument("--raw-directory", type=Path)
    release = subparsers.add_parser("release")
    release_subparsers = release.add_subparsers(dest="release_command", required=True)
    release_complete = release_subparsers.add_parser("complete")
    release_complete.add_argument("--database", type=Path)
    release_complete.add_argument("--release-id", required=True)
    release_complete.add_argument("--notes")
    release_complete.add_argument(
        "--research-registry", type=Path,
        help="Explicitly snapshot experimental features and approved comparison CSV",
    )
    release_status = release_subparsers.add_parser("status")
    release_status.add_argument("--database", type=Path)
    smoke = subparsers.add_parser("smoke")
    smoke_subparsers = smoke.add_subparsers(dest="smoke_command", required=True)
    google_task_post = smoke_subparsers.add_parser("google-organic-task-post")
    google_task_post.add_argument("--keyword", required=True)
    google_task_post.add_argument("--location-code", default="2840")
    google_task_post.add_argument("--language-code", default="en")
    google_task_post.add_argument("--device", default="desktop")
    google_task_post.add_argument("--operating-system", default="windows")
    google_task_post.add_argument("--depth", type=int, default=10)
    google_task_post.add_argument("--dry-run", action="store_true")
    google_task_post.add_argument("--max-cost-usd", required=True, type=float)
    google_task_post.add_argument("--allow-real-api", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a non-collecting diagnostic command."""
    arguments = build_parser().parse_args(argv)
    if arguments.command == "version":
        print(__version__)
        return 0
    if arguments.command == "config-check":
        try:
            settings = Settings.load(config_file=arguments.config)
        except ConfigurationError as error:
            print(f"Configuration error: {error}")
            return 2
        print(json.dumps(settings.safe_summary(), indent=2, sort_keys=True))
        return 0
    if arguments.command == "paths":
        paths = RepositoryPaths.discover()
        print(
            json.dumps(
                {key: str(value) for key, value in asdict(paths).items()}, indent=2
            )
        )
        return 0
    if arguments.command == "registry":
        directory = (
            arguments.directory or RepositoryPaths.discover().config / "registries"
        )
        try:
            result = validate_registries(directory)
        except RegistryValidationError as error:
            print(json.dumps({"valid": False, "error": str(error)}))
            return 2
        if arguments.registry_command == "summary":
            print(
                json.dumps(
                    {
                        "assignment_summary": result.assignment_summary,
                        "counts": result.counts,
                    },
                    sort_keys=True,
                )
            )
            return 0
        print(result.model_dump_json(indent=2))
        return 0
    if arguments.command == "storage":
        paths = RepositoryPaths.discover()
        database_path = (
            arguments.database or paths.warehouse_data / "geo_research.duckdb"
        )
        raw_directory = arguments.raw_directory or paths.raw_data
        database = DuckDBStore(database_path)
        if arguments.storage_command == "init":
            database.initialize()
            print(json.dumps({"initialized": True, "database": str(database_path)}))
            return 0
        if arguments.storage_command == "register-raw":
            report = register_verified_raw_evidence(database, raw_directory)
            print(json.dumps(asdict(report), sort_keys=True))
            return 0 if not report.invalid_directories else 2
        report = RawEvidenceRepository(database, RawStore(raw_directory)).verify()
        output = {
            "valid": report.valid,
            "missing_raw_directories": report.missing_raw_directories,
            "unreferenced_raw_directories": [
                str(path) for path in report.unreferenced_raw_directories
            ],
        }
        if arguments.storage_command == "status":
            output["database_exists"] = database_path.exists()
        print(json.dumps(output, sort_keys=True))
        return 0 if report.valid else 2
    if arguments.command == "transform":
        if arguments.transform_command == "llm-raw":
            payload = transform_llm_raw_file(arguments.input)
            serialized = json.dumps(payload, indent=2, ensure_ascii=False)
            if arguments.output is not None:
                arguments.output.parent.mkdir(parents=True, exist_ok=True)
                arguments.output.write_text(serialized + "\n", encoding="utf-8")
            else:
                print(serialized)
            if arguments.database is not None:
                paths = RepositoryPaths.discover()
                raw_directory = arguments.raw_directory or paths.raw_data
                report = transform_bronze_to_silver(
                    DuckDBStore(arguments.database), raw_directory
                )
                print(json.dumps(asdict(report), sort_keys=True))
            return 0
        if arguments.transform_command == "serp-raw":
            paths = RepositoryPaths.discover()
            database_path = (
                arguments.database or paths.warehouse_data / "geo_research.duckdb"
            )
            raw_directory = arguments.raw_directory or paths.raw_data
            report = transform_bronze_to_silver(
                DuckDBStore(database_path), raw_directory
            )
            print(json.dumps(asdict(report), sort_keys=True))
            return 0
        raise ValueError(
            f"Unsupported transform command: {arguments.transform_command}"
        )
    if arguments.command == "release":
        paths = RepositoryPaths.discover()
        database_path = (
            arguments.database or paths.warehouse_data / "geo_research.duckdb"
        )
        repository = ReleaseRepository(DuckDBStore(database_path))
        if arguments.release_command == "status":
            report = repository.assess()
            print(
                json.dumps(
                    {
                        "complete": report.complete,
                        "reasons": list(report.reasons),
                        "checks": report.checks,
                        "current_release_id": repository.current_release_id(),
                    },
                    sort_keys=True,
                    default=str,
                )
            )
            return 0 if report.complete else 2
        if arguments.release_command == "complete":
            try:
                report = repository.complete(
                    arguments.release_id, notes=arguments.notes,
                    research_comparisons=(
                        tuple(load_comparisons(arguments.research_registry))
                        if arguments.research_registry is not None else None
                    ),
                )
            except ReleaseIncompleteError as error:
                print(
                    json.dumps(
                        {
                            "completed": False,
                            "release_id": arguments.release_id,
                            "error": str(error),
                            "reasons": list(repository.assess().reasons),
                        },
                        sort_keys=True,
                    )
                )
                return 2
            print(
                json.dumps(
                    {
                        "completed": True,
                        "release_id": arguments.release_id,
                        "current_release_id": repository.current_release_id(),
                        "complete": report.complete,
                        "checks": report.checks,
                    },
                    sort_keys=True,
                    default=str,
                )
            )
            return 0
        raise ValueError(f"Unsupported release command: {arguments.release_command}")
    if arguments.command == "collect":
        settings = Settings.load()
        target = {
            "serp": "DataForSEO Standard SERP",
            "llm": "DataForSEO LLM Scraper",
            "all": "All Targets",
        }[arguments.collection_category]
        from geo_research.collection.preflight import Phase6Preflight

        preflight_result = Phase6Preflight(
            RepositoryPaths.discover().root / "docs" / "api_evidence_register.md",
            ci_environment=bool(os.environ.get("CI")),
        ).check(
            target=target,
            allow_real_api=arguments.allow_real_api,
            dry_run=arguments.dry_run,
            max_cost_usd=arguments.max_cost_usd,
            kill_switch_enabled=settings.real_api_kill_switch,
            credentials_configured=(
                settings.dataforseo_login is not None
                and settings.dataforseo_password is not None
            ),
        )
        if arguments.collection_category in {"serp", "llm"} and not arguments.dry_run:
            if (
                arguments.estimated_cost_usd is None
                or arguments.estimated_cost_usd <= 0
                or arguments.max_cost_usd is None
                or arguments.estimated_cost_usd > arguments.max_cost_usd
            ):
                print(
                    json.dumps(
                        {
                            "status": "blocked_budget",
                            "http_calls": 0,
                            "reason": (
                                "a positive --estimated-cost-usd no greater than "
                                "--max-cost-usd is required"
                            ),
                        }
                    )
                )
                return 2
        if arguments.collection_category == "serp" and preflight_result.allowed:
            from geo_research.collection.standard_serp import (
                StandardSERPCollector,
                load_active_standard_organic_assignments,
            )

            paths = RepositoryPaths.discover()
            registry_directory = (
                arguments.registries_directory or paths.config / "registries"
            )
            assignments = load_active_standard_organic_assignments(
                str(registry_directory)
            )
            assignments = _filter_standard_serp_assignments(
                assignments,
                query_id=arguments.query_id,
                target_ids=arguments.target_id,
                search_engine=arguments.search_engine,
            )
            if arguments.dry_run:
                print(
                    json.dumps(
                        {
                            "status": "dry_run",
                            "http_calls": 0,
                            "active_assignments": len(assignments),
                        }
                    )
                )
                return 0
            if not assignments:
                print(json.dumps({"status": "no_active_assignments", "http_calls": 0}))
                return 0
            total_estimated_cost = _total_estimated_cost(
                len(assignments), arguments.estimated_cost_usd
            )
            if total_estimated_cost > arguments.max_cost_usd:
                print(
                    json.dumps(
                        {
                            "status": "blocked_budget",
                            "http_calls": 0,
                            "assignment_count": len(assignments),
                            "estimated_total_cost_usd": total_estimated_cost,
                            "max_cost_usd": arguments.max_cost_usd,
                        }
                    )
                )
                return 2
            if (
                settings.dataforseo_login is None
                or settings.dataforseo_password is None
            ):
                raise ConfigurationError("DataForSEO credentials are not configured")
            database_path = (
                arguments.database or paths.warehouse_data / "geo_research.duckdb"
            )
            raw_directory = arguments.raw_directory or paths.raw_data
            database = DuckDBStore(database_path)
            database.initialize()
            run_id = f"serp-{__import__('uuid').uuid4()}"
            raw_store = RawStore(raw_directory)
            repository = RawEvidenceRepository(database, raw_store)
            submitted_keys = repository.submitted_serp_assignment_keys(
                arguments.collection_window
            )
            assignments = [
                assignment
                for assignment in assignments
                if (
                    str(assignment.query.query_id),
                    str(assignment.target.search_target_id),
                )
                not in submitted_keys
            ]
            if not assignments:
                print(
                    json.dumps(
                        {
                            "status": "already_submitted",
                            "http_calls": 0,
                            "collection_window": arguments.collection_window,
                        }
                    )
                )
                return 0
            try:
                with httpx.Client() as transport:
                    client = DataForSEOClient(
                        DataForSEOCredentials(
                            login=settings.dataforseo_login,
                            password=settings.dataforseo_password,
                        ),
                        transport,
                    )
                    collector = StandardSERPCollector(
                        repository,
                        raw_store,
                        client.request,
                    )
                    serp_results = [
                        collector.collect(
                            assignment,
                            run_id=run_id,
                            collection_window=arguments.collection_window,
                            estimated_cost_usd=arguments.estimated_cost_usd,
                        )
                        for assignment in assignments
                    ]
            except (DataForSEOError, ValueError) as error:
                print(json.dumps({"status": "collection_error", "error": str(error)}))
                return 2
            print(
                json.dumps(
                    {
                        "status": "submitted_pending_result",
                        "http_calls": len(serp_results),
                        "request_ids": [result.request_id for result in serp_results],
                        "task_ids": [result.task_id for result in serp_results],
                    }
                )
            )
            return 0
        if arguments.collection_category == "llm" and preflight_result.allowed:
            from geo_research.collection.llm_collector import (
                LLMCollector,
                load_active_llm_scraper_assignments,
            )

            paths = RepositoryPaths.discover()
            registry_directory = (
                arguments.registries_directory or paths.config / "registries"
            )
            llm_assignments = load_active_llm_scraper_assignments(
                str(registry_directory)
            )
            llm_assignments = _filter_llm_assignments(
                llm_assignments,
                prompt_id=arguments.prompt_id,
                target_ids=arguments.target_id,
                platform=arguments.platform,
            )
            if arguments.dry_run:
                print(
                    json.dumps(
                        {
                            "status": "dry_run",
                            "http_calls": 0,
                            "active_assignments": len(llm_assignments),
                        }
                    )
                )
                return 0
            if not llm_assignments:
                print(json.dumps({"status": "no_active_assignments", "http_calls": 0}))
                return 0
            total_estimated_cost = _total_estimated_cost(
                len(llm_assignments), arguments.estimated_cost_usd
            )
            if total_estimated_cost > arguments.max_cost_usd:
                print(
                    json.dumps(
                        {
                            "status": "blocked_budget",
                            "http_calls": 0,
                            "assignment_count": len(llm_assignments),
                            "estimated_total_cost_usd": total_estimated_cost,
                            "max_cost_usd": arguments.max_cost_usd,
                        }
                    )
                )
                return 2
            if (
                settings.dataforseo_login is None
                or settings.dataforseo_password is None
            ):
                raise ConfigurationError("DataForSEO credentials are not configured")
            database_path = (
                arguments.database or paths.warehouse_data / "geo_research.duckdb"
            )
            raw_directory = arguments.raw_directory or paths.raw_data
            database = DuckDBStore(database_path)
            database.initialize()
            raw_store = RawStore(raw_directory)
            repository = RawEvidenceRepository(database, raw_store)
            submitted_keys = repository.submitted_llm_assignment_keys(
                arguments.collection_window
            )
            llm_assignments = [
                assignment
                for assignment in llm_assignments
                if (
                    str(assignment.prompt.prompt_id),
                    str(assignment.target.llm_target_id),
                )
                not in submitted_keys
            ]
            if not llm_assignments:
                print(
                    json.dumps(
                        {
                            "status": "already_submitted",
                            "http_calls": 0,
                            "collection_window": arguments.collection_window,
                        }
                    )
                )
                return 0
            run_id = f"llm-{__import__('uuid').uuid4()}"
            try:
                with httpx.Client(timeout=130.0) as transport:
                    client = DataForSEOClient(
                        DataForSEOCredentials(
                            login=settings.dataforseo_login,
                            password=settings.dataforseo_password,
                        ),
                        transport,
                        read_timeout_seconds=125.0,
                    )
                    llm_collector = LLMCollector(
                        repository,
                        raw_store,
                        client.request,
                    )
                    llm_results = [
                        llm_collector.collect(
                            assignment,
                            run_id=run_id,
                            collection_window=arguments.collection_window,
                            estimated_cost_usd=arguments.estimated_cost_usd,
                        )
                        for assignment in llm_assignments
                    ]
            except (DataForSEOError, ValueError) as error:
                print(json.dumps({"status": "collection_error", "error": str(error)}))
                return 2
            print(
                json.dumps(
                    {
                        "status": "completed",
                        "http_calls": len(llm_results),
                        "request_ids": [result.request_id for result in llm_results],
                    }
                )
            )
            return 0


        print(
            json.dumps(
                {
                    "status": "dry_run" if arguments.dry_run else "blocked_preflight",
                    "dry_run": arguments.dry_run,
                    "http_calls": 0,
                    "preflight_reasons": preflight_result.reasons,
                }
            )
        )
        return 0 if arguments.dry_run else 2
    if arguments.command == "retrieve":
        settings = Settings.load()
        from geo_research.collection.preflight import Phase6Preflight
        from geo_research.collection.standard_serp import StandardSERPCollector

        preflight_result = Phase6Preflight(
            RepositoryPaths.discover().root / "docs" / "api_evidence_register.md",
            ci_environment=bool(os.environ.get("CI")),
        ).check(
            target=(
                "DataForSEO Standard SERP"
                if arguments.retrieval_category == "serp"
                else "DataForSEO LLM Scraper"
            ),
            allow_real_api=arguments.allow_real_api,
            dry_run=arguments.dry_run,
            max_cost_usd=arguments.max_cost_usd,
            kill_switch_enabled=settings.real_api_kill_switch,
            credentials_configured=(
                settings.dataforseo_login is not None
                and settings.dataforseo_password is not None
            ),
        )
        paths = RepositoryPaths.discover()
        database_path = (
            arguments.database or paths.warehouse_data / "geo_research.duckdb"
        )
        raw_directory = arguments.raw_directory or paths.raw_data
        database = DuckDBStore(database_path)
        database.initialize()
        repository = RawEvidenceRepository(database, RawStore(raw_directory))
        if arguments.dry_run:
            pending_tasks = (
                repository.pending_standard_serp_tasks()
                if arguments.retrieval_category == "serp"
                else repository.pending_llm_tasks()
            )
            print(
                json.dumps(
                    {
                        "status": "dry_run",
                        "http_calls": 0,
                        "pending_tasks": len(pending_tasks),
                    }
                )
            )
            return 0
        if not preflight_result.allowed:
            print(
                json.dumps(
                    {
                        "status": "blocked_preflight",
                        "http_calls": 0,
                        "preflight_reasons": preflight_result.reasons,
                    }
                )
            )
            return 2
        if settings.dataforseo_login is None or settings.dataforseo_password is None:
            raise ConfigurationError("DataForSEO credentials are not configured")
        raw_store = RawStore(raw_directory)
        with httpx.Client() as transport:
            client = DataForSEOClient(
                DataForSEOCredentials(
                    login=settings.dataforseo_login,
                    password=settings.dataforseo_password,
                ),
                transport,
            )
            if arguments.retrieval_category == "serp":
                task_ids = StandardSERPCollector(
                    RawEvidenceRepository(database, raw_store),
                    raw_store,
                    client.request,
                ).retrieve_ready()
            else:
                from geo_research.collection.llm_collector import LLMCollector

                task_ids = LLMCollector(
                    RawEvidenceRepository(database, raw_store),
                    raw_store,
                    client.request,
                ).retrieve_ready()
        print(
            json.dumps(
                {
                    "status": "completed",
                    "retrieved_task_ids": task_ids,
                    "http_calls": 1 + len(task_ids),
                }
            )
        )
        return 0
    if arguments.command == "smoke":
        settings = Settings.load()
        from geo_research.collection.preflight import Phase6Preflight

        preflight_result = Phase6Preflight(
            RepositoryPaths.discover().root / "docs" / "api_evidence_register.md",
            ci_environment=bool(os.environ.get("CI")),
        ).check(
            target="Google Organic SERP",
            allow_real_api=arguments.allow_real_api,
            dry_run=arguments.dry_run,
            max_cost_usd=arguments.max_cost_usd,
            kill_switch_enabled=settings.real_api_kill_switch,
            credentials_configured=(
                settings.dataforseo_login is not None
                and settings.dataforseo_password is not None
            ),
        )
        if not preflight_result.allowed:
            print(
                json.dumps(
                    {
                        "status": "blocked_preflight",
                        "http_calls": 0,
                        "preflight_reasons": preflight_result.reasons,
                    }
                )
            )
            return 2
        adapter = GoogleOrganicAdapter()
        request = adapter.build_payload(
            Query(
                query_id="google-task-post-smoke",
                keyword=arguments.keyword,
                language=arguments.language_code,
                market="smoke",
                active=True,
            ),
            SearchTarget(
                search_target_id="google-task-post-smoke",
                provider="dataforseo",
                search_engine="google",
                search_type="organic",
                retrieval_method="standard",
                location_code=arguments.location_code,
                language_code=arguments.language_code,
                device=arguments.device,
                operating_system=arguments.operating_system,
                depth=arguments.depth,
                active=True,
            ),
        )
        if arguments.dry_run:
            print(
                json.dumps(
                    {
                        "status": "dry_run",
                        "http_calls": 0,
                        "endpoint": request.endpoint,
                        "http_method": adapter.capability.http_method,
                        "payload": request.payload,
                    }
                )
            )
            return 0
        if settings.dataforseo_login is None or settings.dataforseo_password is None:
            raise ConfigurationError("DataForSEO credentials are not configured")
        try:
            with httpx.Client() as transport:
                envelope = DataForSEOClient(
                    DataForSEOCredentials(
                        login=settings.dataforseo_login,
                        password=settings.dataforseo_password,
                    ),
                    transport,
                ).request(
                    adapter.capability.http_method or "POST",
                    request.endpoint,
                    request.payload,
                )
        except DataForSEOError as error:
            print(
                json.dumps(
                    {"status": "provider_error", "http_calls": 1, "error": str(error)}
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "status": "submitted",
                    "http_calls": 1,
                    "correlation_id": envelope.correlation_id,
                    "provider_request_id": envelope.provider_request_id,
                    "response": envelope.payload,
                }
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
