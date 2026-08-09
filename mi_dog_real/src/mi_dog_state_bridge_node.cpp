#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "lcm/lcm-cpp.hpp"
#include "protocol/msg/head_tof_payload.hpp"
#include "protocol/msg/rear_tof_payload.hpp"
#include "protocol/lcm/state_estimator_lcmt.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/range.hpp"
#include "std_msgs/msg/float32_multi_array.hpp"

class MiDogStateBridgeNode final : public rclcpp::Node {
 public:
  MiDogStateBridgeNode() : Node("mi_dog_state_bridge") {
    const auto lcm_url = declare_parameter<std::string>(
        "lcm_url", "udpm://239.255.76.67:7669?ttl=255");
    const auto contact_topic = declare_parameter<std::string>(
        "foot_contact_topic", "/mi_dog_real/foot_contact_estimate");
    const auto proximity_topic = declare_parameter<std::string>(
        "proximity_summary_topic", "/mi_dog_real/proximity_summary");
    const auto ultrasonic_topic = declare_parameter<std::string>(
        "ultrasonic_topic", "/mi_desktop_48_b0_2d_7a_fe_40/ultrasonic_payload");
    const auto head_tof_topic = declare_parameter<std::string>(
        "head_tof_topic", "/mi_desktop_48_b0_2d_7a_fe_40/head_tof_payload");
    const auto rear_tof_topic = declare_parameter<std::string>(
        "rear_tof_topic", "/mi_desktop_48_b0_2d_7a_fe_40/rear_tof_payload");

    contact_pub_ = create_publisher<std_msgs::msg::Float32MultiArray>(contact_topic, 10);
    proximity_pub_ = create_publisher<std_msgs::msg::Float32MultiArray>(proximity_topic, 10);
    ultrasonic_sub_ = create_subscription<sensor_msgs::msg::Range>(
        ultrasonic_topic, rclcpp::SensorDataQoS(),
        [this](sensor_msgs::msg::Range::ConstSharedPtr message) {
          std::lock_guard<std::mutex> lock(proximity_mutex_);
          ultrasonic_m_ = std::isfinite(message->range) ? message->range : nan();
        });
    head_tof_sub_ = create_subscription<protocol::msg::HeadTofPayload>(
        head_tof_topic, rclcpp::SensorDataQoS(),
        [this](protocol::msg::HeadTofPayload::ConstSharedPtr message) {
          std::lock_guard<std::mutex> lock(proximity_mutex_);
          head_left_m_ = message->left_head.data_available ?
              median_valid(message->left_head.data) : nan();
          head_right_m_ = message->right_head.data_available ?
              median_valid(message->right_head.data) : nan();
        });
    rear_tof_sub_ = create_subscription<protocol::msg::RearTofPayload>(
        rear_tof_topic, rclcpp::SensorDataQoS(),
        [this](protocol::msg::RearTofPayload::ConstSharedPtr message) {
          std::lock_guard<std::mutex> lock(proximity_mutex_);
          rear_left_m_ = message->left_rear.data_available ?
              median_valid(message->left_rear.data) : nan();
          rear_right_m_ = message->right_rear.data_available ?
              median_valid(message->right_rear.data) : nan();
        });
    proximity_timer_ = create_wall_timer(
        std::chrono::milliseconds(100), [this]() { publish_proximity(); });
    lcm_ = std::make_unique<lcm::LCM>(lcm_url);
    if (!lcm_->good()) {
      throw std::runtime_error("Failed to initialize state_estimator LCM subscriber");
    }
    lcm_->subscribe("state_estimator", &MiDogStateBridgeNode::handle_state_estimator, this);
    running_ = true;
    lcm_thread_ = std::thread([this]() {
      while (running_ && rclcpp::ok()) {
        lcm_->handleTimeout(200);
      }
    });
    RCLCPP_WARN(
        get_logger(),
        "Read-only state_estimator bridge active; contact order is RF, LF, RR, LR.");
  }

  ~MiDogStateBridgeNode() override {
    running_ = false;
    if (lcm_thread_.joinable()) {
      lcm_thread_.join();
    }
  }

 private:
  static float nan() {
    return std::numeric_limits<float>::quiet_NaN();
  }

  static float median_valid(const std::vector<float> &input) {
    std::vector<float> valid;
    valid.reserve(input.size());
    for (const float value : input) {
      if (std::isfinite(value) && value > 0.0f) {
        valid.push_back(value);
      }
    }
    if (valid.empty()) {
      return nan();
    }
    const auto middle = valid.begin() + valid.size() / 2;
    std::nth_element(valid.begin(), middle, valid.end());
    return *middle;
  }

  void publish_proximity() {
    std_msgs::msg::Float32MultiArray output;
    {
      std::lock_guard<std::mutex> lock(proximity_mutex_);
      // Order: ultrasonic, head-left, head-right, rear-left, rear-right (metres).
      output.data = {ultrasonic_m_, head_left_m_, head_right_m_, rear_left_m_, rear_right_m_};
    }
    proximity_pub_->publish(output);
  }

  void handle_state_estimator(
      const lcm::ReceiveBuffer *, const std::string &,
      const state_estimator_lcmt *message) {
    std_msgs::msg::Float32MultiArray output;
    output.data.assign(
        message->contactEstimate,
        message->contactEstimate + 4);
    contact_pub_->publish(output);
  }

  std::unique_ptr<lcm::LCM> lcm_;
  std::atomic<bool> running_{false};
  std::thread lcm_thread_;
  rclcpp::Publisher<std_msgs::msg::Float32MultiArray>::SharedPtr contact_pub_;
  rclcpp::Publisher<std_msgs::msg::Float32MultiArray>::SharedPtr proximity_pub_;
  rclcpp::Subscription<sensor_msgs::msg::Range>::SharedPtr ultrasonic_sub_;
  rclcpp::Subscription<protocol::msg::HeadTofPayload>::SharedPtr head_tof_sub_;
  rclcpp::Subscription<protocol::msg::RearTofPayload>::SharedPtr rear_tof_sub_;
  rclcpp::TimerBase::SharedPtr proximity_timer_;
  std::mutex proximity_mutex_;
  float ultrasonic_m_{nan()};
  float head_left_m_{nan()};
  float head_right_m_{nan()};
  float rear_left_m_{nan()};
  float rear_right_m_{nan()};
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MiDogStateBridgeNode>());
  rclcpp::shutdown();
  return 0;
}
