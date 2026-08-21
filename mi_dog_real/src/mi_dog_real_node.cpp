#include <algorithm>
#include <array>
#include <cctype>
#include <chrono>
#include <cmath>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>

#include "geometry_msgs/msg/twist.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "geometry_msgs/msg/quaternion.hpp"
#include "mi_dog_real/front_clearance_filter.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "protocol/msg/motion_servo_cmd.hpp"
#include "protocol/msg/touch_status.hpp"
#include "protocol/srv/audio_text_play.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/image.hpp"
#include "sensor_msgs/msg/laser_scan.hpp"
#include "sensor_msgs/msg/range.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"
#include "std_msgs/msg/int32.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

namespace {
constexpr char kArmToken[] = "I_UNDERSTAND_REAL_ROBOT_RISK";
constexpr int32_t kServoStart = protocol::msg::MotionServoCmd::SERVO_START;
constexpr int32_t kServoCommand = protocol::msg::MotionServoCmd::SERVO_DATA;
constexpr int32_t kServoStop = protocol::msg::MotionServoCmd::SERVO_END;
constexpr int32_t kSlowGait = 303;
constexpr int32_t kVisualCommandSource = 2;

double move_toward(double current, double target, double maximum_delta) {
  return current + std::clamp(target - current, -maximum_delta, maximum_delta);
}

std::string normalize_phrase(std::string text) {
  text.erase(
      std::remove_if(text.begin(), text.end(), [](unsigned char value) {
        return value < 0x80 && std::isspace(value);
      }),
      text.end());
  const std::array<std::string, 7> suffixes{"。", "！", "!", "？", "?", "，", ","};
  bool removed = true;
  while (removed) {
    removed = false;
    for (const auto &suffix : suffixes) {
      if (text.size() >= suffix.size() &&
          text.compare(text.size() - suffix.size(), suffix.size(), suffix) == 0) {
        text.erase(text.size() - suffix.size());
        removed = true;
        break;
      }
    }
  }
  return text;
}
}  // namespace

