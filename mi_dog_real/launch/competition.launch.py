from launch import LaunchDescription
from launch_ros.actions import Node

ROOT = "/home/mi/mi_dog_ws/src/mi_dog_real/config"


def generate_launch_description():
    return LaunchDescription([
        Node(package="mi_dog_real", executable="mi_dog_real_node", name="mi_dog_real",
             output="screen", parameters=[f"{ROOT}/this_robot_competition.yaml"]),
        Node(package="mi_dog_real", executable="mi_dog_state_bridge_node",
             name="mi_dog_state_bridge", output="screen"),
        Node(package="mi_dog_real", executable="mi_dog_supervisor_node",
             name="mi_dog_supervisor", output="screen",
             parameters=[f"{ROOT}/supervisor.yaml"]),
        # No external E-stop input is installed. Operator STOP, supervisor
        # permission, watchdog, tilt and lidar gates remain active.
        Node(package="mi_dog_real", executable="course_perception.py",
             name="mi_dog_course_perception", output="screen",
             parameters=[f"{ROOT}/course_perception.yaml"]),
        Node(package="mi_dog_real", executable="race_controller.py",
             name="mi_dog_race_controller", output="screen",
             parameters=[f"{ROOT}/race_controller.yaml"]),
    ])
