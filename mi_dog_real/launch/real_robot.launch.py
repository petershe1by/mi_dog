from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="mi_dog_real",
            executable="mi_dog_real_node",
            name="mi_dog_real",
            output="screen",
            parameters=["config/real_robot.yaml"],
        ),
    ])
