"""
robot_ready.py — Q5 机器人就绪状态卡（只读）。

综合评估 4 个维度，而非简单包装 SDK is_ready()：
1. 生命周期阶段（lifecycle state）
2. 控制权限（control authority）
3. 消息新鲜度（message freshness）
4. SDK is_ready() 差异（gap）
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

CARD = "robot_ready"
TYPE = "sensor"
TOPIC = "/{ns}/q5/robot_ready"
FMT = "data/json"
HZ = 2.0
NODE = "q5_robot_ready"
DESC = "Q5 机器人就绪状态：综合评估生命周期/控制权限/消息新鲜度/SDK状态"

STALE_THRESHOLD_MS = 5000


def build(snap: dict, lifecycle_state: str = "unknown") -> dict:
    """综合评估就绪状态。"""
    d = {
        "timestamp_ms": int(time.time() * 1000),
    }

    # 维度 1：消息新鲜度
    fresh = bool(snap.get("fresh", False))
    age_ms = snap.get("age_ms", -1)
    d["message_freshness"] = {
        "fresh": fresh,
        "age_ms": age_ms,
        "stale_threshold_ms": STALE_THRESHOLD_MS,
    }

    # 维度 2：生命周期阶段。未接入厂商接口前必须保守地保持 unknown。
    d["lifecycle"] = {
        "state": lifecycle_state,
        "ready": lifecycle_state == "active",
    }

    # 维度 3：控制权限（Q5 尚无明确接口，先占位）
    d["control_authority"] = {
        "available": None,
        "source": "not_implemented",
    }

    # 维度 4：SDK is_ready() 差异。这里没有调用厂商 SDK。
    d["sdk_is_ready"] = {
        "available": None,
        "gap": "未查询；收到新鲜关节消息不代表生命周期或控制权限已就绪",
    }

    # 综合判定
    is_ready = fresh and lifecycle_state == "active" and d["control_authority"]["available"] is True
    d["ready"] = is_ready
    d["available"] = fresh

    if not fresh:
        d["message"] = "机器人未就绪：未收到 /joint_states 消息"
    elif lifecycle_state != "active":
        d["message"] = "机器人就绪状态未知：生命周期尚未确认 active"
    else:
        d["message"] = "机器人就绪状态未知：控制权限尚未实现"

    return d


class Plugin:
    """就绪状态卡插件。"""

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
                self._node.get_logger().info(f"q5 robot_ready -> {self._topic} @ {HZ}Hz")
            except Exception as e:
                print(f"[{CARD}] ROS2 发布不可用，退回 MCP 轮询: {e}", flush=True)
                self._node = None

    def _tick(self):
        try:
            m = String()
            m.data = json.dumps(build(self._client.snapshot(),
                                      self._client.get_lifecycle_state()))
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
                "data": build(self._client.snapshot(),
                              self._client.get_lifecycle_state()),
                "topic_out": ([{"topic": self._topic, "format": FMT}] if self._node else []),
            }
        return None


def make_plugin(plugin_config, namespace, executor, client):
    return Plugin(plugin_config, namespace, executor, client)
