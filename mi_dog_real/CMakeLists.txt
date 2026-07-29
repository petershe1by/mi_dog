cmake_minimum_required(VERSION 3.8)
project(mi_dog_real)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(protocol REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)

add_executable(mi_dog_real_node src/mi_dog_real_node.cpp)
ament_target_dependencies(mi_dog_real_node
  geometry_msgs protocol rclcpp sensor_msgs)

install(TARGETS mi_dog_real_node
  DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME})

ament_package()
