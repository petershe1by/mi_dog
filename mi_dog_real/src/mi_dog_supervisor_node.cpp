#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "protocol/msg/bms_status.hpp"
#include "protocol/msg/motion_status.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/float32_multi_array.hpp"
#include "std_msgs/msg/int32.hpp"
#include "std_msgs/msg/string.hpp"

namespace {
constexpr int kFirstStage = 1;
constexpr int kLastStage = 6;
// Xiaomi motion_action defines INT32_MIN as the normal/no-error motor sentinel.
constexpr int32_t kMotorNormal = std::numeric_limits<int32_t>::min();
constexpr int8_t kMotionSwitchNormal = 0;
constexpr int8_t kMotionSwitchTransitioning = 1;
constexpr int8_t kMotionSwitchCharging = 14;

enum class SupervisorState {
  kDownWaiting,
  kRunning,
  kPaused,
  kEmergencyStop,
  kFinished,
};

const char *state_name(SupervisorState state) {
  switch (state) {
    case SupervisorState::kDownWaiting: return "DOWN_WAITING";
    case SupervisorState::kRunning: return "RUNNING";
    case SupervisorState::kPaused: return "PAUSED";
    case SupervisorState::kEmergencyStop: return "EMERGENCY_STOP";
    case SupervisorState::kFinished: return "FINISHED";
  }
  return "UNKNOWN";
}
}  // namespace

