"""Verify the production Week-8 calculator MCP server through Inspector CLI."""

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
RESULT = ROOT / "evaluation/results/week8_mcp_inspector_verification.json"
CACHE = ROOT / ".cache/npm-mcp-inspector"
SERVER_NAME = "legal-calculator"
SERVER_MODULE = "vietnamese_labor_law_assistant.mcp_servers.legal_calculator.server"
ALLOWLIST = ["calculate_notice_period", "calculate_contract_duration"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_args(args: list[str]) -> list[str]:
    result: list[str] = []
    for argument in args:
        path = Path(argument)
        if path.is_absolute():
            result.append("<temp-config>" if path.suffix == ".json" else f"<{path.name}>")
        else:
            result.append(argument)
    return result


def _run(
    name: str, args: list[str], env: dict[str, str], timeout: int
) -> tuple[dict[str, Any], str]:
    started, started_at = time.perf_counter(), _now()
    try:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        stdout, stderr, code, timed_out = (
            completed.stdout,
            completed.stderr,
            completed.returncode,
            False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        code, timed_out = None, True
    return (
        {
            "name": name,
            "args": _safe_args(args),
            "exit_code": code,
            "timed_out": timed_out,
            "started_at": started_at,
            "finished_at": _now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_sha256": sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": sha256(stderr.encode("utf-8")).hexdigest(),
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
        },
        stdout,
    )


def _candidates(text: str) -> list[Any]:
    decoder, values = json.JSONDecoder(), []
    for index, character in enumerate(text):
        if character in "[{":
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            values.append(value)
    return values


def _find(value: Any, predicate: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if predicate(value):
            return value
        for child in value.values():
            found = _find(child, predicate)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find(child, predicate)
            if found:
                return found
    return None


def _tools(text: str) -> list[dict[str, Any]] | None:
    for candidate in reversed(_candidates(text)):
        found = _find(candidate, lambda item: isinstance(item.get("tools"), list))
        if found and all(isinstance(tool, dict) for tool in found["tools"]):
            return found["tools"]
    return None


def _response(text: str) -> dict[str, Any] | None:
    for candidate in reversed(_candidates(text)):
        found = _find(
            candidate,
            lambda item: (
                isinstance(item.get("ok"), bool)
                and isinstance(item.get("meta"), dict)
                and "tool" in item["meta"]
            ),
        )
        if found:
            return found
    return None


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "npm_config_cache": str(CACHE),
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


def _config(directory: Path) -> Path:
    path = directory / "week8_mcp_inspector_config.json"
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
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _inspector_args(version: str, config: Path, method: str, *tool_args: str) -> list[str]:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx is None:
        raise RuntimeError("npx executable was not found")
    return [
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
        *tool_args,
    ]


def _call(tool: str, *arguments: str) -> tuple[str, ...]:
    return (
        "--tool-name",
        tool,
        *(part for argument in arguments for part in ("--tool-arg", argument)),
    )


def _success(response: dict[str, Any] | None, tool: str) -> bool:
    return bool(
        response
        and response.get("ok") is True
        and response.get("meta", {}).get("tool") == tool
        and response.get("meta", {}).get("schema_version") == "1.0"
        and response.get("meta", {}).get("request_id")
    )


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    probe = CACHE / ".write-probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    env, commands = _environment(), []
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm executable was not found")
    record, output = _run(
        "npm_view_inspector_version",
        [npm, "view", "@modelcontextprotocol/inspector", "version"],
        env,
        120,
    )
    commands.append(record)
    version = output.strip().splitlines()[-1] if record["exit_code"] == 0 and output.strip() else ""
    outputs: dict[str, str] = {}
    if version:
        with tempfile.TemporaryDirectory(prefix="week8-mcp-inspector-") as temporary:
            config = _config(Path(temporary))
            requests = [
                ("tools_list", "tools/list", (), 180),
                (
                    "notice",
                    "tools/call",
                    _call("calculate_notice_period", "contract_type=INDEFINITE"),
                    180,
                ),
                (
                    "duration",
                    "tools/call",
                    _call(
                        "calculate_contract_duration",
                        "contract_type=FIXED_TERM",
                        "start_date=2026-01-01",
                        "end_date=2029-01-01",
                    ),
                    180,
                ),
                (
                    "invalid_enum",
                    "tools/call",
                    _call("calculate_notice_period", "contract_type=UNKNOWN"),
                    180,
                ),
                (
                    "invalid_range",
                    "tools/call",
                    _call(
                        "calculate_contract_duration",
                        "contract_type=FIXED_TERM",
                        "start_date=2026-02-01",
                        "end_date=2026-01-01",
                    ),
                    180,
                ),
                ("post_invalid_tools_list", "tools/list", (), 180),
            ]
            for name, method, args, timeout in requests:
                record, output = _run(
                    name, _inspector_args(version, config, method, *args), env, timeout
                )
                commands.append(record)
                outputs[name] = output
    listed = _tools(outputs.get("tools_list", "")) or []
    by_name = {tool.get("name"): tool for tool in listed}
    notice_props = (
        by_name.get("calculate_notice_period", {}).get("inputSchema", {}).get("properties", {})
    )
    duration_props = (
        by_name.get("calculate_contract_duration", {}).get("inputSchema", {}).get("properties", {})
    )
    parsed = {name: _response(output) for name, output in outputs.items()}
    invalid_enum = parsed.get("invalid_enum")
    invalid_range = parsed.get("invalid_range")
    all_text = "\n".join(outputs.values()).casefold()
    checks = {
        "tools_list": "PASS"
        if commands and len(commands) > 1 and commands[1]["exit_code"] == 0
        else "FAIL",
        "exact_tool_allowlist": "PASS"
        if [tool.get("name") for tool in listed] == ALLOWLIST
        else "FAIL",
        "tool_schemas": "PASS"
        if all(tool.get("description") and tool.get("inputSchema") for tool in listed)
        and "contract_type" in notice_props
        and len(notice_props.get("contract_type", {}).get("enum", [])) == 3
        and "start_date" in duration_props
        and "pattern" in duration_props.get("start_date", {})
        else "FAIL",
        "calculate_notice_period": "PASS"
        if _success(parsed.get("notice"), "calculate_notice_period")
        else "FAIL",
        "calculate_contract_duration": "PASS"
        if _success(parsed.get("duration"), "calculate_contract_duration")
        else "FAIL",
        "invalid_enum": "PASS"
        if invalid_enum
        and invalid_enum.get("ok") is False
        and invalid_enum.get("error", {}).get("code") == "INVALID_CONTRACT_TYPE"
        else "FAIL",
        "invalid_date_range": "PASS"
        if invalid_range
        and invalid_range.get("ok") is False
        and invalid_range.get("error", {}).get("code") == "END_DATE_BEFORE_START_DATE"
        else "FAIL",
        "error_sanitization": "PASS"
        if not any(
            item in all_text
            for item in ("traceback", "api_key", "openai_api_key", str(ROOT).casefold())
        )
        else "FAIL",
        "post_invalid_server_health": "PASS"
        if commands
        and commands[-1]["name"] == "post_invalid_tools_list"
        and commands[-1]["exit_code"] == 0
        else "FAIL",
    }
    passed = bool(version) and all(value == "PASS" for value in checks.values())
    report = {
        "week": 8,
        "verification": "mcp_inspector_cli",
        "status": "PASS" if passed else "FAIL",
        "verified_at": _now(),
        "inspector": {
            "package": "@modelcontextprotocol/inspector",
            "version": version or None,
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
            "Evidence retains hashes and byte counts, not raw output.",
        ],
    }
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
