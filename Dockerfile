FROM cyberdog_sim:v2026
COPY overlay/gazebo.xacro /home/cyberdog_sim/src/cyberdog_simulator/cyberdog_robot/cyberdog_description/xacro/gazebo.xacro
RUN sed -i 's@</world>@<plugin name="gazebo_ros_state" filename="libgazebo_ros_state.so"><update_rate>20.0</update_rate></plugin></world>@' /home/cyberdog_sim/src/cyberdog_simulator/cyberdog_gazebo/world/race.world
RUN sed -i 's/? 0.04 : 0.06/? 0.22 : 0.06/' /home/cyberdog_sim/src/cyberdog_locomotion/common/src/command_interface/command_interface.cpp
RUN sed -i 's/if ( current_state_->check_robot_lifted_ ) {/if ( false \&\& current_state_->check_robot_lifted_ ) {/' /home/cyberdog_sim/src/cyberdog_locomotion/control/src/fsm_states/control_fsm.cpp
RUN sed -i '526s@.*@        cmd_cur_.rpy_des[ 1 ]     = 0;@;527s@.*@        cmd_cur_.pos_des[ 2 ] = gamepad_cmd_.rightStickAnalog[ 1 ] > 0.5 ? 0.14 : ( ( robotType == RobotType::CYBERDOG2 ) ? 0.24 : 0.32 );@' /home/cyberdog_sim/src/cyberdog_locomotion/common/src/command_interface/command_interface.cpp
RUN sed -i 's/pos_cmd_rel_min_ << 0.0, 0.0, 0.23;/pos_cmd_rel_min_ << 0.0, 0.0, 0.13;/' /home/cyberdog_sim/src/cyberdog_locomotion/control/src/convex_mpc/convex_mpc_loco_gaits.cpp && sed -i 's/pos_cmd_min_ << 0.0, 0.0, 0.23;/pos_cmd_min_ << 0.0, 0.0, 0.13;/' /home/cyberdog_sim/src/cyberdog_locomotion/control/src/convex_mpc/convex_mpc_loco_gaits.cpp && sed -i '2307s@user_params_.*+  // user params and delta based on x vel@ctrl_cmd_->pos_des[ 2 ] +  // user params and delta based on x vel@;2318s@user_params_.*+  // user params and delta based on x vel@ctrl_cmd_->pos_des[ 2 ] +  // user params and delta based on x vel@;2321s@user_params_.*cos( slope_ )@ctrl_cmd_->pos_des[ 2 ] * cos( slope_ )@' /home/cyberdog_sim/src/cyberdog_locomotion/control/src/convex_mpc/convex_mpc_loco_gaits.cpp
RUN bash -lc 'cd /home/cyberdog_sim && source /opt/ros/galactic/setup.bash && source install/setup.bash && colcon build --merge-install --symlink-install --packages-select cyberdog_locomotion'
COPY cyberdog_autonomy /home/cyberdog_sim/src/cyberdog_autonomy
COPY audio /opt/mi_dog/audio
COPY scripts/start_sim.sh /opt/mi_dog/start_sim.sh
RUN chmod +x /opt/mi_dog/start_sim.sh && bash -lc 'cd /home/cyberdog_sim && source /opt/ros/galactic/setup.bash && source install/setup.bash && colcon build --merge-install --symlink-install --packages-select cyberdog_autonomy'
WORKDIR /home/cyberdog_sim
CMD ["/opt/mi_dog/start_sim.sh"]
