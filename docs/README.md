> 接手硬件与上位机开发：先读 [AI-HANDOFF.md](AI-HANDOFF.md)，再读本目录历史资料。

# 文档目录

这是 SurgeryBox Project 的文档索引。根目录 `README.md` 面向快速上手，本目录下的专题文档面向开发、调试和维护。

## 阅读路线

| 场景 | 建议阅读 |
| --- | --- |
| 第一次接手项目 | [project-overview.md](project-overview.md) |
| 只想把项目跑起来 | [setup-and-run.md](setup-and-run.md) |
| 调 ESP8266、编码器、舵机、电机 | [hardware-and-protocol.md](hardware-and-protocol.md) |
| 规划最终有线训练站、人体模型硬件、摄像头和上位机 | [mobile-hardware-camera-architecture.md](mobile-hardware-camera-architecture.md) |
| 改训练 UI、Quiz 或流程 | [simulator-training-flow.md](simulator-training-flow.md) |
| 处理数据、AI、配置、安全问题 | [data-ai-and-maintenance.md](data-ai-and-maintenance.md) |

## 文档清单

| 文档 | 维护重点 |
| --- | --- |
| [project-overview.md](project-overview.md) | 项目目标、模块边界、目录结构、当前状态 |
| [setup-and-run.md](setup-and-run.md) | 安装依赖、运行桌面端、编译上传固件、测试通信 |
| [hardware-and-protocol.md](hardware-and-protocol.md) | 引脚、编码器换算、舵机角度、UDP 指令、事件状态机 |
| [mobile-hardware-camera-architecture.md](mobile-hardware-camera-architecture.md) | 有线训练站、人体模型内部硬件、外部摄像头、上位机低延迟融合架构 |
| [simulator-training-flow.md](simulator-training-flow.md) | 主界面、训练入口、No Simulator / Simulator 流程、Quiz 和记录 |
| [data-ai-and-maintenance.md](data-ai-and-maintenance.md) | 本地数据、AI Mentor、密钥风险、`.gitignore` 和维护建议 |

## 原始教学资料

这些文件仍保留在应用资源目录中，由程序直接读取：

| 文件 | 说明 |
| --- | --- |
| [../simulator/assets/reading.md](../simulator/assets/reading.md) | 硬膜外导管拔除学习材料 |
| [../simulator/assets/epidural_quiz_questions.json](../simulator/assets/epidural_quiz_questions.json) | Q1-Q5 题库 |

## 文档维护规则

- 修改 MCU UDP 指令、端口、事件名称时，同步更新 [hardware-and-protocol.md](hardware-and-protocol.md)。
- 修改最终产品拓扑、硬件有线接口、摄像头接口、上位机职责或软件端职责时，同步更新 [mobile-hardware-camera-architecture.md](mobile-hardware-camera-architecture.md)。
- 修改桌面端训练阶段、Quiz 触发、记录格式时，同步更新 [simulator-training-flow.md](simulator-training-flow.md)。
- 修改依赖、启动方式、模型下载方式时，同步更新 [setup-and-run.md](setup-and-run.md)。
- 修改 AI provider、密钥读取方式、数据目录或发布策略时，同步更新 [data-ai-and-maintenance.md](data-ai-and-maintenance.md)。
- 教学内容和题库变更后，同步检查 `reading.md`、`epidural_quiz_questions.json` 和 AI Mentor 预加载上下文是否一致。

## 当前文档状态

本目录是对现有代码、脚本注释和教学材料的整理版，不代表所有代码问题已经修复。文档中明确标出的风险项，例如 API Key 暴露、`TestFlow` 过期、MCU `SEQ` 与上位机 `pull_config` 双事件来源，仍需要后续单独处理。
