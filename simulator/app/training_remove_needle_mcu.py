"""
Remove Needle Training Module
拔针训练：包括初始指导、按住针头、撕医用贴三个阶段
"""

import cv2
import numpy as np
import os
import time
import socket
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QRect, QPoint, QUrl
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QPushButton
from PySide6.QtGui import QFont, QPixmap, QImage, QPainter, QColor, QBrush
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

try:
    from app.hardware.serial_connector import SerialHardwareListener
except Exception as exc:
    SerialHardwareListener = None
    SERIAL_IMPORT_ERROR = exc
else:
    SERIAL_IMPORT_ERROR = None


class ExternalUDPListener(QThread):
    message_received = Signal(str)

    def __init__(self, board_ip: str, board_port: int, local_port: int):
        super().__init__()
        self.board_ip = board_ip
        self.board_port = board_port
        self.local_port = local_port
        self.stop_flag = False
        self.sock = None
        self.ready = False
        self.last_error = ""

    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(("", self.local_port))
            self.sock.settimeout(1.0)
            self.ready = True
            # 发送握手，确保MCU记录本机端口
            try:
                self.sock.sendto(b"HELLO_PC", (self.board_ip, self.board_port))
            except Exception:
                pass
            while not self.stop_flag:
                try:
                    data, _ = self.sock.recvfrom(1024)
                    if not data:
                        continue
                    try:
                        text = data.decode(errors="replace").strip()
                    except Exception:
                        text = ""
                    if text:
                        self.message_received.emit(text)
                except socket.timeout:
                    continue
                except Exception:
                    if self.stop_flag:
                        break
        except Exception as e:
            self.last_error = str(e)
        finally:
            self.ready = False
            try:
                self.sock.close()
            except Exception:
                pass

    def send_message(self, msg: str):
        """复用同一个端口发送，确保MCU回包落在监听端口"""
        try:
            if not self.ready:
                return False
            if self.sock:
                self.sock.sendto(msg.encode(), (self.board_ip, self.board_port))
                return True
        except Exception as e:
            print(f"[External->MCU] Send error (listener socket): {e}")
        return False

from app.camera_manager import (
    CameraThread,
    get_configured_camera_index,
    get_required_gemini_camera_index,
    required_gemini_camera_status,
)
from app.hand_gesture_recognizer import HandGestureRecognizer
from app.imu_posture_reader import ImuPostureThread
from app.i18n import tr
from app.training_records import get_training_record_manager
from app.ui.blood_light_training import BloodLightTrainingMixin


class SuccessDisplay:
    """
    可复用的成功显示模块
    负责显示成功文字（渐变效果）+ 播放成功音频
    """
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.success_label = None
        self.success_timer = None
        self.pass_label = None  # 存储pass标签，防止被垃圾回收
        self.pass_timer = None  # 存储pass计时器
        self.media_player = None
        self.audio_output = None
        self._setup_ui()
    
    def _setup_ui(self):
        """创建成功标签"""
        self.success_label = QLabel(self.parent)
        self.success_label.setText("✓ Success")
        self.success_label.setStyleSheet("""
            QLabel {
                color: #00AA00;
                background: rgba(0, 170, 0, 80);
                padding: 33px 67px;
                border-radius: 27px;
                border: 5px solid #00AA00;
                text-align: center;
                font-family: 'Segoe Print';
                font-size: 67px;
                font-weight: bold;
            }
        """)
        self.success_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.success_label.hide()
        
        # 初始化音频播放器
        try:
            self.media_player = QMediaPlayer(self.parent)
            self.audio_output = QAudioOutput(self.parent)
            self.media_player.setAudioOutput(self.audio_output)
        except Exception:
            self.media_player = None
    
    def show_success(self, audio_path=None, duration_ms=1000):
        """
        显示成功消息，带有渐变效果
        
        Args:
            audio_path: 成功音频文件路径（可选）
            duration_ms: 显示持续时间（毫秒）
        """
        try:
            # 播放成功音频
            if audio_path and self.media_player:
                try:
                    self.media_player.setSource(QUrl.fromLocalFile(audio_path))
                    self.media_player.play()
                except Exception:
                    pass
            
            # 显示成功标签（在屏幕中央，2/3大小）
            self.success_label.setGeometry(
                self.parent.width() // 2 - 333,
                self.parent.height() // 2 - 167,
                667,
                333
            )
            self.success_label.show()
            
            # 定时隐藏
            self.success_timer = QTimer(self.parent)
            self.success_timer.timeout.connect(lambda: self._fade_out_success(duration_ms))
            self.success_timer.start(duration_ms)
        except RuntimeError:
            # Parent已被删除
            return
    
    def _fade_out_success(self, _):
        """淡出成功标签"""
        try:
            if self.success_timer:
                self.success_timer.stop()
            if self.success_label:
                self.success_label.hide()
        except RuntimeError:
            # Widget已被删除
            pass
    
    def show_pass(self, duration_ms=3000, elapsed_time=0.0):
        """
        显示Pass统计页面，显示training用时
        
        Args:
            duration_ms: 显示持续时间（毫秒，默认3秒）
            elapsed_time: 训练耗时（秒）
        """
        # 检查parent是否仍然有效
        try:
            if not self.parent or not self.parent.isVisible():
                return
        except RuntimeError:
            # Parent已被删除
            return
        
        try:
            # 首先隐藏success标签，避免背景遮挡pass文字
            if self.success_label:
                self.success_label.hide()
            if self.success_timer:
                self.success_timer.stop()
            
            # 清理旧的pass widget
            if hasattr(self, 'pass_widget') and self.pass_widget:
                try:
                    self.pass_widget.hide()
                    self.pass_widget.deleteLater()
                except Exception:
                    pass
            if self.pass_timer:
                try:
                    self.pass_timer.stop()
                except Exception:
                    pass

            # 创建一个新的临时widget显示Pass和统计信息，并附带 Back 按钮
            self.pass_widget = QWidget(self.parent)
            layout = QVBoxLayout(self.pass_widget)
            layout.setContentsMargins(24, 24, 24, 24)

            pass_label = QLabel(f"✓ PASS\n\nTime: {elapsed_time:.1f}s")
            pass_label.setAlignment(Qt.AlignCenter)
            pass_label.setStyleSheet("""
                QLabel {
                    color: #00AA00;
                    background-color: rgba(0, 170, 0, 100);
                    padding: 18px;
                    border-radius: 18px;
                    border: 3px solid #00AA00;
                    font-family: 'Segoe Print';
                    font-size: 36px;
                    font-weight: bold;
                }
            """)
            layout.addWidget(pass_label)

            back_btn = QPushButton("Back")
            back_btn.setFixedWidth(140)
            back_btn.setStyleSheet("""
                QPushButton { background: #4DA3FF; color: white; border-radius: 8px; padding: 8px; }
                QPushButton:hover { background: #2E7FD4; }
            """)
            back_btn.clicked.connect(self._on_pass_back_clicked)
            layout.addStretch()
            layout.addWidget(back_btn, 0, Qt.AlignHCenter)

            # 设置位置和大小（与之前的pass_label一致）
            self.pass_widget.setGeometry(
                self.parent.width() // 2 - 333,
                self.parent.height() // 2 - 167,
                667,
                333
            )
            self.pass_widget.show()

            # 定时隐藏并删除widget
            self.pass_timer = QTimer(self.parent)
            self.pass_timer.setSingleShot(True)
            self.pass_timer.timeout.connect(lambda: self._hide_and_delete_pass_widget())
            self.pass_timer.start(duration_ms)
        except RuntimeError:
            # Parent或其他组件已被删除
            return

    def _hide_and_delete_pass_widget(self):
        try:
            if hasattr(self, 'pass_widget') and self.pass_widget:
                try:
                    self.pass_widget.hide()
                    self.pass_widget.deleteLater()
                except Exception:
                    pass
                self.pass_widget = None
        except Exception:
            pass

    def _on_pass_back_clicked(self):
        # 找到拥有 _complete_training 的祖先并调用
        try:
            # 隐藏并删除本widget，先清理UI
            self._hide_and_delete_pass_widget()
            owner = self.parent
            if hasattr(owner, 'parent') and owner.parent():
                owner = owner.parent()
            # cancel scheduled completion timer if present
            try:
                if hasattr(owner, '_complete_timer') and owner._complete_timer:
                    owner._complete_timer.stop()
                    owner._complete_timer = None
            except Exception:
                pass
            if hasattr(owner, '_complete_training'):
                owner._complete_training()
        except Exception:
            pass


