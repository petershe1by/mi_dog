cmake_minimum_required(VERSION 3.8)
project(mi_dog_real)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(lcm REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(protocol REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(mi_dog_real_node src/mi_dog_real_node.cpp)
target_include_directories(mi_dog_real_node PRIVATE include)
ament_target_dependencies(mi_dog_real_node
  geometry_msgs nav_msgs protocol rclcpp sensor_msgs std_msgs)

add_executable(mi_dog_supervisor_node src/mi_dog_supervisor_node.cpp)
ament_target_dependencies(mi_dog_supervisor_node nav_msgs protocol rclcpp std_msgs)

add_executable(mi_dog_state_bridge_node src/mi_dog_state_bridge_node.cpp)
target_link_libraries(mi_dog_state_bridge_node lcm)
ament_target_dependencies(mi_dog_state_bridge_node protocol rclcpp sensor_msgs std_msgs)

add_executable(mi_dog_estop_guard_node src/mi_dog_estop_guard_node.cpp)
ament_target_dependencies(mi_dog_estop_guard_node rclcpp std_msgs)

install(TARGETS mi_dog_real_node mi_dog_supervisor_node mi_dog_state_bridge_node
  mi_dog_estop_guard_node
  DESTINATION lib/${PROJECT_NAME})
install(PROGRAMS
  scripts/race_controller.py
  scripts/race_controller_offline_test.py
  scripts/race_controller_gate_isolated_test.py
  scripts/race_controller_sensor_stale_isolated_test.py
  scripts/race_mission.py
  scripts/race_mission_offline_test.py
  scripts/race_replay.py
  scripts/course_perception.py
  scripts/course_perception_offline_test.py
  scripts/course_perception_isolated_test.py
  scripts/ground_tof_capture.py
  scripts/estop_guard_isolated_test.py
  scripts/estop_hid_input.py
  scripts/estop_hid_isolated_test.py
  scripts/motion_servo_sequence_isolated_test.py
  scripts/supervisor_power_gate_isolated_test.py
  scripts/supervisor_stage_select_isolated_test.py
  DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME})
install(DIRECTORY include/
  DESTINATION include)
install(FILES ../audio/orange_ball.wav
  DESTINATION share/${PROJECT_NAME}/audio)

ament_package()
