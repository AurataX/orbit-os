"""FastAPI transport and the static ORBIT-OS dashboard."""
import asyncio
import json
import os
import secrets
from pathlib import Path
from time import monotonic

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from orbit.compare import DEFAULT, RAM_FRAMES, VRAM_FRAMES, compare, what_if
from orbit.engine import CRISIS_QUEUE, MAX_TICKS
from orbit.logfmt import dmesg
from orbit.metrics import summarize
from session import REGISTRIES, Session, config_for, event_rows, task_row
from shell import MUTATING, choices_for, run_command, words_for

app = FastAPI(title="ORBIT-OS", version="1.0")
DEV_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000") if os.getenv("ORBIT_DEV") == "1" else ()
if DEV_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Orbit-Token"])

sessions: dict[str, Session] = {}


@app.exception_handler(ValueError)
async def bad_input(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def trusted_origin(connection):
    origin = connection.headers.get("origin")
    host = connection.headers.get("host")
    return not origin or origin in (*DEV_ORIGINS, f"http://{host}", f"https://{host}")


def authorized(token):
    expected = os.getenv("ORBIT_TOKEN")
    return not expected or (isinstance(token, str) and secrets.compare_digest(token.encode(), expected.encode()))


def require_token(request: Request):
    if not trusted_origin(request) or not authorized(request.headers.get("x-orbit-token")):
        raise HTTPException(403, "This action requires a valid demo token. Enter it under Settings.")


def session_for(id: str):
    if id not in sessions:
        raise HTTPException(404, "Session not found. Start a new simulation.")
    return sessions[id]


class Policies(BaseModel):
    cpu: str | None = None
    page: str | None = None
    disk: str | None = None
    place: str | None = None
    deadlock: str | None = None


class NewSession(Policies):
    seed: int = 42
    n_tasks: int = 40
    ram: int = RAM_FRAMES
    vram: int = VRAM_FRAMES


class Step(BaseModel):
    n: int = Field(1, ge=1, le=500)


class Rewind(BaseModel):
    tick: int


class Inject(BaseModel):
    kind: str
    n: int = 1


class Storm(BaseModel):
    name: str


class Resize(BaseModel):
    ram: int | None = None
    vram: int | None = None


class Kill(BaseModel):
    pid: int


class Boost(Kill):
    priority: int


class Command(BaseModel):
    line: str = Field(max_length=1000)


@app.get("/api/options")
def options():
    return {**{key: list(registry) for key, registry in REGISTRIES.items()}, "defaults": DEFAULT,
            "ram": RAM_FRAMES, "vram": VRAM_FRAMES, "crisis_queue": CRISIS_QUEUE,
            "max_ticks": MAX_TICKS, "token_required": bool(os.getenv("ORBIT_TOKEN"))}


@app.post("/api/sessions", dependencies=[Depends(require_token)])
def create(body: NewSession):
    session = Session(config_for(**body.model_dump(exclude_none=True)))
    id = secrets.token_urlsafe(12)
    sessions[id] = session
    return {"id": id, "frame": session.frame(), "config": session.config}


@app.get("/api/sessions/{id}/frame")
def frame(id: str, detail: bool = False, since: int | None = None, branch: str | None = None):
    session = session_for(id)
    with session.lock:
        if branch is not None and branch not in session.branches:
            raise HTTPException(404, "Branch not found.")
        return session.frame(detail, since, branch)


@app.post("/api/sessions/{id}/step", dependencies=[Depends(require_token)])
def step(id: str, body: Step):
    session = session_for(id)
    with session.lock:
        session.stop("Playback paused for manual stepping")
        session.advance(session.engine.now + body.n, action="step", params={"n": body.n})
        return session.frame()


@app.post("/api/sessions/{id}/checkpoint", dependencies=[Depends(require_token)])
def checkpoint(id: str):
    session = session_for(id)
    with session.lock:
        return {"tick": session.checkpoint(), "frame": session.frame()}


@app.post("/api/sessions/{id}/rewind", dependencies=[Depends(require_token)])
def rewind(id: str, body: Rewind):
    session = session_for(id)
    with session.lock:
        session.rewind(body.tick)
        return session.frame(since=0)


@app.post("/api/sessions/{id}/replay", dependencies=[Depends(require_token)])
def swap_policies(id: str, body: Policies):
    session = session_for(id)
    with session.lock:
        session.change("replay", body.model_dump(exclude_none=True))
        session.stop("Playback paused for the policy change")
        return session.frame()


@app.post("/api/sessions/{id}/finish", dependencies=[Depends(require_token)])
def finish(id: str, branch: str | None = None):
    session = session_for(id)
    with session.lock:
        branch = branch or session.active
        if branch not in session.branches:
            raise HTTPException(404, "Branch not found.")
        if branch == session.active:
            session.stop("Playback paused to finish the branch")
        session.advance(MAX_TICKS, branch, action="finish")
        return {"summary": session.branches[branch].summary(), "frame": session.frame()}


def change(id, action, body):
    session = session_for(id)
    params = body.model_dump(exclude_none=True)
    if action == "resize":
        if not params:
            raise ValueError("Provide a RAM or VRAM size")
        config_for(**params)
    with session.lock:
        result = session.change(action, params)
        response = session.frame()
        if result is not None:
            response["pids"] = result
        return response


@app.post("/api/sessions/{id}/inject", dependencies=[Depends(require_token)])
def inject(id: str, body: Inject):
    return change(id, "inject", body)


@app.post("/api/sessions/{id}/storm", dependencies=[Depends(require_token)])
def storm(id: str, body: Storm):
    return change(id, "storm", body)


@app.post("/api/sessions/{id}/resize", dependencies=[Depends(require_token)])
def resize(id: str, body: Resize):
    return change(id, "resize", body)


@app.post("/api/sessions/{id}/kill", dependencies=[Depends(require_token)])
def kill(id: str, body: Kill):
    return change(id, "kill", body)


@app.post("/api/sessions/{id}/boost", dependencies=[Depends(require_token)])
def boost(id: str, body: Boost):
    return change(id, "boost", body)


@app.get("/api/sessions/{id}/branches")
def branches(id: str):
    session = session_for(id)
    with session.lock:
        return session.branch_rows()


@app.get("/api/sessions/{id}/actions")
def actions(id: str):
    session = session_for(id)
    with session.lock:
        return [entry.copy() for entry in session.actions]


@app.get("/api/sessions/{id}/dmesg")
def read_dmesg(id: str, grep: str | None = None, tail: int | None = Query(None, ge=1, le=10000)):
    session = session_for(id)
    with session.lock:
        return {"lines": dmesg(session.engine, grep, tail)}


@app.get("/api/sessions/{id}/ps")
def read_ps(id: str):
    session = session_for(id)
    with session.lock:
        return {"rows": [task_row(session.engine, task) for task in session.engine.tasks]}


@app.post("/api/sessions/{id}/shell")
def shell(id: str, body: Command, request: Request):
    session = session_for(id)
    if words_for(body.line)[0] in MUTATING:
        require_token(request)
        with session.lock:
            branch, generation = session.active, session.generation
            output = run_command(session, body.line)
            reset = branch != session.active or generation != session.generation
            return {"output": output, "frame": session.frame(since=0 if reset else None),
                    "config": session.config}
    return {"output": run_command(session, body.line)}


@app.get("/api/sessions/{id}/export")
def export(id: str):
    session = session_for(id)
    with session.lock:
        return {"config": session.config, "actions": [entry.copy() for entry in session.actions],
                "log": event_rows(session.engine), "log_base": session.engine.log_base,
                "summaries": session.branch_rows()}


@app.get("/api/compare")
def comparison(seed: int = 42, tasks: int = Query(40, ge=1, le=200)):
    return compare(seed, tasks)


@app.get("/api/whatif")
def counterfactual(seed: int = 42, base: str = "cpu:FCFS,page:FIFO,disk:FCFS",
                   alt: str = "cpu:MLFQ,page:LRU,disk:SCAN", tasks: int = Query(40, ge=1, le=200),
                   ram: int = Query(RAM_FRAMES, ge=1, le=200), vram: int = Query(VRAM_FRAMES, ge=0, le=64)):
    baseline = DEFAULT | {"ram": ram, "vram": vram} | choices_for(base.split(","), ":")
    result = what_if(seed, baseline, baseline | choices_for(alt.split(","), ":"), tasks)
    if result is None:
        raise HTTPException(404, "The baseline never reached a crisis for this seed.")
    return {"crisis_at": result["crisis_at"], "rewound_to": result["rewound_to"],
            "original": summarize(result["original"]), "replayed": summarize(result["replayed"]),
            "policy_log": dmesg(result["replayed"], grep="policy")}


def stream_frame(session, connection, ticks, detail, previous):
    with session.lock:
        if ticks and session.controller == connection:
            session.advance(session.engine.now + ticks)
        key = (session.generation, session.active)
        revision, old_key, cursor = previous
        if revision == session.revision:
            return None, previous
        frame = session.frame(detail, since=cursor if key == old_key else 0)
        return frame, (frame["revision"], key, frame["cursor"])


def stream_command(session, connection, kind, speed, token):
    with session.lock:
        if not authorized(token):
            return "Playback requires a valid demo token. Enter it under Settings."
        tick = session.engine.now
        if kind == "play":
            if type(speed) is not int or not 1 <= speed <= 200:
                return "Playback speed must be an integer from 1 to 200 ticks/s."
            if session.controller not in (None, connection):
                return "Another connection is playing this session."
            if session.branch.done or session.engine.timed_out:
                return "This branch has stopped. Rewind or start a new simulation."
            effect = f"{speed} simulated ticks per second"
            action = "play" if session.controller is None else "speed"
            if session.controller is None:
                session.play_started = tick
            session.controller, session.speed = connection, speed
            session.record(tick, action, {"speed": speed}, effect)
        else:
            if session.controller not in (None, connection):
                return "Another connection is playing this session."
            session.stop("Paused playback")
        session.revision += 1
        return None


@app.websocket("/api/sessions/{id}/stream")
async def stream(ws: WebSocket, id: str):
    if id not in sessions or not trusted_origin(ws):
        await ws.close(code=1008)
        return
    session = sessions[id]
    await ws.accept()
    connection = object()
    detail = False
    previous = (-1, None, 0)
    last = monotonic()
    credit = 0.0
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=0.1)
            except asyncio.TimeoutError:
                now = monotonic()
                if session.controller == connection and session.speed:
                    credit += min(now - last, 0.25) * session.speed
                ticks = int(credit)
                credit -= ticks
                last = now
                response, previous = await run_in_threadpool(
                    stream_frame, session, connection, ticks, detail, previous)
                if response:
                    await ws.send_json(response)
                continue
            except (json.JSONDecodeError, KeyError):
                await ws.send_json({"type": "error", "detail": "Send a JSON playback command."})
                continue

            kind = msg.get("type") if isinstance(msg, dict) else None
            if kind in ("play", "pause"):
                error = await run_in_threadpool(stream_command, session, connection, kind, msg.get("speed"),
                                                ws.headers.get("x-orbit-token") or msg.get("token"))
                if error:
                    await ws.send_json({"type": "error", "detail": error, "request": msg.get("request")})
                    continue
                credit, last = 0.0, monotonic()
            elif kind != "subscribe":
                await ws.send_json({"type": "error", "detail": "Use play, pause or subscribe."})
                continue

            if "detail" in msg and bool(msg["detail"]) != detail:
                detail = bool(msg["detail"])
                previous = (-1, *previous[1:])
            response, previous = await run_in_threadpool(
                stream_frame, session, connection, 0, detail, previous)
            if response:
                if kind in ("play", "pause"):
                    response["request"] = msg.get("request")
                await ws.send_json(response)
    except WebSocketDisconnect:
        pass
    finally:
        def release():
            with session.lock:
                if session.controller == connection:
                    session.stop("Playback connection closed")
                    session.revision += 1
        await run_in_threadpool(release)


@app.get("/api/{path:path}")
def api_not_found(path: str):
    raise HTTPException(404, "Unknown API route.")


static = Path(__file__).resolve().parents[1] / "frontend" / "out"
if static.is_dir():
    app.mount("/", StaticFiles(directory=static, html=True), name="dashboard")
