#include <algorithm>
#include <chrono>
#include <memory>
#include <stdexcept>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/string.hpp"

class MiDogEstopGuardNode final : public rclcpp::Node {
 public:
  MiDogEstopGuardNode() : Node("mi_dog_estop_guard") {
    const auto input_topic = declare_parameter<std::string>(
        "input_topic", "/mi_dog_real/emergency_stop_input");
    const auto output_topic = declare_parameter<std::string>(
        "output_topic", "/mi_dog_real/emergency_stop");
    const auto status_topic = declare_parameter<std::string>(
        "status_topic", "/mi_dog_real/emergency_stop_guard/status");
    input_timeout_sec_ = declare_parameter<double>("input_timeout_sec", 0.25);
    const auto publish_rate_hz = declare_parameter<double>("publish_rate_hz", 20.0);

    if (input_timeout_sec_ <= 0.0 || publish_rate_hz <= 0.0) {
      throw std::invalid_argument("input_timeout_sec and publish_rate_hz must be positive");
    }

    input_sub_ = create_subscription<std_msgs::msg::Bool>(
        input_topic, rclcpp::QoS(10).best_effort(),
        [this](std_msgs::msg::Bool::ConstSharedPtr message) {
          input_seen_ = true;
          input_asserted_ = message->data;
          last_input_ = now();
          if (input_asserted_) {
            output_asserted_ = true;
            saw_asserted_since_loss_ = true;
            set_reason("input_asserted");
          } else if (saw_asserted_since_loss_) {
            output_asserted_ = false;
            set_reason("armed_after_assert_release_cycle");
          } else {
            output_asserted_ = true;
            set_reason("awaiting_assert_release_cycle");
          }
        });

    output_pub_ = create_publisher<std_msgs::msg::Bool>(
        output_topic, rclcpp::QoS(10).reliable());
    status_pub_ = create_publisher<std_msgs::msg::String>(
        status_topic, rclcpp::QoS(1).transient_local().reliable());

    const auto interval = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::duration<double>(1.0 / std::max(publish_rate_hz, 1.0)));
    timer_ = create_wall_timer(interval, [this] { publish_guard_state(); });
    set_reason("input_missing");
  }

 private:
  void set_reason(const std::string &reason) {
    if (reason_ == reason) return;
    reason_ = reason;
    RCLCPP_WARN(get_logger(), "Emergency-stop guard: %s; output_asserted=%d.",
                reason_.c_str(), output_asserted_);
  }

  void publish_guard_state() {
    const auto current_time = now();
    const bool fresh = input_seen_ &&
        last_input_.nanoseconds() > 0 &&
        (current_time - last_input_).seconds() <= input_timeout_sec_;
    if (!fresh) {
      output_asserted_ = true;
      saw_asserted_since_loss_ = false;
      set_reason(input_seen_ ? "input_stale" : "input_missing");
    }

    std_msgs::msg::Bool output;
    output.data = output_asserted_;
    output_pub_->publish(output);

    std_msgs::msg::String status;
    status.data = reason_;
    status_pub_->publish(status);
  }

  double input_timeout_sec_{0.25};
  bool input_seen_{false};
  bool input_asserted_{true};
  bool output_asserted_{true};
  bool saw_asserted_since_loss_{false};
  std::string reason_;
  rclcpp::Time last_input_{0, 0, RCL_ROS_TIME};
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr input_sub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr output_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MiDogEstopGuardNode>());
  rclcpp::shutdown();
  return 0;
}
