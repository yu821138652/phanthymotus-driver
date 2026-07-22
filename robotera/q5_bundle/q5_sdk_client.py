"""
q5_sdk_client.py — RobotEra Q5 共享 ROS2 客户端（只读版）。

订阅 Q5 的 ROS2 topic（/joint_states 等），解析成一份线程安全的 snapshot() dict。
所有状态卡都读这同一份 snapshot，不各自开订阅。

【降级 / STUB】导入不到 rclpy（如开发机 Mac、无硬件）时进入 STUB：
不订阅、snapshot 为空（fresh=False）。MCP server 仍能起、注册、列 tool。
"""

from __future__ import annotations

import threading
import time

# 消息新鲜度阈值（ms）
STALE_THRESHOLD_MS = 5000


class Q5SdkClient:
    """Q5 只读 ROS2 客户端：订阅 /joint_states 等 topic → 线程安全 snapshot()。"""

    def __init__(self):
        self.available = False
        self._lock = threading.Lock()
        self._running = False
        self._node = None
        self._snapshot: dict = {"fresh": False}
        self._last_joint_stamp = 0.0
        self._lifecycle_state = "unknown"
        self._executor = None

    def _init_ros2(self, executor):
        if executor is None:
            return
        try:
            from rclpy.node import Node
            from sensor_msgs.msg import JointState
            from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

            self._node = Node("q5_sdk_client")
            qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                             history=HistoryPolicy.KEEP_LAST, depth=1)

            self._node.create_subscription(
                JointState, "/joint_states", self._on_joint_state, qos)

            executor.add_node(self._node)
            self._executor = executor
            self.available = True
            print("[Q5SdkClient] ROS2 subscriptions ready (/joint_states)", flush=True)
        except Exception as e:
            print(f"[Q5SdkClient] STUB (ROS2 subscription unavailable: {e})", flush=True)

    def _on_joint_state(self, msg):
        """JointState 回调 → 更新 snapshot。"""
        try:
            joint_map = {}
            for i, name in enumerate(msg.name):
                if i < len(msg.position):
                    joint_map[name] = float(msg.position[i])

            received_at_ms = int(time.time() * 1000)
            stamp = getattr(getattr(msg, "header", None), "stamp", None)
            message_timestamp_ms = None
            if stamp is not None and (stamp.sec or stamp.nanosec):
                message_timestamp_ms = int(stamp.sec * 1000 + stamp.nanosec / 1_000_000)
            with self._lock:
                self._last_joint_stamp = time.time()
                self._snapshot = {
                    "fresh": True,
                    "timestamp_ms": received_at_ms,
                    "received_at_ms": received_at_ms,
                    "message_timestamp_ms": message_timestamp_ms,
                    "joints": joint_map,
                    "joint_names": list(msg.name),
                    "header_frame": msg.header.frame_id if hasattr(msg, 'header') else "",
                }
        except Exception as e:
            print(f"[Q5SdkClient] _on_joint_state error: {e}", flush=True)

    def start(self, executor=None):
        if not self._running:
            self._init_ros2(executor)
            self._running = self.available

    def stop(self):
        self._running = False
        if self._node is not None:
            try:
                if self._executor is not None:
                    self._executor.remove_node(self._node)
                self._node.destroy_node()
            except Exception:
                pass
            finally:
                self._node = None
                self._executor = None

    def snapshot(self) -> dict:
        with self._lock:
            snap = dict(self._snapshot) if self._snapshot else {"fresh": False}

        # 检查新鲜度
        if snap.get("fresh"):
            elapsed_ms = int((time.time() - self._last_joint_stamp) * 1000)
            snap["age_ms"] = elapsed_ms
            if elapsed_ms > STALE_THRESHOLD_MS:
                snap["fresh"] = False
                snap["stale"] = True

        return snap

    def get_lifecycle_state(self) -> str:
        return self._lifecycle_state