class MiDogSupervisorNode final : public rclcpp::Node {
 public:
  MiDogSupervisorNode() : Node("mi_dog_supervisor") {
    const auto operator_event_topic = declare_parameter<std::string>(
        "operator_event_topic", "/mi_dog_real/operator_event");
    const auto stage_complete_topic = declare_parameter<std::string>(
        "stage_complete_topic", "/mi_dog_real/stage_complete");
    const auto stage_select_topic = declare_parameter<std::string>(
        "stage_select_topic", "/mi_dog_real/supervisor/select_stage");
    const auto state_topic = declare_parameter<std::string>(
        "state_topic", "/mi_dog_real/supervisor/state");
    const auto stage_topic = declare_parameter<std::string>(
        "stage_topic", "/mi_dog_real/supervisor/current_stage");
    const auto pause_request_topic = declare_parameter<std::string>(
        "pause_request_topic", "/mi_dog_real/supervisor/pause_request");
    const auto lie_down_request_topic = declare_parameter<std::string>(
        "lie_down_request_topic", "/mi_dog_real/supervisor/lie_down_request");
    const auto run_allowed_topic = declare_parameter<std::string>(
        "run_allowed_topic", "/mi_dog_real/supervisor/run_allowed");
    const auto safe_to_lie_down_topic = declare_parameter<std::string>(
        "safe_to_lie_down_topic", "/mi_dog_real/supervisor/safe_to_lie_down");
    const auto safety_reason_topic = declare_parameter<std::string>(
        "safety_reason_topic", "/mi_dog_real/supervisor/lie_down_safety_reason");
    const auto odometry_topic = declare_parameter<std::string>(
        "odometry_topic", "/mi_desktop_48_b0_2d_7a_fe_40/odom_out");
    const auto motion_status_topic = declare_parameter<std::string>(
        "motion_status_topic", "/mi_desktop_48_b0_2d_7a_fe_40/motion_status");
    const auto bms_status_topic = declare_parameter<std::string>(
        "bms_status_topic", "/mi_desktop_48_b0_2d_7a_fe_40/bms_status");
    const auto foot_contact_topic = declare_parameter<std::string>(
        "foot_contact_topic", "/mi_dog_real/foot_contact_estimate");
    min_foot_contact_estimate_ = declare_parameter<double>(
        "min_foot_contact_estimate", 0.0);
    sensor_freshness_sec_ = declare_parameter<double>("sensor_freshness_sec", 0.5);
    bms_freshness_sec_ = declare_parameter<double>("bms_freshness_sec", 3.0);
    stable_hold_sec_ = declare_parameter<double>("stable_hold_sec", 1.5);
    max_tilt_rad_ = declare_parameter<double>("max_tilt_deg", 25.0) * M_PI / 180.0;
    max_linear_speed_ = declare_parameter<double>("max_linear_speed", 0.03);
    max_angular_speed_ = declare_parameter<double>("max_angular_speed", 0.08);
    min_battery_soc_ = declare_parameter<int>("min_battery_soc", 30);
    checkpoint_path_ = declare_parameter<std::string>(
        "checkpoint_path", "/home/mi/mi_dog_ws/state/supervisor_checkpoint.txt");
    current_stage_ = declare_parameter<int>("initial_stage", kFirstStage);
    if (current_stage_ < kFirstStage || current_stage_ > kLastStage) {
      throw std::invalid_argument("initial_stage must be in [1, 6]");
    }
    if (min_battery_soc_ < 1 || min_battery_soc_ > 100) {
      throw std::invalid_argument("min_battery_soc must be in [1, 100]");
    }

    load_checkpoint();
    // A reboot or process restart must never resume physical motion automatically.
    state_ = SupervisorState::kDownWaiting;

    const auto latched_qos = rclcpp::QoS(1).transient_local().reliable();
    state_pub_ = create_publisher<std_msgs::msg::String>(state_topic, latched_qos);
    stage_pub_ = create_publisher<std_msgs::msg::Int32>(stage_topic, latched_qos);
    pause_request_pub_ = create_publisher<std_msgs::msg::Bool>(pause_request_topic, latched_qos);
    lie_down_request_pub_ = create_publisher<std_msgs::msg::Bool>(
        lie_down_request_topic, latched_qos);
    run_allowed_pub_ = create_publisher<std_msgs::msg::Bool>(run_allowed_topic, latched_qos);
    safe_to_lie_down_pub_ = create_publisher<std_msgs::msg::Bool>(
        safe_to_lie_down_topic, latched_qos);
    safety_reason_pub_ = create_publisher<std_msgs::msg::String>(
        safety_reason_topic, latched_qos);

    operator_event_sub_ = create_subscription<std_msgs::msg::String>(
        operator_event_topic, 10,
        [this](std_msgs::msg::String::ConstSharedPtr message) {
          handle_operator_event(message->data);
        });
    stage_complete_sub_ = create_subscription<std_msgs::msg::Int32>(
        stage_complete_topic, 10,
        [this](std_msgs::msg::Int32::ConstSharedPtr message) {
          handle_stage_complete(message->data);
        });
    stage_select_sub_ = create_subscription<std_msgs::msg::Int32>(
        stage_select_topic, 10,
        [this](std_msgs::msg::Int32::ConstSharedPtr message) {
          handle_stage_select(message->data);
        });
    odometry_sub_ = create_subscription<nav_msgs::msg::Odometry>(
        odometry_topic, rclcpp::SensorDataQoS(),
        [this](nav_msgs::msg::Odometry::ConstSharedPtr message) {
          handle_odometry(*message);
        });
    motion_status_sub_ = create_subscription<protocol::msg::MotionStatus>(
        motion_status_topic, rclcpp::SensorDataQoS(),
        [this](protocol::msg::MotionStatus::ConstSharedPtr message) {
          handle_motion_status(*message);
        });
    bms_status_sub_ = create_subscription<protocol::msg::BmsStatus>(
        bms_status_topic, 10,
        [this](protocol::msg::BmsStatus::ConstSharedPtr message) {
          handle_bms_status(*message);
        });
    foot_contact_sub_ = create_subscription<std_msgs::msg::Float32MultiArray>(
        foot_contact_topic, rclcpp::SensorDataQoS(),
        [this](std_msgs::msg::Float32MultiArray::ConstSharedPtr message) {
          handle_foot_contact(*message);
        });
    safety_timer_ = create_wall_timer(
        std::chrono::milliseconds(100), [this]() { evaluate_lie_down_safety(); });

    publish_state();
    RCLCPP_WARN(
        get_logger(),
        "Supervisor ready in fail-closed DOWN_WAITING at stage %d; no motion is generated here.",
        current_stage_);
  }

