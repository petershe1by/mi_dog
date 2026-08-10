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
ament_target_dependencies(mi_dog_real_node
  geometry_msgs protocol rclcpp sensor_msgs std_msgs)

add_executable(mi_dog_supervisor_node src/mi_dog_supervisor_node.cpp)
ament_target_dependencies(mi_dog_supervisor_node nav_msgs protocol rclcpp std_msgs)

add_executable(mi_dog_state_bridge_node src/mi_dog_state_bridge_node.cpp)
target_link_libraries(mi_dog_state_bridge_node lcm)
ament_target_dependencies(mi_dog_state_bridge_node protocol rclcpp sensor_msgs std_msgs)

install(TARGETS mi_dog_real_node mi_dog_supervisor_node mi_dog_state_bridge_node
  DESTINATION lib/${PROJECT_NAME})
install(PROGRAMS scripts/ground_tof_capture.py
  DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME})

ament_package()
