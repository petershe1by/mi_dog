from launch import LaunchDescription
from launch_ros.actions import Node

ROOT = "/home/mi/mi_dog_ws/src/mi_dog_real/config"


def generate_launch_description():
    """Manual UI mode: armed safety adapter, no autonomous race controller."""
    return LaunchDescription([
        Node(package="mi_dog_real", executable="mi_dog_real_node", name="mi_dog_real",
             output="screen", parameters=[
                 f"{ROOT}/this_robot_competition.yaml",
                 # Manual low-speed jog uses lidar, odometry and tilt gates.
                 # Camera remains observable but does not revoke a jog.
                 {"require_camera_ready": False},
             ]),
        Node(package="mi_dog_real", executable="mi_dog_state_bridge_node",
             name="mi_dog_state_bridge", output="screen"),
        Node(package="mi_dog_real", executable="mi_dog_supervisor_node",
             name="mi_dog_supervisor", output="screen", parameters=[f"{ROOT}/supervisor.yaml"]),
        # No external E-stop device is installed. Starting estop_guard here would
        # assert its fail-closed output forever and block every manual jog.
    ])
