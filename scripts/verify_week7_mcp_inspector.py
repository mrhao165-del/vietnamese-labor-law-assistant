"""Verify the production Week-7 MCP server through the official Inspector CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "evaluation/results/week7_mcp_inspector_verification.json"
CACHE_PATH = ROOT / ".cache/npm-mcp-inspector"
SERVER_NAME = "legal-retrieval"
SERVER_MODULE = "vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server"
TOOL_ALLOWLIST = [
    "search_labor_law",
    "get_article",
    "get_clause",
    "get_document_metadata",
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sanitized_args(args: list[str]) -> list[str]:
    """Keep reproducible argument shapes without persisting local absolute paths."""
    sanitized: list[str] = []
    for argument in args:
        path = Path(argument)
        if path.is_absolute():
            sanitized.append("<temp-config>" if path.suffix == ".json" else f"<{path.name}>")
        else:
            sanitized.append(argument)
    return sanitized


def _command_record(
    name: str, args: list[str], env: dict[str, str], timeout_seconds: int
) -> tuple[dict[str, Any], str]:
    started = time.perf_counter()
    started_at = _now()
    try:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        record = {
            "name": name,
            "args": _sanitized_args(args),
            "exit_code": completed.returncode,
            "timed_out": False,
            "started_at": started_at,
            "finished_at": _now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_sha256": sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": sha256(stderr.encode("utf-8")).hexdigest(),
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
        }
        return record, stdout
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        record = {
            "name": name,
            "args": _sanitized_args(args),
            "exit_code": None,
            "timed_out": True,
            "started_at": started_at,
            "finished_at": _now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_sha256": sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": sha256(stderr.encode("utf-8")).hexdigest(),
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
        }
        return record, stdout


def _json_candidates(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    values: list[Any] = []
    for index, character in enumerate(text):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        values.append(value)
    return values


def _find_mapping(value: Any, predicate: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if predicate(value):
            return value
        for nested in value.values():
            found = _find_mapping(nested, predicate)
            if found is not None:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _find_mapping(nested, predicate)
            if found is not None:
                return found
    return None


def _tool_response(text: str) -> dict[str, Any] | None:
    for candidate in reversed(_json_candidates(text)):
        response = _find_mapping(
            candidate,
            lambda item: (
                isinstance(item.get("ok"), bool)
                and isinstance(item.get("meta"), dict)
                and "tool" in item["meta"]
            ),
        )
        if response is not None:
            return response
    return None


def _tools(text: str) -> list[dict[str, Any]] | None:
    for candidate in reversed(_json_candidates(text)):
        response = _find_mapping(
            candidate,
            lambda item: (
                isinstance(item.get("tools"), list)
                and all(isinstance(tool, dict) for tool in item["tools"])
            ),
        )
        if response is not None:
            return response["tools"]
    return None


def _environment(cache_path: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "npm_config_cache": str(cache_path),
            "npm_config_update_notifier": "false",
            "npm_config_fund": "false",
            "npm_config_audit": "false",
            "MCP_AUTO_OPEN_ENABLED": "false",
            "NO_COLOR": "1",
            "CI": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return environment


def _write_config(directory: Path) -> Path:
    path = directory / "week7_mcp_inspector_config.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    SERVER_NAME: {
                        "type": "stdio",
                        "command": "uv",
                        "args": ["run", "python", "-m", SERVER_MODULE],
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _inspector_args(version: str, config: Path, method: str, *tool_args: str) -> list[str]:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx is None:
        raise RuntimeError("npx executable was not found")
    args = [
        npx,
        "-y",
        f"@modelcontextprotocol/inspector@{version}",
        "--cli",
        "--config",
        str(config),
        "--server",
        SERVER_NAME,
        "--method",
        method,
    ]
    args.extend(tool_args)
    return args


def _tool_call_args(tool_name: str, *arguments: str) -> tuple[str, ...]:
    return (
        "--tool-name",
        tool_name,
        *(item for argument in arguments for item in ("--tool-arg", argument)),
    )


def _successful_tool_response(response: dict[str, Any] | None, name: str) -> bool:
    """Return whether a parsed tool response matches the public success envelope."""
    return bool(
        response
        and response.get("ok") is True
        and response.get("meta", {}).get("tool") == name
        and response.get("meta", {}).get("schema_version") == "1.0"
        and response.get("meta", {}).get("request_id")
    )


def main() -> None:
    CACHE_PATH.mkdir(parents=True, exist_ok=True)
    probe = CACHE_PATH / ".write-probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    environment = _environment(CACHE_PATH)
    commands: list[dict[str, Any]] = []
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm executable was not found")
    version_record, version_stdout = _command_record(
        "npm_view_inspector_version",
        [npm, "view", "@modelcontextprotocol/inspector", "version"],
        environment,
        120,
    )
    commands.append(version_record)
    version = version_stdout.strip().splitlines()[-1] if version_record["exit_code"] == 0 else ""
    if not version:
        report = {
            "week": 7,
            "verification": "mcp_inspector_cli",
            "status": "FAIL",
            "verified_at": _now(),
            "inspector": {"package": "@modelcontextprotocol/inspector", "version": None},
            "npm_cache": {
                "strategy": "isolated",
                "location_kind": "workspace",
                "eacces_avoided": True,
            },
            "server": {"type": "production", "entrypoint": SERVER_MODULE},
            "checks": {},
            "commands": commands,
            "notes": [
                "Could not resolve the official Inspector version through the isolated cache."
            ],
        }
        RESULT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(1)

    with tempfile.TemporaryDirectory(prefix="week7-mcp-inspector-") as temporary:
        config = _write_config(Path(temporary))
        requests = [
            ("tools_list", "tools/list", (), 180),
            (
                "search_labor_law",
                "tools/call",
                _tool_call_args(
                    "search_labor_law",
                    "query=Người lao động nghỉ việc phải báo trước bao lâu?",
                    "top_k=5",
                ),
                300,
            ),
            ("get_article", "tools/call", _tool_call_args("get_article", "article_number=35"), 180),
            (
                "get_clause",
                "tools/call",
                _tool_call_args("get_clause", "article_number=35", "clause_number=1"),
                180,
            ),
            ("get_document_metadata", "tools/call", _tool_call_args("get_document_metadata"), 180),
            (
                "invalid_top_k",
                "tools/call",
                _tool_call_args("search_labor_law", "query=nghỉ việc", "top_k=0"),
                180,
            ),
            ("post_invalid_tools_list", "tools/list", (), 180),
        ]
        outputs: dict[str, str] = {}
        for name, method, tool_args, timeout_seconds in requests:
            record, output = _command_record(
                name,
                _inspector_args(version, config, method, *tool_args),
                environment,
                timeout_seconds,
            )
            commands.append(record)
            outputs[name] = output

    listed_tools = _tools(outputs["tools_list"])
    exact_allowlist = (
        bool(listed_tools) and [tool.get("name") for tool in listed_tools] == TOOL_ALLOWLIST
    )
    search_schema = next(
        (tool for tool in listed_tools or [] if tool.get("name") == "search_labor_law"), {}
    )
    search_properties = search_schema.get("inputSchema", {}).get("properties", {})
    schema_ok = (
        bool(listed_tools)
        and all(tool.get("description") and tool.get("inputSchema") for tool in listed_tools)
        and {"query", "top_k"}.issubset(search_properties)
        and search_properties["top_k"].get("minimum") == 1
        and search_properties["top_k"].get("maximum") == 10
        and "article_number"
        in next(tool for tool in listed_tools if tool.get("name") == "get_article")
        .get("inputSchema", {})
        .get("properties", {})
        and {"article_number", "clause_number"}.issubset(
            next(tool for tool in listed_tools if tool.get("name") == "get_clause")
            .get("inputSchema", {})
            .get("properties", {})
        )
    )
    parsed = {name: _tool_response(output) for name, output in outputs.items()}
    search = parsed["search_labor_law"]
    article = parsed["get_article"]
    clause = parsed["get_clause"]
    metadata = parsed["get_document_metadata"]
    invalid = parsed["invalid_top_k"]
    search_rows = search.get("data", {}).get("results", []) if search else []
    article_data = article.get("data", {}) if article else {}
    clause_data = clause.get("data", {}) if clause else {}
    metadata_data = metadata.get("data", {}) if metadata else {}
    search_ok = (
        _successful_tool_response(search, "search_labor_law")
        and bool(search_rows)
        and len({row.get("chunk_id") for row in search_rows}) == len(search_rows)
    )
    article_ok = (
        _successful_tool_response(article, "get_article")
        and article_data.get("article_number") == 35
    )
    clause_ok = (
        _successful_tool_response(clause, "get_clause")
        and clause_data.get("article_number") == 35
        and clause_data.get("clause_number") == 1
    )
    metadata_ok = _successful_tool_response(metadata, "get_document_metadata") and bool(
        metadata_data
    )
    invalid_ok = bool(
        (invalid and invalid.get("ok") is False)
        or (commands[-2]["exit_code"] not in (0, None) and not commands[-2]["timed_out"])
    )
    no_leak_terms = ("traceback", "api_key", "openai_api_key", str(ROOT).casefold())
    all_output = "\n".join(outputs.values()).casefold()
    sanitization_ok = not any(term.casefold() in all_output for term in no_leak_terms)
    checks = {
        "tools_list": "PASS" if commands[1]["exit_code"] == 0 and listed_tools else "FAIL",
        "exact_tool_allowlist": "PASS" if exact_allowlist else "FAIL",
        "tool_schemas": "PASS" if schema_ok else "FAIL",
        "search_labor_law": "PASS" if search_ok else "FAIL",
        "get_article": "PASS" if article_ok else "FAIL",
        "get_clause": "PASS" if clause_ok else "FAIL",
        "get_document_metadata": "PASS" if metadata_ok else "FAIL",
        "invalid_top_k": "PASS" if invalid_ok and commands[-1]["exit_code"] == 0 else "FAIL",
        "error_sanitization": "PASS" if sanitization_ok else "FAIL",
    }
    passed = all(value == "PASS" for value in checks.values())
    report = {
        "week": 7,
        "verification": "mcp_inspector_cli",
        "status": "PASS" if passed else "FAIL",
        "verified_at": _now(),
        "inspector": {
            "package": "@modelcontextprotocol/inspector",
            "version": version,
            "node_version": subprocess.check_output(["node", "--version"], text=True).strip(),
            "npm_version": subprocess.check_output([npm, "--version"], text=True).strip(),
            "transport": "stdio",
            "mode": "cli",
        },
        "npm_cache": {"strategy": "isolated", "location_kind": "workspace", "eacces_avoided": True},
        "server": {"type": "production", "entrypoint": SERVER_MODULE},
        "checks": checks,
        "commands": commands,
        "notes": [
            "Temporary MCP config was deleted after the run.",
            "Raw output was validated in-process; evidence retains hashes and byte counts.",
        ],
    }
    RESULT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
