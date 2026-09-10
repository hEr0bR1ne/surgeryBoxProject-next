#ifndef CONFIG_H
#define CONFIG_H

// Upper-computer handoff: unresolved driver direction fault. No serial command
// may enable motor output; restoration requires an intentional firmware change.
constexpr bool MOTOR_OUTPUT_ENABLED = false;

// 预设10组数组，每组四个距离值（单位可自行定义，比如米）
extern float distanceArrays[10][4];

// 当前活动数组（被Start指令随机选中）
extern float currentArray[4];

// 标志位
extern bool sequenceRunning;
extern bool eventTriggered[4];

#endif
