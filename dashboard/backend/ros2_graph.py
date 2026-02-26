# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
ROS2 graph builder - parses ros2 CLI output into a node/topic/edge graph structure.
"""

import os
import sys

sys.path.insert(0, os.path.expanduser("~/agent-stack"))

from tools.bash import execute


def _parse_node_info(node_name: str) -> dict:
    """
    Run `ros2 node info {node_name}` and parse into structured data.

    Returns dict with keys: publishers, subscribers, service_servers, service_clients.
    Each is a list of {"name": str, "type": str}.
    """
    result = execute(f"ros2 node info {node_name}")
    if result["returncode"] != 0:
        return {"publishers": [], "subscribers": [], "service_servers": [], "service_clients": []}

    info = {"publishers": [], "subscribers": [], "service_servers": [], "service_clients": []}
    current_section = None
    section_map = {
        "Subscribers:": "subscribers",
        "Publishers:": "publishers",
        "Service Servers:": "service_servers",
        "Service Clients:": "service_clients",
        "Action Servers:": None,
        "Action Clients:": None,
    }

    for line in result["stdout"].split("\n"):
        stripped = line.strip()
        if stripped in section_map:
            current_section = section_map[stripped]
            continue
        if current_section and ": " in stripped:
            parts = stripped.split(": ", 1)
            info[current_section].append({"name": parts[0], "type": parts[1]})

    return info


def get_ros2_graph() -> dict:
    """
    Build complete ROS2 node-topic graph.

    Returns:
        Dict with keys: online (bool), nodes, topics, services, edges.
        Returns online=False with empty lists when ROS2 is not running.
    """
    from tools.ros2 import list_nodes

    nodes = list_nodes()
    if not nodes:
        return {"online": False, "nodes": [], "topics": [], "services": [], "edges": []}

    graph_nodes = []
    all_topics = {}
    all_services = {}
    edges = []

    for node_name in nodes:
        info = _parse_node_info(node_name)

        node_pubs = [p["name"] for p in info["publishers"]]
        node_subs = [s["name"] for s in info["subscribers"]]
        node_srvs = [s["name"] for s in info["service_servers"]]

        graph_nodes.append({
            "id": node_name,
            "type": "node",
            "publishers": node_pubs,
            "subscribers": node_subs,
            "services": node_srvs,
            "status": "active",
        })

        for pub in info["publishers"]:
            all_topics.setdefault(pub["name"], {"msg_type": pub["type"], "publishers": [], "subscribers": []})
            all_topics[pub["name"]]["msg_type"] = pub["type"]
            all_topics[pub["name"]]["publishers"].append(node_name)
            edges.append({"source": node_name, "target": pub["name"], "type": "publishes"})

        for sub in info["subscribers"]:
            all_topics.setdefault(sub["name"], {"msg_type": sub["type"], "publishers": [], "subscribers": []})
            all_topics[sub["name"]]["msg_type"] = sub["type"]
            all_topics[sub["name"]]["subscribers"].append(node_name)
            edges.append({"source": sub["name"], "target": node_name, "type": "subscribes"})

        for srv in info["service_servers"]:
            all_services.setdefault(srv["name"], {"srv_type": srv["type"], "servers": []})
            all_services[srv["name"]]["srv_type"] = srv["type"]
            all_services[srv["name"]]["servers"].append(node_name)
            edges.append({"source": node_name, "target": srv["name"], "type": "serves"})

    topic_nodes = [
        {
            "id": tid,
            "type": "topic",
            "msg_type": tdata["msg_type"],
            "publishers": list(set(tdata["publishers"])),
            "subscribers": list(set(tdata["subscribers"])),
        }
        for tid, tdata in all_topics.items()
    ]

    service_nodes = [
        {
            "id": sid,
            "type": "service",
            "srv_type": sdata["srv_type"],
            "servers": list(set(sdata["servers"])),
        }
        for sid, sdata in all_services.items()
    ]

    return {
        "online": True,
        "nodes": graph_nodes,
        "topics": topic_nodes,
        "services": service_nodes,
        "edges": edges,
    }
