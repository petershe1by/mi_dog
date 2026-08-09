from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="mi_dog_real",
            executable="mi_dog_real_node",
            name="mi_dog_real",
            output="screen",
            parameters=[
                PathJoinSubstitution([
                    FindPackageShare("mi_dog_real"),
                    "config",
                    "real_robot.yaml",
                ])
            ],
        ),
    ])