 private:
  void handle_operator_event(const std::string &event) {
    if (event == "STOP") {
      transition(SupervisorState::kEmergencyStop, "operator STOP");
      return;
    }
    if (event == "PAUSE" || event == "PAUSE_TOUCH") {
      if (state_ != SupervisorState::kEmergencyStop && state_ != SupervisorState::kFinished) {
        transition(SupervisorState::kPaused, event.c_str());
      }
      return;
    }
    if (event == "START") {
      if (state_ == SupervisorState::kDownWaiting || state_ == SupervisorState::kPaused) {
        if (!run_inputs_allow_motion(now())) {
          RCLCPP_ERROR(
              get_logger(),
              "Rejected START because run inputs are not currently safe; operator must retry.");
          return;
        }
        current_stage_ = kFirstStage;
        persist_checkpoint();
        transition(SupervisorState::kRunning, "operator START from stage 1");
      } else {
        RCLCPP_WARN(get_logger(), "Ignored START while state=%s.", state_name(state_));
      }
      return;
    }
    if (event == "CONTINUE") {
      if (state_ == SupervisorState::kDownWaiting || state_ == SupervisorState::kPaused) {
        if (!run_inputs_allow_motion(now())) {
          RCLCPP_ERROR(
              get_logger(),
              "Rejected CONTINUE because run inputs are not currently safe; operator must retry.");
          return;
        }
        transition(SupervisorState::kRunning, "operator CONTINUE checkpoint");
      } else {
        RCLCPP_WARN(get_logger(), "Ignored CONTINUE while state=%s.", state_name(state_));
      }
      return;
    }
    RCLCPP_WARN(get_logger(), "Ignored unknown operator event: %s.", event.c_str());
  }

  void handle_stage_complete(int completed_stage) {
    if (state_ != SupervisorState::kRunning) {
      RCLCPP_WARN(
          get_logger(), "Ignored stage completion %d while state=%s.",
          completed_stage, state_name(state_));
      return;
    }
    if (completed_stage != current_stage_) {
      RCLCPP_ERROR(
          get_logger(), "Rejected out-of-order stage completion %d; expected %d.",
          completed_stage, current_stage_);
      return;
    }
    if (current_stage_ == kLastStage) {
      persist_checkpoint();
      transition(SupervisorState::kFinished, "all six stages complete");
      return;
    }
    ++current_stage_;
    persist_checkpoint();
    publish_state();
    RCLCPP_INFO(get_logger(), "Advanced to checkpoint stage %d.", current_stage_);
  }

  void handle_stage_select(int selected_stage) {
    if (selected_stage < kFirstStage || selected_stage > kLastStage) {
      RCLCPP_ERROR(
          get_logger(), "Rejected stage selection %d; valid range is 1..6.", selected_stage);
      return;
    }
    if (state_ != SupervisorState::kDownWaiting && state_ != SupervisorState::kPaused) {
      RCLCPP_ERROR(
          get_logger(), "Rejected stage selection %d while state=%s; pause or restart first.",
          selected_stage, state_name(state_));
      return;
    }
    current_stage_ = selected_stage;
    persist_checkpoint();
    publish_state();
    RCLCPP_WARN(
        get_logger(), "Operator selected checkpoint stage %d; motion remains inhibited.",
        current_stage_);
  }

