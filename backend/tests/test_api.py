"""Exercise the dashboard's real API, including its playback and replay paths."""
import pytest
from fastapi.testclient import TestClient

from api import app, sessions
from orbit.engine import MAX_TICKS


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ORBIT_TOKEN", raising=False)
    sessions.clear()
    with TestClient(app) as test:
        yield test
    sessions.clear()


def start(client, **overrides):
    response = client.post("/api/sessions", json={"seed": 42, **overrides})
    assert response.status_code == 200, response.text
    data = response.json()
    return "/api/sessions/" + data["id"], data["frame"]


def post(client, root, route, **body):
    response = client.post(f"{root}/{route}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_frame_options_and_absolute_event_cursor(client):
    options = client.get("/api/options").json()
    assert options["defaults"]["cpu"] == "MLFQ"
    assert options["place"] == ["CPU", "GPU", "ADAPTIVE"]
    root, frame = start(client)
    assert frame["snapshot"]["tick"] == 0
    assert frame["status"]["branch"] == "main"
    assert len(frame["tasks"]) == 40 and frame["summary"] is None
    assert frame["tasks"][0].keys() == {"id", "kind", "state", "placement", "priority", "burst", "left"}

    session = sessions[root.split("/")[-1]]
    session.engine.log_limit = 15
    advanced = post(client, root, "step", n=100)
    assert advanced["snapshot"]["tick"] == 100
    assert advanced["log_base"] > 0
    assert advanced["events"][0]["index"] == advanced["log_base"]
    assert all({"level", "subsystem", "text", "pid"} <= row.keys() for row in advanced["events"])
    details = client.get(f"{root}/frame?detail=1&since={advanced['cursor']}").json()
    assert details["events"] == []
    assert {"ram_frames", "vram_held", "bus_task", "disk"} <= details["snapshot"].keys()
    assert "ram_frames" not in advanced["snapshot"]


def test_seeded_crisis_rewind_and_compare(client):
    root, _ = start(client, cpu="FCFS", page="FIFO", disk="FCFS")
    first = post(client, root, "step", n=48)
    assert first["status"]["crisis_at"] == 48
    assert post(client, root, "checkpoint")["tick"] == 48
    rewound = post(client, root, "rewind", tick=47)
    assert rewound["snapshot"]["tick"] == 40
    assert rewound["status"]["branch"] == "branch-1"
    assert client.get(f"{root}/frame?branch=main").json()["snapshot"]["tick"] == 48

    patched = post(client, root, "shell", line="set cpu=MLFQ page=LRU disk=SCAN")["frame"]
    assert patched["status"]["policies"]["cpu"] == "MLFQ"
    assert post(client, root, "finish")["summary"]["makespan"] == 421
    assert post(client, root, "finish?branch=main")["summary"]["makespan"] == 999
    before, after = client.get(f"{root}/branches").json()
    assert before["summary"]["avg_wait"] == 400.9
    assert after["summary"]["avg_wait"] == 128.1 and after["parent"] == "main"
    expected = {"new", "step", "checkpoint", "rewind", "replay", "finish"}
    export = client.get(f"{root}/export").json()
    assert expected == {item["action"] for item in export["actions"]}
    assert all(action["effect"] for action in export["actions"])
    assert export["summaries"] == [before, after]
    benchmark = client.get("/api/whatif?seed=42").json()
    assert benchmark["original"] == before["summary"]
    assert benchmark["replayed"] == after["summary"]
    assert "after 381 ticks" in next(row["effect"] for row in export["actions"] if row["action"] == "replay")

    post(client, root, "rewind", tick=40)
    post(client, root, "replay", cpu="SJF")
    post(client, root, "finish")
    original, first_replay, second_replay = client.get(f"{root}/branches").json()
    assert first_replay["policies"]["cpu"] == "MLFQ"
    assert second_replay["policies"]["cpu"] == "SJF"
    assert second_replay["policies"]["page"] == original["policies"]["page"] == "FIFO"


def test_live_actions_and_replay_of_a_recorded_surge(client):
    root, _ = start(client)
    post(client, root, "step", n=15)
    assert len(post(client, root, "storm", name="ai-burst")["pids"]) == 4
    pid = post(client, root, "inject", kind="interactive", n=1)["pids"][0]
    resize = post(client, root, "resize", ram=45, vram=0)
    assert resize["snapshot"]["ram_total"] == 45 and resize["snapshot"]["vram_total"] == 0
    boost = post(client, root, "boost", pid=pid, priority=-3)
    assert any(event["kind"] == "boost" and "Priority" in event["info"] for event in boost["events"])
    kill = post(client, root, "kill", pid=pid)
    assert next(task for task in kill["tasks"] if task["id"] == pid)["state"] == "killed"
    post(client, root, "step", n=5)
    post(client, root, "rewind", tick=10)
    replayed = post(client, root, "step", n=10)
    assert len(replayed["tasks"]) == 45
    assert replayed["snapshot"]["ram_total"] == 45
    assert next(task for task in replayed["tasks"] if task["id"] == pid)["state"] == "killed"
    assert any(row["action"] == "replayed storm" for row in client.get(f"{root}/actions").json())


def test_shell_views_and_errors(client):
    root, _ = start(client)
    post(client, root, "shell", line="step 30")
    commands = {
        "top": "CLASS", "ps": "PID", "free": "FAULTS", "iostat": "PENDING",
        "gpustat": "GPU-PID", "dmesg nexus 10": "nexus", "help": "whatif", "compare": "UNFINISHED",
    }
    for command, expected in commands.items():
        assert expected in "\n".join(post(client, root, "shell", line=command)["output"])
    assert client.get(f"{root}/dmesg?grep=nexus&tail=2").json()["lines"]
    assert client.get(f"{root}/ps").json()["rows"][0]["pid"] == 0
    for path, body in [
        ("/api/sessions", {"cpu": "unknown"}),
        (f"{root}/replay", {"disk": "unknown"}),
        (f"{root}/shell", {"line": "xyz"}),
        (f"{root}/shell", {"line": "new --ram nope"}),
        (f"{root}/resize", {"ram": -2}),
        (f"{root}/kill", {"pid": 1000}),
        (f"{root}/rewind", {"tick": 31}),
    ]:
        result = client.post(path, json=body)
        assert result.status_code == 400, result.text
        assert isinstance(result.json()["detail"], str)
    assert set(client.get("/api/compare?seed=42").json()) == {"cpu", "page", "disk", "place"}
    reset = post(client, root, "shell", line="new --seed 7 --ram 55")
    assert reset["config"]["seed"] == 7 and reset["frame"]["snapshot"]["tick"] == 0


def test_http_and_stream_require_token(client, monkeypatch):
    monkeypatch.setenv("ORBIT_TOKEN", "test-token")
    assert client.post("/api/sessions", json={}).status_code == 403
    created = client.post("/api/sessions", json={}, headers={"X-Orbit-Token": "test-token"})
    root = f"/api/sessions/{created.json()['id']}"
    assert client.get(f"{root}/frame").status_code == 200
    assert client.post(f"{root}/step", json={"n": 4}).status_code == 403
    assert client.post(f"{root}/shell", json={"line": "step"}).status_code == 403
    assert client.post(f"{root}/shell", json={"line": "free"}).status_code == 200
    with client.websocket_connect(f"{root}/stream") as socket:
        socket.send_json({"type": "play", "speed": 20})
        assert "token" in socket.receive_json()["detail"]
        socket.send_json({"type": "play", "speed": 0, "token": "test-token"})
        assert "speed" in socket.receive_json()["detail"]
        socket.send_json({"type": "play", "speed": 20, "token": "test-token", "detail": True, "request": 7})
        status = socket.receive_json()
        assert status["status"]["playing"] and status["request"] == 7
        frame = socket.receive_json()
        assert frame["snapshot"]["tick"] > 0 and "disk" in frame["snapshot"]
        socket.send_json({"type": "pause", "token": "test-token"})
        for _ in range(5):
            if not socket.receive_json()["status"]["playing"]:
                break
        else:
            pytest.fail("Playback did not stop")
    assert {"play", "pause"} <= {item["action"] for item in client.get(f"{root}/actions").json()}


def test_thrashing_is_capped_and_tick_zero_finish_is_valid(client):
    root, _ = start(client, cpu="FCFS", page="FIFO", disk="FCFS", place="CPU", ram=30)
    result = post(client, root, "finish")
    assert result["summary"]["makespan"] == MAX_TICKS
    assert result["summary"]["unfinished"] > 0 and result["frame"]["status"]["timed_out"]

    tiny, _ = start(client, n_tasks=1)
    final = post(client, tiny, "kill", pid=0)
    assert final["status"]["done"]
    assert final["summary"]["makespan"] == 0 and final["summary"]["killed"] == 1


def test_spectator_comparison_releases_session_lock(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import shell

    root, _ = start(client)
    lock = sessions[root.split("/")[-1]].lock
    original = shell.compare

    def probe():
        if not lock.acquire(blocking=False):
            return False
        lock.release()
        return True

    def compare_without_lock(seed, tasks):
        with ThreadPoolExecutor(max_workers=1) as worker:
            assert worker.submit(probe).result()
        return original(seed, tasks)

    monkeypatch.setattr(shell, "compare", compare_without_lock)
    assert post(client, root, "shell", line="compare")["output"]
