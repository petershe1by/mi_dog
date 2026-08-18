#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <vector>

namespace mi_dog_real {

struct FrontClearanceConfig {
  double half_angle_rad{0.45};
  double stop_distance_m{0.35};
  double slow_distance_m{0.70};
  double lidar_self_echo_max_m{0.32};
  double lidar_cluster_range_jump_m{0.12};
  std::size_t lidar_cluster_min_samples{4};
  std::size_t confirmation_frames{3};
  double ultrasonic_extreme_stop_m{0.20};
};

// The CyberDog 2 planar scan contains persistent ground/body returns close to
// angle zero.  Treating the minimum sample as an obstacle makes an empty floor
// permanently blocked.  This filter requires a spatially coherent cluster
// outside the measured self-return envelope and temporal confirmation.  The
// forward ultrasonic sensor independently preserves protection inside that
// envelope; an extreme ultrasonic return is accepted immediately.
class FrontClearanceFilter {
 public:
  explicit FrontClearanceFilter(FrontClearanceConfig config) : config_(config) {}

  double update_lidar(const std::vector<float> &ranges, double angle_min,
                      double angle_increment, double range_min, double range_max) {
    double candidate = infinity();
    std::size_t cluster_size = 0;
    double cluster_min = infinity();
    double previous_range = infinity();

    const auto finish_cluster = [&]() {
      if (cluster_size >= config_.lidar_cluster_min_samples) {
        candidate = std::min(candidate, cluster_min);
      }
      cluster_size = 0;
      cluster_min = infinity();
      previous_range = infinity();
    };

    for (std::size_t index = 0; index < ranges.size(); ++index) {
      const double angle = angle_min + static_cast<double>(index) * angle_increment;
      const double wrapped = std::atan2(std::sin(angle), std::cos(angle));
      if (std::abs(wrapped) > config_.half_angle_rad) {
        finish_cluster();
        continue;
      }
      const double range = ranges[index];
      const bool usable = std::isfinite(range) && range >= range_min && range <= range_max &&
                          range > config_.lidar_self_echo_max_m &&
                          range <= config_.slow_distance_m;
      if (!usable) {
        finish_cluster();
        continue;
      }
      if (cluster_size > 0 &&
          std::abs(range - previous_range) > config_.lidar_cluster_range_jump_m) {
        finish_cluster();
      }
      ++cluster_size;
      cluster_min = std::min(cluster_min, range);
      previous_range = range;
    }
    finish_cluster();
    update_confirmed(candidate, lidar_obstacle_frames_, lidar_clear_frames_,
                     lidar_candidate_is_stop_, lidar_clearance_m_);
    return lidar_clearance_m_;
  }

  double update_ultrasonic(double range, double range_min, double range_max) {
    const bool valid = std::isfinite(range) && range >= range_min && range <= range_max;
    if (!valid) return ultrasonic_clearance_m_;
    if (range <= config_.ultrasonic_extreme_stop_m) {
      ultrasonic_obstacle_frames_ = config_.confirmation_frames;
      ultrasonic_clear_frames_ = 0;
      ultrasonic_clearance_m_ = range;
    } else {
      const double candidate = range <= config_.slow_distance_m ? range : infinity();
      update_confirmed(candidate, ultrasonic_obstacle_frames_, ultrasonic_clear_frames_,
                       ultrasonic_candidate_is_stop_, ultrasonic_clearance_m_);
    }
    return ultrasonic_clearance_m_;
  }

  double clearance() const {
    return std::min(lidar_clearance_m_, ultrasonic_clearance_m_);
  }

  double lidar_clearance() const { return lidar_clearance_m_; }
  double ultrasonic_clearance() const { return ultrasonic_clearance_m_; }

 private:
  static double infinity() { return std::numeric_limits<double>::infinity(); }

  void update_confirmed(double candidate, std::size_t &obstacle_frames,
                        std::size_t &clear_frames, bool &candidate_is_stop,
                        double &confirmed) {
    if (std::isfinite(candidate)) {
      const bool new_candidate_is_stop = candidate <= config_.stop_distance_m;
      if (obstacle_frames > 0 && candidate_is_stop != new_candidate_is_stop) {
        obstacle_frames = 0;
      }
      candidate_is_stop = new_candidate_is_stop;
      clear_frames = 0;
      obstacle_frames = std::min(obstacle_frames + 1, config_.confirmation_frames);
      if (obstacle_frames >= config_.confirmation_frames) confirmed = candidate;
      return;
    }
    obstacle_frames = 0;
    clear_frames = std::min(clear_frames + 1, config_.confirmation_frames);
    if (clear_frames >= config_.confirmation_frames) confirmed = infinity();
  }

  FrontClearanceConfig config_;
  std::size_t lidar_obstacle_frames_{0};
  std::size_t lidar_clear_frames_{0};
  std::size_t ultrasonic_obstacle_frames_{0};
  std::size_t ultrasonic_clear_frames_{0};
  bool lidar_candidate_is_stop_{false};
  bool ultrasonic_candidate_is_stop_{false};
  double lidar_clearance_m_{infinity()};
  double ultrasonic_clearance_m_{infinity()};
};

}  // namespace mi_dog_real
