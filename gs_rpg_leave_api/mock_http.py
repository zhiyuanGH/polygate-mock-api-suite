"""Small dependency-free HTTP toolkit for independently deployable mock APIs."""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


Json = dict[str, Any] | list[Any]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


class JsonStore:
    def __init__(self, seed_path: Path):
        self.seed_path = seed_path
        self.lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.data = json.loads(self.seed_path.read_text(encoding="utf-8"))


@dataclass
class Actor:
    actor_id: str
    role: str


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    body: dict[str, Any]
    headers: Any
    params: dict[str, str]
    actor: Actor | None

    def one(self, name: str, default: str | None = None) -> str | None:
        values = self.query.get(name)
        return values[0] if values else default

    def require(self, *names: str) -> None:
        missing = [name for name in names if self.body.get(name) in (None, "")]
        if missing:
            raise ApiError(400, "missing_field", f"Required field(s): {', '.join(missing)}")


@dataclass
class Route:
    method: str
    pattern: re.Pattern[str]
    path_template: str
    handler: Callable[[Request, JsonStore], tuple[int, Json] | Json]
    operation_id: str
    summary: str
    description: str
    parameters: list[dict[str, Any]]
    request_schema: dict[str, Any] | None
    public: bool


class Api:
    def __init__(self, title: str, service: str, version: str = "1.0.0"):
        self.title = title
        self.service = service
        self.version = version
        self.routes: list[Route] = []

    def route(
        self,
        method: str,
        pattern: str,
        path_template: str,
        handler: Callable[[Request, JsonStore], tuple[int, Json] | Json],
        *,
        operation_id: str,
        summary: str,
        description: str = "",
        parameters: list[dict[str, Any]] | None = None,
        request_schema: dict[str, Any] | None = None,
        public: bool = False,
    ) -> None:
        self.routes.append(
            Route(
                method.upper(),
                re.compile(f"^{pattern}$"),
                path_template,
                handler,
                operation_id,
                summary,
                description,
                parameters or [],
                request_schema,
                public,
            )
        )

    def openapi(self, base_url: str) -> dict[str, Any]:
        paths: dict[str, Any] = {
            "/health": {"get": {"operationId": "healthCheck", "summary": "Check service health", "security": [], "responses": {"200": {"description": "Service is healthy"}}}},
            "/openapi.json": {"get": {"operationId": "getOpenApiDocument", "summary": "Get this agent tool contract", "security": [], "responses": {"200": {"description": "OpenAPI 3.1 document"}}}},
        }
        for route in self.routes:
            operation: dict[str, Any] = {
                "operationId": route.operation_id,
                "summary": route.summary,
                "description": route.description,
                "parameters": route.parameters,
                "responses": {
                    "200": {"description": "Successful operation", "content": {"application/json": {}}},
                    "400": {"description": "Invalid request"},
                    "401": {"description": "Missing or invalid token"},
                    "404": {"description": "Resource not found"},
                    "409": {"description": "State or scheduling conflict"},
                },
            }
            if route.request_schema is not None:
                operation["requestBody"] = {
                    "required": True,
                    "content": {"application/json": {"schema": route.request_schema}},
                }
            if not route.public:
                operation["security"] = [{"bearerAuth": []}]
            paths.setdefault(route.path_template, {})[route.method.lower()] = operation
        return {
            "openapi": "3.1.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": "Synthetic competition service. It is isolated from PolyU production systems.",
            },
            "servers": [{"url": base_url}],
            "paths": paths,
            "components": {
                "securitySchemes": {
                    "bearerAuth": {"type": "http", "scheme": "bearer", "description": "Demo token from README"}
                }
            },
        }

    def make_handler(self, store: JsonStore, tokens: dict[str, Actor]):
        api = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"PolyGate/{api.version}"

            def send_json(self, status: int, payload: Json) -> None:
                body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Request-Id", str(uuid.uuid4()))
                self.end_headers()
                self.wfile.write(body)

            def parse_body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length == 0:
                    return {}
                if length > 1_000_000:
                    raise ApiError(413, "payload_too_large", "JSON body exceeds 1 MB")
                try:
                    value = json.loads(self.rfile.read(length))
                except json.JSONDecodeError as exc:
                    raise ApiError(400, "invalid_json", str(exc)) from exc
                if not isinstance(value, dict):
                    raise ApiError(400, "invalid_json", "JSON body must be an object")
                return value

            def actor_for(self, public: bool) -> Actor | None:
                if public:
                    return None
                header = self.headers.get("Authorization", "")
                token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
                actor = tokens.get(token)
                if actor is None:
                    raise ApiError(401, "unauthorized", "Use a valid Bearer token")
                return actor

            def dispatch(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/health" and self.command == "GET":
                    self.send_json(200, {"status": "ok", "service": api.service, "environment": "competition-sandbox"})
                    return
                if parsed.path == "/openapi.json" and self.command == "GET":
                    host = self.headers.get("Host", "localhost")
                    self.send_json(200, api.openapi(f"http://{host}"))
                    return
                try:
                    for route in api.routes:
                        match = route.pattern.match(parsed.path)
                        if route.method != self.command or match is None:
                            continue
                        request = Request(
                            self.command,
                            parsed.path,
                            parse_qs(parsed.query),
                            self.parse_body(),
                            self.headers,
                            match.groupdict(),
                            self.actor_for(route.public),
                        )
                        result = route.handler(request, store)
                        status, payload = result if isinstance(result, tuple) else (200, result)
                        self.send_json(status, payload)
                        return
                    raise ApiError(404, "not_found", f"No route for {self.command} {parsed.path}")
                except ApiError as exc:
                    error: dict[str, Any] = {"code": exc.code, "message": exc.message}
                    if exc.details is not None:
                        error["details"] = exc.details
                    self.send_json(exc.status, {"error": error})
                except (TypeError, ValueError) as exc:
                    self.send_json(400, {"error": {"code": "invalid_parameter", "message": str(exc)}})

            do_GET = dispatch
            do_POST = dispatch
            do_PATCH = dispatch
            do_DELETE = dispatch

            def log_message(self, format: str, *args: Any) -> None:
                stamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
                print(f"{stamp} {self.address_string()} {format % args}")

        return Handler


def query_parameter(name: str, description: str, schema_type: str = "string", required: bool = False) -> dict[str, Any]:
    return {"name": name, "in": "query", "required": required, "description": description, "schema": {"type": schema_type}}


def path_parameter(name: str, description: str) -> dict[str, Any]:
    return {"name": name, "in": "path", "required": True, "description": description, "schema": {"type": "string"}}


def object_schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "required": required, "properties": properties, "additionalProperties": False}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
