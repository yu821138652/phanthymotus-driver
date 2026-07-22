"""
joint_state.py — Q5 关节状态卡（只读）。

订阅 /joint_states，对外提供 20 个关节的角度数据。
装了 rclpy 时发 ROS2 topic 在画布渲染，否则走 MCP action=info 轮询。
"""

from __future__ import annotations

import json
import time

try:
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
    from std_msgs.msg import String
    _HAS_ROS2 = True
    _QOS = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                      history=HistoryPolicy.KEEP_LAST, depth=1,
                      durability=DurabilityPolicy.VOLATILE)
except Exception:
    _HAS_ROS2 = False

CARD = "joint_state"
TYPE = "sensor"
TOPIC = "/{ns}/q5/joint_state"
FMT = "data/json"
HZ = 10.0
NODE = "q5_joint_state"
DESC = "Q5 关节状态：字段与收到的 /joint_states 消息保持一致"


def build(snap: dict) -> dict:
    """snapshot -> 本卡对外的 dict。"""
    d = {
        "timestamp_ms": int(time.time() * 1000),
        "received_at_ms": snap.get("received_at_ms"),
        "message_timestamp_ms": snap.get("message_timestamp_ms"),
        "control_level": "unknown",
        "fresh": bool(snap.get("fresh", False)),
    }

    if not snap.get("fresh"):
        d["available"] = False
        d["age_ms"] = snap.get("age_ms")
        d["stale"] = bool(snap.get("stale", False))
        d["message"] = "未收到 /joint_states 消息"
        return d

    joints = snap.get("joints", {})
    d["available"] = True
    d["age_ms"] = snap.get("age_ms", 0)
    d["joints"] = {name: joints.get(name, 0.0) for name in joints}
    d["joint_count"] = len(joints)

    return d


class Plugin:
    """状态卡插件：装了 rclpy 就发 topic；始终支持 MCP action=info 轮询。"""

    def __init__(self, plugin_config, namespace, executor, client):
        self._client = client
        self._topic = TOPIC.format(ns=namespace)
        self._node = None
        if _HAS_ROS2 and executor is not None:
            try:
                self._node = Node(NODE)
                self._pub = self._node.create_publisher(String, self._topic, _QOS)
                self._node.create_timer(1.0 / HZ, self._tick)
                executor.add_node(self._node)
                self._node.get_logger().info(f"q5 joint_state -> {self._topic} @ {HZ}Hz")
            except Exception as e:
                print(f"[{CARD}] ROS2 发布不可用，退回 MCP 轮询: {e}", flush=True)
                self._node = None

    def _tick(self):
        try:
            m = String()
            m.data = json.dumps(build(self._client.snapshot()))
            self._pub.publish(m)
        except Exception as e:
            self._node.get_logger().error(f"publish {self._topic} error: {e}")

    def get_tool(self):
        desc = DESC + (f" -> {self._topic}" if self._node else " — poll via MCP action=info")
        return {
            "name": CARD,
            "type": TYPE,
            "multiInstance": False,
            "description": desc,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["info", "start", "stop"],
                        "description": "读取状态或控制卡片生命周期",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            "topic_out": ([{"topic": self._topic, "format": FMT}] if self._node else []),
        }

    def start(self):
        pass

    def stop(self):
        pass

    def dispatch(self, action, args):
        if action == "start":
            return {"state": "running"}
        if action == "stop":
            return {"state": "idle"}
        if action in ("info", "read", "get", CARD):
            return {
                "state": "running",
                "data": build(self._client.snapshot()),
                "topic_out": ([{"topic": self._topic, "format": FMT}] if self._node else []),
            }
        return None


def make_plugin(plugin_config, namespace, executor, client):
    return Plugin(plugin_config, namespace, executor, client)
