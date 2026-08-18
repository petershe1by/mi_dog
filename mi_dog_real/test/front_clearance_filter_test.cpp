#include <cmath>
#include <iostream>
#include <limits>
#include <vector>

#include "mi_dog_real/front_clearance_filter.hpp"

namespace {
constexpr double kAngleMin = -0.50;
constexpr double kIncrement = 0.01;

std::vector<float> empty_floor_scan() {
  std::vector<float> scan(101, 2.0F);
  // Reproduce the persistent close body/floor returns observed on the robot.
  for (std::size_t i = 28; i <= 72; ++i) scan[i] = 0.10F + 0.004F * (i % 30);
  return scan;
}

void require(bool condition, const char *name) {
  std::cout << name << '=' << (condition ? "PASS" : "FAIL") << '\n';
  if (!condition) std::exit(1);
}
}  // namespace

int main() {
  using mi_dog_real::FrontClearanceFilter;
  FrontClearanceFilter filter({});
  auto scan = empty_floor_scan();
  for (int i = 0; i < 5; ++i) {
    filter.update_lidar(scan, kAngleMin, kIncrement, 0.01, 30.0);
    filter.update_ultrasonic(0.62, 0.10, 1.0);
  }
  require(filter.clearance() > 0.35, "empty_floor_not_stopped");

  // One frame of an ordinary obstacle is not enough to change permission.
  for (std::size_t i = 45; i <= 55; ++i) scan[i] = 0.34F;
  filter.update_lidar(scan, kAngleMin, kIncrement, 0.01, 30.0);
  require(filter.clearance() > 0.35, "single_lidar_frame_rejected");
  filter.update_lidar(scan, kAngleMin, kIncrement, 0.01, 30.0);
  filter.update_lidar(scan, kAngleMin, kIncrement, 0.01, 30.0);
  require(filter.clearance() <= 0.35, "confirmed_lidar_cluster_stops");

  // Clearing also needs three frames, preventing one-frame permission flicker.
  scan = empty_floor_scan();
  filter.update_lidar(scan, kAngleMin, kIncrement, 0.01, 30.0);
  require(filter.clearance() <= 0.35, "single_clear_frame_keeps_stop");
  filter.update_lidar(scan, kAngleMin, kIncrement, 0.01, 30.0);
  filter.update_lidar(scan, kAngleMin, kIncrement, 0.01, 30.0);
  require(filter.clearance() > 0.35, "confirmed_clear_releases_lidar");

  // A narrow one- or two-sample speckle never forms an obstacle cluster.
  scan[50] = 0.34F;
  scan[51] = 0.34F;
  for (int i = 0; i < 5; ++i) filter.update_lidar(scan, kAngleMin, kIncrement, 0.01, 30.0);
  require(filter.clearance() > 0.35, "narrow_lidar_speckle_rejected");

  // Ultrasonic confirmation covers obstacles hidden inside the lidar self mask.
  filter.update_ultrasonic(0.29, 0.10, 1.0);
  filter.update_ultrasonic(0.29, 0.10, 1.0);
  require(filter.clearance() > 0.35, "two_ultrasonic_frames_not_enough");
  filter.update_ultrasonic(0.29, 0.10, 1.0);
  require(filter.clearance() <= 0.35, "confirmed_ultrasonic_stops");

  FrontClearanceFilter extreme({});
  extreme.update_ultrasonic(0.15, 0.10, 1.0);
  require(extreme.clearance() <= 0.20, "extreme_ultrasonic_stops_immediately");
  return 0;
}
