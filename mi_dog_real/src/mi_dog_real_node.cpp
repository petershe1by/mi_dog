#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <limits>
#include <memory>
#include <string>

#include "geometry_msgs/msg/twist.hpp"
#include "protocol/msg/motion_servo_cmd.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/image.hpp"
#include "sensor_msgs/msg/imu.hpp"
#include "sensor_msgs/msg/laser_scan.hpp"

using namespace std::chrono_literals;

namespace {
constexpr char kArmToken[] = "I_UNDERSTAND_REAL_ROBOT_RISK";
constexpr uint8_t kServoCommand = 1;
constexpr uint8_t kServoStop = 2;
constexpr uint8_t kSlowGait = 303;
constexpr uint8_t kAppCommandSource = 4;
}  // namespace

class MiDogRealNode final : public rclcpp::Node {
 public:
  MiDogRealNode() : Node("mi_dog_real") {
    enable_motion_ = declare_parameter<bool>("enable_motion", false);
    const auto arm_token = declare_parameter<std::string>("arm_token", "");
    require_sensor_ready_ = declare_parameter<bool>("require_sensor_ready", true);
    const auto camera_topic = declare_parameter<std::string>("camera_topic", "/image_rgb");
    const auto lidar_topic = declare_parameter<std::string>("lidar_topic", "/scan");
    const auto imu_topic = declare_parameter<std::string>("imu_topic", "/camera/imu");
    const auto motion_topic = declare_parameter<std::string>("motion_topic", "/motion_servo_cmd");
    const auto command_topic = declare_parameter<std::string>("command_topic", "/mi_dog_real/safe_cmd_vel");
    sensor_timeout_sec_ = declare_parameter<double>("sensor_timeout_sec", 1.0);
    command_timeout_sec_ = declare_parameter<double>("command_timeout_sec", 0.30);
    const auto publish_rate_hz = declare_parameter<double>("publish_rate_hz", 10.0);
    max_forward_mps_ = declare_parameter<double>("max_forward_mps", 0.25);
    max_lateral_mps_ = declare_parameter<double>("max_lateral_mps", 0.10);
    max_yaw_rps_ = declare_parameter<double>("max_yaw_rps", 0.40);
    step_height_m_ = declare_parameter<double>("step_height_m", 0.05);

    armed_ = enable_motion_ && arm_token == kArmToken;
    if (enable_motion_ && !armed_) {
      RCLCPP_ERROR(get_logger(), "Motion requested but arm_token is invalid; output remains disabled.");
    }
    if (!armed_) {
      RCLCPP_WARN(get_logger(), "SENSOR-ONLY MODE: no motion command will be published.");
    }

    image_sub_ = create_subscription<sensor_msgs::msg::Image>(
        camera_topic, rclcpp::SensorDataQoS(),
        [this](sensor_msgs::msg::Image::ConstSharedPtr) { last_image_ = now(); });
    lidar_sub_ = create_subscription<sensor_msgs::msg::LaserScan>(
        lidar_topic, rclcpp::SensorDataQoS(),
        [this](sensor_msgs::msg::LaserScan::ConstSharedPtr scan) {
          last_lidar_ = now();
          front_clearance_m_ = std::numeric_limits<float>::infinity();
          for (const auto range : scan->ranges) {
            if (std::isfinite(range) && range >= scan->range_min && range <= scan->range_max) {
              front_clearance_m_ = std::min(front_clearance_m_, range);
            }
          }
        });
    imu_sub_ = create_subscription<sensor_msgs::msg::Imu>(
        imu_topic, rclcpp::SensorDataQoS(),
        [this](sensor_msgs::msg::Imu::ConstSharedPtr) { last_imu_ = now(); });
    command_sub_ = create_subscription<geometry_msgs::msg::Twist>(
        command_topic, 10,
        [this](geometry_msgs::msg::Twist::ConstSharedPtr command) {
          last_command_ = now();
          command_ = *command;
        });
    motion_pub_ = create_publisher<protocol::msg::MotionServoCmd>(motion_topic, 10);

    const auto interval = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::duration<double>(1.0 / std::max(publish_rate_hz, 1.0)));
    timer_ = create_wall_timer(interval, [this] { on_timer(); });
  }

 private:
  bool recent(const rclcpp::Time &stamp) const {
    return stamp.nanoseconds() > 0 && (now() - stamp).seconds() <= sensor_timeout_sec_;
  }

  bool sensors_ready() const {
    return recent(last_image_) && recent(last_lidar_) && recent(last_imu_);
  }

  protocol::msg::MotionServoCmd make_command(uint8_t command_type) const {
    protocol::msg::MotionServoCmd message;
    message.motion_id = kSlowGait;
    message.cmd_type = command_type;
    message.cmd_source = kAppCommandSource;
    message.value = 0;
    message.vel_des[0] = std::clamp(command_.linear.x, -max_forward_mps_, max_forward_mps_);
    message.vel_des[1] = std::clamp(command_.linear.y, -max_lateral_mps_, max_lateral_mps_);
    message.vel_des[2] = std::clamp(command_.angular.z, -max_yaw_rps_, max_yaw_rps_);
    message.step_height[0] = step_height_m_;
    message.step_height[1] = step_height_m_;
    return message;
  }

  void publish_stop_once() {
    if (!stop_sent_) {
      motion_pub_->publish(make_command(kServoStop));
      stop_sent_ = true;
      RCLCPP_WARN(get_logger(), "Motion watchdog sent stop command.");
    }
  }

  void on_timer() {
    if (!armed_) return;
    if (require_sensor_ready_ && !sensors_ready()) {
      publish_stop_once();
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000,
                           "Motion inhibited: camera=%d lidar=%d imu=%d (check topic mapping).",
                           recent(last_image_), recent(last_lidar_), recent(last_imu_));
      return;
    }
    if ((now() - last_command_).seconds() > command_timeout_sec_) {
      publish_stop_once();
      return;
    }
    motion_pub_->publish(make_command(kServoCommand));
    stop_sent_ = false;
  }

  bool enable_motion_{false};
  bool armed_{false};
  bool require_sensor_ready_{true};
  bool stop_sent_{false};
  double sensor_timeout_sec_{1.0};
  double command_timeout_sec_{0.30};
  double max_forward_mps_{0.25};
  double max_lateral_mps_{0.10};
  double max_yaw_rps_{0.40};
  double step_height_m_{0.05};
  float front_clearance_m_{std::numeric_limits<float>::infinity()};
  rclcpp::Time last_image_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_lidar_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_imu_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_command_{0, 0, RCL_ROS_TIME};
  geometry_msgs::msg::Twist command_{};
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_sub_;
  rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr lidar_sub_;
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr command_sub_;
  rclcpp::Publisher<protocol::msg::MotionServoCmd>::SharedPtr motion_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MiDogRealNode>());
  rclcpp::shutdown();
  return 0;
}
