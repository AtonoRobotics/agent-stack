#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Mission Control by Alpha - Robotics Fleet Intelligence Platform."""

import os
import sys
import json
import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.expanduser("~/agent-stack"))

import aiosqlite
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yaml
import uvicorn

from dashboard.backend.auth import AuthManager

DB_PATH = os.path.expanduser("~/agent-stack/data/metrics.db")
CONFIG_DIR = os.path.expanduser("~/agent-stack/config")
FRONTEND_DIR = os.path.expanduser("~/agent-stack/dashboard/frontend")

ws_connections: list[WebSocket] = []
_ros2_executor = ThreadPoolExecutor(max_workers=1)

auth = AuthManager()
security = HTTPBearer(auto_error=False)


# ── Auth dependencies ────────────────────────────────────

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = credentials.credentials
    if token.startswith("mc_ak_"):
        user = auth.verify_api_key(token)
    else:
        user = auth.verify_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


async def require_auth(user: dict = Depends(get_current_user)) -> dict:
    return user


async def require_operator(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Operator access required")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── App setup ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(ws_broadcast_loop())
    yield
    task.cancel()


app = FastAPI(
    title="Mission Control API",
    description="Mission Control by Alpha - Robotics Fleet Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


async def db_query(sql: str, params: tuple = ()) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def db_query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = await db_query(sql, params)
    return rows[0] if rows else None


def load_yaml(filename: str) -> dict:
    path = os.path.join(CONFIG_DIR, filename)
    if os.path.exists(path):
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


# ── Auth routes ──────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str


class CreateApiKeyRequest(BaseModel):
    name: str
    role: str


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    user = auth.verify_credentials(req.username, req.password)
    if not user:
        auth.log_audit("login_failed", req.username, request.client.host if request.client else None)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth.create_token(req.username, user["role"])
    auth.log_audit("login_success", req.username, request.client.host if request.client else None)
    return {"token": token, "username": req.username, "role": user["role"]}


@app.post("/api/auth/logout")
async def logout(request: Request, user: dict = Depends(require_auth)):
    if user.get("jti"):
        auth.revoke_token(user["jti"])
    auth.log_audit("logout", user["username"], request.client.host if request.client else None)
    return {"ok": True}


@app.get("/api/auth/me")
async def get_me(user: dict = Depends(require_auth)):
    return {"username": user["username"], "role": user["role"]}


@app.get("/api/auth/users")
async def list_users(user: dict = Depends(require_admin)):
    return auth.list_users()


@app.post("/api/auth/users")
async def create_user(req: CreateUserRequest, request: Request, user: dict = Depends(require_admin)):
    try:
        auth.create_user(req.username, req.password, req.role, created_by=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    auth.log_audit("user_created", user["username"], request.client.host if request.client else None, f"created {req.username} ({req.role})")
    return {"ok": True, "username": req.username}


@app.delete("/api/auth/users/{username}")
async def delete_user(username: str, request: Request, user: dict = Depends(require_admin)):
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    try:
        auth.delete_user(username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    auth.log_audit("user_deleted", user["username"], request.client.host if request.client else None, f"deleted {username}")
    return {"ok": True}


@app.post("/api/auth/apikey")
async def create_api_key(req: CreateApiKeyRequest, request: Request, user: dict = Depends(require_admin)):
    try:
        key = auth.create_api_key(req.name, req.role, created_by=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    auth.log_audit("apikey_created", user["username"], request.client.host if request.client else None, f"key '{req.name}' ({req.role})")
    return {"key": key, "name": req.name, "role": req.role}


@app.get("/api/auth/audit")
async def get_audit_log(limit: int = 100, user: dict = Depends(require_admin)):
    return await db_query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))


# ── Protected data routes ────────────────────────────────

@app.get("/api/summary")
async def get_summary(user: dict = Depends(require_auth)):
    fleet = await db_query(
        "SELECT machine, status FROM fleet_health WHERE id IN (SELECT MAX(id) FROM fleet_health GROUP BY machine)"
    )
    machines_online = sum(1 for m in fleet if m.get("status") == "online")
    models_config = load_yaml("models.yml")
    models_count = len(models_config.get("models", {}))
    active = await db_query("SELECT COUNT(*) as count FROM agent_tasks WHERE completed IS NULL")
    active_count = active[0]["count"] if active else 0
    today = datetime.now().strftime("%Y-%m-%d")
    sims = await db_query("SELECT COUNT(*) as count FROM simulation_runs WHERE timestamp LIKE ?", (f"{today}%",))
    sims_count = sims[0]["count"] if sims else 0
    training = await db_query("SELECT COUNT(*) as count FROM training_runs WHERE status = 'running'")
    training_active = (training[0]["count"] if training else 0) > 0
    incidents = await db_query("SELECT COUNT(*) as count FROM incidents WHERE resolved = 0")
    incidents_count = incidents[0]["count"] if incidents else 0
    activity = await db_query("SELECT * FROM activity_log ORDER BY id DESC LIMIT 10")
    return {
        "machines_online": machines_online,
        "machines_total": max(len(fleet), 4),
        "models_loaded": models_count,
        "active_tasks": active_count,
        "simulations_today": sims_count,
        "training_active": training_active,
        "open_incidents": incidents_count,
        "recent_activity": activity,
    }


@app.get("/api/fleet")
async def get_fleet(user: dict = Depends(require_auth)):
    fleet_config = load_yaml("fleet.yml").get("machines", {})
    metrics = await db_query(
        "SELECT * FROM fleet_health WHERE id IN (SELECT MAX(id) FROM fleet_health GROUP BY machine) ORDER BY machine"
    )
    metrics_by_machine = {m["machine"]: m for m in metrics}
    result = []
    for name, config in fleet_config.items():
        result.append({"name": name, "config": config, "metrics": metrics_by_machine.get(name, {"status": "no_data"})})
    return result


@app.get("/api/fleet/{machine}")
async def get_fleet_machine(machine: str, hours: int = Query(default=24), user: dict = Depends(require_auth)):
    config = load_yaml("fleet.yml").get("machines", {}).get(machine, {})
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    history = await db_query("SELECT * FROM fleet_health WHERE machine = ? AND timestamp > ? ORDER BY timestamp", (machine, cutoff))
    latest = await db_query_one("SELECT * FROM fleet_health WHERE machine = ? ORDER BY id DESC LIMIT 1", (machine,))
    return {"name": machine, "config": config, "current": latest, "history": history}


@app.get("/api/robots")
async def get_robots(user: dict = Depends(require_auth)):
    repos_config = load_yaml("repos.yml").get("robots", {})
    result = []
    for robot_id, repo_name in repos_config.items():
        deployment = await db_query_one("SELECT * FROM deployment_history WHERE robot_serial = ? ORDER BY id DESC LIMIT 1", (robot_id,))
        sim = await db_query_one("SELECT * FROM simulation_runs WHERE robot = ? ORDER BY id DESC LIMIT 1", (robot_id,))
        metrics = await db_query(
            "SELECT metric_name, value, units FROM performance_metrics WHERE robot_serial = ? AND id IN (SELECT MAX(id) FROM performance_metrics WHERE robot_serial = ? GROUP BY metric_name)",
            (robot_id, robot_id),
        )
        result.append({
            "id": robot_id, "repo": repo_name, "latest_deployment": deployment,
            "latest_simulation": sim,
            "metrics": {m["metric_name"]: {"value": m["value"], "units": m["units"]} for m in metrics},
        })
    return result


@app.get("/api/robots/{robot_id}")
async def get_robot_detail(robot_id: str, user: dict = Depends(require_auth)):
    repos_config = load_yaml("repos.yml").get("robots", {})
    deployments = await db_query("SELECT * FROM deployment_history WHERE robot_serial = ? ORDER BY id DESC LIMIT 20", (robot_id,))
    sims = await db_query("SELECT * FROM simulation_runs WHERE robot = ? ORDER BY id DESC LIMIT 50", (robot_id,))
    training = await db_query("SELECT * FROM training_runs WHERE robot = ? ORDER BY id DESC LIMIT 20", (robot_id,))
    metrics = await db_query("SELECT * FROM performance_metrics WHERE robot_serial = ? ORDER BY id DESC LIMIT 100", (robot_id,))
    incidents = await db_query("SELECT * FROM incidents WHERE robot_serial = ? ORDER BY id DESC LIMIT 20", (robot_id,))
    return {"id": robot_id, "repo": repos_config.get(robot_id, ""), "deployments": deployments, "simulations": sims, "training": training, "metrics": metrics, "incidents": incidents}


@app.get("/api/simulations")
async def get_simulations(robot: str = None, result: str = None, limit: int = 50, user: dict = Depends(require_auth)):
    sql = "SELECT * FROM simulation_runs WHERE 1=1"
    params = []
    if robot:
        sql += " AND robot = ?"
        params.append(robot)
    if result:
        sql += " AND result = ?"
        params.append(result)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return await db_query(sql, tuple(params))


@app.get("/api/simulations/{sim_id}")
async def get_simulation(sim_id: int, user: dict = Depends(require_auth)):
    return await db_query_one("SELECT * FROM simulation_runs WHERE id = ?", (sim_id,))


@app.get("/api/training")
async def get_training(robot: str = None, status: str = None, limit: int = 50, user: dict = Depends(require_auth)):
    sql = "SELECT * FROM training_runs WHERE 1=1"
    params = []
    if robot:
        sql += " AND robot = ?"
        params.append(robot)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return await db_query(sql, tuple(params))


@app.get("/api/training/{train_id}")
async def get_training_detail(train_id: int, user: dict = Depends(require_auth)):
    return await db_query_one("SELECT * FROM training_runs WHERE id = ?", (train_id,))


@app.get("/api/metrics/{robot}/{metric}")
async def get_metrics(robot: str, metric: str, hours: int = 24, user: dict = Depends(require_auth)):
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    return await db_query(
        "SELECT timestamp, value, units FROM performance_metrics WHERE robot_serial = ? AND metric_name = ? AND timestamp > ? ORDER BY timestamp",
        (robot, metric, cutoff),
    )


@app.get("/api/agents")
async def get_agents(user: dict = Depends(require_auth)):
    tasks = await db_query("SELECT * FROM agent_tasks ORDER BY id DESC LIMIT 100")
    total = len(tasks)
    successful = sum(1 for t in tasks if t.get("success"))
    local_tasks = sum(1 for t in tasks if t.get("tokens_saved"))
    agent_stats = {}
    for t in tasks:
        agent = t.get("agent", "unknown")
        if agent not in agent_stats:
            agent_stats[agent] = {"total": 0, "success": 0, "local": 0}
        agent_stats[agent]["total"] += 1
        if t.get("success"):
            agent_stats[agent]["success"] += 1
        if t.get("tokens_saved"):
            agent_stats[agent]["local"] += 1
    return {
        "tasks": tasks,
        "stats": {
            "total": total, "successful": successful,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "local_tasks": local_tasks, "api_tasks": total - local_tasks,
            "cost_savings_pct": (local_tasks / total * 100) if total > 0 else 0,
        },
        "per_agent": agent_stats,
    }


@app.get("/api/incidents")
async def get_incidents(user: dict = Depends(require_auth)):
    return await db_query("SELECT * FROM incidents ORDER BY id DESC LIMIT 50")


@app.get("/api/activity")
async def get_activity(limit: int = 50, user: dict = Depends(require_auth)):
    return await db_query("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,))


@app.get("/api/ros2/graph")
async def get_ros2_graph_api(user: dict = Depends(require_auth)):
    from dashboard.backend.ros2_graph import get_ros2_graph
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_ros2_executor, get_ros2_graph)
    return result


# ── Robot cockpit routes ──────────────────────────────────

@app.get("/api/robot/{robot_id}/status")
async def get_robot_status(robot_id: str, user: dict = Depends(require_auth)):
    from dashboard.backend.robot_status import get_full_status
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ros2_executor, get_full_status)


@app.get("/api/robot/{robot_id}/joints")
async def get_robot_joints(robot_id: str, user: dict = Depends(require_auth)):
    from dashboard.backend.robot_status import get_joint_states
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ros2_executor, get_joint_states)


@app.get("/api/robot/{robot_id}/pose")
async def get_robot_pose(robot_id: str, user: dict = Depends(require_auth)):
    from dashboard.backend.robot_status import get_end_effector_pose
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ros2_executor, get_end_effector_pose)