  void handle_odometry(const nav_msgs::msg::Odometry &message) {
    const auto &q = message.pose.pose.orientation;
    const double norm = std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
    odometry_valid_ = std::isfinite(norm) && norm > 0.99 && norm < 1.01;
    if (odometry_valid_) {
      const double sin_roll = 2.0 * (q.w * q.x + q.y * q.z);
      const double cos_roll = 1.0 - 2.0 * (q.x * q.x + q.y * q.y);
      roll_rad_ = std::atan2(sin_roll, cos_roll);
      const double sin_pitch = 2.0 * (q.w * q.y - q.z * q.x);
      pitch_rad_ = std::asin(std::max(-1.0, std::min(1.0, sin_pitch)));
    }
    const auto &linear = message.twist.twist.linear;
    const auto &angular = message.twist.twist.angular;
    linear_speed_ = std::sqrt(
        linear.x * linear.x + linear.y * linear.y + linear.z * linear.z);
    angular_speed_ = std::sqrt(
        angular.x * angular.x + angular.y * angular.y + angular.z * angular.z);
    last_odometry_time_ = now();
    have_odometry_ = true;
  }

  void handle_motion_status(const protocol::msg::MotionStatus &message) {
    motion_switch_status_ = message.switch_status;
    motion_errors_clear_ = message.ori_error == 0 &&
                           message.footpos_error == 0 &&
                           std::all_of(
                               message.motor_error.begin(), message.motor_error.end(),
                               [](int32_t error) {
                                 // Observed firmware uses both 0 and kMotorNormal when healthy.
                                 return error == 0 || error == kMotorNormal;
                               });
    motion_status_healthy_ = message.switch_status == kMotionSwitchNormal &&
                             motion_errors_clear_;
    last_motion_status_time_ = now();
    have_motion_status_ = true;
  }

  void handle_bms_status(const protocol::msg::BmsStatus &message) {
    wired_charging_ = message.power_wired_charging;
    battery_soc_ = message.batt_soc;
    bms_healthy_ = message.power_normal &&
                   !message.charge_over_current &&
                   !message.discharge_over_current &&
                   !message.cell_over_voltage &&
                   !message.cell_under_voltage &&
                   !message.cell_volt_abnormal &&
                   !message.mos_over_temp &&
                   !message.discharge_short &&
                   !message.fuse &&
                   !message.discharge_over_tmp &&
                   !message.discharge_under_tmp &&
                   !message.charge_over_temp &&
                   !message.charge_under_temp &&
                   !message.chg_mos_fault &&
                   !message.dsg_mos_fault;
    last_bms_status_time_ = now();
    have_bms_status_ = true;
  }

  void handle_foot_contact(const std_msgs::msg::Float32MultiArray &message) {
    foot_contact_valid_ = message.data.size() == 4 &&
        std::all_of(message.data.begin(), message.data.end(), [this](float value) {
          // Xiaomi's official skin-manager code treats contactEstimate > 0 as liftdown.
          return std::isfinite(value) && value > min_foot_contact_estimate_;
        });
    last_foot_contact_time_ = now();
    have_foot_contact_ = true;
  }

