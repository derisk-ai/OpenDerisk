"""FastAPI utilities."""

import importlib.metadata as metadata
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI
from fastapi.routing import APIRouter
from starlette.routing import WebSocketRoute

_FASTAPI_VERSION = metadata.version("fastapi")


class PriorityAPIRouter(APIRouter):
    """A router with priority.

    The route with higher priority will be put in the front of the route list.
    WebSocket routes are given higher priority by default to ensure proper routing.
    """

    def __init__(self, *args, **kwargs):
        """Init a PriorityAPIRouter."""
        super().__init__(*args, **kwargs)
        self.route_priority: Dict[str, int] = {}

    def add_api_route(
        self, path: str, endpoint: Callable, *, priority: int = 0, **kwargs: Any
    ):
        """Add a route with priority.

        Args:
            path (str): The path of the route.
            endpoint (Callable): The endpoint of the route.
            priority (int, optional): The priority of the route. Defaults to 0.
            **kwargs (Any): Other arguments.
        """
        super().add_api_route(path, endpoint, **kwargs)
        self.route_priority[path] = priority
        # Sort the routes by priority.
        self.sort_routes_by_priority()

    def add_api_websocket_route(
        self, path: str, endpoint: Callable, *, priority: int = 10, **kwargs: Any
    ):
        """Add a WebSocket route with priority.

        WebSocket routes get higher priority by default (10) to ensure they are
        matched before HTTP routes, preventing 403 Forbidden errors.

        Args:
            path (str): The path of the WebSocket route.
            endpoint (Callable): The WebSocket endpoint.
            priority (int, optional): The priority. Defaults to 10 for WebSocket routes.
            **kwargs (Any): Other arguments.
        """
        super().add_api_websocket_route(path, endpoint, **kwargs)
        self.route_priority[path] = priority
        # Sort the routes by priority to ensure WebSocket routes are first.
        self.sort_routes_by_priority()

    def add_websocket_route(
        self,
        path: str,
        endpoint: Callable,
        name: Optional[str] = None,
        *,
        priority: int = 10,
    ):
        """Add a WebSocket route with priority.

        This method is called by include_router for starlette.routing.WebSocketRoute.
        WebSocket routes get higher priority by default (10).

        Args:
            path (str): The path of the WebSocket route.
            endpoint (Callable): The WebSocket endpoint.
            name (str, optional): The name of the route.
            priority (int, optional): The priority. Defaults to 10.
        """
        super().add_websocket_route(path, endpoint, name=name)
        self.route_priority[path] = priority
        # Sort the routes by priority to ensure WebSocket routes are first.
        self.sort_routes_by_priority()

    def sort_routes_by_priority(self):
        """Sort the routes by priority.

        WebSocket routes get higher priority (10) by default to ensure they are
        matched before HTTP routes, preventing 403 Forbidden errors.
        """

        def get_priority(route):
            # Check if route is WebSocket route using isinstance
            # WebSocketRoute is from starlette.routing
            if isinstance(route, WebSocketRoute):
                # WebSocket routes get higher priority to ensure proper routing
                return self.route_priority.get(route.path, 10)
            # Root/static routes get lowest priority
            if route.path in ["", "/"]:
                return -100
            return self.route_priority.get(route.path, 0)

        self.routes.sort(key=get_priority, reverse=True)


_HAS_STARTUP = False
_HAS_SHUTDOWN = False
_GLOBAL_STARTUP_HANDLERS: List[Callable] = []

_GLOBAL_SHUTDOWN_HANDLERS: List[Callable] = []


def register_event_handler(app: FastAPI, event: str, handler: Callable):
    import sys
    print(f"[register_event_handler] event={event}, FastAPI version={_FASTAPI_VERSION}", file=sys.stderr, flush=True)
    if _FASTAPI_VERSION >= "0.109.1":
        if event == "startup":
            if _HAS_STARTUP:
                raise ValueError(
                    "FastAPI app already started. Cannot add startup handler."
                )
            _GLOBAL_STARTUP_HANDLERS.append(handler)
            print(f"[register_event_handler] Added startup handler, total: {len(_GLOBAL_STARTUP_HANDLERS)}", file=sys.stderr, flush=True)
        elif event == "shutdown":
            if _HAS_SHUTDOWN:
                raise ValueError(
                    "FastAPI app already shutdown. Cannot add shutdown handler."
                )
            _GLOBAL_SHUTDOWN_HANDLERS.append(handler)
        else:
            raise ValueError(f"Invalid event: {event}")
    else:
        if event == "startup":
            app.add_event_handler("startup", handler)
        elif event == "shutdown":
            app.add_event_handler("shutdown", handler)
        else:
            raise ValueError(f"Invalid event: {event}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys
    print(f"[lifespan] Called, handlers count: {len(_GLOBAL_STARTUP_HANDLERS)}", file=sys.stderr, flush=True)
    global _HAS_STARTUP, _HAS_SHUTDOWN
    for handler in _GLOBAL_STARTUP_HANDLERS:
        print(f"[lifespan] Calling handler: {handler}", file=sys.stderr, flush=True)
        await handler()
    _HAS_STARTUP = True
    print("[lifespan] Startup complete", file=sys.stderr, flush=True)
    yield
    for handler in _GLOBAL_SHUTDOWN_HANDLERS:
        await handler()
    _HAS_SHUTDOWN = True


def create_app(*args, **kwargs) -> FastAPI:
    import sys
    print(f"[create_app] Called, FastAPI version={_FASTAPI_VERSION}", file=sys.stderr, flush=True)
    _sp = None
    if _FASTAPI_VERSION >= "0.109.1":
        if "lifespan" not in kwargs:
            kwargs["lifespan"] = lifespan
            print("[create_app] Using default lifespan", file=sys.stderr, flush=True)
        _sp = kwargs["lifespan"]
    app = FastAPI(*args, **kwargs)
    if _sp:
        app.__derisk_custom_lifespan = _sp
        print(f"[create_app] Set __derisk_custom_lifespan", file=sys.stderr, flush=True)
    return app


def replace_router(app: FastAPI, router: Optional[APIRouter] = None):
    import sys
    print(f"[replace_router] Called, FastAPI version={_FASTAPI_VERSION}", file=sys.stderr, flush=True)
    if not router:
        router = PriorityAPIRouter()
    if _FASTAPI_VERSION >= "0.109.1":
        if hasattr(app, "__derisk_custom_lifespan"):
            _sp = getattr(app, "__derisk_custom_lifespan")
            router.lifespan_context = _sp
            print(f"[replace_router] Set lifespan_context on router", file=sys.stderr, flush=True)
        else:
            print("[replace_router] No __derisk_custom_lifespan found", file=sys.stderr, flush=True)

    app.router = router
    app.setup()
    return app