class TextDisplayWidget(QFrame):
    """
    文字显示widget，支持渐变进入/退出效果
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        
        # 文字标签
        self.text_label = QLabel()
        self.text_label.setFont(QFont("Segoe Print", 20, QFont.Bold))
        self.text_label.setAlignment(Qt.AlignCenter | Qt.AlignTop)
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("""
            QLabel {
                color: #003366;
                background: rgba(255, 255, 255, 200);
                padding: 15px;
                border-radius: 10px;
                margin: 10px;
            }
        """)
        
        self.layout_main.addWidget(self.text_label)
        self.layout_main.addStretch()
        
        # 音频播放器
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        
        # 渐变效果计时器
        self.fade_timer = None
        self.fade_alpha = 0
        self.is_fading_in = False
        self.is_fading_out = False
    
    def set_text(self, text: str):
        """设置文字内容"""
        self.text_label.setText(text)
    
    def fade_in(self, duration_ms=1000):
        """文字渐变进入"""
        self.fade_alpha = 0
        self.is_fading_in = True
        self.is_fading_out = False
        
        self.text_label.show()
        
        steps = max(1, duration_ms // 50)
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(lambda: self._update_fade_in(steps))
        self.fade_timer.start(50)
    
    def _update_fade_in(self, steps):
        """更新渐变进入"""
        self.fade_alpha += 1.0 / steps
        if self.fade_alpha >= 1.0:
            self.fade_alpha = 1.0
            if self.fade_timer:
                self.fade_timer.stop()
            self.is_fading_in = False
        
        alpha = int(200 * self.fade_alpha)
        self.text_label.setStyleSheet(f"""
            QLabel {{
                color: #003366;
                background: rgba(255, 255, 255, {alpha});
                padding: 15px;
                border-radius: 10px;
                margin: 10px;
            }}
        """)
    
    def fade_out(self, duration_ms=1000):
        """文字渐变退出"""
        self.fade_alpha = 1.0
        self.is_fading_in = False
        self.is_fading_out = True
        
        steps = max(1, duration_ms // 50)
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(lambda: self._update_fade_out(steps))
        self.fade_timer.start(50)
    
    def _update_fade_out(self, steps):
        """更新渐变退出"""
        if not self.fade_timer:
            return
            
        self.fade_alpha -= 1.0 / steps
        if self.fade_alpha <= 0.0:
            self.fade_alpha = 0.0
            if self.fade_timer:
                self.fade_timer.stop()
            self.is_fading_out = False
            self.text_label.hide()
            return
        
        alpha = int(200 * self.fade_alpha)
        self.text_label.setStyleSheet(f"""
            QLabel {{
                color: #003366;
                background: rgba(255, 255, 255, {alpha});
                padding: 15px;
                border-radius: 10px;
                margin: 10px;
            }}
        """)
    
    def play_audio(self, audio_path: str):
        """播放音频文件"""
        try:
            self.media_player.stop()  # 确保重置播放器状态
            self.media_player.setSource(QUrl.fromLocalFile(audio_path))
            self.media_player.play()
            print(f"[TextDisplay] Playing audio: {audio_path}")
        except Exception as e:
            print(f"[TextDisplay] Error playing audio: {e}")


class RemoveNeedleTraining(BloodLightTrainingMixin, QWidget):
    """
    拔针训练模块
    分为三个阶段：1.初始指导 2.按住针头 3.撕医用贴
    第四阶段：拔针管（有两种模式：有硬件/无硬件）
    """
    
    # 信号
    training_completed = Signal()
    quiz_triggered = Signal(str)  # 触发Quiz，参数为题目ID (Q3, Q4, Q5)
    
    def __init__(self, parent=None, training_mode="remove_needle_no_simulator"):
        super().__init__(parent)
        print(f"[RemoveNeedleTraining] __init__ called with parent={parent}, mode={training_mode}")
        self.setObjectName("RemoveNeedleTraining")
        self.training_mode = training_mode  # "remove_needle_simulator" or "remove_needle_no_simulator"
        # 临时关闭摄像头/手势识别，便于仅依靠外设测试流程
        self.disable_camera = True
        # 外设UDP输入配置（MCU为热点时默认板载IP 192.168.4.1:4210）
        self.board_ip = "192.168.4.1"
        self.board_port = 4210
        self.local_udp_port = 4211  # PC监听端口
        self.external_thread = None
        self.hardware_transport = os.getenv("SURGERYBOX_HARDWARE_TRANSPORT", "serial").strip().lower()
        if self.hardware_transport not in ("serial", "udp"):
            self.hardware_transport = "serial"
        self.serial_port = os.getenv("SURGERYBOX_SERIAL_PORT", "COM4").strip() or "COM4"
        try:
            self.serial_baudrate = int(os.getenv("SURGERYBOX_SERIAL_BAUDRATE", "115200"))
        except ValueError:
            self.serial_baudrate = 115200
        self.serial_thread = None
        self.auto_rewind_after_training = os.getenv("SURGERYBOX_AUTO_REWIND", "0").strip().lower() not in ("0", "false", "no")
        self.external_event_flags = []
        # 速度显示相关（MCU模式）
        self.speed_display_end = 0.0
        self.last_distance_sample_cm = 0.0
        self.last_distance_sample_time = 0.0
        self.current_speed_cmps = 0.0
        self.min_phase4_duration = 10.0  # 最短停留时间，避免过快完成
        self.external_speed_cmps = 0.0
        self.external_pos_cm = 0.0
        self.seq_info = ""
        self.last_event_msg = ""
        self.info_overlay = None
        self.external_speed_cmps = 0.0
        # IMU posture sensor. Defaults match the sensor tested on COM3/115200.
        self.imu_thread = None
        self.imu_port = os.environ.get("IMU_PORT", "COM3")
        self.imu_baud = int(os.environ.get("IMU_BAUD", "115200"))
        self.imu_axis = os.environ.get("IMU_AXIS", "roll").lower()
        self.posture_status = "WAITING"
        self.posture_roll = 0.0
        self.posture_pitch = 0.0
        self.posture_yaw = 0.0
        self.posture_angle = 0.0
        self.posture_overlay = None
        self.posture_required_hold_seconds = 3.0
        self.posture_ok_since = None
        self.posture_gate_passed = False
        self.posture_blocked = True
        self.posture_pause_started_at = None
        self.pending_training_start = False
        self.training_started_after_posture = False
        self.paused_for_posture = False
        self.paused_phase_timer_remaining_ms = None
        self.paused_wipe_blood_remaining = None
        self.paused_pinch_elapsed = None
        
        # 初始化组件
        print(f"[RemoveNeedleTraining] Setting up UI")
        self._setup_ui()
        print(f"[RemoveNeedleTraining] Setting up camera")
        self._setup_camera()
        print(f"[RemoveNeedleTraining] Setting up hand detector")
        self._setup_hand_detector()
        
        # 状态管理
        self.current_phase = 0
        self.phase_timer = None
        self.pinch_start_time = None
        self.last_pinch_time = None  # Track last detected pinch for loss tolerance
        self.finger_left_time = None
        self.phase3_animation_start_time = None  # Phase 3 动画计时器
        self.wipe_blood_start_time = None  # 血迹擦拭计时器
        self.wipe_blood_duration = 5.0  # 血迹擦拭持续时间
        self.frame_count = 0  # Frame counter for skip detection
        self.last_hand_data = []  # Cache last hand data to avoid flickering
        
        # Phase 1 PNG图像显示标志
        self.show_phase1_icon = False
        
        # Phase 4 拔针状态
        self.needle_x = None  # 线条X位置（屏幕中央，运行时初始化）
        self.needle_head_y = None  # 针头位置Y（注射点，运行时初始化为80）
        self.needle_full_length = 240  # 线条的完整长度（像素），对应20cm（原300改为240，方便完全拉出）
        self.needle_full_length_cm = 20  # 针线的实际长度（厘米）
        self.pinching = False  # 是否正在捏着
        self.pinch_history = []  # 历史位置用于速度计算
        self.last_pinch_y = None  # 上一帧的pinch位置
        self.needle_pulled_distance = 0  # 当前拉出的距离（像素）
        self.needle_pulled_distance_cm = 0  # 当前拉出的距离（厘米）
        self.max_pulled_distance = 0  # 最大拉出距离（像素，不会往回走）
        self.max_pulled_distance_cm = 0  # 最大拉出距离（厘米）
        self.pull_start_y = None  # 第一次捏住时的Y位置
        self.pull_speed_warning_time = None  # 速度过快提示的时间
        self.quiz_paused = False  # 标志：是否因为quiz而暂停拔针
        self.phase4_events_completed = 0  # Phase 4中完成的事件数（0-4）
        self.hand_pinching_near_needle = False  # 手是否正在黄点附近捏着（用于保持绿色状态）
        self.training_start_time = None  # Phase 4开始时间（用于计算训练耗时）
        self._training_complete_called = False
        self._complete_timer = None
        self._phase4_complete_called = False
        
        # 训练数据收集（用于保存训练记录）
        self.pull_config = None  # 4个事件的触发位置配置
        self.events_triggered = {}  # 记录每个事件何时被触发 {"Q3": time, "Q4": time, ...}
        # 记录每次触发的quiz结果（list of dicts），用于计算最终准确率
        # e.g. [{ 'question_id': 'Q3', 'trigger_time': 1.23, 'correct': True }, ...]
        self.events_results = []
        self.max_pull_distance_achieved = 0  # 最大拉出距离（最终记录）
        self.current_user = None  # 用户名（由主窗口设置）
        
        # 音频路径
        self.audio_guide_1 = "assets/training_remove_needle_guide1.mp3"
        self.audio_guide_2 = "assets/training_remove_needle_guide2.mp3"
        self.audio_guide_3 = "assets/training_remove_needle_guide3.mp3"
        self.audio_success = "assets/success.mp3"
        
        # 初始化媒体播放器（用于播放pain.mp3）
        try:
            self.media_player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.media_player.setAudioOutput(self.audio_output)
        except Exception as e:
            print(f"[RemoveNeedleTraining] Error initializing media player: {e}")
            self.media_player = None
            self.audio_output = None
        
        print(f"[RemoveNeedleTraining] Starting IMU posture listener")
        self._start_imu_posture_listener()
        print(f"[RemoveNeedleTraining] Initialization complete")
    
    def _setup_ui(self):
        """设置UI界面"""
        print(f"[RemoveNeedleTraining._setup_ui] Starting")
        self.setStyleSheet("background: black;")
        self.setContentsMargins(0, 0, 0, 0)
        print(f"[RemoveNeedleTraining._setup_ui] Widget size: {self.width()} x {self.height()}")
        
        # 直接使用QLabel作为摄像头画布，不用layout
        print(f"[RemoveNeedleTraining._setup_ui] Creating camera_display")
        self.camera_display = QLabel(self)
        self.camera_display.setStyleSheet("background: black;")
        self.camera_display.setAlignment(Qt.AlignCenter)
        self.camera_display.setScaledContents(False)
        self.camera_display.setGeometry(0, 0, self.width(), self.height())
        self.camera_display.setVisible(True)
        print(f"[RemoveNeedleTraining._setup_ui] camera_display created at (0,0) size {self.width()}x{self.height()}")
        
        # 文字显示层（浮于摄像头之上）
        print(f"[RemoveNeedleTraining._setup_ui] Creating text_display")
        self.text_display = TextDisplayWidget(self)
        self.text_display.setMaximumHeight(200)
        self.text_display.setStyleSheet("background: transparent;")
        self.text_display.setParent(self.camera_display)
        self.text_display.setGeometry(0, 0, self.camera_display.width(), 200)
        self.text_display.setVisible(True)
        print(f"[RemoveNeedleTraining._setup_ui] text_display created")
        
        # 信息叠加层（显示 Seq / Last Event / Pos / Speed）
        self.info_overlay = QLabel(self.camera_display)
        self.info_overlay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.info_overlay.setStyleSheet("color: #00FF00; background: rgba(0,0,0,120); padding: 8px; font-size: 18px;")
        self.info_overlay.setGeometry(10, 10, 420, 160)
        self.info_overlay.setVisible(True)

        self.posture_overlay = QLabel(self.camera_display)
        self.posture_overlay.setAlignment(Qt.AlignCenter)
        self.posture_overlay.setWordWrap(True)
        self.posture_overlay.setVisible(True)
        self._layout_posture_overlay()
        self._set_posture_overlay("WAITING", 0.0, 0.0, 0.0)

        # 成功显示
        print(f"[RemoveNeedleTraining._setup_ui] Creating success_display")
        self.success_display = SuccessDisplay(self.camera_display)
        print(f"[RemoveNeedleTraining._setup_ui] Complete")
    
    def _layout_posture_overlay(self):
        if not self.posture_overlay:
            return
        width = min(720, max(360, int(self.camera_display.width() * 0.72)))
        height = 150
        x = max(0, (self.camera_display.width() - width) // 2)
        y = max(80, (self.camera_display.height() - height) // 2)
        self.posture_overlay.setGeometry(x, y, width, height)

    def _set_posture_overlay(self, status: str, roll: float, pitch: float, yaw: float):
        if not self.posture_overlay:
            return
        if status == "OK":
            title = tr("posture.ok_title")
            detail = tr("posture.ok_detail")
            color = "#0F7A3A"
            border = "#24C66B"
            bg = "rgba(230, 255, 239, 220)"
        elif status == "BAD":
            title = tr("posture.bad_title")
            detail = tr("posture.bad_detail")
            color = "#9A1B1B"
            border = "#FF5A5A"
            bg = "rgba(255, 238, 238, 225)"
        elif status == "ERROR":
            title = tr("posture.error_title")
            detail = tr("posture.error_detail", port=self.imu_port)
            color = "#8A5A00"
            border = "#F5B942"
            bg = "rgba(255, 249, 224, 225)"
        else:
            title = tr("posture.waiting_title")
            detail = tr("posture.waiting_detail", port=self.imu_port)
            color = "#24415F"
            border = "#6EA8D9"
            bg = "rgba(235, 246, 255, 220)"
        self.posture_overlay.setText(f"{title}\n{detail}")
        self.posture_overlay.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background: {bg};
                border: 3px solid {border};
                border-radius: 8px;
                padding: 18px;
                font-family: 'Microsoft YaHei', 'Segoe UI', Arial;
                font-size: 28px;
                font-weight: 700;
            }}
        """)
        self.posture_overlay.raise_()

    def _hide_posture_overlay(self):
        if self.posture_overlay:
            self.posture_overlay.hide()

    def _show_posture_overlay(self, status: str):
        if not self.posture_overlay:
            return
        self.posture_overlay.show()
        self._set_posture_overlay(status, self.posture_roll, self.posture_pitch, self.posture_yaw)

    def _start_imu_posture_listener(self):
        if self.imu_thread:
            return
        try:
            self.imu_thread = ImuPostureThread(
                port=self.imu_port,
                baud=self.imu_baud,
                axis=self.imu_axis,
                min_deg=55.0,
                max_deg=125.0,
                parent=self,
            )
            self.imu_thread.posture_changed.connect(self._on_imu_posture_changed)
            self.imu_thread.error.connect(self._on_imu_posture_error)
            self.imu_thread.start()
            print(f"[IMU] Posture listener started on {self.imu_port} at {self.imu_baud}")
        except Exception as e:
            self._on_imu_posture_error(str(e))

    def _on_imu_posture_changed(self, status: str, roll: float, pitch: float, yaw: float, angle: float):
        self.posture_status = status
        self.posture_roll = roll
        self.posture_pitch = pitch
        self.posture_yaw = yaw
        self.posture_angle = angle
        now = time.time()
        if status == "OK":
            if self.posture_ok_since is None:
                self.posture_ok_since = now
            self._show_posture_overlay("OK")
            if now - self.posture_ok_since >= self.posture_required_hold_seconds:
                self._release_posture_gate()
        elif status == "BAD":
            self.posture_ok_since = None
            self._block_for_posture()
        else:
            self.posture_ok_since = None
            self._show_posture_overlay(status)
        self._set_posture_overlay(status, roll, pitch, yaw)
        self._update_info_overlay()

    def _on_imu_posture_error(self, message: str):
        print(f"[IMU] {message}")
        self.posture_status = "ERROR"
        self.posture_ok_since = None
        self._block_for_posture()
        self._set_posture_overlay("ERROR", 0.0, 0.0, 0.0)
        self._update_info_overlay()

    def _block_for_posture(self):
        self._show_posture_overlay("BAD")
        if self.posture_blocked:
            return
        self.posture_blocked = True
        self.paused_for_posture = True
        self.posture_pause_started_at = time.time()
        if self.phase_timer and self.phase_timer.isActive():
            self.paused_phase_timer_remaining_ms = max(0, self.phase_timer.remainingTime())
            self.phase_timer.stop()
        if getattr(self, "wipe_blood_start_time", None) is not None:
            elapsed = time.time() - self.wipe_blood_start_time
            self.paused_wipe_blood_remaining = max(0.0, self.wipe_blood_duration - elapsed)
            self.wipe_blood_start_time = None
        if getattr(self, "pinch_start_time", None) is not None:
            self.paused_pinch_elapsed = max(0.0, time.time() - self.pinch_start_time)
            self.pinch_start_time = None
        self.quiz_paused = True

    def _release_posture_gate(self):
        if not self.posture_gate_passed or self.posture_blocked:
            self.posture_gate_passed = True
        if self.posture_blocked:
            self.posture_blocked = False
            self.quiz_paused = False
            if self.posture_pause_started_at and self.training_start_time:
                self.training_start_time += time.time() - self.posture_pause_started_at
            self.posture_pause_started_at = None
            if self.paused_wipe_blood_remaining is not None:
                self.wipe_blood_start_time = time.time() - (self.wipe_blood_duration - self.paused_wipe_blood_remaining)
                self.paused_wipe_blood_remaining = None
            if self.paused_pinch_elapsed is not None:
                self.pinch_start_time = time.time() - self.paused_pinch_elapsed
                self.last_pinch_time = time.time()
                self.paused_pinch_elapsed = None
            if self.paused_phase_timer_remaining_ms is not None and self.phase_timer:
                self.phase_timer.start(max(1, self.paused_phase_timer_remaining_ms))
                self.paused_phase_timer_remaining_ms = None
        self.paused_for_posture = False
        self._hide_posture_overlay()
        if self.pending_training_start:
            self.pending_training_start = False
            self._begin_training_after_posture_gate()

    def resizeEvent(self, event):
        """窗口大小改变时更新camera_display"""
        super().resizeEvent(event)
        print(f"[RemoveNeedleTraining.resizeEvent] New size: {self.width()} x {self.height()}")
        self.camera_display.setGeometry(0, 0, self.width(), self.height())
        self.text_display.setGeometry(0, 0, self.camera_display.width(), 200)
        self._layout_posture_overlay()
    
    def _setup_camera(self):
        """设置摄像头"""
        if getattr(self, "disable_camera", False):
            print("[RemoveNeedleTraining._setup_camera] Camera disabled for hardware-only testing")
            self.camera_thread = None
            self.camera_display.setText("Camera disabled (hardware-only test)")
            self.camera_display.setStyleSheet("background: black; color: white; font-size: 20px;")
            return
        try:
            ok, message, _names = required_gemini_camera_status()
            if not ok:
                print(f"[RemoveNeedleTraining._setup_camera] {message}")
                self.camera_thread = None
                self.camera_display.setText(message)
                self.camera_display.setStyleSheet("background: black; color: white; font-size: 20px;")
                return
            camera_index = get_required_gemini_camera_index(get_configured_camera_index(0))
            print(f"[RemoveNeedleTraining._setup_camera] Creating CameraThread index={camera_index}")
            self.camera_thread = CameraThread(camera_index=camera_index)
            print(f"[RemoveNeedleTraining._setup_camera] Connecting frame_ready signal")
            self.camera_thread.frame_ready.connect(self._on_frame_ready)
            print(f"[RemoveNeedleTraining._setup_camera] Starting camera thread")
            self.camera_thread.start()
            print(f"[RemoveNeedleTraining._setup_camera] Camera thread started, is_running={self.camera_thread.isRunning()}")
        except Exception as e:
            print(f"[RemoveNeedleTraining._setup_camera] Error: {e}")
            import traceback
            traceback.print_exc()
            self.camera_display.setText(f"Camera Error: {str(e)[:50]}")
    
    def _setup_hand_detector(self):
        """设置手势检测器"""
        if getattr(self, "disable_camera", False):
            print("[RemoveNeedleTraining._setup_hand_detector] Disabled (camera off)")
            self.hand_detector = None
            self.finger_icon = None
            self.phase1_icon = None
            self.medical_dressing_icon = None
            self.blood_stain_icons = []
            self.medical_cotton_icon = None
            return
        self.hand_detector = HandGestureRecognizer()
        
        # 加载indexfinger.png
        try:
            self.finger_icon = cv2.imread("assets/indexfinger.png", cv2.IMREAD_UNCHANGED)
            if self.finger_icon is not None:
                print(f"[RemoveNeedleTraining] Loaded indexfinger.png: {self.finger_icon.shape}")
            else:
                print(f"[RemoveNeedleTraining] Failed to load indexfinger.png")
                self.finger_icon = None
        except Exception as e:
            print(f"[RemoveNeedleTraining] Error loading PNG: {e}")
            self.finger_icon = None
        
        # 加载removal1-1.png (Phase 1 文字图像)
        try:
            self.phase1_icon = cv2.imread("assets/removal1-1.png", cv2.IMREAD_UNCHANGED)
            if self.phase1_icon is not None:
                print(f"[RemoveNeedleTraining] Loaded removal1-1.png: {self.phase1_icon.shape}")
            else:
                print(f"[RemoveNeedleTraining] Failed to load removal1-1.png")
                self.phase1_icon = None
        except Exception as e:
            print(f"[RemoveNeedleTraining] Error loading Phase 1 PNG: {e}")
            self.phase1_icon = None
        
        # 加载medicaldressing.png (Phase 3 医用贴图像)
        try:
            self.medical_dressing_icon = cv2.imread("assets/medicaldressing.png", cv2.IMREAD_UNCHANGED)
            if self.medical_dressing_icon is not None:
                print(f"[RemoveNeedleTraining] Loaded medicaldressing.png: {self.medical_dressing_icon.shape}")
            else:
                print(f"[RemoveNeedleTraining] Failed to load medicaldressing.png")
                self.medical_dressing_icon = None
        except Exception as e:
            print(f"[RemoveNeedleTraining] Error loading medical dressing PNG: {e}")
            self.medical_dressing_icon = None
        
        # 加载三个血迹PNG (Phase 3.5 擦拭血迹)
        self.blood_stain_icons = []
        for i in range(1, 4):  # blood1.png, blood2.png, blood3.png
            try:
                blood_icon = cv2.imread(f"assets/blood{i}.png", cv2.IMREAD_UNCHANGED)
                if blood_icon is not None:
                    self.blood_stain_icons.append(blood_icon)
                    print(f"[RemoveNeedleTraining] Loaded blood{i}.png: {blood_icon.shape}")
                else:
                    print(f"[RemoveNeedleTraining] Failed to load blood{i}.png")
            except Exception as e:
                print(f"[RemoveNeedleTraining] Error loading blood{i}.png: {e}")
        
        # 加载 medicalcotton.png (Phase 3.5 擦拭血迹时使用)
        try:
            self.medical_cotton_icon = cv2.imread("assets/medicalcotton.png", cv2.IMREAD_UNCHANGED)
            if self.medical_cotton_icon is not None:
                print(f"[RemoveNeedleTraining] Loaded medicalcotton.png: {self.medical_cotton_icon.shape}")
            else:
                print(f"[RemoveNeedleTraining] Failed to load medicalcotton.png")
                self.medical_cotton_icon = None
        except Exception as e:
            print(f"[RemoveNeedleTraining] Error loading medicalcotton.png: {e}")
            self.medical_cotton_icon = None
    
    def start_training(self):
        """开始训练"""
        print(f"[RemoveNeedleTraining.start_training] Starting phase 0")
        self.current_phase = 0
        if not self.posture_gate_passed:
            self.pending_training_start = True
            self._show_posture_overlay("BAD" if self.posture_status == "BAD" else "WAITING")
            print("[IMU] Waiting for 3 seconds of stable side-lying posture before training starts")
            return
        self._begin_training_after_posture_gate()

    def _begin_training_after_posture_gate(self):
        if self.training_started_after_posture:
            return
        self.training_started_after_posture = True
        self.posture_blocked = False
        if getattr(self, "disable_camera", False):
            print("[SKIP_P1_P3] Camera disabled; skipping phases 1-3, jumping to Phase 4")
            # [SKIP_P1_P3] self._start_phase_1()  # 保留标记：跳过Phase1-3
            self._start_hardware_listener()
            self._start_phase_4()
            QTimer.singleShot(1000, lambda: self._send_start_when_ready())
            return
        self._start_phase_1()
    
    def _start_phase_1(self):
        """阶段1：初始指导 - It's time for you to remove the epidural catheter..."""
        print(f"[RemoveNeedleTraining._start_phase_1] Starting phase 1")
        
        self.current_phase = 0
        self.show_phase1_icon = True  # 显示Phase 1 PNG图像
        
        guide_text = ("It's time for you to remove the epidural catheter. "
                     "Please put your hand on the 3D model and I will tell you how to do. "
                     "First, check epidural catheter marking against medical record. "
                     "Then cleanse catheter entry site. Good Luck!")
        
        # 创建类似 Simulator Connection 风格的按钮样式显示
        # 使用 QFrame 作为容器，QLabel 显示文字
        from PySide6.QtWidgets import QFrame, QVBoxLayout
        from PySide6.QtCore import Qt
        
        # 创建包含文字的按钮样式框
        phase1_info_frame = QFrame(self)
        phase1_info_frame.setGeometry(100, 10, self.width() - 200, 200)
        phase1_info_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.7);
                border: 2px solid #FFFFFF;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        
        info_layout = QVBoxLayout(phase1_info_frame)
        info_label = QLabel(guide_text)
        info_label.setStyleSheet("""
            QLabel {
                color: #003366;
                font-family: 'Segoe Print', 'Segoe UI', Arial;
                font-size: 23px;
                font-weight: 600;
                background: transparent;
                border: none;
                padding: 0;
            }
        """)  
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(info_label)
        phase1_info_frame.setVisible(True)
        phase1_info_frame.raise_()  # 确保在最上层
        
        # 保存为实例变量，以便后续隐藏
        self.phase1_info_frame = phase1_info_frame
        
        # 隐藏原来的text_display
        self.text_display.setVisible(False)
        
        print(f"[RemoveNeedleTraining._start_phase_1] Text frame created and displayed")
        
        # 延迟1秒播放MP3
        QTimer.singleShot(1000, lambda: self._play_phase_1_audio())
        
        # 18秒后进入阶段2
        print(f"[RemoveNeedleTraining._start_phase_1] Starting 18s timer to phase 2")
        self.phase_timer = QTimer(self)
        self.phase_timer.setSingleShot(True)
        self.phase_timer.timeout.connect(self._transition_to_phase_2)
        self.phase_timer.start(18000)
    
    def _play_phase_1_audio(self):
        """播放Phase 1的音频"""
        try:
            audio_path = "assets/removal1-1.mp3"
            self.text_display.play_audio(audio_path)
            print(f"[Phase 1] Playing audio: {audio_path}")
        except Exception as e:
            print(f"[Phase 1] Error playing audio: {e}")
    
    def _transition_to_phase_2(self):
        """过渡到阶段2"""
        if self.phase_timer:
            self.phase_timer.stop()
        
        self.show_phase1_icon = False  # 隐藏Phase 1 PNG图像
        
        # 隐藏Phase 1的信息框
        if hasattr(self, 'phase1_info_frame'):
            self.phase1_info_frame.setVisible(False)
        
        self.text_display.fade_out(duration_ms=500)
        QTimer.singleShot(500, self._start_phase_2)
    
    def _start_phase_2(self):
        """阶段2：按住针头"""
        self.current_phase = 1
        
        guide_text = "Press and hold the catheter head firmly for 5 seconds."
        self.text_display.set_text(guide_text)
        self.text_display.fade_in(duration_ms=500)
        
        self.pinch_start_time = None
    
    def _start_phase_3(self):
        """阶段3：撕医用贴"""
        self.current_phase = 2
        
        self.text_display.fade_out(duration_ms=500)
        QTimer.singleShot(500, self._show_phase_3_content)
    
    def _show_phase_3_content(self):
        """显示阶段3内容"""
        guide_text = "Pull the dressing tape away from the skin carefully."
        self.text_display.set_text(guide_text)
        self.text_display.fade_in(duration_ms=500)
        
        self.finger_left_time = None
        # 初始化Phase 3动画计时器
        self.phase3_animation_start_time = None
        # 初始化血迹擦拭计时器
        self.wipe_blood_start_time = None
        self.wipe_blood_duration = 5.0
    
    def _on_frame_ready(self, qimage: QImage):
        """处理摄像头帧"""
        if getattr(self, "disable_camera", False):
            return
        try:
            width = qimage.width()
            height = qimage.height()
            
            qimage_rgb = qimage.convertToFormat(QImage.Format_RGB888)
            ptr = qimage_rgb.constBits()
            
            if ptr:
                arr = np.frombuffer(ptr, np.uint8).reshape(height, width, 3)
                frame = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                if self.posture_blocked:
                    self._display_frame(frame)
                    return
                
                # 手势检测 - 每5帧检测一次以减轻CPU压力
                hand_data_list = []
                self.frame_count += 1
                if self.frame_count % 5 == 0 and self.hand_detector:
                    hand_data_list = self.hand_detector.process_frame(frame)
                    self.last_hand_data = hand_data_list  # Cache for display
                else:
                    hand_data_list = self.last_hand_data  # Use cached data
                
                # 根据当前阶段处理
                if self.current_phase == 0:
                    self._phase_1_update(frame, hand_data_list)
                elif self.current_phase == 1:
                    self._phase_2_update(frame, hand_data_list)
                elif self.current_phase == 2:
                    # 检查是否在擦拭血迹阶段
                    if hasattr(self, 'wipe_blood_start_time') and self.wipe_blood_start_time is not None:
                        current_time = time.time()
                        if current_time - self.wipe_blood_start_time < self.wipe_blood_duration:
                            self._phase_3_wipe_blood_update(frame, hand_data_list)
                        else:
                            self._phase_3_update(frame, hand_data_list)
                    else:
                        self._phase_3_update(frame, hand_data_list)
                elif self.current_phase == 3:
                    self._phase_4_update(frame, hand_data_list)
                
                self._display_frame(frame)
            else:
                print(f"[RemoveNeedleTraining._on_frame_ready] Failed to get frame data")
        except Exception as e:
            print(f"[RemoveNeedleTraining._on_frame_ready] Error: {e}")
            import traceback
            traceback.print_exc()
    
    def _phase_1_update(self, frame, hand_data_list):
        """阶段1：只显示摄像头和文字"""
        self._draw_hand_skeleton(frame, hand_data_list)
        # 叠加Phase 1的PNG图像（带50%透明白色背景）
        # self._overlay_phase1_icon(frame, alpha=0.5)
    
    def _phase_2_update(self, frame, hand_data_list):
        """阶段2：按住针头"""
        center_x, center_y = frame.shape[1] // 2, frame.shape[0] // 2
        is_pinching = False
        
        for hand_data in hand_data_list:
            joints = hand_data.get('joints', [])
            if joints and len(joints) > 8:
                index_tip = joints[8]  # Index tip landmark
                fx = index_tip.get('x', 0) if isinstance(index_tip, dict) else index_tip[0]
                fy = index_tip.get('y', 0) if isinstance(index_tip, dict) else index_tip[1]
                fx, fy = int(fx), int(fy)
                
                # Distance from index finger tip to center
                distance = np.sqrt((fx - center_x)**2 + (fy - center_y)**2)
                if hand_data_list:  # Log distance for debugging
                    print(f"[Phase 2] Finger to center distance: {distance:.1f}px, threshold: 20px")
                
                # If index finger is inside the 20px circle
                if distance < 20:
                    is_pinching = True
                    break
        
        current_time = time.time()
        
        # Allow up to 0.3s of detection loss (MediaPipe instability)
        if is_pinching:
            if self.pinch_start_time is None:
                self.pinch_start_time = current_time
                self.last_pinch_time = current_time
                print(f"[Phase 2] 开始按住")
            else:
                self.last_pinch_time = current_time
            
            elapsed = current_time - self.pinch_start_time
            if elapsed >= 2.0:
                print(f"[Phase 2] 按住成功！耗时 {elapsed:.2f}秒")
                self._phase_2_success()
            elif elapsed > 1.0 and elapsed % 0.5 < 0.05:  # Log every ~0.5s
                print(f"[Phase 2] 已按住 {elapsed:.2f}秒，还需要 {2.0-elapsed:.2f}秒")
        else:
            # Check if we've been in "not pinching" for too long
            if self.pinch_start_time is not None:
                time_since_last_pinch = current_time - self.last_pinch_time
                
                # If detection loss < 0.5s, continue (MediaPipe can be unstable during pinch)
                if time_since_last_pinch < 0.5:
                    # Silent continue - don't reset yet
                    pass
                else:
                    # Real finger release - reset
                    elapsed = current_time - self.pinch_start_time
                    print(f"[Phase 2] 手指抬起，已按住 {elapsed:.2f}秒，重置")
                    self.pinch_start_time = None
                    self.last_pinch_time = None
            else:
                self.last_pinch_time = None
        
        # 绘制手骨骼点
        self._draw_hand_skeleton(frame, hand_data_list)
        
        # 绘制中心点指引（深绿色圈，更小，更细）
        center_x, center_y = frame.shape[1] // 2, frame.shape[0] // 2
        cv2.circle(frame, (center_x, center_y), 15, (0, 100, 0), 1)
        
        # 在圆圈上叠加医用贴PNG图像
        if self.medical_dressing_icon is not None:
            self._overlay_medical_dressing_with_animation(frame, center_x, center_y, 0, 0, 1.0)
        
        # 在圆圈上叠加手指PNG图像
        if self.finger_icon is not None:
            self._overlay_png_on_circle(frame, center_x, center_y, 20)
        
        # 深绿色文字，居中
        text = "Press here"
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 1.2, 2)[0]
        text_x = center_x - text_size[0] // 2
        text_y = center_y - 80
        cv2.putText(frame, text, (text_x, text_y), font, 1.2, (0, 100, 0), 2)
    
    def _phase_3_update(self, frame, hand_data_list):
        """阶段3：撕医用贴"""
        center_x, center_y = frame.shape[1] // 2, frame.shape[0] // 2
        
        current_time = time.time()
        
        # 检测手指是否在中心区域
        finger_in_center = False
        for hand_data in hand_data_list:
            joints = hand_data.get('joints', [])
            if joints and len(joints) > 8:
                index_finger = joints[8]  # Index tip landmark
                fx = index_finger.get('x', 0) if isinstance(index_finger, dict) else index_finger[0]
                fy = index_finger.get('y', 0) if isinstance(index_finger, dict) else index_finger[1]
                fx, fy = int(fx), int(fy)
                distance = np.sqrt((fx - center_x)**2 + (fy - center_y)**2)
                
                # 70px 为中心区域阈值
                if distance < 70:
                    finger_in_center = True
                    break
        
        # 记录手指离开中心的时间
        if finger_in_center:
            if self.finger_left_time is not None:
                self.finger_left_time = None
                print(f"[Phase 3] 手指回到中心区域")
        else:
            if self.finger_left_time is None:
                self.finger_left_time = current_time
                print(f"[Phase 3] 手指离开中心区域，开始计时")
        
        # 如果是第一次进入Phase 3，初始化动画计时器
        if self.phase3_animation_start_time is None:
            self.phase3_animation_start_time = current_time
            print(f"[Phase 3] Move开始，初始化动画计时器")
        
        # 绘制手骨骼点
        self._draw_hand_skeleton(frame, hand_data_list)
        
        # 计算动画进度
        animation_progress = 0
        dressing_alpha = 1.0  # 医用贴的不透明度
        circle_alpha = 0.0   # 圆的不透明度（始终消失）
        
        elapsed_since_start = current_time - self.phase3_animation_start_time
        dressing_offset_x = 0
        dressing_offset_y = 0
        
        # 步骤1：前3秒保持原样，手指和医用贴不动
        if elapsed_since_start < 3.0:
            dressing_offset_x = 0
            dressing_offset_y = 0
            dressing_alpha = 1.0
        # 步骤2：3-8秒，手指和医用贴移动（5秒移动时间）
        elif elapsed_since_start < 8.0:
            move_progress = (elapsed_since_start - 3.0) / 5.0  # 5秒移动时间
            move_progress = min(1.0, move_progress)
            dressing_offset_x = int(move_progress * 100)  # 向左移动100像素
            dressing_offset_y = int(move_progress * 100)  # 向下移动100像素
            dressing_alpha = 1.0 - move_progress  # 5秒之间渐变消失
        else:
            # 步骤3：8秒后，手指和医用贴完全消失
            dressing_alpha = 0.0
        
        # 检查是否成功（手指离开中心后 6 秒）
        if self.finger_left_time is not None:
            elapsed_left = current_time - self.finger_left_time
            if elapsed_left >= 6.0:
                print(f"[Phase 3] 手指离开中心 {elapsed_left:.2f}秒，成功！")
                self._phase_3_success()
                return  # 直接返回，不再绘制任何东西
        
        # 只在 dressing_alpha > 0 时绘制医用贴和手指
        if dressing_alpha > 0.001:  # 避免浮点数精度问题
            # 绘制医用贴图片（带位移和消失效果）
            if self.medical_dressing_icon is not None:
                self._overlay_medical_dressing_with_animation(frame, center_x, center_y, 
                                                             dressing_offset_x, dressing_offset_y, dressing_alpha)
            
            # 绘制手指PNG图像（同时移动和消失，向左下移动）
            if self.finger_icon is not None:
                # 手指位置也随着医用贴一起向左下移动
                finger_center_x = center_x - dressing_offset_x
                finger_center_y = center_y + dressing_offset_y
                self._overlay_png_on_circle(frame, finger_center_x, finger_center_y, 20)
        
        # 深绿色文字，居中
        text = "Move medical dressing"
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 1.2, 2)[0]
        text_x = center_x - text_size[0] // 2
        text_y = center_y - 80
        cv2.putText(frame, text, (text_x, text_y), font, 1.2, (0, 100, 0), 2)
    
    def _draw_hand_skeleton(self, frame, hand_data_list):
        """绘制手骨骼点和连接线到帧上"""
        # MediaPipe手部21个关键点的连接关系
        HAND_CONNECTIONS = [
            # 手腕到手掌
            (0, 1), (0, 5), (0, 9), (0, 13), (0, 17),
            # 大拇指
            (1, 2), (2, 3), (3, 4),
            # 食指
            (5, 6), (6, 7), (7, 8),
            # 中指
            (9, 10), (10, 11), (11, 12),
            # 无名指
            (13, 14), (14, 15), (15, 16),
            # 小指
            (17, 18), (18, 19), (19, 20),
            # 手掌连接
            (5, 9), (9, 13), (13, 17)
        ]
        
        for hand_data in hand_data_list:
            # 使用'joints'而不是'landmarks'（这是hand_gesture_recognizer返回的key）
            joints = hand_data.get('joints', [])
            if not joints or len(joints) < 21:
                continue
            
            # 统一使用淡天蓝色绘制骨骼，带透明效果
            LIGHT_SKY_BLUE = (230, 200, 100)  # BGR格式: 淡天蓝色
            LINE_WIDTH = 5
            POINT_RADIUS = 6
            ALPHA = 0.6  # 透明度
            
            # 创建副本用于alpha blending
            overlay = frame.copy()
            
            # 先绘制所有连接线到overlay
            for start_idx, end_idx in HAND_CONNECTIONS:
                if start_idx < len(joints) and end_idx < len(joints):
                    start_joint = joints[start_idx]
                    end_joint = joints[end_idx]
                    
                    x1, y1 = int(start_joint['x']), int(start_joint['y'])
                    x2, y2 = int(end_joint['x']), int(end_joint['y'])
                    
                    cv2.line(overlay, (x1, y1), (x2, y2), LIGHT_SKY_BLUE, LINE_WIDTH)
            
            # 再绘制所有关键点到overlay
            for joint in joints:
                x, y = int(joint['x']), int(joint['y'])
                cv2.circle(overlay, (x, y), POINT_RADIUS, LIGHT_SKY_BLUE, -1)
            
            # Alpha blending使骨骼半透明
            cv2.addWeighted(overlay, ALPHA, frame, 1 - ALPHA, 0, frame)
    
    def _display_frame(self, frame):
        """将OpenCV帧转换并显示到UI"""
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = 3 * w
            
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            
            max_width = self.camera_display.width()
            max_height = self.camera_display.height()
            
            if max_width > 0 and max_height > 0:
                pixmap = QPixmap.fromImage(qt_image)
                # 使用IgnoreAspectRatio填满屏幕左右
                scaled_pixmap = pixmap.scaled(max_width, max_height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.camera_display.setPixmap(scaled_pixmap)
                
                # 只在第一帧时打印日志
                if not hasattr(self, '_frame_displayed'):
                    print(f"[RemoveNeedleTraining._display_frame] First frame displayed: {w}x{h} -> {scaled_pixmap.width()}x{scaled_pixmap.height()}")
                    self._frame_displayed = True
        except Exception as e:
            print(f"[RemoveNeedleTraining._display_frame] Error: {e}")
            import traceback
            traceback.print_exc()
    
    def _overlay_png_on_circle(self, frame, center_x, center_y, radius):
        """在圆圈位置上叠加PNG图像
        
        位置和大小调整方法:
        - center_x, center_y: 圆圈中心坐标
        - radius: 圆圈半径，PNG图像会缩放到直径大小 (2*radius)
        
        如果PNG显示位置不对，可以调整:
        1. 改变 radius 参数来改变PNG大小
        2. 改变 offset_x, offset_y 来微调PNG位置
        3. 改变 resize_factor 来控制PNG相对于圆圈的缩放比例
        """
        try:
            if self.finger_icon is None:
                return
            
            # PNG图像尺寸
            png_h, png_w = self.finger_icon.shape[:2]
            
            # 调整PNG大小，使其与圆圈半径相匹配
            # 可以修改下面的倍数来调整大小 (当前是 1.8 倍半径)
            resize_factor = 3
            target_size = int(radius * 2 * resize_factor)
            resized_icon = cv2.resize(self.finger_icon, (target_size, target_size))
            
            # 计算PNG在frame中的位置 (左上角)
            # 可以通过调整 offset_x, offset_y 来微调位置
            offset_x = -50
            offset_y = 50
            x1 = center_x - target_size // 2 + offset_x
            y1 = center_y - target_size // 2 + offset_y
            x2 = x1 + target_size
            y2 = y1 + target_size
            
            # 边界检查
            frame_h, frame_w = frame.shape[:2]
            if x1 < 0 or y1 < 0 or x2 > frame_w or y2 > frame_h:
                return
            
            # 如果PNG有透明通道（RGBA），使用alpha混合
            if resized_icon.shape[2] == 4:
                # 提取RGB和Alpha通道
                png_rgb = resized_icon[:, :, :3]
                png_alpha = resized_icon[:, :, 3:] / 255.0
                
                # 获取frame中的对应区域
                frame_roi = frame[y1:y2, x1:x2]
                
                # Alpha混合
                frame[y1:y2, x1:x2] = (png_rgb * png_alpha + frame_roi * (1 - png_alpha)).astype(np.uint8)
            else:
                # 直接复制RGB通道
                frame[y1:y2, x1:x2] = resized_icon[:, :, :3]
        except Exception as e:
            print(f"[RemoveNeedleTraining._overlay_png_on_circle] Error: {e}")
    
    def _overlay_phase1_icon(self, frame, alpha=0.5):
        """在frame上叠加Phase 1的PNG图像（带白色背景和透明度）
        
        参数:
        - frame: OpenCV的BGR图像帧
        - alpha: 透明度 (0.0-1.0), 默认0.5表示50%透明
        
        位置和大小调整:
        - 图像会居中显示在frame上
        - 可以通过修改 padding 来调整图像位置（上下）
        - 可以通过修改 scale_factor 来调整图像大小
        """
        try:
            if self.phase1_icon is None or not self.show_phase1_icon:
                return
            
            frame_h, frame_w = frame.shape[:2]
            png_h, png_w = self.phase1_icon.shape[:2]
            
            # 调整PNG大小，使其适合frame
            # 可以修改 scale_factor 来改变大小 (当前是 0.8 表示占frame宽度的80%)
            scale_factor = 0.8
            target_width = int(frame_w * scale_factor)
            
            # 按比例缩放，保持宽高比
            ratio = target_width / png_w
            target_height = int(png_h * ratio)
            
            # 缩放PNG
            resized_png = cv2.resize(self.phase1_icon, (target_width, target_height))
            
            # 计算位置（居中）
            # 可以修改 y_offset 来调整上下位置（正数向下）
            x_offset = (frame_w - target_width) // 2
            y_offset = (frame_h - target_height) // 3  # 显示在上面1/3位置
            
            x1 = x_offset
            y1 = y_offset
            x2 = x1 + target_width
            y2 = y1 + target_height
            
            # 边界检查
            if x1 < 0 or y1 < 0 or x2 > frame_w or y2 > frame_h:
                return
            
            # 获取frame中的对应区域
            frame_roi = frame[y1:y2, x1:x2]
            
            # 创建白色背景
            white_bg = np.ones_like(resized_png[:, :, :3]) * 255
            
            # 如果PNG有透明通道，使用它
            if resized_png.shape[2] == 4:
                png_rgb = resized_png[:, :, :3]
                png_alpha = resized_png[:, :, 3:] / 255.0
                
                # 白色背景与PNG合成
                composited = (png_rgb * png_alpha + white_bg * (1 - png_alpha)).astype(np.uint8)
            else:
                composited = resized_png[:, :, :3]
            
            # 将合成后的图像与frame进行alpha混合（50%透明）
            # alpha参数控制透明度：1.0=完全显示，0.5=50%透明，0.0=完全透明
            result = (composited.astype(np.float32) * alpha + 
                     frame_roi.astype(np.float32) * (1 - alpha)).astype(np.uint8)
            
            frame[y1:y2, x1:x2] = result
        except Exception as e:
            print(f"[RemoveNeedleTraining._overlay_phase1_icon] Error: {e}")
    
    def _draw_circle_with_alpha(self, frame, center, radius, color, thickness, alpha):
        """使用alpha混合绘制圆圈
        
        参数:
        - frame: OpenCV图像帧
        - center: 圆心坐标 (x, y)
        - radius: 半径
        - color: BGR颜色 (0, 100, 0)
        - thickness: 线宽
        - alpha: 不透明度 (0.0-1.0)
        """
        try:
            # 创建临时图像用于绘制圆
            overlay = frame.copy()
            cv2.circle(overlay, center, radius, color, thickness)
            
            # Alpha混合
            cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        except Exception as e:
            print(f"[RemoveNeedleTraining._draw_circle_with_alpha] Error: {e}")
    
    def _overlay_medical_dressing_with_animation(self, frame, center_x, center_y, 
                                                 offset_x, offset_y, alpha):
        """在frame上叠加医用贴PNG图像，带移动和消失动画
        
        参数调整指南:
        - offset_x: 向左移动距离（正数向右，负数向左）
        - offset_y: 向下移动距离（正数向下，负数向上）
        - alpha: 不透明度 (0.0-1.0)
        
        图片大小调整:
        - base_scale: 基础缩放因子 (当前0.5表示占圆圈直径的0.5倍)
        """
        try:
            if self.medical_dressing_icon is None:
                return
            
            frame_h, frame_w = frame.shape[:2]
            png_h, png_w = self.medical_dressing_icon.shape[:2]
            
            # 调整医用贴图片大小
            # 可以修改 base_scale 来改变大小 (当前0.5)
            base_scale = 0.8
            radius = 70
            target_size = int(radius * 2 * base_scale)  # 140 * 0.5 = 70像素
            
            # 缩放PNG
            resized_icon = cv2.resize(self.medical_dressing_icon, (target_size, target_size))
            
            # 计算位置（居中 + 移动偏移）
            x1 = center_x - target_size // 2 - offset_x  # 负offset_x使其向左
            y1 = center_y - target_size // 2 + offset_y  # 正offset_y使其向下
            x2 = x1 + target_size
            y2 = y1 + target_size
            
            # 边界检查
            if x1 < 0 or y1 < 0 or x2 > frame_w or y2 > frame_h:
                return
            
            # 获取frame中的对应区域
            frame_roi = frame[y1:y2, x1:x2]
            
            # 如果PNG有透明通道（RGBA），使用alpha混合
            if resized_icon.shape[2] == 4:
                png_rgb = resized_icon[:, :, :3]
                png_alpha = resized_icon[:, :, 3:] / 255.0
                
                # PNG与frame进行alpha混合（考虑消失动画alpha）
                result = (png_rgb.astype(np.float32) * png_alpha * alpha + 
                         frame_roi.astype(np.float32) * (1 - png_alpha * alpha)).astype(np.uint8)
            else:
                # 直接使用RGB
                result = (resized_icon[:, :, :3].astype(np.float32) * alpha +
                         frame_roi.astype(np.float32) * (1 - alpha)).astype(np.uint8)
            
            frame[y1:y2, x1:x2] = result
        except Exception as e:
            print(f"[RemoveNeedleTraining._overlay_medical_dressing_with_animation] Error: {e}")
    
    def _overlay_png_with_alpha(self, frame, x_center, y_center, png_icon, alpha, size_scale=1.0):
        """在frame上叠加PNG图像，带透明度
        
        参数:
        - x_center, y_center: 图像中心位置
        - png_icon: PNG图像数据
        - alpha: 整体透明度 (0.0-1.0)
        - size_scale: 大小缩放因子 (1.0 = 80像素宽度, 2.0 = 160像素宽度)
        """
        try:
            if png_icon is None:
                return
            
            frame_h, frame_w = frame.shape[:2]
            png_h, png_w = png_icon.shape[:2]
            
            # 缩放PNG到合适大小（基础宽度80像素，可通过size_scale调节）
            base_width = 80
            scale = (base_width * size_scale) / png_w
            target_w = int(png_w * scale)
            target_h = int(png_h * scale)
            
            resized_png = cv2.resize(png_icon, (target_w, target_h))
            
            # 计算位置（以中心为基准）
            x1 = x_center - target_w // 2
            y1 = y_center - target_h // 2
            x2 = x1 + target_w
            y2 = y1 + target_h
            
            # 边界检查
            if x1 < 0 or y1 < 0 or x2 > frame_w or y2 > frame_h:
                return
            
            # 获取frame中的对应区域
            frame_roi = frame[y1:y2, x1:x2]
            
            # 如果PNG有透明通道（RGBA），使用alpha混合
            if resized_png.shape[2] == 4:
                png_rgb = resized_png[:, :, :3]
                png_alpha = resized_png[:, :, 3:] / 255.0
                
                # PNG与frame进行alpha混合
                result = (png_rgb.astype(np.float32) * png_alpha * alpha + 
                         frame_roi.astype(np.float32) * (1 - png_alpha * alpha)).astype(np.uint8)
            else:
                # 直接使用RGB
                result = (resized_png[:, :, :3].astype(np.float32) * alpha +
                         frame_roi.astype(np.float32) * (1 - alpha)).astype(np.uint8)
            
            frame[y1:y2, x1:x2] = result
        except Exception as e:
            print(f"[RemoveNeedleTraining._overlay_png_with_alpha] Error: {e}")
    
    def _overlay_png_with_alpha_scaled(self, frame, x_center, y_center, png_icon, alpha, scale):
        """在frame上叠加PNG图像，带透明度和缩放
        
        参数:
        - x_center, y_center: 图像中心位置
        - png_icon: PNG图像数据
        - alpha: 整体透明度 (0.0-1.0)
        - scale: 缩放因子 (1.0 = 基础大小)
        """
        try:
            if png_icon is None:
                return
            
            frame_h, frame_w = frame.shape[:2]
            png_h, png_w = png_icon.shape[:2]
            
            # 缩放PNG到合适大小（基础宽度约100像素）
            base_w = 100
            scale_w = int(base_w * scale)
            scale_h = int(png_h * scale_w / png_w)
            
            resized_png = cv2.resize(png_icon, (scale_w, scale_h))
            
            # 计算位置（以中心为基准）
            x1 = x_center - scale_w // 2
            y1 = y_center - scale_h // 2
            x2 = x1 + scale_w
            y2 = y1 + scale_h
            
            # 边界检查
            if x1 < 0 or y1 < 0 or x2 > frame_w or y2 > frame_h:
                return
            
            # 获取frame中的对应区域
            frame_roi = frame[y1:y2, x1:x2]
            
            # 如果PNG有透明通道（RGBA），使用alpha混合
            if resized_png.shape[2] == 4:
                png_rgb = resized_png[:, :, :3]
                png_alpha = resized_png[:, :, 3:] / 255.0
                
                # PNG与frame进行alpha混合
                result = (png_rgb.astype(np.float32) * png_alpha * alpha + 
                         frame_roi.astype(np.float32) * (1 - png_alpha * alpha)).astype(np.uint8)
            else:
                # 直接使用RGB
                result = (resized_png[:, :, :3].astype(np.float32) * alpha +
                         frame_roi.astype(np.float32) * (1 - alpha)).astype(np.uint8)
            
            frame[y1:y2, x1:x2] = result
        except Exception as e:
            print(f"[RemoveNeedleTraining._overlay_png_with_alpha_scaled] Error: {e}")
    
    def _detect_circular_motion(self, point_history):
        """检测圆周运动（转圈）
        
        参数:
        - point_history: 历史位置列表
        
        返回: 是否检测到新的转圈
        """
        if len(point_history) < 20:
            return False
        
        # 获取最近的一段路径
        recent_points = point_history[-20:]
        
        # 计算中心点
        center_x = sum(p[0] for p in recent_points) / len(recent_points)
        center_y = sum(p[1] for p in recent_points) / len(recent_points)
        
        # 计算每个点到中心的距离
        distances = [np.sqrt((p[0] - center_x)**2 + (p[1] - center_y)**2) for p in recent_points]
        avg_dist = sum(distances) / len(distances)
        
        # 检查是否形成圆周运动（距离变化平稳）
        dist_variance = sum((d - avg_dist)**2 for d in distances) / len(distances)
        
        # 如果方差较小且半径较大（> 35像素），认为是转圈
        # 方差阈值从200调整到300以降低难度
        if dist_variance < 300 and avg_dist > 35:
            # 检查角度变化（是否形成360度圆）
            angles = []
            for p in recent_points:
                angle = np.arctan2(p[1] - center_y, p[0] - center_x)
                angles.append(angle)
            
            # 计算角度跨度
            angle_range = max(angles) - min(angles)
            
            # 如果角度跨度大于90度（约π/2），认为是有效的转圈
            # 从108度（π*0.6）调整到90度（π*0.5）以降低难度
            if angle_range > np.pi * 0.5:
                circles = self.blood_wipe_state['circles_completed']
                if circles < 3:
                    self.blood_wipe_state['circles_completed'] = circles + 1
                    self.blood_wipe_state['blood_fade_start'][circles] = time.time()
                    print(f"[Phase 3.5] 检测到转圈 #{circles + 1}，blood{circles + 1}开始消失")
                    
                    # 检查是否全部完成
                    if self.blood_wipe_state['circles_completed'] == 3 and not self.blood_wipe_state['success_triggered']:
                        self.blood_wipe_state['success_triggered'] = True
                        print(f"[Phase 3.5] 所有血迹消失，2秒后成功")
                        self.wipe_blood_success_delay_timer = QTimer(self)
                        self.wipe_blood_success_delay_timer.timeout.connect(self._phase_3_wipe_blood_success)
                        self.wipe_blood_success_delay_timer.start(2000)  # 2秒后成功
                
                # 清空历史以防止重复检测
                self.blood_wipe_state['pinch_center_history'].clear()
    
    def _phase_3_wipe_blood_success(self):
        """血迹擦拭成功"""
        if getattr(self, "_cleanup_done", False):
            return
        self._set_blood_light(False)
        print(f"[Phase 3.5] 擦拭血迹成功！")
        
        if self.wipe_blood_success_delay_timer:
            self.wipe_blood_success_delay_timer.stop()
            self.wipe_blood_success_delay_timer = None
        
        self.text_display.fade_out(duration_ms=300)
        
        QTimer.singleShot(300, lambda: self.success_display.show_success(
            audio_path=self.audio_success,
            duration_ms=1000
        ))
        
        QTimer.singleShot(1300, self._start_phase_4)
    
    def _phase_2_success(self):
        """阶段2成功"""
        self.pinch_start_time = None
        self.last_pinch_time = None
        
        self.text_display.fade_out(duration_ms=300)
        
        QTimer.singleShot(300, lambda: self.success_display.show_success(
            audio_path=self.audio_success,
            duration_ms=1000
        ))
        
        QTimer.singleShot(1300, self._start_phase_3)
    
    def _phase_3_success(self):
        """阶段3成功，进入血迹擦拭阶段"""
        self.finger_left_time = None
        self.phase3_animation_start_time = None
        
        self.text_display.fade_out(duration_ms=300)
        
        QTimer.singleShot(300, lambda: self.success_display.show_success(
            audio_path=self.audio_success,
            duration_ms=1000
        ))
        
        QTimer.singleShot(1300, self._start_phase_3_wipe_blood)
    
    def _start_phase_3_wipe_blood(self):
        """阶段3.5：擦拭血迹"""
        if getattr(self, "_cleanup_done", False):
            return
        self._set_blood_light(True)
        self.current_phase = 2  # 保持为 Phase 2，但用新的 update 方法处理
        self.wipe_blood_start_time = time.time()
        self.wipe_blood_duration = 999.0  # 长时间，等待手动操作
        
        # 显示Phase 3.5指导文字
        guide_text = "Wipe the blood stains with circular motions until clean."
        self.text_display.set_text(guide_text)
        self.text_display.fade_in(duration_ms=500)
        
        # 初始化血迹擦拭状态
        self.blood_wipe_state = {
            'pinching': False,  # 是否在捏着cotton
            'pinch_start_time': None,  # 开始捏的时间
            'pinch_center_history': [],  # 历史位置用于圆周运动检测
            'circles_completed': 0,  # 完成的圈数（0, 1, 2, 3）
            'blood_fade_start': [None, None, None],  # 每个血迹开始消失的时间
            'success_triggered': False,  # 是否已触发成功
        }
        self.wipe_blood_success_delay_timer = None
        
        self.text_display.set_text("Wipe blood")
        self.text_display.fade_in(duration_ms=500)
        print(f"[Phase 3.5] 擦拭血迹开始")
    
    def _phase_3_wipe_blood_update(self, frame, hand_data_list):
        """阶段3.5：擦拭血迹 - 显示血迹PNG和cotton，检测捏着和转圈"""
        center_x, center_y = frame.shape[1] // 2, frame.shape[0] // 2
        height, width = frame.shape[0], frame.shape[1]
        
        current_time = time.time()
        
        # 绘制手骨骼点
        self._draw_hand_skeleton(frame, hand_data_list)
        
        # 血迹位置和大小参数（可调节）
        blood_scales = [1.0, 0.7, 0.5]  # 第一张最大，第三张最小
        blood_positions = [
            (center_x, center_y),   # 中央重叠
            (center_x, center_y),   # 中央重叠
            (center_x, center_y),   # 中央重叠
        ]
        
        # 检测捏着状态（食指第2、3关节+拇指）
        is_pinching = False
        thumb_tip_x, thumb_tip_y = None, None
        
        for hand_data in hand_data_list:
            joints = hand_data.get('joints', [])
            if joints and len(joints) > 8:
                # 食指关键点：PIP (6), DIP (7), TIP (8)
                # 拇指关键点：IP (2), TIP (4)
                index_pip = joints[6]
                index_dip = joints[7]
                index_tip = joints[8]
                thumb_ip = joints[2]
                thumb_tip = joints[4]
                
                # 获取坐标
                i_pip = (index_pip.get('x', 0), index_pip.get('y', 0)) if isinstance(index_pip, dict) else (index_pip[0], index_pip[1])
                i_dip = (index_dip.get('x', 0), index_dip.get('y', 0)) if isinstance(index_dip, dict) else (index_dip[0], index_dip[1])
                t_tip = (thumb_tip.get('x', 0), thumb_tip.get('y', 0)) if isinstance(thumb_tip, dict) else (thumb_tip[0], thumb_tip[1])
                
                # 计算食指第2、3关节的中点
                index_mid_x = (i_pip[0] + i_dip[0]) / 2
                index_mid_y = (i_pip[1] + i_dip[1]) / 2
                
                # 计算距离
                dist_index_thumb = np.sqrt((index_mid_x - t_tip[0])**2 + (index_mid_y - t_tip[1])**2)
                
                # 捏着判断（距离 < 45 像素，放宽条件以提高灵敏度）
                if dist_index_thumb < 45:
                    is_pinching = True
                    thumb_tip_x, thumb_tip_y = int(t_tip[0]), int(t_tip[1])
                    break
        
        # 更新捏着状态
        if is_pinching:
            if not self.blood_wipe_state['pinching']:
                self.blood_wipe_state['pinching'] = True
                self.blood_wipe_state['pinch_start_time'] = current_time
                self.blood_wipe_state['pinch_center_history'] = []
                print(f"[Phase 3.5] 开始捏着cotton")
            
            if thumb_tip_x and thumb_tip_y:
                self.blood_wipe_state['pinch_center_history'].append((thumb_tip_x, thumb_tip_y))
                # 保持最近100个点
                if len(self.blood_wipe_state['pinch_center_history']) > 100:
                    self.blood_wipe_state['pinch_center_history'].pop(0)
                
                # 检测转圈动作（圆周运动）
                if len(self.blood_wipe_state['pinch_center_history']) >= 20:
                    self._detect_circular_motion(self.blood_wipe_state['pinch_center_history'])
        else:
            if self.blood_wipe_state['pinching']:
                self.blood_wipe_state['pinching'] = False
                print(f"[Phase 3.5] 松开了cotton，已完成 {self.blood_wipe_state['circles_completed']} 圈")
        
        # 绘制血迹（带消失动画）
        if not self._uses_physical_blood() and len(self.blood_stain_icons) >= 3:
            for idx in range(3):
                # 检查该血迹是否应该消失
                if self.blood_wipe_state['blood_fade_start'][idx] is not None:
                    fade_elapsed = current_time - self.blood_wipe_state['blood_fade_start'][idx]
                    if fade_elapsed >= 0.5:  # 消失动画持续0.5秒
                        alpha = 0.0
                    else:
                        alpha = 1.0 - (fade_elapsed / 0.5)  # 渐变消失
                else:
                    alpha = 1.0  # 完全显示
                
                # 如果alpha > 0，绘制血迹
                if alpha > 0.0:
                    self._overlay_png_with_alpha_scaled(
                        frame, 
                        blood_positions[idx][0], 
                        blood_positions[idx][1],
                        self.blood_stain_icons[idx],
                        alpha,
                        blood_scales[idx]
                    )
        
        # 如果在捏着状态，绘制cotton跟随拇指尖
        if is_pinching and thumb_tip_x is not None and thumb_tip_y is not None:
            if self.medical_cotton_icon is not None:
                self._overlay_png_with_alpha(frame, thumb_tip_x, thumb_tip_y, self.medical_cotton_icon, 1.0, size_scale=2.0)
        
        # 显示文字
        text = "Wipe blood"
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 1.5, 2)[0]
        text_x = center_x - text_size[0] // 2
        text_y = center_y - 150
        cv2.putText(frame, text, (text_x, text_y), font, 1.5, (0, 0, 255), 2)
    
    def _start_phase_4(self):
        """阶段4：拔针管（无硬件版本）"""
        if getattr(self, "_cleanup_done", False):
            return
        self.current_phase = 3
        
        # 生成随机的拔针参数配置
        self.pull_config = self._generate_pull_config()
        print(f"[Phase 4] Pull config: {self.pull_config}")

        # 重置训练数据收集
        self.events_triggered = {}
        self.max_pull_distance_achieved = 0
        # 标记每个事件是否已触发（与 events_queue 对齐）
        self.external_event_flags = [False] * len(self.pull_config['events_queue'])
        
        # 初始化拔针跟踪数据
        self.needle_x = None  # 会在_phase_4_update中初始化
        self.needle_head_y = None
        self.needle_pulled_distance = 0
        self.max_pulled_distance = 0
        self.pinching = False
        self.pinch_history = []
        self.last_pinch_y = None
        self.pull_start_y = None
        self.pull_speed_warning_time = None
        self.phase4_events_completed = 0  # 重置事件计数器
        self.hand_pinching_near_needle = False  # 重置手捏着的state
        self.training_start_time = time.time()  # 记录Phase 4开始时间
        
        # 显示Phase 4指导文字
        guide_text = "Pull out the epidural catheter smoothly and steadily."
        self.text_display.set_text(guide_text)
        self.text_display.fade_in(duration_ms=500)

        # 如果禁用摄像头，则显示简化提示并请求MCU开始实时流
        if getattr(self, "disable_camera", False):
            now = time.time()
            self.speed_display_end = now + 60.0  # 显示窗口延长到60秒，避免中途不更新
            self.last_distance_sample_cm = 0.0
            self.last_distance_sample_time = now
            self.current_speed_cmps = 0.0
            self._update_info_overlay()
            self.camera_display.setStyleSheet("background: black; color: white; font-size: 20px;")
            # 确保监听线程已启动
            self._start_hardware_listener()

    def _start_hardware_listener(self):
        """Start the selected hardware transport for Phase 4."""
        if self.hardware_transport == "udp":
            self._start_external_listener()
            return
        self._start_serial_listener()

    def _start_serial_listener(self):
        """Start USB serial telemetry for the wired training station."""
        if self.serial_thread:
            return
        if SerialHardwareListener is None:
            message = f"Serial connector unavailable: {SERIAL_IMPORT_ERROR}"
            self.last_event_msg = message
            self._update_info_overlay()
            print(f"[Serial] {message}")
            return
        try:
            self.serial_thread = SerialHardwareListener(self.serial_port, self.serial_baudrate)
            self.serial_thread.message_received.connect(self._on_serial_message)
            self.serial_thread.connection_changed.connect(self._on_serial_connection_changed)
            self.serial_thread.start()
            print(f"[Serial] Listener starting on {self.serial_port} @ {self.serial_baudrate}")
        except Exception as e:
            self.serial_thread = None
            print(f"[Serial] Failed to start serial listener: {e}")

    def _on_serial_connection_changed(self, connected: bool, message: str):
        state = "connected" if connected else "disconnected"
        print(f"[Serial] {state}: {message}")
        if not connected and message and message != "Serial disconnected":
            self.last_event_msg = message
            self._update_info_overlay()

    def _on_serial_message(self, msg: str):
        print(f"[Serial] Received: {msg}")
        self._on_external_message(msg)

    def _hardware_ready(self):
        if self.hardware_transport == "serial":
            return bool(self.serial_thread and getattr(self.serial_thread, "ready", False))
        return bool(self.external_thread and getattr(self.external_thread, "ready", False))

    def _hardware_last_error(self):
        try:
            if self.hardware_transport == "serial" and self.serial_thread:
                return getattr(self.serial_thread, "last_error", "")
            if self.external_thread:
                return getattr(self.external_thread, "last_error", "")
        except Exception:
            return ""
        return ""

    def _start_external_listener(self):
        """启动UDP监听，接收MCU信号驱动Phase4"""
        if self.external_thread:
            return
        try:
            self.external_thread = ExternalUDPListener(self.board_ip, self.board_port, self.local_udp_port)
            self.external_thread.message_received.connect(self._on_external_message)
            self.external_thread.start()
            print(f"[External] UDP listener started on port {self.local_udp_port}")
        except Exception as e:
            print(f"[External] Failed to start UDP listener: {e}")

    def _send_start_when_ready(self, retries: int = 20):
        """确保监听socket就绪后再发送Start，避免回包落到随机端口"""
        try:
            if self._hardware_ready():
                self._send_hardware_message("HELLO_PC")
                self._send_hardware_message("Start")
                return
        except Exception:
            pass
        if retries <= 0:
            err = self._hardware_last_error()
            print(f"[Hardware] {self.hardware_transport} listener not ready, Start not sent. {err}".strip())
            return
        QTimer.singleShot(100, lambda: self._send_start_when_ready(retries - 1))

    def _on_external_message(self, msg: str):
        """处理来自MCU的UDP消息，映射到Phase4进度/事件"""
        if self._receive_blood_light(msg):
            return
        print(f"[External] Received: {msg}")
        m = msg.lower().strip()
        # 优先匹配距离指令
        if m.startswith("seq:"):
            try:
                seq_body = msg.split(":", 1)[1].strip()
                self.seq_info = seq_body
                print(f"[External] Sequence received: {seq_body}")
                self._update_info_overlay()
            except Exception:
                pass
            return

        if m.startswith("dist:") or m.startswith("pull:") or m.startswith("pos:"):
            try:
                val = float(m.split(":", 1)[1])
                self._handle_phase4_external_progress(val)
                self._update_info_overlay()
                return
            except Exception:
                pass
        if m.startswith("speed:"):
            try:
                val = float(m.split(":", 1)[1])
                self.external_speed_cmps = val
                self._update_info_overlay()
                return
            except Exception:
                pass
        # 根据MCU信号映射到预设距离
        if m == "rewind_done" or m.startswith("error: rewind"):
            self.last_event_msg = msg
            self._update_info_overlay()
            return
        mapping = {
            "pain": 5.0,
            "pain2": 10.0,
            "highdamp": 14.0,
            "lowdamp": 18.0,
            "keep": 19.0,
        }
        if m in mapping:
            self.last_event_msg = msg  # 记录最近事件信号
            print(f"[External] Event signal received: {msg}")
            self._update_info_overlay()
            self._handle_phase4_external_progress(mapping[m])

    def _update_info_overlay(self):
        """把当前外设信息实时叠加到训练界面"""
        try:
            if not self.info_overlay:
                return
            seq_line = f"Seq: {self.seq_info}" if self.seq_info else "Seq: (waiting)"
            evt_line = f"Last Event: {self.last_event_msg}" if self.last_event_msg else "Last Event: (none)"
            pos_val = self.external_pos_cm if self.external_pos_cm else getattr(self, "needle_pulled_distance_cm", 0.0)
            speed_val = self.external_speed_cmps if self.external_speed_cmps else getattr(self, "current_speed_cmps", 0.0)
            pos_line = f"Pos: {pos_val:.2f} cm"
            speed_line = f"Speed: {speed_val:.2f} cm/s"
            posture = getattr(self, "posture_status", "WAITING")
            posture_line = f"Posture: {posture}"
            overlay_text = "\n".join([seq_line, evt_line, pos_line, speed_line, posture_line])
            self.info_overlay.setText(overlay_text)
        except Exception as e:
            print(f"[External] Failed to update info overlay: {e}")

    def _handle_phase4_external_progress(self, distance_cm: float):
        """根据外部距离进度更新Phase4状态，触发对应事件/完成"""
        if self.posture_blocked:
            return
        # 如果还未进入Phase4，先启动
        if self.current_phase != 3:
            self._start_phase_4()

        # 记录外部位置
        self.external_pos_cm = distance_cm

        # 计算速度并在10秒窗口内显示
        now = time.time()
        if self.last_distance_sample_time > 0:
            dt = now - self.last_distance_sample_time
            if dt > 0:
                self.current_speed_cmps = (distance_cm - self.last_distance_sample_cm) / dt
        self.last_distance_sample_cm = distance_cm
        self.last_distance_sample_time = now

        self.needle_pulled_distance_cm = max(0.0, min(distance_cm, self.needle_full_length_cm))
        self.needle_pulled_distance = (self.needle_pulled_distance_cm / self.needle_full_length_cm) * self.needle_full_length
        self.max_pulled_distance_cm = max(self.max_pulled_distance_cm, self.needle_pulled_distance_cm)
        self.max_pulled_distance = max(self.max_pulled_distance, self.needle_pulled_distance)

        if getattr(self, "disable_camera", False):
            speed_show = self.external_speed_cmps if self.external_speed_cmps != 0 else self.current_speed_cmps
            pos_show = self.external_pos_cm if self.external_pos_cm != 0 else self.needle_pulled_distance_cm
            seq_line = f"\\nSeq: {self.seq_info}" if self.seq_info else ""
            evt_line = f"\\nLast Event: {self.last_event_msg}" if self.last_event_msg else ""
            self.camera_display.setText(f"Phase 4: awaiting hardware signals{seq_line}{evt_line}\\nPos: {pos_show:.2f} cm\\nSpeed: {speed_show:.2f} cm/s")

        # 检查事件触发
        for idx, (dist, evt_type) in enumerate(self.pull_config['events_queue']):
            if self.external_event_flags[idx]:
                continue
            if self.needle_pulled_distance_cm >= dist:
                self.external_event_flags[idx] = True
                if getattr(self, "disable_camera", False):
                    # MCU全自动模式：直接计数，不弹Quiz
                    self.phase4_events_completed = min(self.phase4_events_completed + 1, 4)
                    print(f"[External] Auto-complete event {evt_type} at {dist:.1f}cm, completed={self.phase4_events_completed}/4")
                else:
                    if evt_type == "Q3":
                        self._trigger_quiz_q3()
                    elif evt_type == "Q4":
                        self._trigger_quiz_q4()
                    elif evt_type == "Q5":
                        self._trigger_quiz_q5()

        # 完成判定：达到全程且所有事件完成计数>=4
        elapsed = time.time() - self.training_start_time if self.training_start_time else 0
        if (self.needle_pulled_distance_cm >= self.needle_full_length_cm and
                self.phase4_events_completed >= 4 and
                elapsed >= self.min_phase4_duration):
            self._phase_4_complete()
    
    def _generate_pull_config(self):
        """
        生成随机拔针配置数组
        在20cm的线上随机生成4个事件的触发位置，顺序也是随机的
        每个事件的position都是随机的2-18cm（不累加，直接是绝对位置）
        生成浮点数，确保4个值都不相同
        返回：包含随机顺序的事件列表和查询映射
        """
        import random
        
        # 生成4个不同的随机浮点数事件触发位置（绝对位置，单位：cm）
        distances = set()
        while len(distances) < 4:
            distance = round(random.uniform(2.0, 18.0), 1)
            distances.add(distance)
        
        distances_list = sorted(list(distances))  # 按升序排列，然后随机打乱顺序
        
        # 4个事件类型
        event_types = ['Q3', 'Q3', 'Q4', 'Q5']  # 两个Q3事件，一个Q4，一个Q5
        
        # 随机打乱事件的顺序
        random.shuffle(event_types)
        
        # 创建事件队列：[(距离, 事件类型), ...]
        # 这个列表按拔针顺序排列，不是按固定顺序
        events_queue = list(zip(distances_list, event_types))
        # 再次打乱，确保距离小的事件可能在任何位置
        
        config = {
            'events_queue': events_queue,  # [(2.1, 'Q4'), (4.5, 'Q3'), (8.2, 'Q5'), (15.3, 'Q3')]
            'event_map': {  # 保留用于日志/调试
                'scream_distance_1': distances_list[0] if event_types[0] == 'Q3' else None,
                'scream_distance_2': distances_list[1] if event_types[1] == 'Q3' else None,
                'high_damping_distance': distances_list[2] if event_types[2] == 'Q4' else None,
                'low_damping_distance': distances_list[3] if event_types[3] == 'Q5' else None,
            },
            'damping_after_reposition': random.randint(0, 1)
        }
        
        # 打印事件顺序用于调试
        event_order = " -> ".join([f"{evt_type}@{dist:.1f}cm" for dist, evt_type in events_queue])
        print(f"[Phase 4] Randomized event order: {event_order}")
        
        return config
    
    def _phase_4_update(self, frame, hand_data_list):
        """
        阶段4：拔针管（无硬件版本）
        在屏幕上画一条线头，用户捏着往下拔
        注射点固定，线从上往下逐渐显示
        """
        if getattr(self, "disable_camera", False):
            # 摄像头关闭时不处理帧，由外部信号驱动 _handle_phase4_external_progress
            return
        height, width = frame.shape[0], frame.shape[1]
        
        # Phase 4 拔针 - 使用手关节检测（而不是手指尖）
        # 初始化针线位置
        if self.needle_x is None:
            self.needle_x = width // 2
            self.needle_head_y = 150  # 针头（注射点）固定位置，留更多空间拉20cm，最低点Y=390
        
        # 如果因为quiz而暂停，显示等待标记但不处理拔针逻辑
        if self.quiz_paused:
            # 绘制线头（针线）
            needle_bottom = self.needle_head_y + self.needle_pulled_distance
            cv2.line(frame, (self.needle_x, self.needle_head_y), (self.needle_x, int(needle_bottom)), (100, 100, 255), 10)
            
            # 绘制黄点
            yellow_point_y = int(self.needle_head_y + self.needle_pulled_distance)
            cv2.circle(frame, (self.needle_x, yellow_point_y), 10, (0, 255, 255), -1)
            
            # 显示当前拉出的厘米数
            pull_text = f"Pull: {self.needle_pulled_distance_cm:.1f} cm / {self.needle_full_length_cm} cm"
            cv2.putText(frame, pull_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            
            # 即使暂停也要检查是否已经完全拉出（resume后马上完成）
            if self.phase4_events_completed == 4 and self.max_pulled_distance >= self.needle_full_length:
                print(f"[Phase 4] Detected completion while paused - completing NOW!")
                self._phase_4_complete()
            
            return
        
        # 检测手指捏着动作（使用拇指尖和食指PIP）
        # MediaPipe关键点：4=拇指尖, 3=拇指中间关节
        #                  8=食指尖, 7=食指中间关节（PIP）
        is_pinching = False
        pinch_y = None
        hand_near_needle = False  # 标记是否在黄点附近（仅用于显示绿色/黄色）
        
        for hand_data in hand_data_list:
            joints = hand_data.get('joints', [])
            if len(joints) >= 21:
                # 获取拇指尖（关键点4）和食指PIP（关键点7）- 反应最快
                thumb_tip = joints[4]
                index_pip = joints[7]
                t_x = thumb_tip.get('x', 0) if isinstance(thumb_tip, dict) else thumb_tip[0]
                t_y = thumb_tip.get('y', 0) if isinstance(thumb_tip, dict) else thumb_tip[1]
                i_x = index_pip.get('x', 0) if isinstance(index_pip, dict) else index_pip[0]
                i_y = index_pip.get('y', 0) if isinstance(index_pip, dict) else index_pip[1]
                
                # 检测捏着（拇指尖和食指PIP距离 < 50像素 - 非常灵敏）
                distance = np.sqrt((t_x - i_x)**2 + (t_y - i_y)**2)
                if distance < 50:
                    is_pinching = True
                    pinch_y = t_y  # 用拇指尖的Y位置（反应最快）
                    
                    # 检查是否在黄点附近（仅用于点的颜色显示）
                    yellow_point_y = self.needle_head_y + self.max_pulled_distance
                    if abs(pinch_y - yellow_point_y) < 40:
                        hand_near_needle = True
                    break
        
        # 更新拔针状态
        if is_pinching and pinch_y is not None:
            # 只有在绿色状态（手在黄点附近）拉才计数
            # 保留原来的相对计算逻辑，但只在hand_near_needle时更新max_pulled_distance
            if hand_near_needle:
                # 简化逻辑：在绿点区域时，按每帧拇指Y的增量直接累加到已拉出距离
                # 这样用户拇指往下移动多少，线就移动多少（更直观、实时）
                if self.last_pinch_y is not None:
                    delta = pinch_y - self.last_pinch_y
                    if delta > 0:
                        self.max_pulled_distance += delta

                # 限制最大值到线的完整长度（像素）
                if self.max_pulled_distance > self.needle_full_length:
                    self.max_pulled_distance = self.needle_full_length
            
            # 永远显示max_pulled_distance（不让线回退）
            self.needle_pulled_distance = min(self.max_pulled_distance, self.needle_full_length)
            
            # 转换为厘米
            self.max_pulled_distance_cm = (self.max_pulled_distance / self.needle_full_length) * self.needle_full_length_cm
            self.needle_pulled_distance_cm = (self.needle_pulled_distance / self.needle_full_length) * self.needle_full_length_cm
            
            # 记录历史用于速度计算
            self.pinch_history.append((time.time(), pinch_y))
            
            # 计算拔的速度（最近100ms内的速度）
            current_time = time.time()
            recent_pinches = [p for p in self.pinch_history if current_time - p[0] < 0.1]
            if len(recent_pinches) >= 2:
                time_diff = recent_pinches[-1][0] - recent_pinches[0][0]
                if time_diff > 0:
                    speed = abs(recent_pinches[-1][1] - recent_pinches[0][1]) / time_diff  # 像素/秒
                    # 如果速度过快（> 800像素/秒）
                    if speed > 800:
                        self.pull_speed_warning_time = current_time
            
            self.last_pinch_y = pinch_y
            self.pinching = True
            
            # 更新手是否在黄点附近的state（一旦在黄点附近捏着，保持状态直到手松开）
            if hand_near_needle:
                self.hand_pinching_near_needle = True
        else:
            self.pinching = False
            self.pinch_history = []
            # 手松开时重置状态，下次捏住时重新开始计算增量
            self.pull_start_y = None
            self.last_pinch_y = None
            self.hand_pinching_near_needle = False  # 手松开时重置state
        
        # 清除超过1秒的历史数据
        current_time = time.time()
        self.pinch_history = [p for p in self.pinch_history if current_time - p[0] < 1.0]
        
        # 绘制线头（针线）
        # 线的顶部固定在needle_head_y，底部根据拉出距离扩展
        needle_bottom = self.needle_head_y + self.needle_pulled_distance
        
        # 绘制线条（宽度10，蓝色）
        cv2.line(frame, (self.needle_x, self.needle_head_y), (self.needle_x, int(needle_bottom)), (100, 100, 255), 10)
        
        # 绘制黄点（显示当前已拉出的最大距离）
        # 如果手在黄点附近且捏着，显示绿色；保持这个状态直到手完全松开
        yellow_point_y = int(self.needle_head_y + self.needle_pulled_distance)
        point_color = (0, 255, 0) if self.hand_pinching_near_needle else (0, 255, 255)  # 绿色或黄色
        cv2.circle(frame, (self.needle_x, yellow_point_y), 10, point_color, -1)
        
        # 显示拉出的厘米数
        pull_text = f"Pull: {self.needle_pulled_distance_cm:.1f} cm / {self.needle_full_length_cm} cm"
        cv2.putText(frame, pull_text, (20, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        
        # 显示速度过快警告
        if self.pull_speed_warning_time and (current_time - self.pull_speed_warning_time) < 1.5:
            text = "Pull too fast"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1.0
            thickness = 2
            # compute text size and place at bottom-right with 20px margin
            (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
            x = max(10, width - text_w - 20)
            y = max(text_h + 10, height - 20)
            cv2.putText(frame, text, (x, y), font, font_scale, (0, 0, 255), thickness)
        
        # 检查是否拔到了关键点，触发问题
        # 支持新的 pull_config['events_queue'] 格式：[(dist_cm, event_type), ...]
        try:
            events_queue = self.pull_config.get('events_queue', None) if isinstance(self.pull_config, dict) else None
        except Exception:
            events_queue = None

        # 如果存在新的事件队列，按队列顺序触发事件（队列已随机化）
        if events_queue and isinstance(events_queue, (list, tuple)) and len(events_queue) > 0:
            # 将队列中当前待触发事件（由 phase4_events_completed 指示）的厘米值转换为像素阈值
            next_idx = int(self.phase4_events_completed)
            if next_idx < len(events_queue):
                dist_cm, evt_type = events_queue[next_idx]
                threshold_px = (dist_cm / self.needle_full_length_cm) * self.needle_full_length
                print(f"[Phase 4] Pulled: {self.needle_pulled_distance_cm:.1f}cm, Next event: {evt_type}@{dist_cm:.1f}cm (px {threshold_px:.0f}), Progress: {self.phase4_events_completed}/{len(events_queue)}")
                if self.max_pulled_distance >= threshold_px:
                    # 触发对应事件
                    if evt_type == 'Q3':
                        print(f"[Phase 4] Triggering Q3 at {self.max_pulled_distance_cm:.1f}cm")
                        self._trigger_quiz_q3()
                    elif evt_type == 'Q4':
                        print(f"[Phase 4] Triggering Q4 at {self.max_pulled_distance_cm:.1f}cm")
                        self._trigger_quiz_q4()
                    elif evt_type == 'Q5':
                        print(f"[Phase 4] Triggering Q5 at {self.max_pulled_distance_cm:.1f}cm")
                        self._trigger_quiz_q5()
                    else:
                        print(f"[Phase 4] Unknown event type: {evt_type}")
        else:
            # 兼容旧配置（scream_distance_1 等），保持向后兼容
            try:
                scream_len_1 = self.pull_config['scream_distance_1']
                scream_len_2 = self.pull_config['scream_distance_2']
                high_damp_len = self.pull_config['high_damping_distance']
                low_damp_len = self.pull_config['low_damping_distance']

                # 将配置长度（厘米）转换到像素长度（直接转换，不累加）
                q3_first_threshold = (scream_len_1 / self.needle_full_length_cm) * self.needle_full_length
                q3_second_threshold = (scream_len_2 / self.needle_full_length_cm) * self.needle_full_length
                q4_threshold = (high_damp_len / self.needle_full_length_cm) * self.needle_full_length
                q5_threshold = (low_damp_len / self.needle_full_length_cm) * self.needle_full_length

                # 调试输出
                print(f"[Phase 4] Pulled: {self.needle_pulled_distance_cm:.1f}cm, Events: {self.phase4_events_completed}/4, Thresholds(px): Q3_1={q3_first_threshold:.0f}, Q3_2={q3_second_threshold:.0f}, Q4={q4_threshold:.0f}, Q5={q5_threshold:.0f}")

                if self.phase4_events_completed == 0 and self.max_pulled_distance >= q3_first_threshold:
                    print(f"[Phase 4] Event 1/4: First scream at {self.max_pulled_distance_cm:.1f}cm - triggering Q3")
                    self._trigger_quiz_q3()
                elif self.phase4_events_completed == 1 and self.max_pulled_distance >= q3_second_threshold:
                    print(f"[Phase 4] Event 2/4: Second scream at {self.max_pulled_distance_cm:.1f}cm - triggering Q3")
                    self._trigger_quiz_q3()
                elif self.phase4_events_completed == 2 and self.max_pulled_distance >= q4_threshold:
                    print(f"[Phase 4] Event 3/4: High resistance at {self.max_pulled_distance_cm:.1f}cm - triggering Q4")
                    self._trigger_quiz_q4()
                elif self.phase4_events_completed == 3 and self.max_pulled_distance >= q5_threshold:
                    print(f"[Phase 4] Event 4/4: Low resistance at {self.max_pulled_distance_cm:.1f}cm - triggering Q5")
                    self._trigger_quiz_q5()
            except Exception:
                # 如果旧配置也不存在，忽略
                print("[Phase 4] No valid pull_config found for event triggers")

        # 完成检查：如果已经完成所有事件并且拉到末端则完成训练
        if self.phase4_events_completed >= 4 and self.max_pulled_distance >= self.needle_full_length:
            print(f"[Phase 4] All events completed or counter>=4, needle fully extracted ({self.max_pulled_distance_cm:.1f}cm) - training complete NOW!!!")
            self._phase_4_complete()
        
        # 绘制手骨骼点
        self._draw_hand_skeleton(frame, hand_data_list)
    
    def _trigger_quiz_q3(self):
        """触发Q3：尖叫时的处理"""
        self.text_display.set_text("Patient screams! - Do Q3")
        self.text_display.fade_in(duration_ms=300)
        
        # 记录事件触发时间
        # append an event trigger (allow duplicates for Q3 twice)
        trigger_time = time.time() - self.training_start_time if self.training_start_time else 0
        # store trigger time (keep multiple occurrences)
        idx = len([k for k in self.events_triggered.keys() if k == "Q3"]) if isinstance(self.events_triggered, dict) else 0
        # keep a simple map for quick debug, but also push into events_results list with correct flag=None
        self.events_triggered.setdefault("Q3", []).append(trigger_time)
        self.events_results.append({'question_id': 'Q3', 'trigger_time': trigger_time, 'correct': None})
        
        # 播放pain.mp3音频
        if self.media_player:
            try:
                pain_audio_path = os.path.join(os.getcwd(), 'assets', 'pain.mp3')
                if os.path.exists(pain_audio_path):
                    self.media_player.setSource(QUrl.fromLocalFile(pain_audio_path))
                    self.media_player.play()
                    print(f"[Phase 4] Playing pain.mp3")
                else:
                    print(f"[Phase 4] Pain audio file not found: {pain_audio_path}")
            except Exception as e:
                print(f"[Phase 4] Error playing pain.mp3: {e}")
        
        self.quiz_triggered.emit("Q3")
    
    def _trigger_quiz_q4(self):
        """触发Q4：高阻尼"""
        self.text_display.set_text("High resistance! - Do Q4")
        self.text_display.fade_in(duration_ms=300)
        
        # 记录事件触发时间
        trigger_time = time.time() - self.training_start_time if self.training_start_time else 0
        self.events_triggered.setdefault("Q4", []).append(trigger_time)
        self.events_results.append({'question_id': 'Q4', 'trigger_time': trigger_time, 'correct': None})
        
        self.quiz_triggered.emit("Q4")
    
    def _trigger_quiz_q5(self):
        """触发Q5：低阻尼"""
        self.text_display.set_text("Low resistance! - Do Q5")
        self.text_display.fade_in(duration_ms=300)
        
        # 记录事件触发时间
        trigger_time = time.time() - self.training_start_time if self.training_start_time else 0
        self.events_triggered.setdefault("Q5", []).append(trigger_time)
        self.events_results.append({'question_id': 'Q5', 'trigger_time': trigger_time, 'correct': None})
        
        self.quiz_triggered.emit("Q5")
    
    def _phase_4_complete(self):
        """Phase 4完成，拔针成功"""
        # Avoid scheduling multiple completion timers if this is called repeatedly
        if getattr(self, '_phase4_complete_called', False):
            print("[Phase 4] _phase_4_complete already handled, skipping duplicate call")
            return
        self._phase4_complete_called = True
        # 计算训练耗时
        elapsed_time = 0
        if self.training_start_time:
            elapsed_time = time.time() - self.training_start_time
        
        # 显示成功消息和耗时
        success_text = f"Needle removed successfully!\nTime: {elapsed_time:.1f}s"
        self.text_display.set_text(success_text)
        self.text_display.fade_in(duration_ms=500)
        
        # 显示success动画和音效（持续2秒），随后显示pass统计（持续5秒）
        # 成功时间固定为拔针完成时刻的快照（elapsed_time 已计算）
        # 先显示 success（立即显示）
        self.success_display.show_success(
            audio_path=self.audio_success,
            duration_ms=2000
        )

        # 在 success 结束后立刻显示 pass（2s 后）
        # 保存一个快照，确保后续不会被重算或改变
        self._pass_elapsed_snapshot = elapsed_time
        # Use an actual QTimer for the pass display so we can cancel if Back is pressed
        show_pass_timer = QTimer(self)
        show_pass_timer.setSingleShot(True)
        show_pass_timer.timeout.connect(lambda: self.success_display.show_pass(duration_ms=5000, elapsed_time=elapsed_time))
        show_pass_timer.start(2000)
        # schedule completion with a cancellable timer (2s + 5s)
        self._complete_timer = QTimer(self)
        self._complete_timer.setSingleShot(True)
        self._complete_timer.timeout.connect(self._complete_training)
        self._complete_timer.start(7000)
    
    def _complete_training(self):
        """训练完成，保存训练记录"""
        if getattr(self, '_training_complete_called', False):
            print("[RemoveNeedleTraining] _complete_training already called, skipping.")
            return
        self._training_complete_called = True
        # Use snapshot elapsed time if available (so pass display is stable)
        elapsed_time = getattr(self, '_pass_elapsed_snapshot', None)
        if elapsed_time is None:
            elapsed_time = 0
            if self.training_start_time:
                elapsed_time = time.time() - self.training_start_time
        
        # 计算正确率：优先使用每次quiz的结果记录（events_results）
        accuracy = 0
        try:
            total_expected = 4.0
            if self.events_results:
                correct_count = sum(1 for e in self.events_results if e.get('correct') is True)
                accuracy = (correct_count / total_expected) * 100
            else:
                # Fallback to phase4_events_completed counter
                accuracy = (self.phase4_events_completed / total_expected) * 100 if self.phase4_events_completed > 0 else 0
        except Exception:
            accuracy = 0
        
        # 保存训练记录
        try:
            manager = get_training_record_manager()
            # 获取当前用户名（从主窗口传入，或默认值）
            username = getattr(self, 'current_user', 'unknown')
            
            # 准备训练数据
            training_data = {
                'training_type': self.training_mode,  # 记录training类型
                'training_mode': self.training_mode,  # 兼容旧字段
                'elapsed_time': elapsed_time,
                'accuracy': accuracy,  # 正确率（0-100%）
                'events_triggered': self.events_triggered,
                'events_results': self.events_results,
                'max_pull_distance': self.max_pulled_distance_cm,
                'pull_config': self.pull_config,
                'completed_at': datetime.now().isoformat()
            }
            
            # 保存记录
            manager.save_training_record(username, training_data)
            print(f"[Training] Record saved for {username}: type={self.training_mode}, accuracy={accuracy:.1f}%, time={elapsed_time:.1f}s")
        except Exception as e:
            print(f"[Training] Error saving training record: {e}")
            import traceback
            traceback.print_exc()
        
        # 清理资源并发出完成信号
        self._request_hardware_rewind()
        self.cleanup()
        self.training_completed.emit()
    
    def _request_hardware_rewind(self):
        """Ask the MCU to rewind after simulator-backed training finishes."""
        if not self.auto_rewind_after_training:
            print("[Hardware] Auto rewind disabled by SURGERYBOX_AUTO_REWIND")
            return
        if self.training_mode != "remove_needle_simulator":
            return
        try:
            if self._send_hardware_message("Winding"):
                print("[Hardware] Auto rewind requested after training")
            else:
                print("[Hardware] Auto rewind request skipped; hardware transport not ready")
        except Exception as e:
            print(f"[Hardware] Auto rewind request failed: {e}")

    def cleanup(self):
        """清理资源"""
        self._close_blood_light()
        if getattr(self, "_cleanup_done", False):
            return
        self._cleanup_done = True
        try:
            print(f"[RemoveNeedleTraining.cleanup] Starting cleanup")
            try:
                if self.serial_thread:
                    print("[Serial] Stopping serial listener")
                    self.serial_thread.stop()
                    try:
                        self.serial_thread.wait(1000)
                    except Exception:
                        pass
                    self.serial_thread = None
            except Exception:
                pass
            # 关闭外部UDP线程
            try:
                if self.external_thread:
                    print("[External] Stopping external UDP listener")
                    self.external_thread.stop_flag = True
                    try:
                        # 发送一个空包唤醒阻塞
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        sock.sendto(b"", ("127.0.0.1", self.local_udp_port))
                        sock.close()
                    except Exception:
                        pass
                    try:
                        self.external_thread.wait(1000)
                    except Exception:
                        pass
                    self.external_thread = None
            except Exception:
                pass
            
            # 停止阶段计时器
            try:
                if self.imu_thread:
                    print("[IMU] Stopping posture listener")
                    self.imu_thread.stop_flag = True
                    try:
                        self.imu_thread.wait(1000)
                    except Exception:
                        pass
                    self.imu_thread = None
            except Exception:
                pass

            if self.phase_timer:
                print(f"[RemoveNeedleTraining.cleanup] Stopping phase_timer")
                self.phase_timer.stop()
                self.phase_timer = None
            
            # 停止文字淡出计时器
            if self.text_display and self.text_display.fade_timer:
                print(f"[RemoveNeedleTraining.cleanup] Stopping text fade_timer")
                self.text_display.fade_timer.stop()
                self.text_display.fade_timer = None
            
            # 停止成功显示计时器
            if self.success_display and self.success_display.success_timer:
                print(f"[RemoveNeedleTraining.cleanup] Stopping success_timer")
                self.success_display.success_timer.stop()
                self.success_display.success_timer = None
            
            # 停止摄像头线程并安全等待结束
            if self.camera_thread:
                try:
                    print(f"[RemoveNeedleTraining.cleanup] Stopping camera_thread")
                    try:
                        # disconnect signal to avoid slots being called during teardown
                        try:
                            self.camera_thread.frame_ready.disconnect(self._on_frame_ready)
                        except Exception:
                            pass
                        # Ask thread to stop and quit
                        self.camera_thread.is_running = False
                        try:
                            self.camera_thread.quit()
                        except Exception:
                            pass
                        # Wait up to 3 seconds
                        waited = self.camera_thread.wait(3000)
                        print(f"[RemoveNeedleTraining.cleanup] camera_thread.wait returned: {waited}")
                        if not waited:
                            print("[RemoveNeedleTraining.cleanup] camera_thread did not stop within 2s, forcing stop()")
                            try:
                                self.camera_thread.stop()
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"[RemoveNeedleTraining.cleanup] Error while stopping thread: {e}")
                    print(f"[RemoveNeedleTraining.cleanup] Camera thread stopped")
                except Exception as e:
                    print(f"[RemoveNeedleTraining.cleanup] Error stopping camera thread: {e}")
                finally:
                    self.camera_thread = None

            # Stop scheduled completion timer if present
            try:
                if hasattr(self, '_complete_timer') and self._complete_timer:
                    self._complete_timer.stop()
                    self._complete_timer = None
            except Exception:
                pass
            
            print(f"[RemoveNeedleTraining.cleanup] Cleanup complete")
        except Exception as e:
            print(f"[RemoveNeedleTraining.cleanup] Error in cleanup: {e}")

    # Helpers used by SuccessDisplay callbacks
    def _hide_and_delete_pass_widget(self):
        try:
            if hasattr(self, 'success_display') and hasattr(self.success_display, 'pass_widget') and self.success_display.pass_widget:
                self.success_display.pass_widget.hide()
                self.success_display.pass_widget.deleteLater()
                self.success_display.pass_widget = None
        except Exception:
            pass
    
    def pause_phase4(self):
        """暂停Phase 4的拔针操作（用于在quiz出现时停止）"""
        self.quiz_paused = True
        # 不重置pull_start_y，这样quiz完成后，线不会回去
        print(f"[RemoveNeedleTraining] Phase 4 paused for quiz")
    
    def resume_phase4(self, quiz_correct=False):
        """恢复Phase 4的拔针操作（用于在quiz完成后）
        
        Args:
            quiz_correct: 是否正确回答了quiz（全部答对）
        """
        if getattr(self, "disable_camera", False):
            # MCU自动模式下不使用Quiz计数，直接返回
            return
        self.quiz_paused = False
        
        # 只有正确回答quiz才增加事件计数
        if quiz_correct:
            self.phase4_events_completed += 1
            print(f"[RemoveNeedleTraining] Quiz answered correctly! Events completed: {self.phase4_events_completed}/4")
        else:
            print(f"[RemoveNeedleTraining] Quiz answered incorrectly. Events still: {self.phase4_events_completed}/4")
        
        # 重置拉线状态，使后续拉线灵敏度恢复正常
        self.pull_start_y = None
        self.pinch_history = []
        self.hand_pinching_near_needle = False
        print(f"[RemoveNeedleTraining] Phase 4 resumed after quiz")

    def record_quiz_result(self, question_id: str, is_correct: bool):
        """Record the result for a triggered quiz question.

        This appends to events_results and also marks the last matching event's correctness.
        """
        try:
            # find the first events_results entry with this question_id that has correct==None
            for entry in self.events_results:
                if entry.get('question_id') == question_id and entry.get('correct') is None:
                    entry['correct'] = bool(is_correct)
                    break
            else:
                # no existing entry, append one (defensive)
                trigger_time = time.time() - self.training_start_time if self.training_start_time else 0
                self.events_results.append({'question_id': question_id, 'trigger_time': trigger_time, 'correct': bool(is_correct)})

            # Phase 4 progress is advanced in resume_phase4() exactly once.
        except Exception as e:
            print(f"[RemoveNeedleTraining] Error recording quiz result: {e}")
    def _send_hardware_message(self, msg: str):
        """Send a command through the active hardware transport."""
        if self.hardware_transport == "serial":
            if self.serial_thread and self.serial_thread.send_message(msg):
                print(f"[Serial->MCU] Sent: {msg}")
                return True
            print(f"[Serial->MCU] Send skipped; serial not ready: {msg}")
            return False
        self._send_to_mcu(msg)
        return True

    def _send_to_mcu(self, msg: str):
        """向MCU发送UDP消息，并打印日志"""
        # 优先使用监听线程的socket保证源端口一致
        if self.external_thread and self.external_thread.send_message(msg):
            print(f"[External->MCU] Sent via listener: {msg}")
            return
        # 退化路径：使用临时socket（源端口随机，MCU回包可能到别的端口）
        try:
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            temp_sock.sendto(msg.encode(), (self.board_ip, self.board_port))
            temp_sock.close()
            print(f"[External->MCU] Sent via temp socket: {msg}")
        except Exception as e:
            print(f"[External->MCU] Send error: {e}")
