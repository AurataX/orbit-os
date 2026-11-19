# Demo and hosting runbook

## Local dashboard

From the project root:

```sh
make install
make test
make build
make serve
```

Open [http://localhost:8000](http://localhost:8000). FastAPI serves the static Next.js build and the simulator API in one process. For separate development servers, run `make dev-api` and `make dev-ui` in different terminals, then open port 3000.

## Public link on demand

Install `cloudflared` once with `brew install cloudflared`. Stop any existing ORBIT server, then generate a fresh token and start the protected server. On macOS, the following copies the token to your clipboard for the Settings field:

```sh
orbit_demo_token="$(openssl rand -hex 24)"
printf '%s' "$orbit_demo_token" | pbcopy
ORBIT_TOKEN="$orbit_demo_token" make serve
```

In a second terminal:

```sh
cloudflared tunnel --url http://localhost:8000
```

Open the HTTPS URL printed by Cloudflare. In **Settings**, paste the token, save it, and start the simulation. Use **Copy spectator link** in Settings to share the active session. The token stays in your browser tab and the spectator link permits reads. Stop the tunnel with Ctrl+C after the demo.

## Presentation flow (5–7 minutes)

1. Open **New simulation → Crisis demo** and run seed 42 at 20 ticks/s.
2. Pause when the crisis marker appears at tick 48. Inspect the disk queue, page faults and VRAM waiters. Try `free`, `iostat`, or `dmesg nexus 10` in ORBIT Shell.
3. Set the timeline to tick 40 and choose **Rewind here**.
4. Choose **Replay with… → Use engine defaults → Apply policies** to select MLFQ, LRU and SCAN. The placement remains ADAPTIVE.
5. In **Compare**, finish the original and replay branches. Seed 42 produces 999 → 421 ticks makespan and 400.9 → 128.1 ticks average wait. Interactive p95 response worsens from 4 to 10 ticks while p95 turnaround improves from 252 to 200.
6. Explain the trade-off with the kernel log and **What you did** panel.

## Offline fallback

```sh
cd backend
.venv/bin/python -m orbit.compare --seed 42
.venv/bin/python -m orbit.compare --seed 42 --rewind cpu=MLFQ page=LRU disk=SCAN
```

## Checks

- [x] Engine and API tests
- [x] Seed 42 crisis and replay in local Chromium
- [x] Simulated 390px phone viewport, light and dark themes, reduced motion
- [ ] Public tunnel on a physical phone