  void evaluate_lie_down_safety() {
    const auto current_time = now();
    // BMS publishes at about 1 Hz on this robot, so it gets a wider freshness window.
    const bool bms_status_fresh = have_bms_status_ &&
        (current_time - last_bms_status_time_).seconds() <= bms_freshness_sec_;
    std::string reason = "ready";
    bool raw_safe = true;
    if (!have_odometry_) {
      raw_safe = false;
      reason = "waiting_for_odometry";
    } else if ((current_time - last_odometry_time_).seconds() > sensor_freshness_sec_) {
      raw_safe = false;
      reason = "stale_odometry";
    } else if (!odometry_valid_) {
      raw_safe = false;
      reason = "invalid_orientation";
    } else if (std::abs(roll_rad_) > max_tilt_rad_ ||
               std::abs(pitch_rad_) > max_tilt_rad_) {
      raw_safe = false;
      reason = "excessive_body_tilt";
    } else if (linear_speed_ > max_linear_speed_) {
      raw_safe = false;
      reason = "body_still_translating";
    } else if (angular_speed_ > max_angular_speed_) {
      raw_safe = false;
      reason = "body_still_rotating";
    } else if (!have_motion_status_) {
      raw_safe = false;
      reason = "waiting_for_motion_status";
    } else if (!motion_status_healthy_) {
      raw_safe = false;
      if (motion_switch_status_ == kMotionSwitchCharging) {
        reason = bms_status_fresh && !wired_charging_ ?
            "motion_controller_charging_state_stale" :
            "motion_controller_charging_inhibited";
      } else {
        reason = "motion_controller_not_healthy";
      }
    } else if (!have_foot_contact_) {
      raw_safe = false;
      reason = "waiting_for_foot_contact";
    } else if ((current_time - last_foot_contact_time_).seconds() > sensor_freshness_sec_) {
      raw_safe = false;
      reason = "stale_foot_contact";
    } else if (!foot_contact_valid_) {
      raw_safe = false;
      reason = "not_all_feet_in_contact";
    } else if (!have_bms_status_) {
      raw_safe = false;
      reason = "waiting_for_bms_status";
    } else if (!bms_status_fresh) {
      raw_safe = false;
      reason = "stale_bms_status";
    } else if (!bms_healthy_) {
      raw_safe = false;
      reason = "bms_not_healthy";
    } else if (battery_soc_ < min_battery_soc_) {
      raw_safe = false;
      reason = "battery_soc_below_minimum";
    } else if (wired_charging_) {
      raw_safe = false;
      reason = "wired_charging_motion_inhibited";
    }

    if (!raw_safe) {
      stable_since_valid_ = false;
    } else if (!stable_since_valid_) {
      stable_since_ = current_time;
      stable_since_valid_ = true;
      reason = "stability_hold";
    } else if ((current_time - stable_since_).seconds() < stable_hold_sec_) {
      reason = "stability_hold";
    }
    const bool safe = raw_safe && stable_since_valid_ &&
                      (current_time - stable_since_).seconds() >= stable_hold_sec_;

    std_msgs::msg::Bool safe_message;
    safe_message.data = safe;
    safe_to_lie_down_pub_->publish(safe_message);
    std_msgs::msg::String reason_message;
    reason_message.data = reason;
    safety_reason_pub_->publish(reason_message);
    publish_run_allowed(current_time);
  }

  bool power_allows_motion(const rclcpp::Time &current_time) const {
    return have_bms_status_ && bms_healthy_ &&
           battery_soc_ >= min_battery_soc_ && !wired_charging_ &&
           (current_time - last_bms_status_time_).seconds() <= bms_freshness_sec_;
  }

  bool run_inputs_allow_motion(const rclcpp::Time &current_time) const {
    const bool odometry_allows_run = have_odometry_ && odometry_valid_ &&
        (current_time - last_odometry_time_).seconds() <= sensor_freshness_sec_ &&
        std::abs(roll_rad_) <= max_tilt_rad_ && std::abs(pitch_rad_) <= max_tilt_rad_;
    const bool motion_switch_allows_run =
        motion_switch_status_ == kMotionSwitchNormal ||
        motion_switch_status_ == kMotionSwitchTransitioning;
    // MotionStatus is emitted on actions/state changes by this firmware, not as
    // a heartbeat. Keep the most recent health result; a new error event revokes
    // permission immediately.
    const bool motion_status_allows_run = have_motion_status_ && motion_errors_clear_ &&
        motion_switch_allows_run;
    return odometry_allows_run && motion_status_allows_run &&
           power_allows_motion(current_time);
  }

  void publish_run_allowed(const rclcpp::Time &current_time) {
    const bool inputs_allow_motion = run_inputs_allow_motion(current_time);
    if (state_ == SupervisorState::kRunning && !inputs_allow_motion) {
      transition(SupervisorState::kPaused, "runtime safety input revoked");
      return;
    }
    std_msgs::msg::Bool message;
    message.data = state_ == SupervisorState::kRunning &&
                   inputs_allow_motion;
    run_allowed_pub_->publish(message);
  }

  void transition(SupervisorState next, const char *reason) {
    const auto previous = state_;
    state_ = next;
    publish_state();
    RCLCPP_WARN(
        get_logger(), "Supervisor %s -> %s at stage %d: %s.",
        state_name(previous), state_name(state_), current_stage_, reason);
  }