class MiDogRealNode final : public rclcpp::Node {
 public:
  MiDogRealNode() : Node("mi_dog_real") {
    enable_motion_ = declare_parameter<bool>("enable_motion", false);
    const auto arm_token = declare_parameter<std::string>("arm_token", "");
    require_sensor_ready_ = declare_parameter<bool>("require_sensor_ready", true);
    require_camera_ready_ = declare_parameter<bool>("require_camera_ready", false);
    require_lidar_ready_ = declare_parameter<bool>("require_lidar_ready", true);
    require_pose_ready_ = declare_parameter<bool>("require_pose_ready", true);
    require_estop_ready_ = declare_parameter<bool>("require_estop_ready", true);
    require_voice_start_ = declare_parameter<bool>("require_voice_start", false);
    require_supervisor_run_allowed_ =
        declare_parameter<bool>("require_supervisor_run_allowed", true);
    const auto camera_topic = declare_parameter<std::string>("camera_topic", "/image");
    const auto lidar_topic = declare_parameter<std::string>("lidar_topic", "/scan");
    const auto ultrasonic_topic =
        declare_parameter<std::string>("ultrasonic_topic", "/ultrasonic_payload");
    const auto pose_topic = declare_parameter<std::string>("pose_topic", "/pose_filtered");
    const auto odometry_topic = declare_parameter<std::string>("odometry_topic", "/odom_out");
    const auto estop_topic =
        declare_parameter<std::string>("estop_topic", "/mi_dog_real/emergency_stop");
    const auto motion_topic = declare_parameter<std::string>("motion_topic", "/motion_servo_cmd");
    const auto command_topic = declare_parameter<std::string>("command_topic", "/mi_dog_real/safe_cmd_vel");
    const auto front_clearance_summary_topic = declare_parameter<std::string>(
        "front_clearance_summary_topic", "/mi_dog_real/front_clearance_summary");
    const auto voice_command_topic =
        declare_parameter<std::string>("voice_command_topic", "/mi_dog_real/voice_command");
    const auto touch_topic =
        declare_parameter<std::string>("touch_topic", "/touch_status");
    const auto race_enabled_topic =
        declare_parameter<std::string>("race_enabled_topic", "/mi_dog_real/race_enabled");
    const auto operator_event_topic =
        declare_parameter<std::string>("operator_event_topic", "/mi_dog_real/operator_event");
    const auto supervisor_run_allowed_topic = declare_parameter<std::string>(
        "supervisor_run_allowed_topic", "/mi_dog_real/supervisor/run_allowed");
    const auto current_stage_topic = declare_parameter<std::string>(
        "current_stage_topic", "/mi_dog_real/supervisor/current_stage");
    const auto audio_feedback_service =
        declare_parameter<std::string>("audio_feedback_service", "/speech_text_play");
    const auto wake_event_topic =
        declare_parameter<std::string>("wake_event_topic", "/dog_wakeup");
    const auto continue_dialog_topic =
        declare_parameter<std::string>("continue_dialog_topic", "/continue_dialog");
    manage_dialogue_ = declare_parameter<bool>("manage_dialogue", false);
    const auto wake_word_topic = declare_parameter<std::string>("wake_word_topic", "wake_word");
    wake_word_ = declare_parameter<std::string>("wake_word", "铁蛋铁蛋");
    publish_wake_word_ = declare_parameter<bool>("publish_wake_word", false);
    start_phrase_ = declare_parameter<std::string>("start_phrase", "开始比赛");
    continue_phrase_ = declare_parameter<std::string>("continue_phrase", "继续比赛");
    pause_phrase_ = declare_parameter<std::string>("pause_phrase", "暂停比赛");
    stop_phrase_ = declare_parameter<std::string>("stop_phrase", "停止比赛");
    touch_pause_enabled_ = declare_parameter<bool>("touch_pause_enabled", true);
    touch_double_tap_state_ = declare_parameter<int>("touch_double_tap_state", 3);
    touch_lockout_sec_ = declare_parameter<double>("touch_lockout_sec", 1.5);
    audio_feedback_enabled_ = declare_parameter<bool>("audio_feedback_enabled", true);
    audio_feedback_play_id_ = declare_parameter<int>("audio_feedback_play_id", 9000);
    sensor_timeout_sec_ = declare_parameter<double>("sensor_timeout_sec", 1.0);
    estop_timeout_sec_ = declare_parameter<double>("estop_timeout_sec", 0.50);
    command_timeout_sec_ = declare_parameter<double>("command_timeout_sec", 0.30);
    supervisor_timeout_sec_ = declare_parameter<double>("supervisor_timeout_sec", 0.50);
    const auto publish_rate_hz = declare_parameter<double>("publish_rate_hz", 10.0);
    max_forward_mps_ = declare_parameter<double>("max_forward_mps", 0.25);
    max_lateral_mps_ = declare_parameter<double>("max_lateral_mps", 0.10);
    max_yaw_rps_ = declare_parameter<double>("max_yaw_rps", 0.40);
    max_forward_accel_mps2_ = declare_parameter<double>("max_forward_accel_mps2", 0.40);
    max_lateral_accel_mps2_ = declare_parameter<double>("max_lateral_accel_mps2", 0.30);
    max_yaw_accel_rps2_ = declare_parameter<double>("max_yaw_accel_rps2", 0.80);
    step_height_m_ = declare_parameter<double>("step_height_m", 0.05);
    stage_1_step_height_m_ = declare_parameter<double>("stage_1_step_height_m", 0.15);
    front_stop_distance_m_ = declare_parameter<double>("front_stop_distance_m", 0.35);
    front_slow_distance_m_ = declare_parameter<double>("front_slow_distance_m", 0.70);
    stage_2_front_stop_distance_m_ =
        declare_parameter<double>("stage_2_front_stop_distance_m", 0.18);
    stage_2_front_slow_distance_m_ =
        declare_parameter<double>("stage_2_front_slow_distance_m", 0.40);
    front_half_angle_rad_ = declare_parameter<double>("front_half_angle_rad", 0.45);
    front_lidar_self_echo_max_m_ =
        declare_parameter<double>("front_lidar_self_echo_max_m", 0.32);
    front_lidar_cluster_range_jump_m_ =
        declare_parameter<double>("front_lidar_cluster_range_jump_m", 0.12);
    front_lidar_cluster_min_samples_ =
        declare_parameter<int>("front_lidar_cluster_min_samples", 4);
    front_confirmation_frames_ = declare_parameter<int>("front_confirmation_frames", 3);
    front_ultrasonic_extreme_stop_m_ =
        declare_parameter<double>("front_ultrasonic_extreme_stop_m", 0.20);
    max_tilt_rad_ = declare_parameter<double>("max_tilt_rad", 0.60);
    stop_heartbeat_sec_ = declare_parameter<double>("stop_heartbeat_sec", 0.20);

    if (sensor_timeout_sec_ <= 0.0 || estop_timeout_sec_ <= 0.0 ||
        command_timeout_sec_ <= 0.0 || supervisor_timeout_sec_ <= 0.0 ||
        publish_rate_hz <= 0.0 ||
        max_forward_mps_ <= 0.0 || max_lateral_mps_ <= 0.0 || max_yaw_rps_ <= 0.0 ||
        max_forward_accel_mps2_ <= 0.0 || max_lateral_accel_mps2_ <= 0.0 ||
        max_yaw_accel_rps2_ <= 0.0 || step_height_m_ <= 0.0 ||
        stage_1_step_height_m_ <= 0.0 || stage_1_step_height_m_ > 0.15 ||
        front_stop_distance_m_ <= 0.0 || front_slow_distance_m_ <= front_stop_distance_m_ ||
        stage_2_front_stop_distance_m_ <= 0.0 ||
        stage_2_front_slow_distance_m_ <= stage_2_front_stop_distance_m_ ||
        stage_2_front_stop_distance_m_ > front_stop_distance_m_ ||
        stage_2_front_slow_distance_m_ > front_slow_distance_m_ ||
        front_half_angle_rad_ <= 0.0 || front_lidar_self_echo_max_m_ <= 0.0 ||
        front_lidar_self_echo_max_m_ >= front_stop_distance_m_ ||
        front_lidar_cluster_range_jump_m_ <= 0.0 ||
        front_lidar_cluster_min_samples_ < 2 || front_confirmation_frames_ < 2 ||
        front_ultrasonic_extreme_stop_m_ <= 0.0 ||
        front_ultrasonic_extreme_stop_m_ >= front_stop_distance_m_ || max_tilt_rad_ <= 0.0 ||
        stop_heartbeat_sec_ <= 0.0 || touch_lockout_sec_ <= 0.0 ||
        audio_feedback_play_id_ < 0 || audio_feedback_play_id_ > 65535) {
      throw std::invalid_argument("Invalid safety parameter: limits must be positive and slow distance must exceed stop distance.");
    }
    control_period_sec_ = 1.0 / publish_rate_hz;
    front_clearance_filter_ = std::make_unique<mi_dog_real::FrontClearanceFilter>(
        mi_dog_real::FrontClearanceConfig{
            front_half_angle_rad_, front_stop_distance_m_, front_slow_distance_m_,
            front_lidar_self_echo_max_m_, front_lidar_cluster_range_jump_m_,
            static_cast<std::size_t>(front_lidar_cluster_min_samples_),
            static_cast<std::size_t>(front_confirmation_frames_),
            front_ultrasonic_extreme_stop_m_});
    front_clearance_pub_ = create_publisher<std_msgs::msg::Float64MultiArray>(
        front_clearance_summary_topic, rclcpp::SensorDataQoS());
    current_stage_sub_ = create_subscription<std_msgs::msg::Int32>(
        current_stage_topic, rclcpp::QoS(1).reliable().transient_local(),
        [this](std_msgs::msg::Int32::ConstSharedPtr stage) {
          current_stage_ = stage->data >= 1 && stage->data <= 6 ? stage->data : 0;
        });

    armed_ = enable_motion_ && arm_token == kArmToken;
    voice_enabled_ = !require_voice_start_;
    if (enable_motion_ && !armed_) {
      RCLCPP_ERROR(get_logger(), "Motion requested but arm_token is invalid; output remains disabled.");
    }
    if (!armed_) {
      RCLCPP_WARN(get_logger(), "SENSOR-ONLY MODE: no motion command will be published.");
    }

    image_sub_ = create_subscription<sensor_msgs::msg::Image>(
        camera_topic, rclcpp::SensorDataQoS(),
        [this](sensor_msgs::msg::Image::ConstSharedPtr image) {
          image_valid_ = image->width > 0 && image->height > 0 && !image->data.empty();
          last_image_ = now();
        });
    lidar_sub_ = create_subscription<sensor_msgs::msg::LaserScan>(
        lidar_topic, rclcpp::SensorDataQoS(),
        [this](sensor_msgs::msg::LaserScan::ConstSharedPtr scan) {
          last_lidar_ = now();
          std::size_t front_samples = 0;
          for (std::size_t index = 0; index < scan->ranges.size(); ++index) {
            const double angle = scan->angle_min + index * scan->angle_increment;
            const double wrapped_angle = std::atan2(std::sin(angle), std::cos(angle));
            if (std::abs(wrapped_angle) > front_half_angle_rad_) continue;
            ++front_samples;
          }
          lidar_valid_ = front_samples > 0 && std::isfinite(scan->range_max) &&
                         scan->range_max > scan->range_min && scan->angle_increment != 0.0;
          if (lidar_valid_) {
            front_clearance_filter_->update_lidar(
                scan->ranges, scan->angle_min, scan->angle_increment,
                scan->range_min, scan->range_max);
            front_clearance_m_ = front_clearance_filter_->clearance();
            publish_front_clearance();
          }
        });
    ultrasonic_sub_ = create_subscription<sensor_msgs::msg::Range>(
        ultrasonic_topic, rclcpp::SensorDataQoS(),
        [this](sensor_msgs::msg::Range::ConstSharedPtr message) {
          front_clearance_filter_->update_ultrasonic(
              message->range, message->min_range, message->max_range);
          front_clearance_m_ = front_clearance_filter_->clearance();
          publish_front_clearance();
        });
    pose_sub_ = create_subscription<geometry_msgs::msg::PoseStamped>(
        pose_topic, rclcpp::SensorDataQoS(),
        [this](geometry_msgs::msg::PoseStamped::ConstSharedPtr pose) {
          update_orientation(pose->pose.orientation);
        });
    odometry_sub_ = create_subscription<nav_msgs::msg::Odometry>(
        odometry_topic, rclcpp::SensorDataQoS(),
        [this](nav_msgs::msg::Odometry::ConstSharedPtr odometry) {
          update_orientation(odometry->pose.pose.orientation);
        });
    estop_sub_ = create_subscription<std_msgs::msg::Bool>(
        estop_topic, rclcpp::SensorDataQoS(),
        [this](std_msgs::msg::Bool::ConstSharedPtr estop) {
          emergency_stop_ = estop->data;
          last_estop_ = now();
        });
    command_sub_ = create_subscription<geometry_msgs::msg::Twist>(
        command_topic, 10,
        [this](geometry_msgs::msg::Twist::ConstSharedPtr command) {
          last_command_ = now();
          command_valid_ = std::isfinite(command->linear.x) &&
                           std::isfinite(command->linear.y) &&
                           std::isfinite(command->angular.z);
          if (!command_valid_) {
            command_ = geometry_msgs::msg::Twist{};
            RCLCPP_ERROR(get_logger(), "Rejected non-finite motion command.");
            return;
          }
          command_ = *command;
        });
    voice_command_sub_ = create_subscription<std_msgs::msg::String>(
        voice_command_topic, 10,
        [this](std_msgs::msg::String::ConstSharedPtr command) {
          const auto text = normalize_phrase(command->data);
          if (text.empty()) return;
          if (text == stop_phrase_ || text == pause_phrase_) {
            inhibit_race(text == stop_phrase_ ? "voice stop" : "voice pause",
                         text == stop_phrase_ ? "STOP" : "PAUSE");
            return;
          }
          if (text != start_phrase_ && text != continue_phrase_) {
            RCLCPP_WARN(get_logger(), "Voice text rejected by exact whitelist: %s.", text.c_str());
            return;
          }
          const bool estop_ready = !require_estop_ready_ ||
              (recent(last_estop_, estop_timeout_sec_) && !emergency_stop_);
          const bool sensor_ready = !require_sensor_ready_ || sensors_ready();
          if (!sensor_ready || !estop_ready) {
            RCLCPP_WARN(
                get_logger(),
                "Voice start refused: sensors_ready=%d estop_ready=%d.",
                sensor_ready, estop_ready);
            return;
          }
          voice_enabled_ = true;
          publish_race_enabled();
          publish_operator_event(text == start_phrase_ ? "START" : "CONTINUE");
          play_audio_feedback(text == start_phrase_ ? "START" : "CONTINUE");
          RCLCPP_INFO(get_logger(), "Voice command accepted: %s.", text.c_str());
        });
    touch_sub_ = create_subscription<protocol::msg::TouchStatus>(
        touch_topic, 10,
        [this](protocol::msg::TouchStatus::ConstSharedPtr touch) {
          if (!touch_pause_enabled_ || touch->touch_state != touch_double_tap_state_) return;
          const auto stamp = now();
          if (recent(last_touch_pause_, touch_lockout_sec_)) {
            RCLCPP_DEBUG(get_logger(), "Ignored duplicate double-tap report.");
            return;
          }
          last_touch_pause_ = stamp;
          inhibit_race("touch double tap", "PAUSE_TOUCH");
        });
    motion_pub_ = create_publisher<protocol::msg::MotionServoCmd>(motion_topic, 10);
    supervisor_run_allowed_sub_ = create_subscription<std_msgs::msg::Bool>(
        supervisor_run_allowed_topic, rclcpp::QoS(1).transient_local().reliable(),
        [this](std_msgs::msg::Bool::ConstSharedPtr allowed) {
          supervisor_run_allowed_ = allowed->data;
          last_supervisor_run_allowed_ = now();
          if (!allowed->data) {
            command_ = geometry_msgs::msg::Twist{};
            command_valid_ = false;
          }
        });
    race_enabled_pub_ = create_publisher<std_msgs::msg::Bool>(
        race_enabled_topic, rclcpp::QoS(1).transient_local().reliable());
    wake_word_pub_ = create_publisher<std_msgs::msg::String>(wake_word_topic, 2);
    operator_event_pub_ = create_publisher<std_msgs::msg::String>(
        operator_event_topic, rclcpp::QoS(10).reliable());
    continue_dialog_pub_ = create_publisher<std_msgs::msg::Bool>(continue_dialog_topic, 2);
    wake_event_sub_ = create_subscription<std_msgs::msg::Bool>(
        wake_event_topic, 10,
        [this](std_msgs::msg::Bool::ConstSharedPtr wake) {
          if (!wake->data) return;
          if (manage_dialogue_) {
            RCLCPP_WARN(
                get_logger(),
                "Wake event received; opening dialogue also exposes the factory action route.");
            set_dialogue(true);
          } else {
            RCLCPP_INFO(
                get_logger(),
                "Wake event received; dialogue management is disabled for factory-action isolation.");
          }
        });
    audio_feedback_client_ = create_client<protocol::srv::AudioTextPlay>(
        audio_feedback_service);
    publish_race_enabled();

    const auto interval = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::duration<double>(1.0 / std::max(publish_rate_hz, 1.0)));
    timer_ = create_wall_timer(interval, [this] { on_timer(); });
  }

 private:
  void update_orientation(const geometry_msgs::msg::Quaternion &quaternion) {
    const double norm = std::sqrt(
        quaternion.x * quaternion.x + quaternion.y * quaternion.y +
        quaternion.z * quaternion.z + quaternion.w * quaternion.w);
    if (!std::isfinite(norm) || norm < 0.5) {
      return;
    }
    const double x = quaternion.x / norm;
    const double y = quaternion.y / norm;
    const double z = quaternion.z / norm;
    const double w = quaternion.w / norm;
    const double roll = std::atan2(
        2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y));
    const double pitch = std::asin(
        std::clamp(2.0 * (w * y - z * x), -1.0, 1.0));
    const double tilt = std::max(std::abs(roll), std::abs(pitch));
    if (!std::isfinite(tilt)) {
      return;
    }
    tilt_rad_ = tilt;
    last_pose_ = now();
    pose_valid_ = true;
  }

  void inhibit_race(const char *reason, const char *event) {
    voice_enabled_ = false;
    command_ = geometry_msgs::msg::Twist{};
    command_valid_ = false;
    publish_race_enabled();
    publish_operator_event(event);
    play_audio_feedback(event);
    RCLCPP_ERROR(get_logger(), "%s accepted; race motion is inhibited.", reason);
  }

  void publish_operator_event(const std::string &event) {
    if (!operator_event_pub_) return;
    std_msgs::msg::String message;
    message.data = event;
    operator_event_pub_->publish(message);
  }

  void set_dialogue(bool enabled) {
    if (!manage_dialogue_ || !continue_dialog_pub_) return;
    std_msgs::msg::Bool message;
    message.data = enabled;
    continue_dialog_pub_->publish(message);
  }

  void play_audio_feedback(const std::string &event) {
    if (!audio_feedback_enabled_ || !audio_feedback_client_) return;
    if (!audio_feedback_client_->service_is_ready()) {
      RCLCPP_WARN(get_logger(), "Audio feedback unavailable for event %s.", event.c_str());
      return;
    }
    auto request = std::make_shared<protocol::srv::AudioTextPlay::Request>();
    request->module_name = "mi_dog_real";
    request->is_online = false;
    request->speech.module_name = "mi_dog_real";
    request->speech.play_id = static_cast<uint16_t>(audio_feedback_play_id_);
    request->text.clear();
    audio_feedback_client_->async_send_request(
        request,
        [this, event](rclcpp::Client<protocol::srv::AudioTextPlay>::SharedFuture future) {
          const auto response = future.get();
          if (response->status == 0) {
            RCLCPP_INFO(get_logger(), "Offline audio feedback completed: %s.", event.c_str());
          } else {
            RCLCPP_WARN(get_logger(), "Offline audio feedback failed: %s status=%u.",
                        event.c_str(), response->status);
          }
        });
  }

  bool recent(const rclcpp::Time &stamp, double timeout_sec) const {
    return stamp.nanoseconds() > 0 && (now() - stamp).seconds() <= timeout_sec;
  }

  void publish_front_clearance() {
    if (!front_clearance_pub_) return;
    std_msgs::msg::Float64MultiArray message;
    message.data = {front_clearance_filter_->clearance(),
                    front_clearance_filter_->lidar_clearance(),
                    front_clearance_filter_->ultrasonic_clearance()};
    front_clearance_pub_->publish(message);
  }

  bool sensors_ready() const {
    const bool camera_ready = image_valid_ && recent(last_image_, sensor_timeout_sec_);
    const bool lidar_ready = lidar_valid_ && recent(last_lidar_, sensor_timeout_sec_);
    const bool pose_ready = pose_valid_ && recent(last_pose_, sensor_timeout_sec_);
    return (!require_camera_ready_ || camera_ready) &&
           (!require_lidar_ready_ || lidar_ready) &&
           (!require_pose_ready_ || pose_ready);
  }

  void publish_race_enabled() {
    if (!race_enabled_pub_) return;
    std_msgs::msg::Bool state;
    state.data = voice_enabled_;
    race_enabled_pub_->publish(state);
  }

  protocol::msg::MotionServoCmd make_command(int32_t command_type) {
    protocol::msg::MotionServoCmd message;
    message.motion_id = kSlowGait;
    message.cmd_type = command_type;
    message.cmd_source = kVisualCommandSource;
    message.value = 0;

    double forward = 0.0;
    double lateral = 0.0;
    double yaw = 0.0;
    if (command_type == kServoCommand) {
      const double active_front_stop_distance = current_stage_ == 2 ?
          stage_2_front_stop_distance_m_ : front_stop_distance_m_;
      const double active_front_slow_distance = current_stage_ == 2 ?
          stage_2_front_slow_distance_m_ : front_slow_distance_m_;
      forward = std::clamp(command_.linear.x, -max_forward_mps_, max_forward_mps_);
      lateral = std::clamp(command_.linear.y, -max_lateral_mps_, max_lateral_mps_);
      yaw = std::clamp(command_.angular.z, -max_yaw_rps_, max_yaw_rps_);
      if (forward > 0.0 && front_clearance_m_ < active_front_slow_distance) {
        const double scale = std::clamp(
            (front_clearance_m_ - active_front_stop_distance) /
                (active_front_slow_distance - active_front_stop_distance),
            0.0, 1.0);
        forward *= scale;
      }
      forward = move_toward(output_forward_mps_, forward,
                            max_forward_accel_mps2_ * control_period_sec_);
      lateral = move_toward(output_lateral_mps_, lateral,
                            max_lateral_accel_mps2_ * control_period_sec_);
      yaw = move_toward(output_yaw_rps_, yaw, max_yaw_accel_rps2_ * control_period_sec_);
    }

    output_forward_mps_ = forward;
    output_lateral_mps_ = lateral;
    output_yaw_rps_ = yaw;
    message.vel_des = {static_cast<float>(forward), static_cast<float>(lateral),
                       static_cast<float>(yaw)};
    // A walking gait can lift its feet even when vel_des is exactly zero.  Do
    // not attach a non-zero step height to START, END, or an idle DATA frame;
    // the real robot otherwise steps in place and can drift while "stopped".
    const bool translating_or_turning = command_type == kServoCommand &&
        (std::abs(forward) > 1e-9 || std::abs(lateral) > 1e-9 || std::abs(yaw) > 1e-9);
    // Stage 1 uses the explicitly configured high-step profile. Missing or
    // invalid stage state fails back to the normal, lower step height.
    const double active_step_height =
        current_stage_ == 1 ? stage_1_step_height_m_ : step_height_m_;
    const float commanded_step_height = translating_or_turning ?
        static_cast<float>(active_step_height) : 0.0F;
    message.step_height = {commanded_step_height, commanded_step_height};
    return message;
  }

  void publish_stop() {
    // SERVO_END is a session transition, not an idle heartbeat.  Repeating it
    // without an active gait session makes the stock motion manager enter
    // BAN_TRANS.  End each active session exactly once, then stay silent.
    if (servo_session_active_ && !stop_sent_) {
      motion_pub_->publish(make_command(kServoStop));
      RCLCPP_WARN(get_logger(), "Safety gate ended the active servo session.");
    }
    stop_sent_ = true;
    servo_session_active_ = false;
  }

  void on_timer() {
    if (publish_wake_word_ && wake_word_publish_count_ < 5) {
      std_msgs::msg::String wake_word;
      wake_word.data = wake_word_;
      wake_word_pub_->publish(wake_word);
      ++wake_word_publish_count_;
      if (wake_word_publish_count_ == 5) {
        RCLCPP_INFO(get_logger(), "Requested wake word: %s.", wake_word_.c_str());
      }
    }
    if (!armed_) {
      RCLCPP_INFO_THROTTLE(
          get_logger(), *get_clock(), 5000,
          "SENSOR-ONLY camera=%d lidar=%d pose=%d; no motion output.",
          image_valid_ && recent(last_image_, sensor_timeout_sec_),
          lidar_valid_ && recent(last_lidar_, sensor_timeout_sec_),
          pose_valid_ && recent(last_pose_, sensor_timeout_sec_));
      return;
    }
    if (require_voice_start_ && !voice_enabled_) {
      publish_stop();
      RCLCPP_INFO_THROTTLE(
          get_logger(), *get_clock(), 2000,
          "Motion inhibited: waiting for wake word and exact voice start phrase.");
      return;
    }
    if (require_supervisor_run_allowed_ &&
        (!recent(last_supervisor_run_allowed_, supervisor_timeout_sec_) ||
         !supervisor_run_allowed_)) {
      publish_stop();
      RCLCPP_WARN_THROTTLE(
          get_logger(), *get_clock(), 2000,
          "Motion inhibited: supervisor run permission is false, missing, or stale.");
      return;
    }
    if (require_sensor_ready_ && !sensors_ready()) {
      publish_stop();
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000,
                           "Motion inhibited: camera=%d lidar=%d pose=%d (check topic mapping).",
                           image_valid_ && recent(last_image_, sensor_timeout_sec_),
                           lidar_valid_ && recent(last_lidar_, sensor_timeout_sec_),
                           pose_valid_ && recent(last_pose_, sensor_timeout_sec_));
      return;
    }
    if (require_estop_ready_ && !recent(last_estop_, estop_timeout_sec_)) {
      publish_stop();
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000,
                           "Motion inhibited: emergency-stop heartbeat missing or stale.");
      return;
    }
    if (emergency_stop_) {
      publish_stop();
      RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 1000,
                            "Motion inhibited: emergency stop asserted.");
      return;
    }
    if (tilt_rad_ > max_tilt_rad_) {
      publish_stop();
      RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 1000,
                            "Motion inhibited: body tilt %.3f rad exceeds %.3f rad.",
                            tilt_rad_, max_tilt_rad_);
      return;
    }
    if (!command_valid_ || !recent(last_command_, command_timeout_sec_)) {
      publish_stop();
      return;
    }
    const double active_front_stop_distance = current_stage_ == 2 ?
        stage_2_front_stop_distance_m_ : front_stop_distance_m_;
    if (command_.linear.x > 0.0 && front_clearance_m_ <= active_front_stop_distance) {
      publish_stop();
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 1000,
                           "Forward motion inhibited: clearance %.3f m <= %.3f m.",
                           front_clearance_m_, active_front_stop_distance);
      return;
    }
    const bool command_requests_motion =
        std::abs(command_.linear.x) > 1e-9 ||
        std::abs(command_.linear.y) > 1e-9 ||
        std::abs(command_.angular.z) > 1e-9;
    if (!servo_session_active_ && !command_requests_motion) {
      // Entering gait 303 can transfer weight or lift a foot even when both
      // velocity and step height are zero.  An idle command must therefore
      // remain in the ended standing mode instead of opening a gait session.
      publish_stop();
      return;
    }
    if (!servo_session_active_) {
      motion_pub_->publish(make_command(kServoStart));
      servo_session_active_ = true;
      stop_sent_ = false;
      RCLCPP_INFO(get_logger(), "Servo session started with a zero-velocity START frame.");
      return;
    }
    auto motion_command = make_command(kServoCommand);
    const bool output_still_moving = std::any_of(
        motion_command.vel_des.begin(), motion_command.vel_des.end(),
        [](float value) { return std::abs(value) > 1e-9F; });
    if (!command_requests_motion && !output_still_moving) {
      publish_stop();
      return;
    }
    motion_pub_->publish(motion_command);
    stop_sent_ = false;
  }

  bool enable_motion_{false};
  bool armed_{false};
  bool require_sensor_ready_{true};
  bool require_camera_ready_{false};
  bool require_lidar_ready_{true};
  bool require_pose_ready_{true};
  bool require_estop_ready_{true};
  bool require_voice_start_{false};
  bool require_supervisor_run_allowed_{true};
  bool publish_wake_word_{false};
  bool touch_pause_enabled_{true};
  bool audio_feedback_enabled_{true};
  bool manage_dialogue_{false};
  bool voice_enabled_{true};
  bool stop_sent_{false};
  bool servo_session_active_{false};
  bool emergency_stop_{false};
  bool supervisor_run_allowed_{false};
  bool image_valid_{false};
  bool lidar_valid_{false};
  bool pose_valid_{false};
  bool command_valid_{false};
  double sensor_timeout_sec_{1.0};
  double estop_timeout_sec_{0.50};
  double command_timeout_sec_{0.30};
  double supervisor_timeout_sec_{0.50};
  double max_forward_mps_{0.25};
  double max_lateral_mps_{0.10};
  double max_yaw_rps_{0.40};
  double max_forward_accel_mps2_{0.40};
  double max_lateral_accel_mps2_{0.30};
  double max_yaw_accel_rps2_{0.80};
  double step_height_m_{0.05};
  double stage_1_step_height_m_{0.15};
  int32_t current_stage_{0};
  double front_stop_distance_m_{0.35};
  double front_slow_distance_m_{0.70};
  double stage_2_front_stop_distance_m_{0.18};
  double stage_2_front_slow_distance_m_{0.40};
  double front_half_angle_rad_{0.45};
  double front_lidar_self_echo_max_m_{0.32};
  double front_lidar_cluster_range_jump_m_{0.12};
  int front_lidar_cluster_min_samples_{4};
  int front_confirmation_frames_{3};
  double front_ultrasonic_extreme_stop_m_{0.20};
  double max_tilt_rad_{0.60};
  double stop_heartbeat_sec_{0.20};
  double touch_lockout_sec_{1.5};
  double control_period_sec_{0.10};
  double front_clearance_m_{std::numeric_limits<double>::infinity()};
  double tilt_rad_{0.0};
  double output_forward_mps_{0.0};
  double output_lateral_mps_{0.0};
  double output_yaw_rps_{0.0};
  std::string wake_word_{"铁蛋铁蛋"};
  std::string start_phrase_{"开始比赛"};
  std::string continue_phrase_{"继续比赛"};
  std::string pause_phrase_{"暂停比赛"};
  std::string stop_phrase_{"停止比赛"};
  int touch_double_tap_state_{3};
  int audio_feedback_play_id_{9000};
  int wake_word_publish_count_{0};
  rclcpp::Time last_image_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_lidar_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_pose_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_estop_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_command_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_supervisor_run_allowed_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_touch_pause_{0, 0, RCL_ROS_TIME};
  geometry_msgs::msg::Twist command_{};
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_sub_;
  rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr lidar_sub_;
  rclcpp::Subscription<sensor_msgs::msg::Range>::SharedPtr ultrasonic_sub_;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr pose_sub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odometry_sub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr estop_sub_;
  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr command_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr voice_command_sub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr supervisor_run_allowed_sub_;
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr current_stage_sub_;
  rclcpp::Subscription<protocol::msg::TouchStatus>::SharedPtr touch_sub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr wake_event_sub_;
  rclcpp::Publisher<protocol::msg::MotionServoCmd>::SharedPtr motion_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr race_enabled_pub_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr front_clearance_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr wake_word_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr operator_event_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr continue_dialog_pub_;
  rclcpp::Client<protocol::srv::AudioTextPlay>::SharedPtr audio_feedback_client_;
  rclcpp::TimerBase::SharedPtr timer_;
  std::unique_ptr<mi_dog_real::FrontClearanceFilter> front_clearance_filter_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MiDogRealNode>());
  rclcpp::shutdown();
  return 0;
}