@app.get("/api/robot/{robot_id}/topics")
async def get_robot_topics(robot_id: str, user: dict = Depends(require_auth)):
    from dashboard.backend.robot_status import get_all_topics_data
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ros2_executor, get_all_topics_data)


@app.get("/api/robot/{robot_id}/diagnostics")
async def get_robot_diagnostics_api(robot_id: str, user: dict = Depends(require_auth)):
    from dashboard.backend.robot_status import get_robot_diagnostics
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ros2_executor, get_robot_diagnostics)


@app.get("/api/robot/{robot_id}/controllers")
async def get_robot_controllers(robot_id: str, user: dict = Depends(require_auth)):
    from dashboard.backend.robot_status import get_controller_state
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ros2_executor, get_controller_state)


@app.get("/api/robot/{robot_id}/urdf")
async def get_robot_urdf(robot_id: str, user: dict = Depends(require_auth)):
    from dashboard.backend.urdf_parser import parse_urdf
    return parse_urdf()


# ── Demo routes ───────────────────────────────────────────

from dashboard.backend.demo_runner import DemoRunner, DEMO_REGISTRY

_demo_runner = DemoRunner()


@app.get("/api/demos")
async def list_demos(user: dict = Depends(require_auth)):
    prereqs = await _demo_runner.check_prerequisites()
    demos = []
    for demo_id, info in DEMO_REGISTRY.items():
        results = _demo_runner.get_results(demo_id)
        status_info = _demo_runner.get_status(demo_id)
        current_status = status_info.get("status", "idle") if status_info.get("demo_id") == demo_id else "idle"
        if results.get("last_run") and results["last_run"].get("status") and current_status == "idle":
            current_status = results["last_run"]["status"]
        demos.append({
            "id": demo_id,
            "name": info["name"],
            "description": info["description"],
            "status": current_status,
            "has_results": results.get("has_results", False),
            "files": results.get("files", []),
            "last_run": results.get("last_run"),
            "has_csv": len(info.get("csv_files", [])) > 0,
        })
    return {"demos": demos, "prerequisites": prereqs}