  void publish_state() {
    std_msgs::msg::String state_message;
    state_message.data = state_name(state_);
    state_pub_->publish(state_message);

    std_msgs::msg::Int32 stage_message;
    stage_message.data = current_stage_;
    stage_pub_->publish(stage_message);

    const bool paused = state_ != SupervisorState::kRunning;
    std_msgs::msg::Bool bool_message;
    bool_message.data = paused;
    pause_request_pub_->publish(bool_message);
    // This is only a request. A future posture controller must verify stable ground first.
    bool_message.data = state_ == SupervisorState::kPaused ||
                        state_ == SupervisorState::kFinished;
    lie_down_request_pub_->publish(bool_message);
    publish_run_allowed(now());
  }

  void load_checkpoint() {
    std::ifstream input(checkpoint_path_);
    int saved_stage = 0;
    if (input >> saved_stage && saved_stage >= kFirstStage && saved_stage <= kLastStage) {
      current_stage_ = saved_stage;
      RCLCPP_INFO(get_logger(), "Loaded checkpoint stage %d.", current_stage_);
    }
  }

  void persist_checkpoint() {
    const auto temporary = checkpoint_path_ + ".tmp";
    {
      std::ofstream output(temporary, std::ios::trunc);
      if (!output) {
        RCLCPP_ERROR(get_logger(), "Cannot write checkpoint temporary file: %s.", temporary.c_str());
        return;
      }
      output << current_stage_ << '\n';
      output.flush();
      if (!output) {
        RCLCPP_ERROR(get_logger(), "Checkpoint write failed: %s.", temporary.c_str());
        return;
      }
    }
    if (std::rename(temporary.c_str(), checkpoint_path_.c_str()) != 0) {
      RCLCPP_ERROR(get_logger(), "Checkpoint rename failed for %s.", checkpoint_path_.c_str());
    }
  }

  SupervisorState state_{SupervisorState::kDownWaiting};
  int current_stage_{kFirstStage};
  std::string checkpoint_path_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr state_pub_;
  rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr stage_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr pause_request_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr lie_down_request_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr run_allowed_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr safe_to_lie_down_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr safety_reason_pub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr operator_event_sub_;
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr stage_complete_sub_;
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr stage_select_sub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odometry_sub_;
  rclcpp::Subscription<protocol::msg::MotionStatus>::SharedPtr motion_status_sub_;
  rclcpp::Subscription<protocol::msg::BmsStatus>::SharedPtr bms_status_sub_;
  rclcpp::Subscription<std_msgs::msg::Float32MultiArray>::SharedPtr foot_contact_sub_;
  rclcpp::TimerBase::SharedPtr safety_timer_;
  double sensor_freshness_sec_{0.5};
  double bms_freshness_sec_{3.0};
  double stable_hold_sec_{1.5};
  double max_tilt_rad_{0.0};
  double max_linear_speed_{0.03};
  double max_angular_speed_{0.08};
  bool have_odometry_{false};
  bool have_motion_status_{false};
  bool odometry_valid_{false};
  bool motion_status_healthy_{false};
  bool motion_errors_clear_{false};
  int8_t motion_switch_status_{0};
  int min_battery_soc_{30};
  int battery_soc_{0};
  bool have_bms_status_{false};
  bool bms_healthy_{false};
  bool wired_charging_{false};
  bool have_foot_contact_{false};
  bool foot_contact_valid_{false};
  bool stable_since_valid_{false};
  double roll_rad_{0.0};
  double pitch_rad_{0.0};
  double linear_speed_{0.0};
  double angular_speed_{0.0};
  rclcpp::Time last_odometry_time_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_motion_status_time_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_bms_status_time_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_foot_contact_time_{0, 0, RCL_ROS_TIME};
  rclcpp::Time stable_since_{0, 0, RCL_ROS_TIME};
  double min_foot_contact_estimate_{0.0};
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MiDogSupervisorNode>());
  rclcpp::shutdown();
  return 0;
}
