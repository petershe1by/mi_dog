#include <algorithm>
#include <array>
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
    const auto head_roi_topic = declare_parameter<std::string>(
        "head_tof_roi_topic", "/mi_dog_real/head_ground_roi_summary");
    const auto ultrasonic_topic = declare_parameter<std::string>(
        "ultrasonic_topic", "/mi_desktop_48_b0_2d_7a_fe_40/ultrasonic_payload");
    const auto head_tof_topic = declare_parameter<std::string>(
        "head_tof_topic", "/mi_desktop_48_b0_2d_7a_fe_40/head_tof_payload");
    const auto rear_tof_topic = declare_parameter<std::string>(
        "rear_tof_topic", "/mi_desktop_48_b0_2d_7a_fe_40/rear_tof_payload");

    contact_pub_ = create_publisher<std_msgs::msg::Float32MultiArray>(contact_topic, 10);
    proximity_pub_ = create_publisher<std_msgs::msg::Float32MultiArray>(proximity_topic, 10);
    head_roi_pub_ = create_publisher<std_msgs::msg::Float32MultiArray>(head_roi_topic, 10);
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
          const auto left_roi = message->left_head.data_available ?
              center_roi_stats(message->left_head.data) :
              std::array<float, 3>{nan(), nan(), 0.0f};
          const auto right_roi = message->right_head.data_available ?
              center_roi_stats(message->right_head.data) :
              std::array<float, 3>{nan(), nan(), 0.0f};
          head_left_roi_p25_m_ = left_roi[0];
          head_left_roi_median_m_ = left_roi[1];
          head_left_roi_valid_fraction_ = left_roi[2];
          head_right_roi_p25_m_ = right_roi[0];
          head_right_roi_median_m_ = right_roi[1];
          head_right_roi_valid_fraction_ = right_roi[2];
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
        std::chrono::milliseconds(100), [this]() { publish_proximity_and_roi(); });
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

  static std::array<float, 3> center_roi_stats(const std::vector<float> &input) {
    if (input.size() != 64) {
      return {nan(), nan(), 0.0f};
    }
    std::vector<float> valid;
    valid.reserve(16);
    // Central 4x4 pixels of the raw 8x8 array. A full 180-degree index reversal
    // used by Xiaomi's point-cloud script maps this symmetric ROI onto itself.
    for (size_t row = 2; row <= 5; ++row) {
      for (size_t column = 2; column <= 5; ++column) {
        const float value = input[row * 8 + column];
        if (std::isfinite(value) && value > 0.0f) {
          valid.push_back(value);
        }
      }
    }
    const float valid_fraction = static_cast<float>(valid.size()) / 16.0f;
    if (valid.empty()) {
      return {nan(), nan(), valid_fraction};
    }
    std::sort(valid.begin(), valid.end());
    const size_t p25_index = (valid.size() - 1) / 4;
    const size_t median_index = valid.size() / 2;
    return {valid[p25_index], valid[median_index], valid_fraction};
  }

  void publish_proximity_and_roi() {
    std_msgs::msg::Float32MultiArray output;
    std_msgs::msg::Float32MultiArray roi_output;
    {
      std::lock_guard<std::mutex> lock(proximity_mutex_);
      // Order: ultrasonic, head-left, head-right, rear-left, rear-right (metres).
      output.data = {ultrasonic_m_, head_left_m_, head_right_m_, rear_left_m_, rear_right_m_};
      // Central 4x4 ROI: four ranges in metres, then two valid-pixel fractions.
      // Existing consumers retain the original first four fields.
      roi_output.data = {
          head_left_roi_p25_m_, head_left_roi_median_m_,
          head_right_roi_p25_m_, head_right_roi_median_m_,
          head_left_roi_valid_fraction_, head_right_roi_valid_fraction_};
    }
    proximity_pub_->publish(output);
    head_roi_pub_->publish(roi_output);
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
  rclcpp::Publisher<std_msgs::msg::Float32MultiArray>::SharedPtr head_roi_pub_;
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
  float head_left_roi_p25_m_{nan()};
  float head_left_roi_median_m_{nan()};
  float head_right_roi_p25_m_{nan()};
  float head_right_roi_median_m_{nan()};
  float head_left_roi_valid_fraction_{0.0f};
  float head_right_roi_valid_fraction_{0.0f};
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MiDogStateBridgeNode>());
  rclcpp::shutdown();
  return 0;
}