@app.get("/api/demos/{demo_id}/results")
async def get_demo_results(demo_id: str, user: dict = Depends(require_auth)):
    return _demo_runner.get_results(demo_id)


@app.post("/api/demos/{demo_id}/run")
async def run_demo(demo_id: str, user: dict = Depends(require_operator)):
    try:
        result = await _demo_runner.launch(demo_id, user.get("username", "unknown"))
        return JSONResponse(result, status_code=202)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.delete("/api/demos/{demo_id}/stop")
async def stop_demo(demo_id: str, user: dict = Depends(require_operator)):
    try:
        return await _demo_runner.stop(demo_id)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/demos/{demo_id}/log")
async def get_demo_log(demo_id: str, offset: int = 0, user: dict = Depends(require_auth)):
    lines = _demo_runner.get_log(demo_id, offset)
    return {"demo_id": demo_id, "offset": offset, "lines": lines, "count": len(lines)}


@app.get("/api/demos/files/{filename}")
async def serve_demo_file(filename: str, user: dict = Depends(require_auth)):
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9_.-]+\.(png|csv)$', filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    results_dir = os.path.expanduser("~/dobot_cr10/results")
    file_path = os.path.join(results_dir, filename)
    resolved = os.path.realpath(file_path)
    if not resolved.startswith(os.path.realpath(results_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.exists(resolved):
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "image/png" if filename.endswith(".png") else "text/csv"
    return FileResponse(resolved, media_type=media_type, filename=filename)


@app.websocket("/ws/demo/{demo_id}")
async def websocket_demo(websocket: WebSocket, demo_id: str, token: str = Query(default=None)):
    if not token:
        await websocket.close(code=4001, reason="Token required")
        return
    if token.startswith("mc_ak_"):
        user = auth.verify_api_key(token)
    else:
        user = auth.verify_token(token)
    if user is None:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    await _demo_runner.subscribe(websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await _demo_runner.unsubscribe(websocket)


# Robot cockpit WebSocket - streams at ~10hz
_robot_ws_connections: list[WebSocket] = []


@app.websocket("/ws/robot/{robot_id}")
async def websocket_robot(websocket: WebSocket, robot_id: str, token: str = Query(default=None)):
    if not token:
        await websocket.close(code=4001, reason="Token required")
        return
    if token.startswith("mc_ak_"):
        user = auth.verify_api_key(token)
    else:
        user = auth.verify_token(token)
    if user is None:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    _robot_ws_connections.append(websocket)
    try:
        while True:
            try:
                from dashboard.backend.robot_status import get_full_status
                loop = asyncio.get_event_loop()
                status = await loop.run_in_executor(_ros2_executor, get_full_status)
                await websocket.send_json({"type": "robot_status", "data": status})
                await asyncio.sleep(0.1)  # ~10hz
            except asyncio.CancelledError:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in _robot_ws_connections:
            _robot_ws_connections.remove(websocket)


# ── WebSocket (auth via query param) ────────────────────

@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket, token: str = Query(default=None)):
    if not token:
        await websocket.close(code=4001, reason="Token required")
        return
    if token.startswith("mc_ak_"):
        user = auth.verify_api_key(token)
    else:
        user = auth.verify_token(token)
    if user is None:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    ws_connections.append(websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        if websocket in ws_connections:
            ws_connections.remove(websocket)
    except Exception:
        if websocket in ws_connections:
            ws_connections.remove(websocket)


async def ws_broadcast_loop():
    last_activity_id = 0
    while True:
        await asyncio.sleep(5)
        if not ws_connections:
            continue
        try:
            fleet = await db_query("SELECT * FROM fleet_health WHERE id IN (SELECT MAX(id) FROM fleet_health GROUP BY machine)")
            active_tasks = await db_query("SELECT * FROM agent_tasks WHERE completed IS NULL ORDER BY id DESC LIMIT 10")
            activity = await db_query("SELECT * FROM activity_log WHERE id > ? ORDER BY id DESC LIMIT 20", (last_activity_id,))
            if activity:
                last_activity_id = max(a["id"] for a in activity)
            alerts = await db_query("SELECT * FROM activity_log WHERE category = 'alert' AND id > ? ORDER BY id DESC LIMIT 10", (max(0, last_activity_id - 100),))
            message = json.dumps({
                "type": "update", "timestamp": datetime.now().isoformat(),
                "fleet": fleet, "active_tasks": active_tasks, "alerts": alerts, "activity": activity,
            })
            dead = []
            for ws in ws_connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                ws_connections.remove(ws)
        except Exception:
            pass


# ── Static frontend ──────────────────────────────────────

@app.get("/")
async def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"error": "Frontend not found. Place index.html in dashboard/frontend/"}, status_code=404)


if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)
