from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="mi_dog_real",
            executable="mi_dog_real_node",
            name="mi_dog_real",
            output="screen",
            parameters=[
                "/home/mi/mi_dog_ws/src/mi_dog_real/config/this_robot_sensor_only.yaml",
                {
                    "require_sensor_ready": False,
                    "require_estop_ready": False,
                },
            ],
        ),
        Node(
            package="mi_dog_real",
            executable="mi_dog_state_bridge_node",
            name="mi_dog_state_bridge",
            output="screen",
        ),
        Node(
            package="mi_dog_real",
            executable="mi_dog_supervisor_node",
            name="mi_dog_supervisor",
            output="screen",
            parameters=[
                "/home/mi/mi_dog_ws/src/mi_dog_real/config/supervisor.yaml",
            ],
        ),
    ])
