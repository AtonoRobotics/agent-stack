# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Isaac ROS nodes management skill."""
import os
import subprocess
import logging
import json

logger = logging.getLogger("skill.isaac_ros_nodes")
BASE_DIR = os.path.expanduser("~/agent-stack")


class IsaacRosNodesSkill:
    """Manages ROS2 nodes for Isaac Sim integration."""

    def list_nodes(self) -> dict:
        """List all running ROS2 nodes."""
        try:
            result = subprocess.run(
                ["ros2", "node", "list"],
                capture_output=True, text=True, timeout=10,
            )
            nodes = [n.strip() for n in result.stdout.strip().split("\n") if n.strip()]
            node_details = []
            for node in nodes:
                try:
                    info = subprocess.run(
                        ["ros2", "node", "info", node],
                        capture_output=True, text=True, timeout=5,
                    )
                    node_details.append({"name": node, "info": info.stdout.strip()})
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    node_details.append({"name": node, "info": "unavailable"})

            return {"nodes": node_details, "count": len(nodes), "status": "ok"}
        except FileNotFoundError:
            logger.warning("ROS2 CLI not found")
            return {"nodes": [], "count": 0, "status": "ros2_not_found"}
        except subprocess.TimeoutExpired:
            logger.warning("ROS2 node list timed out")
            return {"nodes": [], "count": 0, "status": "timeout"}

    def launch_node(self, package: str, executable: str,
                    parameters: dict = None, remappings: dict = None,
                    namespace: str = "") -> dict:
        """Generate ROS2 launch command for a node."""
        parameters = parameters or {}
        remappings = remappings or {}

        cmd_parts = ["ros2", "run", package, executable]

        if namespace:
            cmd_parts.extend(["--ros-args", "-r", f"__ns:={namespace}"])

        for key, value in parameters.items():
            cmd_parts.extend(["-p", f"{key}:={value}"])

        for src, dst in remappings.items():
            cmd_parts.extend(["-r", f"{src}:={dst}"])

        cmd = " ".join(cmd_parts)

        # Generate launch file equivalent
        launch_py = f'''from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package="{package}",
            executable="{executable}",
            name="{executable}",
            namespace="{namespace}",
            parameters=[{json.dumps(parameters)}],
            remappings=[{", ".join(f'("{s}", "{d}")' for s, d in remappings.items())}],
            output="screen",
        ),
    ])
'''
        logger.info(f"Generated launch for {package}/{executable}")
        return {
            "command": cmd,
            "launch_file": launch_py,
            "package": package,
            "executable": executable,
            "parameters": parameters,
            "remappings": remappings,
        }

    def configure_node(self, node_name: str, parameters: dict) -> dict:
        """Generate dynamic reconfigure commands for a running node."""
        commands = []
        for key, value in parameters.items():
            if isinstance(value, bool):
                val_str = "true" if value else "false"
            elif isinstance(value, (int, float)):
                val_str = str(value)
            else:
                val_str = f'"{value}"'

            cmd = f"ros2 param set {node_name} {key} {val_str}"
            commands.append(cmd)

        # Also generate YAML config
        yaml_config = f"{node_name}:\n  ros__parameters:\n"
        for key, value in parameters.items():
            yaml_config += f"    {key}: {value}\n"

        config_path = os.path.join(BASE_DIR, "config", "ros_params",
                                    f"{node_name.strip('/').replace('/', '_')}.yaml")

        logger.info(f"Configured node {node_name} with {len(parameters)} params")
        return {
            "commands": commands,
            "yaml_config": yaml_config,
            "config_path": config_path,
            "node_name": node_name,
            "parameters": parameters,
        }

    def connect_topics(self, publisher_node: str, subscriber_node: str,
                       topic: str, msg_type: str, qos_depth: int = 10) -> dict:
        """Generate configuration to connect two nodes via a topic."""
        code = f'''from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # Publisher node
        Node(
            package="{publisher_node.split('/')[0]}",
            executable="{publisher_node.split('/')[-1]}",
            remappings=[("output", "{topic}")],
            parameters=[{{"qos_depth": {qos_depth}}}],
        ),
        # Subscriber node
        Node(
            package="{subscriber_node.split('/')[0]}",
            executable="{subscriber_node.split('/')[-1]}",
            remappings=[("input", "{topic}")],
            parameters=[{{"qos_depth": {qos_depth}}}],
        ),
    ])
'''
        # Verification command
        verify_cmd = f"ros2 topic info {topic} --verbose"

        logger.info(f"Connected {publisher_node} -> {topic} -> {subscriber_node}")
        return {
            "launch_code": code,
            "topic": topic,
            "msg_type": msg_type,
            "publisher": publisher_node,
            "subscriber": subscriber_node,
            "verify_command": verify_cmd,
            "qos_depth": qos_depth,
        }

    def monitor_health(self, node_names: list = None) -> dict:
        """Monitor health of specified ROS2 nodes."""
        node_names = node_names or []
        health_results = []

        for node in node_names:
            try:
                # Check if node is alive
                result = subprocess.run(
                    ["ros2", "node", "info", node],
                    capture_output=True, text=True, timeout=5,
                )
                alive = result.returncode == 0

                # Get topic list
                topics = []
                if alive:
                    for line in result.stdout.split("\n"):
                        line = line.strip()
                        if line.startswith("/") and ":" in line:
                            topics.append(line.split(":")[0].strip())

                # Check topic rates
                topic_rates = {}
                for topic in topics[:5]:  # limit to first 5
                    try:
                        rate_result = subprocess.run(
                            ["ros2", "topic", "hz", topic, "--window", "5"],
                            capture_output=True, text=True, timeout=3,
                        )
                        if "average rate" in rate_result.stdout:
                            rate_line = rate_result.stdout.strip().split("\n")[-1]
                            rate = float(rate_line.split(":")[1].strip().split()[0])
                            topic_rates[topic] = rate
                    except (subprocess.TimeoutExpired, ValueError, IndexError):
                        topic_rates[topic] = None

                health_results.append({
                    "node": node,
                    "alive": alive,
                    "topic_count": len(topics),
                    "topic_rates": topic_rates,
                    "status": "healthy" if alive else "dead",
                })
            except FileNotFoundError:
                health_results.append({
                    "node": node, "alive": False, "status": "ros2_not_found",
                })
            except subprocess.TimeoutExpired:
                health_results.append({
                    "node": node, "alive": False, "status": "timeout",
                })

        all_healthy = all(r.get("alive", False) for r in health_results)
        result = {
            "nodes": health_results,
            "all_healthy": all_healthy,
            "checked": len(health_results),
            "healthy_count": sum(1 for r in health_results if r.get("alive")),
        }
        logger.info(f"Health check: {result['healthy_count']}/{result['checked']} healthy")
        return result

    def build_node_graph(self, nodes: list = None) -> dict:
        """Build a graph of ROS2 node connections via topics."""
        try:
            result = subprocess.run(
                ["ros2", "topic", "list", "-t"],
                capture_output=True, text=True, timeout=10,
            )
            topics = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.strip().split(" ")
                    topic_name = parts[0]
                    topic_type = parts[1].strip("[]") if len(parts) > 1 else "unknown"
                    topics.append({"name": topic_name, "type": topic_type})

            # Get publishers and subscribers for each topic
            graph = {"nodes": set(), "edges": [], "topics": []}
            for topic in topics:
                try:
                    info = subprocess.run(
                        ["ros2", "topic", "info", topic["name"], "--verbose"],
                        capture_output=True, text=True, timeout=5,
                    )
                    publishers = []
                    subscribers = []
                    section = None
                    for line in info.stdout.split("\n"):
                        if "Publisher count" in line:
                            section = "pub"
                        elif "Subscription count" in line:
                            section = "sub"
                        elif "Node name:" in line:
                            node_name = line.split(":")[-1].strip()
                            if section == "pub":
                                publishers.append(node_name)
                            elif section == "sub":
                                subscribers.append(node_name)

                    for pub in publishers:
                        graph["nodes"].add(pub)
                        for sub in subscribers:
                            graph["nodes"].add(sub)
                            graph["edges"].append({
                                "from": pub,
                                "to": sub,
                                "topic": topic["name"],
                                "type": topic["type"],
                            })

                    graph["topics"].append({
                        **topic,
                        "publishers": publishers,
                        "subscribers": subscribers,
                    })
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    graph["topics"].append({**topic, "publishers": [], "subscribers": []})

            graph["nodes"] = list(graph["nodes"])
            logger.info(f"Built node graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
            return graph

        except FileNotFoundError:
            return {"nodes": [], "edges": [], "topics": [], "status": "ros2_not_found"}
        except subprocess.TimeoutExpired:
            return {"nodes": [], "edges": [], "topics": [], "status": "timeout"}

    def export_launch_file(self, nodes_config: list, output_path: str = None) -> str:
        """Export a complete launch file from node configurations.

        nodes_config: list of {"package": str, "executable": str,
                               "parameters": dict, "remappings": dict, "namespace": str}
        """
        output_path = output_path or os.path.join(BASE_DIR, "launch", "generated_launch.py")

        node_entries = []
        for i, cfg in enumerate(nodes_config):
            pkg = cfg.get("package", "")
            exe = cfg.get("executable", "")
            ns = cfg.get("namespace", "")
            params = cfg.get("parameters", {})
            remaps = cfg.get("remappings", {})
            name = cfg.get("name", exe)

            remap_str = ", ".join(f'("{s}", "{d}")' for s, d in remaps.items())
            node_entries.append(f'''        Node(
            package="{pkg}",
            executable="{exe}",
            name="{name}",
            namespace="{ns}",
            parameters=[{json.dumps(params)}],
            remappings=[{remap_str}],
            output="screen",
        )''')

        launch_content = f'''"""Auto-generated ROS2 launch file."""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    return LaunchDescription([
{",".join(chr(10) + entry for entry in node_entries)}
    ])
'''
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            f.write(launch_content)

        logger.info(f"Exported launch file with {len(nodes_config)} nodes to {output_path}")
        return output_path

    def test_latency(self, topic: str, n_samples: int = 100) -> dict:
        """Test round-trip latency on a ROS2 topic."""
        code = f'''import rclpy
from rclpy.node import Node
import time
import numpy as np

class LatencyTester(Node):
    def __init__(self):
        super().__init__("latency_tester")
        self.latencies = []
        self.n_samples = {n_samples}
        self.send_times = {{}}
        self.msg_id = 0

        self.publisher = self.create_publisher(String, "{topic}/ping", 10)
        self.subscription = self.create_subscription(
            String, "{topic}/pong", self.pong_callback, 10)
        self.timer = self.create_timer(0.01, self.send_ping)  # 100Hz

    def send_ping(self):
        if self.msg_id >= self.n_samples:
            return
        msg = String()
        msg.data = str(self.msg_id)
        self.send_times[self.msg_id] = time.monotonic()
        self.publisher.publish(msg)
        self.msg_id += 1

    def pong_callback(self, msg):
        recv_time = time.monotonic()
        msg_id = int(msg.data)
        if msg_id in self.send_times:
            latency = (recv_time - self.send_times[msg_id]) * 1000.0  # ms
            self.latencies.append(latency)
            del self.send_times[msg_id]

        if len(self.latencies) >= self.n_samples:
            arr = np.array(self.latencies)
            print(f"Latency test results ({{len(arr)}} samples):")
            print(f"  Mean: {{np.mean(arr):.3f}} ms")
            print(f"  Std:  {{np.std(arr):.3f}} ms")
            print(f"  Min:  {{np.min(arr):.3f}} ms")
            print(f"  Max:  {{np.max(arr):.3f}} ms")
            print(f"  P95:  {{np.percentile(arr, 95):.3f}} ms")
            print(f"  P99:  {{np.percentile(arr, 99):.3f}} ms")
            raise SystemExit(0)

rclpy.init()
tester = LatencyTester()
rclpy.spin(tester)
'''
        logger.info(f"Generated latency test for {topic}")
        return {
            "code": code,
            "topic": topic,
            "n_samples": n_samples,
        }
