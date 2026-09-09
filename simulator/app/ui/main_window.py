from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QStackedWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFrame, QListWidget, QListWidgetItem, QSlider, QComboBox,
    QTextEdit, QScrollArea, QApplication
)
from PySide6.QtGui import QFont, QPixmap

# Multimedia for background music and click sounds
try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaPlaylist, QSoundEffect
    from PySide6.QtMultimediaWidgets import QVideoWidget
except Exception:
    # Some PySide6 builds may not provide QMediaPlaylist; fallback gracefully
    try:
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QSoundEffect
        from PySide6.QtMultimediaWidgets import QVideoWidget
        QMediaPlaylist = None
    except Exception:
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QSoundEffect
        QMediaPlaylist = None
        QVideoWidget = None

import os
import random
import json
import re
from pathlib import Path

from app.config import APP_NAME, APP_VERSION
from app.ui.login_page import LoginPage
from app.camera_manager import CameraManager
from app.hardware_connector import HardwareConnector
from app.ui.theme import Theme, qss_for
from app.ui.widgets import section_placeholder
from app.ui.settings_widget import SettingsWidget
from app.ui.ai_report_widgets import AIReportWorker, AiLoadingIndicator
from app.i18n import get_language, language_options, set_language, tr, tr_training_label
from app.storage import write_profile_if_missing
from app.quiz_module import QuizModule


_SIMULATOR_DIR = Path(__file__).resolve().parents[2]
_PROJECT_DIR = _SIMULATOR_DIR.parent


def _asset_path(filename: str) -> str:
    raw = str(filename).replace("\\", "/")
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    if raw.startswith("assets/"):
        raw = raw[len("assets/"):]
    candidates = [
        _SIMULATOR_DIR / "assets" / raw,
        Path.cwd() / "assets" / raw,
        Path.cwd().parent / "assets" / raw,
        _PROJECT_DIR / "assets" / raw,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} - {APP_VERSION}")
        self.setMinimumSize(1100, 700)  # 适配横屏平板与笔记本

        self.theme = Theme("light")
        self.setStyleSheet(qss_for(self.theme))

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Login as first widget
        self.login = LoginPage()
        self.login.logged_in.connect(self._on_login)
        self.stack.addWidget(self.login)

        self.main = None
        if hasattr(self.login, "clear_fields"):
            self.login.clear_fields()
        if hasattr(self.login, "_apply_language_texts"):
            self.login._apply_language_texts()
        self.stack.setCurrentWidget(self.login)

    def _on_login(self, user):
        write_profile_if_missing(user.username, user.role)

        # Route to a role-specific shell after login.
        if user.role == "trainer":
            from app.ui.teacher_shell import TeacherShell
            self.main = TeacherShell(user=user, on_logout=self._logout, on_toggle_theme=self._toggle_theme)
        else:
            self.main = StudentShell(user=user, on_logout=self._logout, on_toggle_theme=self._toggle_theme)
        account_theme = self._theme_for_user(user.username, user.role)
        self.theme = account_theme
        self.setStyleSheet(qss_for(account_theme))
        if hasattr(self.main, "apply_theme"):
            self.main.apply_theme(account_theme)
        self.stack.addWidget(self.main)
        self.stack.setCurrentWidget(self.main)

        # Start welcome behaviors when the shell supports them.
        if hasattr(self.main, "start_welcome"):
            self.main.start_welcome()


    def _logout(self):
        if hasattr(self, 'main') and self.main and hasattr(self.main, '_stop_manual_rewind'):
            try:
                self.main._stop_manual_rewind(silent=True)
            except Exception:
                pass
        # Clean up camera manager if it exists
        if hasattr(self, 'main') and self.main and hasattr(self.main, 'camera_manager_widget'):
            try:
                self.main.camera_manager_widget.cleanup()
            except Exception:
                pass
        
        # Stop music playback completely before returning to login
        if hasattr(self, 'main') and self.main and hasattr(self.main, 'music_player'):
            if self.main.music_player:
                try:
                    self.main.music_player.stop()
                    # Also ensure volume is muted
                    if hasattr(self.main, 'music_audio_output') and self.main.music_audio_output:
                        self.main.music_audio_output.setVolume(0.0)
                except Exception:
                    pass
        
        # Reset theme to light before returning to login page
        self.theme = Theme("light")
        self.setStyleSheet(qss_for(self.theme))
        
        if hasattr(self.login, "clear_fields"):
            self.login.clear_fields()
        self.stack.setCurrentWidget(self.login)

    def _toggle_theme(self):
        if not self.main or not hasattr(self.main, "user"):
            return

        username = self.main.user.username
        role = self.main.user.role
        theme_names = getattr(self.main, "theme_names", ("light", "dark"))
        current = self._theme_for_user(username, role)
        try:
            current_index = theme_names.index(current.name)
        except ValueError:
            current_index = 0
        next_theme = Theme(theme_names[(current_index + 1) % len(theme_names)])
        self._save_theme_for_user(username, next_theme.name)
        self.theme = next_theme
        self.setStyleSheet(qss_for(next_theme))

        if hasattr(self.main, "apply_theme"):
            self.main.apply_theme(next_theme)

    def _user_settings_path(self):
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "user_settings.json")
        )

    def _load_user_settings(self):
        path = self._user_settings_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            print(f"[Settings] Failed to load user settings: {exc}")
            return {}

    def _save_user_settings(self, settings):
        path = self._user_settings_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as exc:
            print(f"[Settings] Failed to save user settings: {exc}")

    def _default_theme_name_for_role(self, role):
        return "student_blue" if role == "trainee" else "light"

    def _theme_for_user(self, username, role=None):
        settings = self._load_user_settings()
        themes = settings.get("themes_by_user", {})
        if not isinstance(themes, dict):
            themes = {}

        default_theme = self._default_theme_name_for_role(role)
        theme_name = themes.get(username, default_theme)
        if theme_name not in ("student_blue", "light", "dark"):
            theme_name = default_theme
        return Theme(theme_name)

    def _save_theme_for_user(self, username, theme_name):
        settings = self._load_user_settings()
        themes = settings.get("themes_by_user", {})
        if not isinstance(themes, dict):
            themes = {}

        themes[username] = theme_name if theme_name in ("student_blue", "light", "dark") else "light"
        settings["themes_by_user"] = themes
        self._save_user_settings(settings)

class StudentShell(QWidget):
    # Placeholder quotes - replace the strings below with your 5 short nursing quotes
    QUOTES = [
        "The most important practical lesson that can be given to nurses is to teach them what to observe.",
        "Nursing is an art: and if it is to be made an art, it requires as exclusive a devotion as any painter's or sculptor's work.",
        "Nursing is a profession, not a task.",
        "The nurse is the last line of defence.",
        "When in doubt, stop and escalate.",
    ]

    def __init__(self, user, on_logout, on_toggle_theme, parent=None):
        super().__init__(parent)
        # identify root widget for specific stylesheet overrides
        self.setObjectName("StudentShell")
        self.user = user
        self.on_logout = on_logout
        self.on_toggle_theme = on_toggle_theme
        self.theme_name = "student_blue"
        self.theme_names = ("student_blue", "light", "dark")
        self.student_heading_font = "Aptos"
        self.student_body_font = "Aptos"
        self.student_mono_font = "Cascadia Mono"
        self.manual_rewind_serial = None
        self.manual_rewind_active = False
        self.manual_rewind_pending = False
        try:
            self.manual_rewind_timeout_ms = int(os.getenv("SURGERYBOX_MANUAL_REWIND_MS", "7000"))
        except ValueError:
            self.manual_rewind_timeout_ms = 7000
        self.manual_rewind_timer = QTimer(self)
        self.manual_rewind_timer.setSingleShot(True)
        self.manual_rewind_timer.timeout.connect(self._on_manual_rewind_timeout)

        # --- click sound (default) ---
        self.click_sfx = QSoundEffect()
        click_path = _asset_path('click.wav')
        if os.path.exists(click_path):
            self.click_sfx.setSource(QUrl.fromLocalFile(click_path))
        else:
            self.click_sfx = None

        # --- background music setup (will be started by start_welcome) ---
        music_path = _asset_path('background.mp3')
        self.music_player = None
        if os.path.exists(music_path):
            try:
                self.music_player = QMediaPlayer()
                self.music_audio_output = QAudioOutput()
                self.music_player.setAudioOutput(self.music_audio_output)
                self.music_audio_output.setVolume(0.2)

                # Prefer QMediaPlaylist when available; otherwise set source and loop manually
                if QMediaPlaylist is not None:
                    self.music_playlist = QMediaPlaylist()
                    self.music_playlist.addMedia(QUrl.fromLocalFile(music_path))
                    self.music_playlist.setPlaybackMode(QMediaPlaylist.Loop)
                    self.music_player.setPlaylist(self.music_playlist)
                else:
                    # Fallback: set source and reconnect on stop to loop
                    self.music_player.setSource(QUrl.fromLocalFile(music_path))
                    try:
                        self.music_player.playbackStateChanged.connect(self._on_music_state_changed)
                    except Exception:
                        # older/newer bindings may use different signal names; ignore if unavailable
                        pass
            except Exception:
                self.music_player = None
        else:
            self.music_player = None

        # Background image for main shell (if provided). Use a QLabel so it is visible despite app-wide QWidget styles.
        bg_path = _asset_path('backgroundMain.jpg')
        if not os.path.exists(bg_path):
            fb = _asset_path('background.jpg')
            if os.path.exists(fb):
                bg_path = fb
            else:
                bg_path = None

        self.bg = None
        if bg_path:
            try:
                pix = QPixmap(bg_path)
                if not pix.isNull():
                    self.bg = QLabel(self)
                    self.bg.setPixmap(pix)
                    self.bg.setScaledContents(True)
                    self.bg.setGeometry(self.rect())
                    self.bg.lower()  # send to back
            except Exception:
                self.bg = None

        # Ensure top/left/content use the hand-drawn font and blue color

        # Load and apply user's font preference
        self._load_and_apply_user_font()

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        # apply a default handwritten font (less cursive) to all child widgets
        try:
            self.setFont(QFont('Segoe Print', 16))
        except Exception:
            pass

        # Top bar (themed translucent strip)
        self.top_bar = QFrame()
        self.top_bar.setObjectName("TopBar")
        top_l = QHBoxLayout(self.top_bar)
        top_l.setContentsMargins(14, 10, 14, 10)
        top_l.setSpacing(10)

        self.left_title = QLabel(tr("app.header"))
        self.left_title.setObjectName("Header")
        top_l.addWidget(self.left_title)
        top_l.addStretch(1)

        # Language selector temporarily disabled
        # self.lang = QComboBox()
        # self.lang.addItems(["English", "中文（繁體）(dev)", "中文（简体）(dev)"])
        # self.lang.setStyleSheet("font-family: 'Segoe Script', cursive; font-size:14px;")
        # self.lang.currentIndexChanged.connect(lambda _: self._on_button_click(lambda: self._set_content("Language switching (dev)")))
        # top_l.addWidget(self.lang)

        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LanguageCombo")
        for code, label in language_options():
            self.lang_combo.addItem(label, code)
        current_lang = get_language()
        for idx in range(self.lang_combo.count()):
            if self.lang_combo.itemData(idx) == current_lang:
                self.lang_combo.setCurrentIndex(idx)
                break
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        top_l.addWidget(self.lang_combo)

        # Reset Simulator button
        self.btn_reset_sim = QPushButton(tr("student.reset_simulator"))
        self.btn_reset_sim.clicked.connect(lambda: self._on_button_click(self._reset_simulator))
        top_l.addWidget(self.btn_reset_sim)

        # Background music mute toggle (default: playing/unmuted).
        self.btn_mute = QPushButton(tr("student.mute"))
        self.btn_mute.setCheckable(True)
        self.btn_mute.clicked.connect(lambda: self._on_button_click(self._toggle_music))
        top_l.addWidget(self.btn_mute)

        # Simulator Connection Debug (new)
        self.btn_sim_conn = QPushButton(tr("student.simulator"))
        self.btn_sim_conn.clicked.connect(lambda: self._on_button_click(self._show_simulator_connection))
        top_l.addWidget(self.btn_sim_conn)

        # Per-account theme toggle for the student shell.
        self.btn_theme = QPushButton(tr("common.theme"))
        self.btn_theme.clicked.connect(lambda: self._on_button_click(self.on_toggle_theme))
        top_l.addWidget(self.btn_theme)

        # Settings (placeholder)
        self.btn_settings = QPushButton(tr("common.settings"))
        self.btn_settings.clicked.connect(lambda: self._on_button_click(self._show_settings))
        top_l.addWidget(self.btn_settings)

        # Logout
        self.btn_logout = QPushButton(tr("common.logout_user", username=self.user.username))
        self.btn_logout.clicked.connect(lambda: self._on_button_click(self._logout_from_student_shell))
        top_l.addWidget(self.btn_logout)

        # Unified button style (boxed look)
        btn_style = """
            QPushButton {
                background: rgba(255,255,255,0.6);
                border: 1px solid rgba(0,0,0,0.06);
                padding: 6px 10px;
                border-radius: 8px;
                font-family: 'Segoe Print', 'Segoe UI', Arial;
                font-size: 16px;
                color: #003366;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.75);
            }
            QPushButton:pressed {
                background: rgba(0,0,0,0.08);
            }
        """
        self.top_buttons = self.top_bar.findChildren(QPushButton)
        for w in self.top_buttons:
            w.setStyleSheet(btn_style)

        root.addWidget(self.top_bar)

        # Body: left menu + content
        body = QHBoxLayout()
        body.setSpacing(12)

        # Left menu
        self.menu_panel = QFrame()
        self.menu_panel.setObjectName("Card")
        menu_l = QVBoxLayout(self.menu_panel)
        menu_l.setContentsMargins(10, 10, 10, 10)
        menu_l.setSpacing(8)

        self.menu_list = QListWidget()
        self.menu_list.setStyleSheet("QListWidget{border:0px; background: transparent;} QListWidget::item{padding:12px;border-radius:10px; color: #003366;}")
        self.menu_list.setFont(QFont('Segoe Script', 12))

        items = [
            (tr("menu.welcome"), "welcome"),
            (tr("menu.simulation"), "simulation"),
            (tr("menu.elearning"), "elearning"),
            (tr("menu.practice"), "practice"),
            (tr("menu.practice_records"), "practice_records"),
            (tr("menu.training_records"), "training_records"),
            (tr("menu.ai_mentor"), "ai_mentor"),  # 新增AI对话菜单
            # ("Report Records", "reports"),
        ]
        # Teacher-only modules live in TeacherShell; the student shell stays training-focused.

        self._menu_items = {}
        for text, key in items:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, key)

            it.setFont(QFont('Segoe Print', 14))
            self.menu_list.addItem(it)
            self._menu_items[key] = it

        self.menu_list.currentItemChanged.connect(self._on_menu)
        # Start with Welcome selected (index 0)
        self.menu_list.setCurrentRow(0)

        self.modules_label = QLabel(tr("student.modules"))
        self.modules_label.setObjectName("ModulesLabel")
        self.modules_label.setFont(QFont(self.student_heading_font, 22, QFont.Bold))
        menu_l.addWidget(self.modules_label)

        # menu list style: transparent bg; items styled as button-like with selection state using Segoe Print
        self.menu_list.setStyleSheet("""
            QListWidget{border:0px; background: transparent;}
            QListWidget::item{padding:14px;border-radius:10px; color: #003366; font-family: 'Segoe Print', 'Segoe UI', Arial; font-size:20px;}
            QListWidget::item:selected{background: rgba(77,163,255,0.12); border-left:4px solid #4DA3FF; color: #003366; font-weight:700;}
        """)
        self.menu_list.setSelectionMode(QListWidget.SingleSelection)
        menu_l.addWidget(self.menu_list)

        self.menu_panel.setFixedWidth(260)
        body.addWidget(self.menu_panel)

        # Content area
        self.content = QFrame()
        self.content.setObjectName("Card")
        content_l = QVBoxLayout(self.content)
        content_l.setContentsMargins(18, 18, 18, 18)
        content_l.setSpacing(12)

        self.content_title = QLabel("")
        self.content_title.setObjectName("Header")
        self.content_title.setFont(QFont('Segoe Print', 28, QFont.Bold))
        self.content_title.setVisible(False)

        self.content_view = QLabel("")
        self.content_view.setAlignment(Qt.AlignCenter)
        self.content_view.setWordWrap(True)
        self.content_view.setVisible(False)

        # quote label centered and larger (kept for generic use)
        self.quote_label = QLabel("")
        self.quote_label.setAlignment(Qt.AlignCenter)
        self.quote_label.setWordWrap(True)

        # welcome_quote: larger, placed center-right of bottom area; visible on Welcome
        self.welcome_quote = QLabel("")
        self.welcome_quote.setWordWrap(True)
        self.welcome_quote.setAlignment(Qt.AlignCenter)
        self.welcome_quote.setVisible(False)  # will be shown when Welcome is selected

        content_l.addWidget(self.content_title)
        content_l.addStretch(1)
        content_l.addWidget(self.content_view)
        content_l.addStretch(1)
        # welcome_quote: fill width and positioned higher
        content_l.addWidget(self.welcome_quote)
        content_l.addStretch(2)

        body.addWidget(self.content, stretch=1)
        root.addLayout(body, stretch=1)
        self.apply_theme(Theme(self.theme_name))

        # default content: trigger welcome on startup (delayed to avoid accessing incomplete objects)
        # Use QTimer to defer the call until after initialization completes
        QTimer.singleShot(300, self._init_welcome)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # keep background covering the full widget
        try:
            if hasattr(self, 'bg') and self.bg:
                self.bg.setGeometry(self.rect())
        except Exception:
            pass

    def _init_welcome(self):
        """Initialize welcome page after full setup."""
        try:
            # Verify all required attributes exist
            if not hasattr(self, 'welcome_quote'):
                print("Warning: welcome_quote not yet initialized")
                QTimer.singleShot(200, self._init_welcome)  # Retry
                return
            
            welcome_item = self.menu_list.item(0)
            if welcome_item:
                self._on_menu(welcome_item, None)
        except Exception as e:
            print(f"Error in _init_welcome: {e}")
            # Retry after another delay
            QTimer.singleShot(200, self._init_welcome)

    def _on_music_state_changed(self, state):
        # Fallback loop helper when QMediaPlaylist isn't available
        try:
            if state == QMediaPlayer.StoppedState and self.music_player is not None:
                self.music_player.setPosition(0)
                self.music_player.play()
        except Exception:
            pass

    # Helper that plays click sound (if any) and then performs callback
    def _on_button_click(self, callback):
        if self.click_sfx:
            try:
                self.click_sfx.play()
            except Exception:
                pass
        if callable(callback):
            callback()

    def _on_language_changed(self):
        if not hasattr(self, "lang_combo"):
            return
        lang = self.lang_combo.currentData()
        set_language(lang)
        self._apply_language_texts()
        self._refresh_visible_page_after_language_change()

    def _apply_language_texts(self):
        if hasattr(self, "left_title"):
            self.left_title.setText(tr("app.header"))
        if hasattr(self, "btn_reset_sim"):
            self.btn_reset_sim.setText(tr("student.reset_simulator"))
        if hasattr(self, "btn_mute"):
            self.btn_mute.setText(tr("student.mute"))
        if hasattr(self, "btn_sim_conn"):
            self.btn_sim_conn.setText(tr("student.simulator"))
        if hasattr(self, "btn_theme"):
            self.btn_theme.setText(tr("common.theme"))
        if hasattr(self, "btn_settings"):
            self.btn_settings.setText(tr("common.settings"))
        if hasattr(self, "btn_logout"):
            self.btn_logout.setText(tr("common.logout_user", username=self.user.username))
        if hasattr(self, "manual_rewind_btn"):
            self.manual_rewind_btn.setText(self._manual_rewind_button_text())
        if hasattr(self, "manual_rewind_status"):
            self._refresh_manual_rewind_status_text()
        if hasattr(self, "modules_label"):
            self.modules_label.setText(tr("student.modules"))
        if hasattr(self, "_menu_items"):
            menu_titles = {
                "welcome": tr("menu.welcome"),
                "simulation": tr("menu.simulation"),
                "elearning": tr("menu.elearning"),
                "practice": tr("menu.practice"),
                "practice_records": tr("menu.practice_records"),
                "training_records": tr("menu.training_records"),
                "ai_mentor": tr("menu.ai_mentor"),
            }
            for key, item in self._menu_items.items():
                if key in menu_titles:
                    item.setText(menu_titles[key])

    def _refresh_visible_page_after_language_change(self):
        """Rebuild lightweight pages so labels change without restarting."""
        try:
            if getattr(self, "current_training", None):
                return
        except Exception:
            pass

        current_item = self.menu_list.currentItem() if hasattr(self, "menu_list") else None
        current_key = current_item.data(Qt.UserRole) if current_item else None

        if hasattr(self, "student_home_container") and self.student_home_container.isVisible():
            self._show_student_home()
            return
        if hasattr(self, "simulation_container") and self.simulation_container.isVisible():
            try:
                self.content.layout().removeWidget(self.simulation_container)
                self.simulation_container.deleteLater()
                delattr(self, "simulation_container")
            except Exception:
                pass
            self._show_simulation_options()
            return
        if hasattr(self, "training_records_container") and self.training_records_container.isVisible():
            self._show_training_records()
            return
        if hasattr(self, "settings_container") and self.settings_container.isVisible():
            self.content_title.setText(tr("common.settings"))
            if hasattr(self, "btn_camera_tab"):
                self.btn_camera_tab.setText(tr("student.camera_settings"))
            if hasattr(self, "btn_font_tab"):
                self.btn_font_tab.setText(tr("student.font_settings"))
            return
        if hasattr(self, "simulator_conn_widget") and self.simulator_conn_widget.isVisible():
            self.content_title.setText(tr("student.simulator"))
            return
        if hasattr(self, "ai_mentor_widget") and self.ai_mentor_widget and self.ai_mentor_widget.isVisible():
            self.content_title.setText(tr("student.ai_mentor"))
            if hasattr(self.ai_mentor_widget, "apply_language_texts"):
                self.ai_mentor_widget.apply_language_texts()
            return
        if current_key == "welcome":
            self._show_student_home()
        elif current_key == "simulation":
            self._show_simulation_options()
        elif current_key == "elearning":
            self.content_title.setText(tr("student.elearning_module"))
        elif current_key == "practice":
            self.content_title.setText(tr("student.practice_questions"))
        elif current_key == "practice_records":
            self.content_title.setText(tr("student.practice_records"))
        elif current_key == "training_records":
            self._show_training_records()
        elif current_key == "ai_mentor":
            self.content_title.setText(tr("student.ai_mentor"))

    def _toggle_music(self):
        if not self.music_player:
            return
        # prefer toggling audio output volume (more reliable across backends)
        try:
            # if we have an audio output, mute by dropping volume to 0 and remember previous
            ao = getattr(self, 'music_audio_output', None)
            if ao is not None:
                current = ao.volume()
                if getattr(self, '_prev_volume', None) is None or current > 0:
                    # mute
                    self._prev_volume = current
                    ao.setVolume(0.0)
                    self.btn_mute.setChecked(True)
                else:
                    # unmute: restore
                    ao.setVolume(getattr(self, '_prev_volume', 0.2))
                    self.btn_mute.setChecked(False)
            else:
                # fallback to QMediaPlayer.muted
                muted = self.music_player.isMuted()
                self.music_player.setMuted(not muted)
                self.btn_mute.setChecked(not muted)
        except Exception:
            pass

    def _reset_simulator(self):
        """Send reset command to simulator hardware"""
        try:
            connector = HardwareConnector()
            success, message = connector.send_command("reset")
            if success:
                # Show success message in status bar or notification
                print(f"[MainWindow] Simulator reset: {message}")
            else:
                print(f"[MainWindow] Simulator reset failed: {message}")
        except Exception as e:
            print(f"[MainWindow] Error resetting simulator: {str(e)}")

    def _load_and_apply_user_font(self):
        """Load user's saved font preference and apply it"""
        try:
            import json
            config_path = os.path.join(os.path.dirname(__file__), "..", "..", "user_settings.json")
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    font_name = settings.get("font", self.student_body_font)
                    if font_name == "Candara":
                        font_name = self.student_body_font
                    self.student_body_font = font_name or self.student_body_font
                    print(f"[Settings] Loaded user font: {font_name}")
                    
                    # Apply font to entire StudentShell
                    self._apply_font_recursively(self, font_name)
        except Exception as e:
            print(f"[Settings] Error loading user font: {e}")
    
    def _apply_font_recursively(self, widget, font_name):
        """Recursively apply font to widget and all children"""
        # Get current font size for this widget
        current_font = widget.font()
        size = current_font.pointSize() if current_font.pointSize() > 0 else 11
        weight = current_font.weight()
        
        # Apply new font with same size and weight
        new_font = QFont(font_name, size)
        new_font.setWeight(weight)
        widget.setFont(new_font)
        
        # Recursively apply to children
        for child in widget.findChildren(QWidget):
            current_font = child.font()
            size = current_font.pointSize() if current_font.pointSize() > 0 else 11
            weight = current_font.weight()
            
            new_font = QFont(font_name, size)
            new_font.setWeight(weight)
            child.setFont(new_font)
    
    def _apply_font_globally(self, font_name):
        """Apply selected font to all UI elements in StudentShell"""
        print(f"[Settings] Applying font to StudentShell: {font_name}")
        self.student_body_font = font_name or self.student_body_font
        self._apply_font_recursively(self, font_name)
        self.apply_theme(Theme(self.theme_name))
        print(f"[Settings] Font applied successfully")

    def _student_theme_tokens(self):
        if self.theme_name == "dark":
            return {
                "shell_bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #071923, stop:0.55 #0d2631, stop:1 #153c45)",
                "panel": "rgba(10, 31, 42, 0.88)",
                "panel_soft": "rgba(16, 46, 58, 0.74)",
                "card": "rgba(16, 51, 63, 0.82)",
                "card_hover": "rgba(22, 70, 84, 0.92)",
                "text": "#e8fbff",
                "muted": "#9dc6cd",
                "accent": "#42d6c5",
                "accent_deep": "#18a999",
                "accent_soft": "rgba(66, 214, 197, 0.18)",
                "border": "rgba(119, 232, 219, 0.26)",
                "shadow": "rgba(0, 0, 0, 0.28)",
            }
        if self.theme_name == "light":
            return {
                "shell_bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #eef8f7, stop:0.55 #f8fbff, stop:1 #eaf2ff)",
                "panel": "rgba(255, 255, 255, 0.84)",
                "panel_soft": "rgba(255, 255, 255, 0.68)",
                "card": "rgba(255, 255, 255, 0.78)",
                "card_hover": "rgba(240, 250, 255, 0.92)",
                "text": "#12354a",
                "muted": "#557382",
                "accent": "#207d88",
                "accent_deep": "#115e67",
                "accent_soft": "rgba(32, 125, 136, 0.13)",
                "border": "rgba(32, 125, 136, 0.20)",
                "shadow": "rgba(32, 72, 96, 0.10)",
            }
        return {
            "shell_bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #eaf6ff, stop:0.48 #f7fbff, stop:1 #dcecff)",
            "panel": "rgba(248, 252, 255, 0.88)",
            "panel_soft": "rgba(235, 246, 255, 0.78)",
            "card": "rgba(255, 255, 255, 0.82)",
            "card_hover": "rgba(230, 244, 255, 0.96)",
            "text": "#15354f",
            "muted": "#58758d",
            "accent": "#3f8fcf",
            "accent_deep": "#246fa8",
            "accent_soft": "rgba(63, 143, 207, 0.15)",
            "border": "rgba(64, 139, 198, 0.22)",
            "shadow": "rgba(44, 96, 140, 0.12)",
        }

    def apply_theme(self, theme):
        """Apply a coordinated theme to the student shell and dynamic pages."""
        self.theme_name = getattr(theme, "name", "light")
        palette = self._student_theme_tokens()
        heading = self.student_heading_font
        body = self.student_body_font

        self.setStyleSheet(
            f"""
            QWidget#StudentShell {{
                background: {palette['shell_bg']};
                color: {palette['text']};
                font-family: '{body}', 'Segoe UI', Arial;
            }}
            QFrame#TopBar, QFrame#Card {{
                background: {palette['panel']};
                border: 1px solid {palette['border']};
                border-radius: 18px;
            }}
            QLabel#Header {{
                color: {palette['text']};
                font-family: '{heading}', '{body}', 'Segoe UI', Arial;
                font-weight: 800;
            }}
            QLabel#ModulesLabel {{
                color: {palette['text']};
                font-family: '{heading}', '{body}', 'Segoe UI', Arial;
                font-size: 28px;
                font-weight: 800;
            }}
            """
        )

        if getattr(self, "bg", None):
            self.bg.setVisible(self.theme_name == "light")

        if hasattr(self, "top_bar"):
            self.top_bar.setStyleSheet(
                f"background: {palette['panel']}; border: 1px solid {palette['border']}; border-radius: 18px;"
            )
        if hasattr(self, "menu_panel"):
            self.menu_panel.setStyleSheet(
                f"background: {palette['panel']}; border: 1px solid {palette['border']}; border-radius: 18px;"
            )
        if hasattr(self, "content"):
            self.content.setStyleSheet(
                f"background: {palette['panel']}; border: 1px solid {palette['border']}; border-radius: 20px;"
            )
        if hasattr(self, "left_title"):
            self.left_title.setStyleSheet(
                f"color: {palette['text']}; font-family: '{heading}', '{body}', 'Segoe UI', Arial; "
                f"font-size: 24px; font-weight: 800; background: transparent; border: none; padding: 0;"
            )
        if hasattr(self, "modules_label"):
            self.modules_label.setStyleSheet(
                f"color: {palette['text']}; font-family: '{heading}', '{body}', 'Segoe UI', Arial; "
                f"font-size: 27px; font-weight: 800; background: transparent; border: none;"
            )
        if hasattr(self, "menu_list"):
            self.menu_list.setStyleSheet(
                f"""
                QListWidget {{
                    border: 0px;
                    background: transparent;
                    outline: none;
                }}
                QListWidget::item {{
                    padding: 14px;
                    border-radius: 12px;
                    color: {palette['muted']};
                    font-family: '{body}', 'Segoe UI', Arial;
                    font-size: 18px;
                }}
                QListWidget::item:hover {{
                    background: {palette['accent_soft']};
                    color: {palette['text']};
                }}
                QListWidget::item:selected {{
                    background: {palette['accent_soft']};
                    border-left: 4px solid {palette['accent']};
                    color: {palette['text']};
                    font-weight: 800;
                }}
                """
            )
        if hasattr(self, "content_title"):
            self.content_title.setStyleSheet(
                f"color: {palette['text']}; background: transparent; "
                f"font-family: '{heading}', '{body}', 'Segoe UI', Arial; font-size: 30px; font-weight: 800;"
            )
        if hasattr(self, "content_view"):
            self.content_view.setStyleSheet(
                f"QLabel {{ font-size: 18px; font-family: '{body}', 'Segoe UI', Arial; "
                f"color: {palette['muted']}; background: transparent; }}"
            )
        if hasattr(self, "quote_label"):
            self.quote_label.setStyleSheet(
                f"font-family: '{heading}', '{body}', 'Segoe UI', Arial; color: {palette['accent']}; "
                f"font-size: 30px; background: transparent;"
            )
        if hasattr(self, "welcome_quote"):
            self.welcome_quote.setStyleSheet(
                f"font-family: '{body}', 'Segoe UI', Arial; color: {palette['muted']}; "
                f"font-size: 22px; background: transparent;"
            )
        if hasattr(self, "top_buttons"):
            button_style = self._student_top_button_style(palette)
            for button in self.top_buttons:
                button.setStyleSheet(button_style)
        if hasattr(self, "lang_combo"):
            self.lang_combo.setStyleSheet(self._student_combo_style(palette))

        current_key = None
        if hasattr(self, "menu_list"):
            current_item = self.menu_list.currentItem()
            if current_item:
                current_key = current_item.data(Qt.UserRole)

        if current_key == "welcome" and hasattr(self, "student_home_container") and self.student_home_container:
            self._show_student_home()
        self._refresh_student_inline_text_colors()
        if hasattr(self, "practice_records_container") and not self.practice_records_container.isHidden():
            self._update_practice_statistics()
            self._refresh_student_inline_text_colors()
        if hasattr(self, "training_records_container") and not self.training_records_container.isHidden():
            self._update_training_records()
            self._refresh_student_inline_text_colors()

    def _student_top_button_style(self, palette=None):
        palette = palette or self._student_theme_tokens()
        return f"""
            QPushButton {{
                background: {palette['panel_soft']};
                border: 1px solid {palette['border']};
                padding: 7px 12px;
                border-radius: 10px;
                font-family: '{self.student_body_font}', 'Segoe UI', Arial;
                font-size: 14px;
                font-weight: 700;
                color: {palette['text']};
            }}
            QPushButton:hover {{
                background: {palette['accent_soft']};
                border-color: {palette['accent']};
            }}
        """

    def _student_inline_text_targets(self):
        """Return readable legacy text colors for inline styles on each student theme."""
        if self.theme_name == "dark":
            return self._student_theme_tokens()["text"], self._student_theme_tokens()["muted"]
        return "#003366", "#234f8d"

    def _replace_student_inline_text_colors(self, style):
        """Retint only CSS text color values; leave content, borders, and layout untouched."""
        if not style:
            return style

        primary, muted = self._student_inline_text_targets()
        primary_sources = ("#003366", "#e8fbff")
        muted_sources = ("#234f8d", "#9dc6cd")

        for old in primary_sources:
            style = re.sub(
                rf"(?<![-\w])color\s*:\s*{re.escape(old)}",
                f"color: {primary}",
                style,
                flags=re.IGNORECASE,
            )
        for old in muted_sources:
            style = re.sub(
                rf"(?<![-\w])color\s*:\s*{re.escape(old)}",
                f"color: {muted}",
                style,
                flags=re.IGNORECASE,
            )
        return style

    def _refresh_student_inline_text_colors(self):
        """Refresh hard-coded legacy blue text on pages that already exist."""
        containers = [
            getattr(self, name, None)
            for name in (
                "elearning_container",
                "learning_materials_container",
                "practice_container",
                "topic_container",
                "practice_records_container",
                "training_records_container",
                "simulation_container",
                "simulator_conn_widget",
                "settings_container",
                "ai_mentor_widget",
                "_completion_frame",
            )
        ]

        for container in containers:
            if not container:
                continue
            for widget_type in (QLabel, QPushButton, QListWidget, QTextEdit):
                for widget in container.findChildren(widget_type):
                    old_style = widget.styleSheet()
                    new_style = self._replace_student_inline_text_colors(old_style)
                    if new_style != old_style:
                        widget.setStyleSheet(new_style)
    
    def start_welcome(self):
        # Play music (if available)
        if self.music_player:
            try:
                self.music_player.play()
                self.music_player.setMuted(False)
                self.btn_mute.setChecked(False)
            except Exception:
                pass

    def _logout_from_student_shell(self):
        self._stop_manual_rewind(silent=True)
        if callable(self.on_logout):
            self.on_logout()

    def _on_training_button_click(self, training_key: str):
        """处理训练按钮点击"""
        print(f"\n[MainWindow] _on_training_button_click called with key: {training_key}")
        self._stop_manual_rewind(silent=True)
        
        # 播放点击音效
        if self.click_sfx:
            try:
                self.click_sfx.play()
            except Exception as e:
                print(f"Error playing click sound: {e}")
        
        # Start the matching training workflow by key.
        if training_key in ["remove_needle", "remove_needle_simulator", "remove_needle_no_simulator"]:
            print(f"[MainWindow] Starting remove_needle training with key: {training_key}")
            self._start_remove_needle_training(training_key)
        elif training_key == "change_dressing":
            print(f"[MainWindow] Starting change_dressing training")
            self._start_change_dressing_training()
        elif training_key == "comprehensive":
            print(f"[MainWindow] Starting comprehensive training")
            self._start_comprehensive_training()
        elif training_key == "training_records":
            print(f"[MainWindow] Opening training records")
            self._show_training_records()
        else:
            print(f"[MainWindow] Unknown training key: {training_key}")
    
    def _start_remove_needle_training(self, training_key: str = "remove_needle_no_simulator"):
        """启动拔针训练"""
        print(f"\n[Training] Entering _start_remove_needle_training with key: {training_key}")
        try:
            print(f"[Training] Importing RemoveNeedleTraining...")
            # Simulator 版本改用 MCU 驱动的简化实现（跳过P1-P3、无摄像头）
            if training_key == "remove_needle_simulator":
                from app.training_remove_needle_mcu import RemoveNeedleTraining
            else:
                from app.training_remove_needle import RemoveNeedleTraining
            print(f"[Training] Import successful")
            
            # 清除菜单栏选中
            print(f"[Training] Clearing menu selection")
            self.menu_list.clearSelection()
            
            # 隐藏当前内容
            print(f"[Training] Hiding current content")
            if hasattr(self, 'simulation_container'):
                self.simulation_container.setVisible(False)
            self.welcome_quote.setVisible(False)
            self.content_title.setVisible(False)
            self.content_view.setVisible(False)
            
            # Create the training widget directly under content instead of adding it to the layout.
            print(f"[Training] Creating RemoveNeedleTraining widget")
            print(f"[Training] self.content = {self.content}, type = {type(self.content)}")
            self.current_training = RemoveNeedleTraining(self.content, training_mode=training_key)
            # Pass username so the training record can be saved.
            self.current_training.current_user = self.user.username
            print(f"[Training] RemoveNeedleTraining created successfully")
            
            print(f"[Training] Connecting training_completed signal")
            self.current_training.training_completed.connect(self._on_training_completed)
            
            print(f"[Training] Connecting quiz_triggered signal")
            self.current_training.quiz_triggered.connect(self._on_quiz_triggered_from_training)
            
            # 初始化quiz_module用于训练模式
            print(f"[Training] Initializing quiz_module for training mode")
            if not hasattr(self, 'quiz_module') or self.quiz_module is None:
                self.quiz_module = QuizModule(training_mode=True)
                quiz_path = _asset_path("epidural_quiz_questions.json")
                self.quiz_module.load_quiz_data(quiz_path)
                self.quiz_module.quiz_completed.connect(self._on_quiz_completed)
                self.quiz_module.back_clicked.connect(self._on_quiz_back)
                # Add to content and keep it hidden initially.
                content_l = self.content.layout()
                content_l.insertWidget(2, self.quiz_module)
                self.quiz_module.setVisible(False)
            
            # 设置训练widget占满整个content区域
            print(f"[Training] Setting training widget geometry to fill content")
            self.current_training.setGeometry(self.content.rect())
            
            # 使训练widget可见
            print(f"[Training] Setting training widget visible")
            self.current_training.setVisible(True)
            
            # Start training.
            print(f"[Training] Calling start_training()")
            self.current_training.start_training()
            print(f"[Training] Training started successfully!")
        except Exception as e:
            import traceback
            print(f"\n[ERROR] Error starting remove needle training: {e}")
            print(traceback.format_exc())
    
    def _start_change_dressing_training(self):
        """Start AR dressing-change training."""
        print("\n[Training] Starting change dressing AR training")
        try:
            from app.training_change_dressing import ChangeDressingTraining

            self._stop_current_training()
            self.menu_list.clearSelection()
            self._hide_all_content_containers()
            if hasattr(self, 'simulation_container'):
                self.simulation_container.setVisible(False)
            self.welcome_quote.setVisible(False)
            self.content_title.setVisible(False)
            self.content_view.setVisible(False)

            self.current_training = ChangeDressingTraining(self.content, training_mode="change_dressing")
            self.current_training.current_user = self.user.username
            self.current_training.training_completed.connect(self._on_training_completed)
            self.current_training.setGeometry(self.content.rect())
            self.current_training.setVisible(True)
            self.current_training.start_training()
            print("[Training] Change dressing AR training started successfully")
        except Exception as e:
            import traceback
            print(f"\n[ERROR] Error starting change dressing training: {e}")
            print(traceback.format_exc())
    
    def _start_comprehensive_training(self):
        """Start the full AR flow: preparation, dressing removal, wiping, and catheter removal."""
        print("[MainWindow] Starting comprehensive full AR training")
        self._start_remove_needle_training("comprehensive")

    def _show_training_placeholder(self, title, message):
        """Show a clear in-app placeholder for planned training modules."""
        self._stop_current_training()
        self._hide_all_content_containers()
        self.content_title.setText(title)
        self.content_title.setVisible(True)
        self.content_view.setText(message)
        self.content_view.setWordWrap(True)
        self.content_view.setVisible(True)
        self._refresh_student_inline_text_colors()
    
    def _on_quiz_triggered_from_training(self, question_id):
        """
        Quiz triggered from training (Q3, Q4, Q5).
        Show a transparent quiz overlay and pause the Phase 4 removal action.
        """
        try:
            print(f"[Training] Quiz triggered during training: {question_id}")
            
            # Pause Phase 4 removal while the quiz is shown.
            if hasattr(self, 'current_training') and self.current_training:
                self.current_training.pause_phase4()
            
            if not hasattr(self, 'quiz_module') or self.quiz_module is None:
                print(f"[Training] Quiz module not initialized, creating now...")
                self.quiz_module = QuizModule(training_mode=True)
                quiz_path = _asset_path("epidural_quiz_questions.json")
                self.quiz_module.load_quiz_data(quiz_path)
                self.quiz_module.quiz_completed.connect(self._on_quiz_completed)
                self.quiz_module.back_clicked.connect(self._on_quiz_back)
                # Add to content.
                if hasattr(self, 'content') and self.content.layout():
                    content_l = self.content.layout()
                    content_l.insertWidget(2, self.quiz_module)
            
            # 验证问题是否存在
            if not self.quiz_module.questions:
                print(f"[Training] Quiz module has no questions loaded!")
                return
                
            if question_id not in self.quiz_module.questions:
                print(f"[Training] Question {question_id} not found in loaded questions")
                print(f"[Training] Available questions: {list(self.quiz_module.questions.keys())}")
                return
            
            # Ensure quiz_module is visible and raised to the front.
            if not self.quiz_module.isVisible():
                self.quiz_module.setVisible(True)
            self.quiz_module.raise_()
            self.quiz_module.activateWindow()
            
            # Use a translucent background so the quiz floats over the training view.
            self.quiz_module.setStyleSheet("""
                QFrame {
                    background: rgba(101, 67, 33, 200);
                    border-radius: 8px;
                }
            """)
            
            # 启动特定的question
            print(f"[Training] Starting quiz with question: {question_id}")
            self.quiz_module.start_quiz([question_id])
            # remember which training quiz is pending so we can record result later
            try:
                self._pending_training_quiz_id = question_id
            except Exception:
                self._pending_training_quiz_id = None
            
        except Exception as e:
            import traceback
            print(f"[Training] Error triggering quiz: {e}")
            print(traceback.format_exc())
    
    def _on_training_completed(self):
        """训练完成"""
        try:
            print(f"[Training] Training completed, cleaning up")
            # 清理当前训练模块
            if hasattr(self, 'current_training') and self.current_training:
                self.current_training.setVisible(False)
                self.current_training.deleteLater()
                self.current_training = None
            
            # 显示训练选项
            print(f"[Training] Showing student dashboard with AI summary")
            self._show_student_home()
            QTimer.singleShot(250, self._generate_student_ai_summary)
        except Exception as e:
            print(f"[Training] Error in training completion: {e}")
    
    def _stop_current_training(self):
        """Stop the active training widget before switching pages."""
        if hasattr(self, 'current_training') and self.current_training:
            try:
                self.current_training.cleanup()
                self.current_training.setVisible(False)
                self.current_training.deleteLater()
                self.current_training = None
            except Exception as e:
                print(f"Error stopping training: {e}")
    
    def _on_menu(self, current, _prev):
        """Handle left-menu navigation."""
        self._stop_manual_rewind(silent=True)
        # Stop any active training first.
        self._stop_current_training()
        
        # Clean up the E-learning video player.
        self._cleanup_elearning_video()
        
        # 清理Practice相关容器
        self._cleanup_practice_containers()
        
        # 清理Practice Records容器
        self._cleanup_practice_records()
        
        # 清理Training Records容器
        self._cleanup_training_records()
        # 隐藏所有特殊内容容器（确保 AI Mentor 等被隐藏并清空）
        try:
            self._hide_all_content_containers()
        except Exception:
            pass
        
        if not current:
            return
        # small click sound when switching menu
        if self.click_sfx:
            try:
                self.click_sfx.play()
            except Exception:
                pass
        key = current.data(Qt.UserRole)
        
        # Always cleanup camera when switching away from settings
        if hasattr(self, 'camera_manager_widget') and key != "settings":
            self.camera_manager_widget.setVisible(False)
            try:
                self.camera_manager_widget.cleanup()
            except Exception:
                pass
        
        # Hide all special containers for non-special items
        if hasattr(self, 'simulation_container'):
            self.simulation_container.setVisible(False)
        if hasattr(self, 'simulator_conn_widget'):
            self.simulator_conn_widget.setVisible(False)
        
        if key == "welcome":
            self._show_student_home()
            return
        elif key == "simulation":
            # Show three training option buttons
            self._show_simulation_options()
            return
        else:
            # hide welcome quote; show content title/view
            self.welcome_quote.setVisible(False)
            self.content_title.setVisible(True)
            
            # Special handling for E-learning
            if key == "elearning":
                self._show_elearning_content()
                return
            
            # Special handling for Practice
            if key == "practice":
                self._show_practice_options()
                return
            
            # Special handling for Practice Records
            if key == "practice_records":
                self._show_practice_records()
                return
            
            # Special handling for Training Records
            if key == "training_records":
                self._show_training_records()
                return
            
            # Special handling for AI Nursing Mentor
            if key == "ai_mentor":
                self._show_ai_mentor()
                return
            
            self.content_view.setVisible(True)

        mapping = {
            "reports": "Report Records (placeholder)\n- Per-user local reports",
            "dashboard": "Trainer Dashboard (placeholder)\n- Statistics view (trainer only)",
        }
        self._set_content(mapping.get(key, "Coming soon"))

    def _set_content(self, text: str):
        self.content_title.setText(text.splitlines()[0])
        self.content_view.setText(text)

    def _show_student_home(self):
        """Show a student-focused landing page with quick actions and recent progress."""
        if not hasattr(self, 'welcome_quote') or not hasattr(self, 'content_title'):
            QTimer.singleShot(200, self._show_student_home)
            return

        self._hide_all_content_containers()
        self.welcome_quote.setVisible(False)
        self.content_view.setVisible(False)
        self.content_title.setText(tr("student.dashboard_title"))
        self.content_title.setVisible(True)

        if hasattr(self, 'student_home_container') and self.student_home_container:
            try:
                self.content.layout().removeWidget(self.student_home_container)
                self.student_home_container.deleteLater()
            except Exception:
                pass

        self.student_home_container = QFrame()
        self.student_home_container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self.student_home_container)
        layout.setSpacing(14)
        layout.setContentsMargins(0, 0, 0, 0)

        palette = self._student_theme_tokens()
        heading = self.student_heading_font
        body = self.student_body_font

        greeting = QLabel(tr("student.dashboard_greeting", username=self.user.username))
        greeting.setWordWrap(True)
        greeting.setStyleSheet(
            f"font-family: '{body}', 'Segoe UI', Arial; font-size: 17px; "
            f"color: {palette['muted']}; font-weight: 700; background: transparent;"
        )
        layout.addWidget(greeting)

        stats = self._get_student_training_stats()
        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(self._student_metric_card(tr("student.completed"), str(stats["total_trainings"])))
        cards.addWidget(self._student_metric_card(tr("student.dressing_changes"), str(stats.get("change_dressing_count", 0))))
        cards.addWidget(self._student_metric_card(tr("student.avg_time"), self._student_format_seconds(stats["avg_time"])))
        cards.addWidget(self._student_metric_card(tr("student.best_time"), self._student_format_seconds(stats["best_time"])))
        cards.addWidget(self._student_metric_card(tr("student.avg_accuracy"), f"{stats['avg_accuracy']:.0f}%"))
        layout.addLayout(cards)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addWidget(self._student_action_button(tr("student.start_dressing_change"), "change_dressing"))
        actions.addWidget(self._student_action_button(tr("student.start_catheter_removal"), "remove_needle_simulator"))

        summary_btn = QPushButton(tr("student.generate_ai_summary"))
        summary_btn.setStyleSheet(self._student_action_button_style())
        summary_btn.clicked.connect(self._generate_student_ai_summary)
        self.student_ai_summary_btn = summary_btn
        actions.addWidget(summary_btn)

        records_btn = QPushButton(tr("student.view_records"))
        records_btn.setStyleSheet(self._student_action_button_style())
        records_btn.clicked.connect(lambda: self._on_button_click(self._show_training_records))
        actions.addWidget(records_btn)

        rewind_btn = QPushButton(self._manual_rewind_button_text())
        rewind_btn.setStyleSheet(self._manual_rewind_button_style())
        rewind_btn.clicked.connect(lambda: self._on_button_click(self._toggle_manual_rewind))
        self.manual_rewind_btn = rewind_btn
        actions.addWidget(rewind_btn)
        layout.addLayout(actions)

        self.manual_rewind_status = QLabel(self._manual_rewind_default_status())
        self.manual_rewind_status.setWordWrap(True)
        self.manual_rewind_status.setStyleSheet(self._manual_rewind_status_style())
        layout.addWidget(self.manual_rewind_status)

        recent_title = QLabel(tr("student.recent_training"))
        recent_title.setStyleSheet(
            f"font-family: '{heading}', '{body}', 'Segoe UI', Arial; font-size: 18px; "
            f"color: {palette['text']}; font-weight: 800; background: transparent;"
        )
        layout.addWidget(recent_title)

        recent = QTextEdit()
        recent.setReadOnly(True)
        recent.setMaximumHeight(160)
        recent.setStyleSheet(f"""
            QTextEdit {{
                background: {palette['card']};
                border: 1px solid {palette['border']};
                border-radius: 14px;
                padding: 10px;
                color: {palette['text']};
                font-family: '{body}', 'Segoe UI', Arial;
                font-size: 13px;
            }}
            {self._student_scrollbar_style(palette)}
        """)
        recent.setText(self._student_recent_training_text(stats["summaries"]))
        layout.addWidget(recent)

        ai_header = QHBoxLayout()
        ai_header.setSpacing(8)
        ai_title = QLabel(tr("student.ai_training_summary"))
        ai_title.setStyleSheet(
            f"font-family: '{heading}', '{body}', 'Segoe UI', Arial; font-size: 18px; "
            f"color: {palette['text']}; font-weight: 800; background: transparent;"
        )
        ai_header.addWidget(ai_title)
        ai_header.addStretch(1)
        layout.addLayout(ai_header)

        self.student_ai_loading = AiLoadingIndicator()
        self.student_ai_loading.apply_palette(palette)
        self.student_ai_loading.setVisible(False)
        layout.addWidget(self.student_ai_loading)

        self.student_ai_summary = QTextEdit()
        self.student_ai_summary.setReadOnly(True)
        self.student_ai_summary.setMaximumHeight(280)
        self.student_ai_summary.setStyleSheet(f"""
            QTextEdit {{
                background: {palette['card']};
                border: 1px solid {palette['border']};
                border-radius: 14px;
                padding: 10px;
                color: {palette['text']};
                font-family: '{body}', 'Segoe UI', Arial;
                font-size: 13px;
            }}
            {self._student_scrollbar_style(palette)}
        """)
        self.student_ai_summary.setText(tr("student.ai_summary_placeholder"))
        layout.addWidget(self.student_ai_summary)
        layout.addStretch(1)

        self.content.layout().insertWidget(2, self.student_home_container)
        self.student_home_container.setVisible(True)

    def _student_metric_card(self, label, value):
        palette = self._student_theme_tokens()
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {palette['card']};
                border: 1px solid {palette['border']};
                border-radius: 16px;
                padding: 10px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        value_label = QLabel(value)
        value_label.setStyleSheet(
            f"font-family: '{self.student_heading_font}', '{self.student_body_font}', 'Segoe UI', Arial; "
            f"font-size: 25px; color: {palette['text']}; font-weight: 800; background: transparent; border: none;"
        )
        label_label = QLabel(label)
        label_label.setStyleSheet(
            f"font-family: '{self.student_body_font}', 'Segoe UI', Arial; font-size: 13px; "
            f"color: {palette['muted']}; font-weight: 700; background: transparent; border: none;"
        )
        layout.addWidget(value_label)
        layout.addWidget(label_label)
        return card

    def _student_action_button(self, text, training_key):
        button = QPushButton(text)
        button.setStyleSheet(self._student_action_button_style())
        button.clicked.connect(lambda: self._on_training_button_click(training_key))
        return button

    def _student_action_button_style(self):
        palette = self._student_theme_tokens()
        return f"""
            QPushButton {{
                background: {palette['accent_soft']};
                border: 1px solid {palette['accent']};
                border-radius: 16px;
                padding: 16px;
                font-family: '{self.student_heading_font}', '{self.student_body_font}', 'Segoe UI', Arial;
                font-size: 16px;
                font-weight: 800;
                color: {palette['text']};
                min-height: 78px;
            }}
            QPushButton:hover {{
                background: {palette['card_hover']};
                border-color: {palette['accent_deep']};
            }}
        """

    def _manual_rewind_button_text(self):
        if getattr(self, "manual_rewind_active", False) or getattr(self, "manual_rewind_pending", False):
            return tr("student.stop_rewind")
        return tr("student.rewind_line")

    def _manual_rewind_default_status(self):
        seconds = max(1, self.manual_rewind_timeout_ms // 1000)
        return tr("student.rewind_hint", seconds=seconds)

    def _manual_rewind_button_style(self):
        palette = self._student_theme_tokens()
        return f"""
            QPushButton {{
                background: rgba(255, 190, 96, 0.22);
                border: 1px solid #E58A2A;
                border-radius: 16px;
                padding: 16px;
                font-family: '{self.student_heading_font}', '{self.student_body_font}', 'Segoe UI', Arial;
                font-size: 16px;
                font-weight: 800;
                color: {palette['text']};
                min-height: 78px;
            }}
            QPushButton:hover {{
                background: rgba(255, 190, 96, 0.34);
                border-color: #B86116;
            }}
        """

    def _manual_rewind_status_style(self, error=False):
        palette = self._student_theme_tokens()
        color = "#B84A32" if error else palette["muted"]
        return (
            f"font-family: '{self.student_body_font}', 'Segoe UI', Arial; "
            f"font-size: 13px; color: {color}; font-weight: 700; "
            "background: transparent;"
        )

    def _set_manual_rewind_status(self, text, error=False):
        if hasattr(self, "manual_rewind_status") and self.manual_rewind_status:
            self.manual_rewind_status.setText(text)
            self.manual_rewind_status.setStyleSheet(self._manual_rewind_status_style(error))

    def _refresh_manual_rewind_status_text(self):
        if self.manual_rewind_pending:
            self._set_manual_rewind_status(tr("student.rewind_preparing"))
        elif self.manual_rewind_active:
            self._set_manual_rewind_status(tr("student.rewind_running"))
        else:
            self._set_manual_rewind_status(self._manual_rewind_default_status())

    def _manual_rewind_direction(self):
        direction = os.getenv("SURGERYBOX_MANUAL_REWIND_DIRECTION", "MR").strip().upper()
        return direction if direction in ("MR", "MF") else "MR"

    def _toggle_manual_rewind(self):
        if self.manual_rewind_active or self.manual_rewind_pending:
            self._stop_manual_rewind()
        else:
            self._start_manual_rewind()

    def _start_manual_rewind(self):
        if getattr(self, "current_training", None):
            self._set_manual_rewind_status(tr("student.rewind_training_active"), error=True)
            return

        try:
            import serial
        except Exception as exc:
            self._set_manual_rewind_status(
                tr("student.rewind_unavailable", message=f"pyserial unavailable: {exc}"),
                error=True,
            )
            return

        port = os.getenv("SURGERYBOX_SERIAL_PORT", "COM4")
        try:
            baudrate = int(os.getenv("SURGERYBOX_SERIAL_BAUD", "115200"))
        except ValueError:
            baudrate = 115200

        self._close_manual_rewind_serial()
        try:
            self.manual_rewind_serial = serial.Serial(
                port,
                baudrate,
                timeout=0.2,
                write_timeout=0.5,
            )
            try:
                self.manual_rewind_serial.dtr = False
                self.manual_rewind_serial.rts = False
            except Exception:
                pass
        except Exception as exc:
            self.manual_rewind_serial = None
            self.manual_rewind_pending = False
            self.manual_rewind_active = False
            self._set_manual_rewind_status(
                tr("student.rewind_unavailable", message=f"{port}: {exc}"),
                error=True,
            )
            return

        self.manual_rewind_pending = True
        self.manual_rewind_active = False
        self._update_manual_rewind_button()
        self._set_manual_rewind_status(tr("student.rewind_preparing"))
        QTimer.singleShot(1300, self._begin_manual_rewind_after_boot)

    def _begin_manual_rewind_after_boot(self):
        if not self.manual_rewind_pending:
            return
        if not self.manual_rewind_serial or not self.manual_rewind_serial.is_open:
            self.manual_rewind_pending = False
            self._update_manual_rewind_button()
            self._set_manual_rewind_status(tr("student.rewind_unavailable", message="serial closed"), error=True)
            return

        direction = self._manual_rewind_direction()
        if not self._write_manual_rewind_command("BR"):
            self._stop_manual_rewind(silent=True)
            self._set_manual_rewind_status(tr("student.rewind_unavailable", message="failed to release brake"), error=True)
            return
        if not self._write_manual_rewind_command(direction):
            self._stop_manual_rewind(silent=True)
            self._set_manual_rewind_status(tr("student.rewind_unavailable", message="failed to start motor"), error=True)
            return

        self.manual_rewind_pending = False
        self.manual_rewind_active = True
        self._update_manual_rewind_button()
        self._set_manual_rewind_status(tr("student.rewind_running"))
        self.manual_rewind_timer.start(max(1000, self.manual_rewind_timeout_ms))

    def _write_manual_rewind_command(self, command):
        try:
            if not self.manual_rewind_serial or not self.manual_rewind_serial.is_open:
                return False
            payload = (command.strip() + "\n").encode("utf-8")
            self.manual_rewind_serial.write(payload)
            self.manual_rewind_serial.flush()
            print(f"[ManualRewind] Sent: {command}")
            return True
        except Exception as exc:
            print(f"[ManualRewind] Send failed for {command}: {exc}")
            return False

    def _stop_manual_rewind(self, silent=False):
        was_active = self.manual_rewind_active or self.manual_rewind_pending
        self.manual_rewind_timer.stop()
        if self.manual_rewind_serial and self.manual_rewind_serial.is_open:
            self._write_manual_rewind_command("MS")
            self._write_manual_rewind_command("BL")
        self.manual_rewind_active = False
        self.manual_rewind_pending = False
        self._close_manual_rewind_serial()
        self._update_manual_rewind_button()
        if not silent and was_active:
            self._set_manual_rewind_status(tr("student.rewind_stopped"))

    def _on_manual_rewind_timeout(self):
        self._stop_manual_rewind(silent=True)
        self._set_manual_rewind_status(tr("student.rewind_timeout"), error=True)

    def _close_manual_rewind_serial(self):
        try:
            if self.manual_rewind_serial and self.manual_rewind_serial.is_open:
                self.manual_rewind_serial.close()
        except Exception:
            pass
        self.manual_rewind_serial = None

    def _update_manual_rewind_button(self):
        if hasattr(self, "manual_rewind_btn") and self.manual_rewind_btn:
            self.manual_rewind_btn.setText(self._manual_rewind_button_text())
            self.manual_rewind_btn.setStyleSheet(self._manual_rewind_button_style())

    def _student_combo_style(self, palette=None):
        palette = palette or self._student_theme_tokens()
        return f"""
            QComboBox {{
                background: {palette['panel_soft']};
                border: 1px solid {palette['border']};
                border-radius: 10px;
                padding: 6px 24px 6px 10px;
                color: {palette['text']};
                font-family: '{self.student_body_font}', 'Segoe UI', Arial;
                font-size: 14px;
                font-weight: 700;
                min-width: 92px;
            }}
            QComboBox:hover {{
                background: {palette['accent_soft']};
                border-color: {palette['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 22px;
            }}
            QComboBox QAbstractItemView {{
                background: {palette['panel']};
                color: {palette['text']};
                border: 1px solid {palette['border']};
                selection-background-color: {palette['accent_soft']};
            }}
        """

    def _student_scrollbar_style(self, palette):
        return f"""
            QScrollBar:vertical {{
                background: transparent;
                width: 12px;
                margin: 6px 3px 6px 3px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {palette['accent']};
                border-radius: 5px;
                min-height: 42px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {palette['accent_deep']};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
                border: none;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 10px;
                margin: 3px 6px 3px 6px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {palette['accent']};
                border-radius: 4px;
                min-width: 42px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {palette['accent_deep']};
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: transparent;
                border: none;
            }}
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}
        """

    def _get_student_training_stats(self):
        try:
            from app.training_records import get_training_record_manager
            manager = get_training_record_manager()
            stats = manager.get_training_statistics(self.user.username)
            summaries = []
            for record in stats.get("details", []):
                training_data = record.get("training_data", {}) if isinstance(record, dict) else {}
                if not isinstance(training_data, dict):
                    training_data = {}
                summaries.append({
                    "completed_at": record.get("completed_at") or training_data.get("completed_at"),
                    "training_mode": training_data.get("training_mode") or training_data.get("training_type"),
                    "training_type": training_data.get("training_type") or training_data.get("training_mode"),
                    "elapsed_time": training_data.get("elapsed_time", 0),
                    "accuracy": training_data.get("accuracy", 0),
                    "expected_events": training_data.get("expected_events", 0),
                    "events_completed": training_data.get("phase4_events_completed", 0),
                    "events_triggered": training_data.get("events_triggered", {}),
                    "events_results": training_data.get("events_results", []),
                    "max_pull_distance": training_data.get("max_pull_distance", 0),
                    "pull_config": training_data.get("pull_config", {}),
                    "training_data": training_data,
                })
            accuracies = [
                item.get("accuracy", 0)
                for item in summaries
                if item.get("training_mode") != "change_dressing" and item.get("accuracy", 0) > 0
            ]
            stats["summaries"] = summaries
            stats["avg_accuracy"] = stats.get("avg_accuracy") or (sum(accuracies) / len(accuracies) if accuracies else 0)
            stats["change_dressing_count"] = stats.get("change_dressing_count", 0)
            return stats
        except Exception as e:
            print(f"[StudentHome] Error loading training stats: {e}")
            return {
                "total_trainings": 0,
                "avg_time": 0,
                "best_time": None,
                "avg_accuracy": 0,
                "change_dressing_count": 0,
                "summaries": [],
            }

    def _student_recent_training_text(self, summaries):
        if not summaries:
            return tr("student.no_training_records")

        lines = []
        for item in summaries[:5]:
            result_text = self._student_training_result_text(item)
            lines.append(
                f"{self._student_format_date(item.get('completed_at'))} | "
                f"{self._student_training_label(item.get('training_mode'))} | "
                f"{self._student_format_seconds(item.get('elapsed_time'))} | "
                f"{result_text}"
            )
        return "\n".join(lines)

    def _student_training_result_text(self, item):
        if item.get("training_mode") == "change_dressing":
            completed = int(item.get("events_completed") or len(item.get("events_results", [])) or 0)
            expected = int(item.get("expected_events") or completed or 3)
            return f"{completed}/{expected} {tr('student.steps')}"
        return f"{item.get('accuracy', 0):.0f}%"

    def _generate_student_ai_summary(self):
        if not hasattr(self, "student_ai_summary") or self.student_ai_summary is None:
            return
        if getattr(self, "_student_ai_worker", None) and self._student_ai_worker.isRunning():
            return

        stats = self._get_student_training_stats()
        summaries = stats.get("summaries", [])
        if not summaries:
            self.student_ai_summary.setText(tr("student.no_training_record_available"))
            return

        if hasattr(self, "student_ai_summary_btn"):
            self.student_ai_summary_btn.setEnabled(False)
        if hasattr(self, "student_ai_loading"):
            self.student_ai_loading.start(
                tr("ai.loading_title"),
                tr("ai.student_loading_detail"),
            )
        self.student_ai_summary.clear()
        QApplication.processEvents()

        def build_report():
            from app.ai_training_agents import create_student_training_agent

            agent = create_student_training_agent()
            return agent.summarize_after_training(
                self.user.username,
                summaries[0],
                recent_records=summaries[1:6],
            )

        def on_result(summary):
            self._set_ai_report_content(self.student_ai_summary, summary)

        def on_error(message):
            print(f"[StudentHome] AI summary failed: {message}")
            self.student_ai_summary.setText(tr("student.ai_summary_failed"))

        def on_finished():
            if hasattr(self, "student_ai_loading"):
                self.student_ai_loading.stop()
            if hasattr(self, "student_ai_summary_btn"):
                self.student_ai_summary_btn.setEnabled(True)
            self._student_ai_worker = None

        self._student_ai_worker = AIReportWorker(build_report, self)
        self._student_ai_worker.result_ready.connect(on_result)
        self._student_ai_worker.error_ready.connect(on_error)
        self._student_ai_worker.finished.connect(on_finished)
        self._student_ai_worker.start()

    def _open_student_ai_summary(self):
        self._show_student_home()
        QTimer.singleShot(100, self._generate_student_ai_summary)

    def _set_ai_report_content(self, widget, content):
        try:
            if hasattr(widget, "setMarkdown"):
                widget.setMarkdown(content)
            else:
                widget.setPlainText(content)
        except Exception:
            try:
                widget.setPlainText(content)
            except Exception:
                widget.setText(content)

    def _student_format_seconds(self, seconds):
        if seconds is None:
            return "-"
        try:
            seconds = int(float(seconds))
        except (TypeError, ValueError):
            return "-"
        minutes, sec = divmod(seconds, 60)
        return tr("common.minutes_seconds", minutes=minutes, seconds=sec) if minutes else tr("common.seconds", seconds=sec)

    def _student_format_date(self, raw):
        if not raw:
            return "-"
        try:
            from datetime import datetime
            return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(raw)[:16]

    def _student_training_label(self, mode):
        label = tr_training_label(mode)
        if label.startswith("training."):
            return mode or tr("common.unknown")
        return label

    def _show_elearning_content(self):
        """Show E-learning module with video player."""
        # Hide all other content containers.
        self._hide_all_content_containers()
        
        # Hide content_view (text placeholder)
        self.content_view.setVisible(False)
        
        # Set title
        self.content_title.setText(tr("student.elearning_module"))
        self.content_title.setVisible(True)
        
        # Create E-learning container if not exists
        if not hasattr(self, 'elearning_container'):
            self.elearning_container = QFrame()
            self.elearning_container.setStyleSheet("background: transparent;")
            layout = QVBoxLayout(self.elearning_container)
            layout.setSpacing(8)
            layout.setContentsMargins(0, 0, 0, 0)
            
            # Video section - create thumbnail view (left-aligned)
            video_section = QFrame()
            video_section.setStyleSheet("background: transparent;")
            video_layout = QVBoxLayout(video_section)
            video_layout.setSpacing(8)
            video_layout.setContentsMargins(0, 0, 0, 0)
            
            # Video title
            video_title = QLabel("Medical Dressing Tutorial")
            video_title.setStyleSheet("""
                font-family: 'Segoe Print', 'Segoe UI', Arial;
                font-size: 18px;
                font-weight: 700;
                color: #003366;
            """)
            video_layout.addWidget(video_title)
            
            # Video thumbnail placeholder (clickable) - 2/3 size
            self.video_thumbnail = QPushButton()
            thumbnail_width = 400  # 2/3 of 600
            thumbnail_height = 225  # Maintain 16:9 ratio
            self.video_thumbnail.setFixedSize(thumbnail_width, thumbnail_height)
            self.video_thumbnail.setStyleSheet("""
                QPushButton {
                    background: #000000;
                    border: 2px solid #4DA3FF;
                    border-radius: 8px;
                    padding: 0px;
                }
                QPushButton:hover {
                    border: 2px solid #234f8d;
                    background: #1a1a1a;
                }
            """)
            
            # Load and display video thumbnail (first frame)
            video_path = os.path.join("assets", "medicaldressing.mp4")
            if os.path.exists(video_path):
                # Try to capture first frame as thumbnail
                try:
                    import cv2
                    cap = cv2.VideoCapture(video_path)
                    ret, frame = cap.read()
                    if ret:
                        # Convert to RGB
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        # Resize to thumbnail size maintaining aspect ratio
                        h, w = frame_rgb.shape[:2]
                        aspect = w / h
                        target_aspect = thumbnail_width / thumbnail_height  # 16:9
                        
                        if aspect > target_aspect:
                            # Image is wider, fit by height
                            new_h = thumbnail_height
                            new_w = int(thumbnail_height * aspect)
                        else:
                            # Image is taller, fit by width
                            new_w = thumbnail_width
                            new_h = int(thumbnail_width / aspect)
                        
                        frame_rgb = cv2.resize(frame_rgb, (new_w, new_h))
                        
                        # Center crop to target size
                        y_offset = (new_h - thumbnail_height) // 2
                        x_offset = (new_w - thumbnail_width) // 2
                        frame_rgb = frame_rgb[y_offset:y_offset+thumbnail_height, x_offset:x_offset+thumbnail_width]
                        
                        # Convert to QPixmap
                        from PySide6.QtGui import QImage
                        h, w, ch = frame_rgb.shape
                        bytes_per_line = 3 * w
                        qt_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                        pixmap = QPixmap.fromImage(qt_image)
                        
                        self.video_thumbnail.setIcon(pixmap)
                        self.video_thumbnail.setIconSize(pixmap.size())
                    cap.release()
                except Exception as e:
                    # Fallback: just show black button with play icon
                    self.video_thumbnail.setText("Click to Play")
                    self.video_thumbnail.setStyleSheet("""
                        QPushButton {
                            background: #000000;
                            border: 2px solid #4DA3FF;
                            border-radius: 8px;
                            padding: 0px;
                            color: #FFFFFF;
                            font-size: 48px;
                            font-weight: 700;
                        }
                        QPushButton:hover {
                            border: 2px solid #234f8d;
                            background: #1a1a1a;
                        }
                    """)
            else:
                self.video_thumbnail.setText("Click to Play")
                self.video_thumbnail.setStyleSheet("""
                    QPushButton {
                        background: #000000;
                        border: 2px solid #4DA3FF;
                        border-radius: 8px;
                        padding: 0px;
                        color: #FFFFFF;
                        font-size: 48px;
                        font-weight: 700;
                    }
                    QPushButton:hover {
                        border: 2px solid #234f8d;
                        background: #1a1a1a;
                    }
                """)
            
            self.video_thumbnail.clicked.connect(self._play_elearning_video)
            video_layout.addWidget(self.video_thumbnail, alignment=Qt.AlignLeft)
            video_layout.addStretch()
            
            layout.addWidget(video_section)
            
            # Learning Materials button
            materials_button_container = QFrame()
            materials_button_container.setStyleSheet("background: transparent;")
            materials_button_layout = QHBoxLayout(materials_button_container)
            materials_button_layout.setSpacing(12)
            materials_button_layout.setContentsMargins(0, 0, 0, 0)
            
            btn_learning_materials = QPushButton("Learning Materials")
            btn_learning_materials.setStyleSheet("""
                QPushButton {
                    background: rgba(77, 163, 255, 0.2);
                    border: 2px solid #4DA3FF;
                    border-radius: 8px;
                    padding: 12px;
                    font-family: 'Segoe Print', 'Segoe UI', Arial;
                    font-size: 16px;
                    font-weight: 600;
                    color: #003366;
                    min-height: 50px;
                    min-width: 200px;
                }
                QPushButton:hover {
                    background: rgba(77, 163, 255, 0.3);
                    border: 2px solid #234f8d;
                }
                QPushButton:pressed {
                    background: rgba(77, 163, 255, 0.4);
                }
            """)
            btn_learning_materials.clicked.connect(self._show_learning_materials)
            materials_button_layout.addWidget(btn_learning_materials, alignment=Qt.AlignLeft)
            materials_button_layout.addStretch()
            
            layout.addWidget(materials_button_container)
            layout.addStretch()
            
            # Add to content area
            content_l = self.content.layout()
            content_l.insertWidget(2, self.elearning_container)
        
        self.elearning_container.setVisible(True)
        self._refresh_student_inline_text_colors()
    
    def _show_learning_materials(self):
        """Show learning materials from reading.md."""
        # Hide elearning container
        if hasattr(self, 'elearning_container'):
            self.elearning_container.setVisible(False)
        
        # Create learning materials container if not exists
        if not hasattr(self, 'learning_materials_container'):
            self.learning_materials_container = QFrame()
            self.learning_materials_container.setStyleSheet("background: transparent;")
            materials_layout = QVBoxLayout(self.learning_materials_container)
            materials_layout.setSpacing(12)
            materials_layout.setContentsMargins(0, 0, 0, 0)
            
            # Create scroll area for content
            scroll_area = QScrollArea()
            scroll_area.setStyleSheet("""
                QScrollArea {
                    background: transparent;
                    border: none;
                }
                QScrollBar:vertical {
                    background: rgba(200, 200, 200, 0.2);
                    width: 10px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical {
                    background: rgba(77, 163, 255, 0.5);
                    border-radius: 5px;
                    min-height: 20px;
                }
                QScrollBar::handle:vertical:hover {
                    background: rgba(77, 163, 255, 0.7);
                }
            """)
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setMinimumHeight(500)
            
            # Content display (read-only text edit)
            self.txt_materials_content = QTextEdit()
            self.txt_materials_content.setReadOnly(True)
            self.txt_materials_content.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.txt_materials_content.setStyleSheet("""
                QTextEdit {
                    font-family: 'Segoe Print', 'Segoe UI', Arial;
                    font-size: 14px;
                    color: #003366;
                    background: rgba(255, 255, 255, 0.5);
                    border: 2px solid rgba(77, 163, 255, 0.3);
                    border-radius: 8px;
                    padding: 12px;
                    line-height: 1.6;
                }
            """)
            scroll_area.setWidget(self.txt_materials_content)
            
            materials_layout.addWidget(scroll_area, 1)
            
            # Back button
            back_button_container = QFrame()
            back_button_container.setStyleSheet("background: transparent;")
            back_button_layout = QHBoxLayout(back_button_container)
            back_button_layout.setSpacing(12)
            back_button_layout.setContentsMargins(0, 0, 0, 0)
            
            btn_back = QPushButton("Back")
            btn_back.setStyleSheet("""
                QPushButton {
                    background: rgba(200, 200, 200, 0.3);
                    border: 2px solid #999999;
                    border-radius: 8px;
                    padding: 10px;
                    font-family: 'Segoe Print', 'Segoe UI', Arial;
                    font-size: 14px;
                    font-weight: 600;
                    color: #003366;
                    min-width: 100px;
                }
                QPushButton:hover {
                    background: rgba(200, 200, 200, 0.4);
                }
                QPushButton:pressed {
                    background: rgba(200, 200, 200, 0.5);
                }
            """)
            btn_back.clicked.connect(self._return_from_learning_materials)
            back_button_layout.addWidget(btn_back, alignment=Qt.AlignLeft)
            back_button_layout.addStretch()
            
            materials_layout.addWidget(back_button_container)
            
            # Add to content area
            content_l = self.content.layout()
            content_l.insertWidget(2, self.learning_materials_container)
        
        # Load and display reading.md content
        reading_path = os.path.join("assets", "reading.md")
        if os.path.exists(reading_path):
            with open(reading_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Simple markdown formatting: convert headers to bold
                content = content.replace("### ", "")
                content = content.replace("## ", "")
                content = content.replace("# ", "")
                self.txt_materials_content.setText(content)
        else:
            self.txt_materials_content.setText("Learning materials not found.")
        
        # Scroll to top
        self.txt_materials_content.verticalScrollBar().setValue(0)
        
        self.learning_materials_container.setVisible(True)
        self._refresh_student_inline_text_colors()
    
    def _return_from_learning_materials(self):
        """Return from learning materials to elearning main view."""
        # Hide learning materials
        if hasattr(self, 'learning_materials_container'):
            self.learning_materials_container.setVisible(False)
        
        # Show elearning container
        if hasattr(self, 'elearning_container'):
            self.elearning_container.setVisible(True)
    
    def _play_elearning_video(self):
        """Play video in full-screen within content area."""
        video_path = os.path.join("assets", "medicaldressing.mp4")
        if not os.path.exists(video_path):
            return
        
        # Hide the thumbnail container
        if hasattr(self, 'elearning_container'):
            self.elearning_container.setVisible(False)
        
        # Create video player frame
        if not hasattr(self, 'elearning_video_player'):
            self.elearning_video_player = QFrame()
            self.elearning_video_player.setStyleSheet("background: #000000;")
            self.elearning_video_player.setMinimumHeight(500)  # Set minimum height for video display
            player_layout = QVBoxLayout(self.elearning_video_player)
            player_layout.setSpacing(0)
            player_layout.setContentsMargins(0, 0, 0, 0)
            
            # Video output widget - Use QVideoWidget if available
            if QVideoWidget is not None:
                self.video_output = QVideoWidget()
                self.video_output.setStyleSheet("background: #000000;")
            else:
                # Fallback if QVideoWidget not available
                self.video_output = QFrame()
                self.video_output.setStyleSheet("background: #000000;")
            
            player_layout.addWidget(self.video_output, 1)  # stretch=1 makes it fill available space
            
            # Control bar with exit button
            control_bar = QFrame()
            control_bar.setStyleSheet("background: rgba(0, 0, 0, 0.8);")
            control_layout = QHBoxLayout(control_bar)
            control_layout.setSpacing(8)
            control_layout.setContentsMargins(12, 8, 12, 8)
            
            # Play/Pause button
            self.btn_play_pause = QPushButton("Pause")
            self.btn_play_pause.setStyleSheet("""
                QPushButton {
                    background: rgba(77, 163, 255, 0.5);
                    border: 1px solid #4DA3FF;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-family: 'Segoe Print';
                    font-size: 14px;
                    color: #FFFFFF;
                    font-weight: 600;
                }
                QPushButton:hover { background: rgba(77, 163, 255, 0.7); }
                QPushButton:pressed { background: rgba(77, 163, 255, 0.9); }
            """)
            self.btn_play_pause.clicked.connect(self._toggle_video_playback)
            control_layout.addWidget(self.btn_play_pause)
            
            # Time display
            self.lbl_time = QLabel("00:00 / 00:00")
            self.lbl_time.setStyleSheet("""
                font-family: 'Segoe Print';
                font-size: 12px;
                color: #FFFFFF;
            """)
            control_layout.addWidget(self.lbl_time)
            
            # Time slider
            self.video_slider = QSlider(Qt.Horizontal)
            self.video_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    background: rgba(200, 200, 200, 0.3);
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #4DA3FF;
                    width: 12px;
                    margin: -3px 0;
                    border-radius: 6px;
                }
            """)
            self.video_slider.sliderMoved.connect(self._seek_video)
            control_layout.addWidget(self.video_slider, 1)
            
            control_layout.addStretch()
            
            # Exit button
            btn_exit = QPushButton("Exit")
            btn_exit.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 80, 80, 0.5);
                    border: 1px solid #FF5050;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-family: 'Segoe Print';
                    font-size: 14px;
                    color: #FFFFFF;
                    font-weight: 600;
                    min-width: 60px;
                }
                QPushButton:hover { background: rgba(255, 80, 80, 0.7); }
                QPushButton:pressed { background: rgba(255, 80, 80, 0.9); }
            """)
            btn_exit.clicked.connect(self._exit_elearning_video)
            control_layout.addWidget(btn_exit)
            
            player_layout.addWidget(control_bar)
            
            # Add to content area
            content_l = self.content.layout()
            content_l.insertWidget(2, self.elearning_video_player)
        
        self.elearning_video_player.setVisible(True)
        
        # Create media player if not exists
        if not hasattr(self, 'elearning_media_player'):
            self.elearning_media_player = QMediaPlayer()
            self.elearning_audio_output = QAudioOutput()
            self.elearning_media_player.setAudioOutput(self.elearning_audio_output)
            
            # Set video output if QVideoWidget is available
            if QVideoWidget is not None and isinstance(self.video_output, QVideoWidget):
                self.elearning_media_player.setVideoOutput(self.video_output)
            
            # Connect signals
            self.elearning_media_player.positionChanged.connect(self._update_video_position)
            self.elearning_media_player.durationChanged.connect(self._update_video_duration)
            self.elearning_media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        
        # Set and play video
        self.elearning_media_player.setSource(QUrl.fromLocalFile(os.path.abspath(video_path)))
        self.elearning_media_player.play()
    
    def _toggle_video_playback(self):
        """Toggle video play/pause."""
        try:
            # Check if media player exists and has valid state
            if not hasattr(self, 'elearning_media_player'):
                return
            
            from PySide6.QtMultimedia import QMediaPlayer
            
            current_state = self.elearning_media_player.playbackState()
            
            # In PySide6, PlayingState is an enum
            if current_state == QMediaPlayer.PlayingState:
                self.elearning_media_player.pause()
                self.btn_play_pause.setText("Play")
            else:
                self.elearning_media_player.play()
                self.btn_play_pause.setText("Pause")
        except Exception as e:
            # Fallback: just toggle play/pause
            try:
                if hasattr(self, 'elearning_media_player'):
                    if self.elearning_media_player.isPlaying():
                        self.elearning_media_player.pause()
                        self.btn_play_pause.setText("Play")
                    else:
                        self.elearning_media_player.play()
                        self.btn_play_pause.setText("Pause")
            except Exception:
                pass
    
    def _seek_video(self, position):
        """Seek to video position."""
        if hasattr(self, 'elearning_media_player'):
            self.elearning_media_player.setPosition(position)
    
    def _update_video_position(self, position):
        """Update video position display and slider."""
        if hasattr(self, 'video_slider'):
            self.video_slider.blockSignals(True)
            self.video_slider.setValue(position)
            self.video_slider.blockSignals(False)
        
        if hasattr(self, 'lbl_time'):
            current_sec = position // 1000
            current_min = current_sec // 60
            current_sec = current_sec % 60
            
            if hasattr(self, 'elearning_media_player'):
                duration = self.elearning_media_player.duration()
                total_sec = duration // 1000
                total_min = total_sec // 60
                total_sec = total_sec % 60
                
                self.lbl_time.setText(f"{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}")
    
    def _update_video_duration(self, duration):
        """Update video duration for slider."""
        if hasattr(self, 'video_slider'):
            self.video_slider.setMaximum(duration)
    
    def _on_playback_state_changed(self):
        """Handle playback state change."""
        try:
            if hasattr(self, 'elearning_media_player') and hasattr(self, 'btn_play_pause'):
                from PySide6.QtMultimedia import QMediaPlayer
                
                current_state = self.elearning_media_player.playbackState()
                if current_state == QMediaPlayer.PlayingState:
                    self.btn_play_pause.setText("Pause")
                else:
                    self.btn_play_pause.setText("Play")
        except Exception:
            pass
    
    def _cleanup_elearning_video(self):
        """Cleanup E-learning video player and hide all video-related widgets."""
        try:
            # Stop media player if it exists and is playing
            if hasattr(self, 'elearning_media_player'):
                self.elearning_media_player.stop()
        except Exception:
            pass
        
        # Hide video player if exists
        if hasattr(self, 'elearning_video_player'):
            try:
                self.elearning_video_player.setVisible(False)
            except Exception:
                pass
        
        # Hide container if exists
        if hasattr(self, 'elearning_container'):
            try:
                self.elearning_container.setVisible(False)
            except Exception:
                pass
        
        # Hide learning materials if exists
        if hasattr(self, 'learning_materials_container'):
            try:
                self.learning_materials_container.setVisible(False)
            except Exception:
                pass
    
    def _cleanup_practice_containers(self):
        """Cleanup practice-related containers and quiz module."""
        try:
            # Hide practice container
            if hasattr(self, 'practice_container'):
                self.practice_container.setVisible(False)
        except Exception:
            pass
        
        try:
            # Hide topic container
            if hasattr(self, 'topic_container'):
                self.topic_container.setVisible(False)
        except Exception:
            pass
        
        try:
            # Hide quiz module and stop audio
            if hasattr(self, 'quiz_module'):
                self.quiz_module.setVisible(False)
                # Stop audio playback
                if hasattr(self.quiz_module, 'audio_player'):
                    self.quiz_module.audio_player.stop()
        except Exception:
            pass
        
        try:
            # Hide completion frame
            if hasattr(self, '_completion_frame'):
                self._completion_frame.setVisible(False)
        except Exception:
            pass
    
    def _exit_elearning_video(self):
        """Exit video player and return to thumbnail view."""
        # Stop playback
        if hasattr(self, 'elearning_media_player'):
            self.elearning_media_player.stop()
        
        # Hide video player
        if hasattr(self, 'elearning_video_player'):
            self.elearning_video_player.setVisible(False)
        
        # Show thumbnail container
        if hasattr(self, 'elearning_container'):
            self.elearning_container.setVisible(True)

    def _show_practice_options(self):
        """Show practice mode selection buttons."""
        # Hide all other content containers.
        self._hide_all_content_containers()
        
        # Hide content view
        self.content_view.setVisible(False)
        
        # Hide topic container
        if hasattr(self, 'topic_container'):
            self.topic_container.setVisible(False)
        
        # Hide quiz module
        if hasattr(self, 'quiz_module'):
            self.quiz_module.setVisible(False)
        
        # Hide completion frame
        if hasattr(self, '_completion_frame'):
            self._completion_frame.setVisible(False)
        
        # Show and set title
        self.content_title.setText(tr("student.practice_questions"))
        self.content_title.setVisible(True)
        
        # Create practice container if not exists
        if not hasattr(self, 'practice_container'):
            self.practice_container = QFrame()
            self.practice_container.setStyleSheet("background: transparent;")
            button_layout = QVBoxLayout(self.practice_container)
            button_layout.setSpacing(16)
            button_layout.setContentsMargins(0, 0, 0, 0)
            
            # Random Practice button
            btn_random = QPushButton("Random Practice\n(Random Selection)")
            btn_random.setStyleSheet("""
                QPushButton {
                    background: rgba(77, 163, 255, 0.2);
                    border: 2px solid #4DA3FF;
                    border-radius: 8px;
                    padding: 16px;
                    font-family: 'Segoe Print', 'Segoe UI', Arial;
                    font-size: 16px;
                    font-weight: 600;
                    color: #003366;
                    min-height: 80px;
                }
                QPushButton:hover {
                    background: rgba(77, 163, 255, 0.3);
                    border: 2px solid #234f8d;
                }
                QPushButton:pressed {
                    background: rgba(77, 163, 255, 0.4);
                }
            """)
            btn_random.clicked.connect(self._start_random_practice)
            button_layout.addWidget(btn_random)
            
            # Topic-Based Practice button
            btn_topic = QPushButton("Topic-Based Practice\n(Choose a topic)")
            btn_topic.setStyleSheet("""
                QPushButton {
                    background: rgba(77, 163, 255, 0.2);
                    border: 2px solid #4DA3FF;
                    border-radius: 8px;
                    padding: 16px;
                    font-family: 'Segoe Print', 'Segoe UI', Arial;
                    font-size: 16px;
                    font-weight: 600;
                    color: #003366;
                    min-height: 80px;
                }
                QPushButton:hover {
                    background: rgba(77, 163, 255, 0.3);
                    border: 2px solid #234f8d;
                }
                QPushButton:pressed {
                    background: rgba(77, 163, 255, 0.4);
                }
            """)
            btn_topic.clicked.connect(self._show_topic_options)
            button_layout.addWidget(btn_topic)
            
            button_layout.addStretch()
            
            # Add to content area
            content_l = self.content.layout()
            content_l.insertWidget(2, self.practice_container)
        
        self.practice_container.setVisible(True)
        self._refresh_student_inline_text_colors()
    
    def _start_random_practice(self):
        """Start random practice with all questions shuffled."""
        # Hide practice options
        if hasattr(self, 'practice_container'):
            self.practice_container.setVisible(False)
        
        # Hide topic container if visible
        if hasattr(self, 'topic_container'):
            self.topic_container.setVisible(False)
        
        # Create or show quiz module
        if not hasattr(self, 'quiz_module'):
            self.quiz_module = QuizModule()
            quiz_path = os.path.join("assets", "epidural_quiz_questions.json")
            self.quiz_module.load_quiz_data(quiz_path)
            
            # Connect completion signal
            self.quiz_module.quiz_completed.connect(self._on_quiz_completed)
            # Connect back button signal
            self.quiz_module.back_clicked.connect(self._on_quiz_back)
            
            # Add to content area
            content_l = self.content.layout()
            content_l.insertWidget(2, self.quiz_module)
        
        self.quiz_module.setVisible(True)
        
        # Get all question IDs and shuffle
        all_questions = list(self.quiz_module.questions.keys())
        random.shuffle(all_questions)
        
        # Start quiz
        self.quiz_module.start_quiz(all_questions)
    
    def _show_topic_options(self):
        """Show topic selection buttons."""
        # Hide all other content containers.
        self._hide_all_content_containers()
        
        # Hide practice options
        if hasattr(self, 'practice_container'):
            self.practice_container.setVisible(False)
        
        # Hide quiz module if visible
        if hasattr(self, 'quiz_module'):
            self.quiz_module.setVisible(False)
        
        # Hide completion frame if visible
        if hasattr(self, '_completion_frame'):
            self._completion_frame.setVisible(False)
        
        # Create topic container if not exists
        if not hasattr(self, 'topic_container'):
            self.topic_container = QFrame()
            self.topic_container.setStyleSheet("background: transparent;")
            button_layout = QVBoxLayout(self.topic_container)
            button_layout.setSpacing(16)
            button_layout.setContentsMargins(0, 0, 0, 0)
            
            # Topic 1 button (in order)
            btn_topic1 = QPushButton("Topic 1")
            btn_topic1.setStyleSheet("""
                QPushButton {
                    background: rgba(77, 163, 255, 0.2);
                    border: 2px solid #4DA3FF;
                    border-radius: 8px;
                    padding: 16px;
                    font-family: 'Segoe Print', 'Segoe UI', Arial;
                    font-size: 16px;
                    font-weight: 600;
                    color: #003366;
                    min-height: 80px;
                }
                QPushButton:hover {
                    background: rgba(77, 163, 255, 0.3);
                    border: 2px solid #234f8d;
                }
                QPushButton:pressed {
                    background: rgba(77, 163, 255, 0.4);
                }
            """)
            btn_topic1.clicked.connect(lambda: self._start_topic_practice("topic1"))
            button_layout.addWidget(btn_topic1)
            
            # Topic 2 button (reverse order)
            btn_topic2 = QPushButton("Topic 2")
            btn_topic2.setStyleSheet("""
                QPushButton {
                    background: rgba(77, 163, 255, 0.2);
                    border: 2px solid #4DA3FF;
                    border-radius: 8px;
                    padding: 16px;
                    font-family: 'Segoe Print', 'Segoe UI', Arial;
                    font-size: 16px;
                    font-weight: 600;
                    color: #003366;
                    min-height: 80px;
                }
                QPushButton:hover {
                    background: rgba(77, 163, 255, 0.3);
                    border: 2px solid #234f8d;
                }
                QPushButton:pressed {
                    background: rgba(77, 163, 255, 0.4);
                }
            """)
            btn_topic2.clicked.connect(lambda: self._start_topic_practice("topic2"))
            button_layout.addWidget(btn_topic2)
            
            # Back button
            btn_back = QPushButton("Back to Practice Menu")
            btn_back.setStyleSheet("""
                QPushButton {
                    background: rgba(200, 200, 200, 0.3);
                    border: 2px solid #999999;
                    border-radius: 8px;
                    padding: 10px;
                    font-family: 'Segoe Print', 'Segoe UI', Arial;
                    font-size: 14px;
                    font-weight: 600;
                    color: #003366;
                }
                QPushButton:hover {
                    background: rgba(200, 200, 200, 0.4);
                }
                QPushButton:pressed {
                    background: rgba(200, 200, 200, 0.5);
                }
            """)
            btn_back.clicked.connect(self._show_practice_options)
            button_layout.addWidget(btn_back)
            
            button_layout.addStretch()
            
            # Add to content area
            content_l = self.content.layout()
            content_l.insertWidget(2, self.topic_container)
        
        self.topic_container.setVisible(True)
        self._refresh_student_inline_text_colors()
    
    def _start_topic_practice(self, topic_id):
        """Start topic-based practice."""
        # Hide topic container
        if hasattr(self, 'topic_container'):
            self.topic_container.setVisible(False)
        
        # Create or show quiz module
        if not hasattr(self, 'quiz_module'):
            self.quiz_module = QuizModule()
            quiz_path = os.path.join("assets", "epidural_quiz_questions.json")
            self.quiz_module.load_quiz_data(quiz_path)
            
            # Connect completion signal
            self.quiz_module.quiz_completed.connect(self._on_quiz_completed)
            # Connect back button signal
            self.quiz_module.back_clicked.connect(self._on_quiz_back)
            
            # Add to content area
            content_l = self.content.layout()
            content_l.insertWidget(2, self.quiz_module)
        
        self.quiz_module.setVisible(True)
        
        # Get all question IDs
        all_questions = list(self.quiz_module.questions.keys())
        
        if topic_id == "topic1":
            # Topic 1: Sequential order (Q1, Q2, Q3, Q4, Q5)
            question_list = sorted(all_questions)
        else:
            # Topic 2: Reverse order (Q5, Q4, Q3, Q2, Q1)
            question_list = sorted(all_questions, reverse=True)
        
        # Start quiz
        self.quiz_module.start_quiz(question_list)
    
    def _on_quiz_back(self):
        """Handle back button click in quiz."""
        # Hide quiz module
        if hasattr(self, 'quiz_module'):
            self.quiz_module.setVisible(False)
        
        # Show practice options
        self._show_practice_options()
    
    def _on_quiz_completed(self):
        """Handle quiz completion."""
        if not hasattr(self, 'quiz_module'):
            return
        
        # Check if in training mode
        if hasattr(self.quiz_module, 'training_mode') and self.quiz_module.training_mode:
            # Training mode: check if answered correctly
            correct, total = self.quiz_module.get_score()
            is_correct = (correct == total)  # 只有全部答对才算成功
            
            print(f"[Training] Quiz completed: {correct}/{total} correct, is_correct={is_correct}")
            self.quiz_module.setVisible(False)
            
            # Resume Phase 4 removal and pass the quiz result.
            if hasattr(self, 'current_training') and self.current_training:
                # record the quiz result into the training module (so records can include accuracy)
                try:
                    qid = getattr(self, '_pending_training_quiz_id', None)
                    if qid:
                        try:
                            self.current_training.record_quiz_result(qid, is_correct)
                        except Exception as e:
                            print(f"[Training] Error recording quiz result: {e}")
                    # clear pending id
                    self._pending_training_quiz_id = None
                except Exception:
                    pass
                self.current_training.resume_phase4(quiz_correct=is_correct)
            
            return
        
        # Practice mode: show score and completion message
        # Get score
        correct, total = self.quiz_module.get_score()
        
        # Save to practice history
        self._save_practice_record(correct, total)
        
        # Hide quiz module
        self.quiz_module.setVisible(False)
        
        # Play pass.mp3
        pass_audio_path = os.path.join("assets", "pass.mp3")
        if os.path.exists(pass_audio_path):
            audio_player = QMediaPlayer()
            audio_output = QAudioOutput()
            audio_player.setAudioOutput(audio_output)
            audio_player.setSource(QUrl.fromLocalFile(os.path.abspath(pass_audio_path)))
            audio_player.play()
            
            # Store player to prevent garbage collection
            self._completion_audio_player = audio_player
        
        # Show completion message
        self._show_quiz_completion_message(correct, total)
    
    def _show_quiz_completion_message(self, correct, total):
        """Show quiz completion message."""
        # Play pass.mp3 when quiz completes
        pass_audio_path = os.path.join("assets", "pass.mp3")
        if os.path.exists(pass_audio_path):
            pass_player = QMediaPlayer()
            pass_output = QAudioOutput()
            pass_player.setAudioOutput(pass_output)
            pass_player.setSource(QUrl.fromLocalFile(os.path.abspath(pass_audio_path)))
            pass_player.play()
            # Store to prevent garbage collection
            self._pass_audio_player = pass_player
        
        # Create completion container
        completion_frame = QFrame()
        completion_frame.setStyleSheet("background: transparent;")
        completion_layout = QVBoxLayout(completion_frame)
        completion_layout.setSpacing(20)
        completion_layout.setContentsMargins(0, 0, 0, 0)
        
        # Completion message
        lbl_completion = QLabel(f"Quiz Completed!\n\nYour Score: {correct}/{total}")
        lbl_completion.setStyleSheet("""
            font-family: 'Segoe Print', 'Segoe UI', Arial;
            font-size: 28px;
            font-weight: 700;
            color: #003366;
            background: rgba(200, 255, 200, 0.3);
            padding: 20px;
            border-radius: 10px;
        """)
        lbl_completion.setAlignment(Qt.AlignCenter)
        completion_layout.addWidget(lbl_completion)
        
        # Back to practice menu button
        btn_back = QPushButton("Back to Practice Menu")
        btn_back.setStyleSheet("""
            QPushButton {
                background: rgba(77, 163, 255, 0.3);
                border: 2px solid #4DA3FF;
                border-radius: 8px;
                padding: 12px;
                font-family: 'Segoe Print', 'Segoe UI', Arial;
                font-size: 16px;
                font-weight: 600;
                color: #003366;
                min-height: 50px;
            }
            QPushButton:hover {
                background: rgba(77, 163, 255, 0.4);
            }
            QPushButton:pressed {
                background: rgba(77, 163, 255, 0.5);
            }
        """)
        btn_back.clicked.connect(self._return_to_practice_options)
        completion_layout.addWidget(btn_back)
        
        completion_layout.addStretch()
        
        # Store the completion frame
        self._completion_frame = completion_frame
        
        # Add to content area and raise to front
        content_l = self.content.layout()
        content_l.insertWidget(2, completion_frame)
        completion_frame.setVisible(True)
        completion_frame.raise_()
        self._refresh_student_inline_text_colors()
    
    def _return_to_practice_options(self):
        """Return to practice menu."""
        # Hide completion frame
        if hasattr(self, '_completion_frame'):
            self._completion_frame.setVisible(False)
        
        # Hide topic container
        if hasattr(self, 'topic_container'):
            self.topic_container.setVisible(False)
        
        # Hide quiz module
        if hasattr(self, 'quiz_module'):
            self.quiz_module.setVisible(False)
        
        # Show practice options
        self._show_practice_options()

    def _show_practice_records(self):
        """Show practice records with statistics and curve."""
        self.content_view.setVisible(False)
        self.content_title.setText(tr("student.practice_records"))
        self.content_title.setVisible(True)
        
        # Always recreate the container to ensure fresh display
        if hasattr(self, 'practice_records_container') and self.practice_records_container:
            try:
                self.content.layout().removeWidget(self.practice_records_container)
                self.practice_records_container.deleteLater()
            except:
                pass
        
        self.practice_records_container = QFrame()
        self.practice_records_container.setStyleSheet("background: transparent;")
        records_layout = QVBoxLayout(self.practice_records_container)
        records_layout.setSpacing(12)
        records_layout.setContentsMargins(0, 0, 0, 0)
        
        # Statistics panel
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background: rgba(255, 255, 255, 0.3); border: 2px solid rgba(77, 163, 255, 0.3); border-radius: 8px; padding: 12px;")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setSpacing(20)
        
        # Overall accuracy label
        self.lbl_overall_accuracy = QLabel("Overall Accuracy: 0%")
        self.lbl_overall_accuracy.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #003366; font-weight: 700;")
        stats_layout.addWidget(self.lbl_overall_accuracy)
        
        # Recent attempts label
        self.lbl_recent_accuracy = QLabel("Recent 10: 0%")
        self.lbl_recent_accuracy.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #234f8d; font-weight: 600;")
        stats_layout.addWidget(self.lbl_recent_accuracy)
        
        # Info label
        lbl_info = QLabel("(Statistics based on first attempt only)")
        lbl_info.setStyleSheet("font-family: 'Segoe Print'; font-size: 12px; color: #666666; font-style: italic;")
        stats_layout.addWidget(lbl_info)
        
        stats_layout.addStretch()
        records_layout.addWidget(stats_frame)
        
        # Chart area - placeholder for matplotlib figure
        self.records_chart_container = QFrame()
        self.records_chart_container.setStyleSheet("background: rgba(255, 255, 255, 0.2); border: 2px solid rgba(77, 163, 255, 0.2); border-radius: 8px;")
        self.records_chart_layout = QVBoxLayout(self.records_chart_container)
        self.records_chart_layout.setContentsMargins(8, 8, 8, 8)
        self.records_chart_layout.setSpacing(8)
        
        lbl_chart = QLabel("Practice Accuracy Trend (Last 10 Attempts)")
        lbl_chart.setStyleSheet("font-family: 'Segoe Print'; font-size: 14px; color: #003366; font-weight: 600;")
        self.records_chart_layout.addWidget(lbl_chart)
        
        # Chart will be added here dynamically
        self.records_chart_canvas = None
        
        records_layout.addWidget(self.records_chart_container, 1)
        
        # Add to content area
        content_l = self.content.layout()
        content_l.insertWidget(2, self.practice_records_container)
        
        self.practice_records_container.setVisible(True)
        self._update_practice_statistics()
        self._refresh_student_inline_text_colors()

    def _update_practice_statistics(self):
        """Update practice statistics from history file."""
        try:
            history_path = os.path.join("assets", "practice_history.json")
            if not os.path.exists(history_path):
                return
            
            with open(history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            records = data.get("records", [])
            if not records:
                return
            
            # Calculate overall accuracy
            total_correct = sum(r.get("correct", 0) for r in records)
            total_questions = sum(r.get("total", 5) for r in records)
            overall_accuracy = int(total_correct * 100 / total_questions) if total_questions > 0 else 0
            
            self.lbl_overall_accuracy.setText(f"Overall Accuracy: {overall_accuracy}%")
            
            # Recent 10 attempts
            recent_10 = records[-10:] if len(records) >= 10 else records
            recent_correct = sum(r.get("correct", 0) for r in recent_10)
            recent_total = sum(r.get("total", 5) for r in recent_10)
            recent_accuracy = int(recent_correct * 100 / recent_total) if recent_total > 0 else 0
            self.lbl_recent_accuracy.setText(f"Recent 10: {recent_accuracy}%")
            
            # Draw chart
            self._draw_practice_chart(recent_10)
            
        except Exception as e:
            print(f"Error updating practice statistics: {e}")

    def _draw_practice_chart(self, recent_records):
        """Draw practice accuracy trend chart using matplotlib."""
        try:
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            
            # Check if we have data
            if not recent_records:
                print("[MainWindow] No records to draw chart")
                return
            
            print(f"[MainWindow] Drawing chart with {len(recent_records)} records")
            
            # Clear previous canvas - only remove canvas widgets, not the title
            widget_to_remove = None
            for i in range(self.records_chart_layout.count()):
                widget = self.records_chart_layout.itemAt(i).widget()
                if widget and hasattr(widget, '__class__') and 'FigureCanvas' in str(widget.__class__):
                    widget_to_remove = widget
                    break
            
            if widget_to_remove:
                self.records_chart_layout.removeWidget(widget_to_remove)
                widget_to_remove.deleteLater()
            
            # Create figure with better size
            fig = Figure(figsize=(7, 2.8), dpi=100)
            fig.patch.set_alpha(0.0)
            ax = fig.add_subplot(111)
            chart_text_color, chart_grid_color = self._student_inline_text_targets()
            
            # Prepare data
            attempts = list(range(1, len(recent_records) + 1))
            accuracies = [r.get("accuracy", 0) for r in recent_records]
            
            print(f"[MainWindow] Attempts: {attempts}, Accuracies: {accuracies}")
            
            # Plot - use matplotlib-compatible colors
            ax.plot(attempts, accuracies, marker='o', linestyle='-', linewidth=2.5, 
                   color='#4DA3FF', markersize=8, markerfacecolor='#4DA3FF', 
                   markeredgecolor=chart_text_color, markeredgewidth=2)
            ax.fill_between(attempts, accuracies, alpha=0.25, color='#4DA3FF')
            
            # Styling - use hex colors and tuples instead of rgba()
            ax.set_xlabel("Attempt", fontsize=12, color=chart_text_color, weight='bold')
            ax.set_ylabel("Accuracy (%)", fontsize=12, color=chart_text_color, weight='bold')
            ax.set_ylim(0, 105)
            ax.set_xlim(0.5, len(recent_records) + 0.5)
            ax.grid(True, alpha=0.3, linestyle='--', color=chart_grid_color)
            ax.set_facecolor((1.0, 1.0, 1.0, 0.05))  # Use tuple instead of rgba()
            
            # Set tick colors and labels
            ax.tick_params(colors=chart_text_color, labelsize=10)
            ax.set_xticks(attempts)
            
            # Spine styling
            for spine in ax.spines.values():
                spine.set_color('#4DA3FF')
                spine.set_linewidth(2)
            
            fig.tight_layout(pad=1.0)
            
            # Create and add canvas
            canvas = FigureCanvas(fig)
            self.records_chart_layout.addWidget(canvas, 1)
            
            # Force layout update
            self.records_chart_container.update()
            
            print(f"[MainWindow] Chart successfully drawn")
            
        except ImportError as e:
            print(f"[MainWindow] matplotlib not available: {e}")
            self._show_simple_chart(recent_records)
        except Exception as e:
            print(f"[MainWindow] Error drawing practice chart: {e}")
            import traceback
            traceback.print_exc()
            # Fall back to simple chart
            self._show_simple_chart(recent_records)

    def _show_simple_chart(self, recent_records):
        """Show a simple text-based chart alternative when matplotlib is not available."""
        try:
            # Remove any existing canvas
            for i in range(self.records_chart_layout.count()):
                widget = self.records_chart_layout.itemAt(i).widget()
                if widget and hasattr(widget, '__class__') and 'FigureCanvas' in str(widget.__class__):
                    self.records_chart_layout.removeWidget(widget)
                    widget.deleteLater()
                    break
            
            # Create a text-based representation
            chart_text = "Accuracy Trend:\n\n"
            for i, record in enumerate(recent_records, 1):
                accuracy = record.get("accuracy", 0)
                bars = int(accuracy / 5)
                chart_text += f"Attempt {i:2d}: {'#' * bars}{'.' * (20 - bars)} {accuracy}%\n"
            
            text_widget = QTextEdit()
            text_widget.setReadOnly(True)
            text_widget.setText(chart_text)
            text_widget.setStyleSheet("""
                QTextEdit {
                    font-family: 'Courier New', monospace;
                    font-size: 11px;
                    color: #003366;
                    background: rgba(255, 255, 255, 0.05);
                    border: none;
                    padding: 8px;
                }
            """)
            text_widget.setMaximumHeight(180)
            
            self.records_chart_layout.addWidget(text_widget, 1)
            print("[MainWindow] Simple chart displayed")
            
        except Exception as e:
            print(f"[MainWindow] Error showing simple chart: {e}")

    def _cleanup_practice_records(self):
        """Cleanup practice records container."""
        try:
            if hasattr(self, 'practice_records_container'):
                self.practice_records_container.setVisible(False)
        except Exception:
            pass

    def _show_training_records(self):
        """Show training (simulation) records with statistics."""
        if hasattr(self, 'student_home_container'):
            self.student_home_container.setVisible(False)
        self.content_view.setVisible(False)
        self.content_title.setText(tr("student.training_records"))
        self.content_title.setVisible(True)
        
        # Always recreate the container to ensure fresh display
        if hasattr(self, 'training_records_container') and self.training_records_container:
            try:
                self.content.layout().removeWidget(self.training_records_container)
                self.training_records_container.deleteLater()
            except:
                pass
        
        self.training_records_container = QFrame()
        self.training_records_container.setStyleSheet("background: transparent;")
        records_layout = QVBoxLayout(self.training_records_container)
        records_layout.setSpacing(12)
        records_layout.setContentsMargins(0, 0, 0, 0)
        
        # Statistics panel
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background: rgba(255, 255, 255, 0.3); border: 2px solid rgba(77, 163, 255, 0.3); border-radius: 8px; padding: 12px;")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setSpacing(20)
        
        # Training count
        self.lbl_training_count = QLabel(tr("student.total_trainings", count=0))
        self.lbl_training_count.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #003366; font-weight: 700;")
        stats_layout.addWidget(self.lbl_training_count)

        self.lbl_dressing_changes = QLabel(tr("student.dressing_changes") + ": 0")
        self.lbl_dressing_changes.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #234f8d; font-weight: 600;")
        stats_layout.addWidget(self.lbl_dressing_changes)
        
        # Total time
        self.lbl_training_time = QLabel(tr("student.total_time", time=tr("common.seconds", seconds=0)))
        self.lbl_training_time.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #234f8d; font-weight: 600;")
        stats_layout.addWidget(self.lbl_training_time)
        
        # Average time
        self.lbl_training_avg = QLabel(tr("student.average_time", time=tr("common.seconds", seconds=0)))
        self.lbl_training_avg.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #234f8d; font-weight: 600;")
        stats_layout.addWidget(self.lbl_training_avg)

        btn_training_ai_summary = QPushButton(tr("student.generate_ai_summary_inline"))
        btn_training_ai_summary.setStyleSheet("""
            QPushButton {
                background: rgba(77, 163, 255, 0.24);
                border: 2px solid #4DA3FF;
                border-radius: 8px;
                padding: 8px 12px;
                font-family: 'Segoe Print', 'Segoe UI', Arial;
                font-size: 14px;
                font-weight: 700;
                color: #003366;
            }
            QPushButton:hover {
                background: rgba(77, 163, 255, 0.34);
                border-color: #234f8d;
            }
        """)
        btn_training_ai_summary.clicked.connect(self._open_student_ai_summary)
        stats_layout.addWidget(btn_training_ai_summary)
        
        stats_layout.addStretch()
        records_layout.addWidget(stats_frame)
        
        # Records list
        self.training_records_list = QListWidget()
        self.training_records_list.setStyleSheet("""
            QListWidget {
                background: rgba(255, 255, 255, 0.2);
                border: 2px solid rgba(77, 163, 255, 0.2);
                border-radius: 8px;
                outline: 0;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(77, 163, 255, 0.1);
                color: #003366;
                background: transparent;
            }
            QListWidget::item:hover {
                background: rgba(77, 163, 255, 0.1);
            }
            QListWidget::item:selected {
                background: rgba(77, 163, 255, 0.2);
                color: #003366;
            }
        """)
        self.training_records_list.setFont(QFont('Segoe Print', 11))
        records_layout.addWidget(self.training_records_list, 1)
        
        # 添加两个图表容器（时间和正确率趋势）
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(12)
        
        # Time trend chart container.
        time_chart_container = QFrame()
        time_chart_container.setStyleSheet("background: transparent;")
        time_chart_layout = QVBoxLayout(time_chart_container)
        time_chart_layout.setContentsMargins(0, 0, 0, 0)
        time_chart_title = QLabel(tr("student.training_time_trend"))
        time_chart_title.setFont(QFont('Segoe Print', 12, QFont.Bold))
        time_chart_title.setStyleSheet("color: #003366;")
        time_chart_layout.addWidget(time_chart_title)
        self.training_time_chart_layout = QVBoxLayout()
        self.training_time_chart_layout.setContentsMargins(0, 0, 0, 0)
        time_chart_layout.addLayout(self.training_time_chart_layout)
        charts_layout.addWidget(time_chart_container)
        
        # 正确率趋势图容器
        accuracy_chart_container = QFrame()
        accuracy_chart_container.setStyleSheet("background: transparent;")
        accuracy_chart_layout = QVBoxLayout(accuracy_chart_container)
        accuracy_chart_layout.setContentsMargins(0, 0, 0, 0)
        accuracy_chart_title = QLabel(tr("student.accuracy_trend"))
        accuracy_chart_title.setFont(QFont('Segoe Print', 12, QFont.Bold))
        accuracy_chart_title.setStyleSheet("color: #003366;")
        accuracy_chart_layout.addWidget(accuracy_chart_title)
        self.training_accuracy_chart_layout = QVBoxLayout()
        self.training_accuracy_chart_layout.setContentsMargins(0, 0, 0, 0)
        accuracy_chart_layout.addLayout(self.training_accuracy_chart_layout)
        charts_layout.addWidget(accuracy_chart_container)
        
        records_layout.addLayout(charts_layout, 1)
        
        # Add to content area
        content_l = self.content.layout()
        content_l.insertWidget(2, self.training_records_container)
        
        self.training_records_container.setVisible(True)
        self._update_training_records()
        self._refresh_student_inline_text_colors()

    def _update_training_records(self):
        """Update training records from storage with charts."""
        try:
            from app.training_records import get_training_record_manager
            
            manager = get_training_record_manager()
            stats = manager.get_training_statistics(self.user.username)
            
            # Update statistics
            self.lbl_training_count.setText(tr("student.total_trainings", count=stats['total_trainings']))
            if hasattr(self, "lbl_dressing_changes"):
                self.lbl_dressing_changes.setText(f"{tr('student.dressing_changes')}: {stats.get('change_dressing_count', 0)}")
            total_minutes = int(stats['total_time'] // 60)
            self.lbl_training_time.setText(tr("student.total_time", time=tr("common.minutes_seconds", minutes=total_minutes, seconds=int(stats['total_time'] % 60))))
            avg_seconds = int(stats['avg_time'])
            self.lbl_training_avg.setText(tr("student.average_time", time=tr("common.seconds", seconds=avg_seconds)))
            
            # Collect records data
            details = stats['details']
            elapsed_times = []
            accuracies = []
            training_types = []
            
            for record in details:
                training_data = record.get('training_data', {})
                elapsed_time = training_data.get('elapsed_time', 0)
                accuracy = training_data.get('accuracy', 0)
                training_type = training_data.get('training_mode') or training_data.get('training_type', 'unknown')
                elapsed_times.append(elapsed_time)
                if training_type != "change_dressing" and accuracy:
                    accuracies.append(accuracy)
                training_types.append(training_type)
            
            # Update records list
            self.training_records_list.clear()
            for i, record in enumerate(details):
                training_data = record.get('training_data', {})
                elapsed_time = training_data.get('elapsed_time', 0)
                accuracy = training_data.get('accuracy', 0)
                training_type = training_data.get('training_mode') or training_data.get('training_type', 'unknown')
                completed_at = record.get('completed_at', 'Unknown')
                
                # Format datetime
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(completed_at)
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    time_str = completed_at[:10]
                
                if training_type == "change_dressing":
                    completed = int(training_data.get("phase4_events_completed") or len(training_data.get("events_results", [])) or 0)
                    expected = int(training_data.get("expected_events") or completed or 3)
                    result_text = f"{completed}/{expected} {tr('student.steps')}"
                else:
                    result_text = f"{accuracy:.0f}%"

                item_text = f"{time_str} | {self._student_training_label(training_type)} | {elapsed_time:.1f}s | {result_text}"
                item = QListWidgetItem(item_text)
                self.training_records_list.addItem(item)
            
            # Draw charts
            if elapsed_times:
                self._draw_training_time_chart(elapsed_times)
                self._draw_training_accuracy_chart(accuracies)
            
        except Exception as e:
            print(f"Error updating training records: {e}")
            import traceback
            traceback.print_exc()
    
    def _draw_training_time_chart(self, elapsed_times):
        """Draw training time trend chart."""
        try:
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            
            # Clear previous canvas
            while self.training_time_chart_layout.count():
                widget = self.training_time_chart_layout.takeAt(0).widget()
                if widget and hasattr(widget, '__class__') and 'FigureCanvas' in str(widget.__class__):
                    widget.deleteLater()
            
            # Create figure
            fig = Figure(figsize=(5, 2.5), dpi=100)
            fig.patch.set_alpha(0.0)
            ax = fig.add_subplot(111)
            chart_text_color, chart_grid_color = self._student_inline_text_targets()
            
            # Prepare data
            attempts = list(range(1, len(elapsed_times) + 1))
            
            # Plot
            ax.plot(attempts, elapsed_times, marker='o', linestyle='-', linewidth=2.5,
                   color='#4DA3FF', markersize=8, markerfacecolor='#4DA3FF',
                   markeredgecolor=chart_text_color, markeredgewidth=2)
            ax.fill_between(attempts, elapsed_times, alpha=0.25, color='#4DA3FF')
            
            # Styling
            ax.set_xlabel("Attempt", fontsize=11, color=chart_text_color, weight='bold')
            ax.set_ylabel("Time (seconds)", fontsize=11, color=chart_text_color, weight='bold')
            ax.set_xlim(0.5, len(elapsed_times) + 0.5)
            ax.grid(True, alpha=0.3, linestyle='--', color=chart_grid_color)
            ax.set_facecolor((1.0, 1.0, 1.0, 0.05))
            
            # Styling ticks
            ax.tick_params(colors=chart_text_color, labelsize=9)
            ax.set_xticks(attempts)
            
            # Spine styling
            for spine in ax.spines.values():
                spine.set_color('#4DA3FF')
                spine.set_linewidth(1.5)
            
            fig.tight_layout(pad=1.0)
            
            # Create and add canvas
            canvas = FigureCanvas(fig)
            self.training_time_chart_layout.addWidget(canvas)
            
        except Exception as e:
            print(f"Error drawing training time chart: {e}")
    
    def _draw_training_accuracy_chart(self, accuracies):
        """Draw training accuracy trend chart."""
        try:
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            
            # Clear previous canvas
            while self.training_accuracy_chart_layout.count():
                widget = self.training_accuracy_chart_layout.takeAt(0).widget()
                if widget and hasattr(widget, '__class__') and 'FigureCanvas' in str(widget.__class__):
                    widget.deleteLater()
            
            # Create figure
            fig = Figure(figsize=(5, 2.5), dpi=100)
            fig.patch.set_alpha(0.0)
            ax = fig.add_subplot(111)
            chart_text_color, chart_grid_color = self._student_inline_text_targets()
            
            # Prepare data
            attempts = list(range(1, len(accuracies) + 1))
            
            # Plot
            ax.plot(attempts, accuracies, marker='o', linestyle='-', linewidth=2.5,
                   color='#00AA00', markersize=8, markerfacecolor='#00AA00',
                   markeredgecolor='#006600', markeredgewidth=2)
            ax.fill_between(attempts, accuracies, alpha=0.25, color='#00AA00')
            
            # Styling
            ax.set_xlabel("Attempt", fontsize=11, color=chart_text_color, weight='bold')
            ax.set_ylabel("Accuracy (%)", fontsize=11, color=chart_text_color, weight='bold')
            ax.set_ylim(0, 105)
            ax.set_xlim(0.5, len(accuracies) + 0.5)
            ax.grid(True, alpha=0.3, linestyle='--', color=chart_grid_color)
            ax.set_facecolor((1.0, 1.0, 1.0, 0.05))
            
            # Styling ticks
            ax.tick_params(colors=chart_text_color, labelsize=9)
            ax.set_xticks(attempts)
            
            # Spine styling
            for spine in ax.spines.values():
                spine.set_color('#00AA00')
                spine.set_linewidth(1.5)
            
            fig.tight_layout(pad=1.0)
            
            # Create and add canvas
            canvas = FigureCanvas(fig)
            self.training_accuracy_chart_layout.addWidget(canvas)
            
        except Exception as e:
            print(f"Error drawing training accuracy chart: {e}")

    def _cleanup_training_records(self):
        """Cleanup training records container."""
        try:
            if hasattr(self, 'training_records_container'):
                self.training_records_container.setVisible(False)
        except Exception:
            pass
    
    def _init_ai_mentor(self):
        """初始化AI Nursing Mentor"""
        # Ensure the attribute exists before later access.
        self.ai_mentor = None
        try:
            from app.ai_mentor import AIMentor

            # 尝试导入配置
            try:
                from app.ai_config_local import API_URL, API_KEY, MODEL, BASE_URL
            except ImportError:
                # 使用示例配置
                from app.ai_config_example import API_URL, API_KEY, MODEL, BASE_URL
                print("[MainWindow] Warning: Using example AI config. Prefer DASHSCOPE_API_KEY env var for secrets")

            # Validate API config
            api_key = API_KEY or os.getenv("DASHSCOPE_API_KEY", "")
            if api_key == "your-api-key-here" or not api_key:
                print("[MainWindow] Error: API key not configured. Please set API_KEY in app/ai_config_local.py")
                return None

            # Create the AI mentor instance, passing model/base_url when supported.
            try:
                self.ai_mentor = AIMentor(API_URL, api_key, model=MODEL, base_url=BASE_URL)
            except Exception:
                # 兼容旧构造（若MODEL/BASE_URL不存在）
                self.ai_mentor = AIMentor(API_URL, api_key)

            print("[MainWindow] AI Mentor initialized successfully")
            return self.ai_mentor

        except ImportError as e:
            print(f"[MainWindow] Error importing AI Mentor: {e}")
            self.ai_mentor = None
            return None
        except Exception as e:
            print(f"[MainWindow] Error initializing AI Mentor: {e}")
            self.ai_mentor = None
            return None

    def _show_ai_mentor(self):
        """显示AI Nursing Mentor对话界面"""
        try:
            from app.ui.ai_mentor_widget import AIMentorWidget
            
            # Initialize AI Mentor if needed.
            if not hasattr(self, 'ai_mentor') or self.ai_mentor is None:
                self._init_ai_mentor()
            # 如果初始化后仍然没有 ai_mentor，给出用户提示并返回
            if not hasattr(self, 'ai_mentor') or self.ai_mentor is None:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    tr("student.ai_mentor_not_configured_title"),
                    tr("student.ai_mentor_not_configured_body")
                )
                return
            
            # 创建或获取AI Mentor Widget
            if not hasattr(self, 'ai_mentor_widget') or self.ai_mentor_widget is None:
                self.ai_mentor_widget = AIMentorWidget(self.ai_mentor, self.content)
                content_l = self.content.layout()
                content_l.insertWidget(2, self.ai_mentor_widget)
            elif hasattr(self.ai_mentor_widget, "apply_language_texts"):
                self.ai_mentor_widget.apply_language_texts()
            
            # Hide all other containers.
            self._hide_all_content_containers()
            
            # 显示AI Mentor
            self.ai_mentor_widget.setVisible(True)
            self.content_title.setText(tr("student.ai_mentor"))
            self.content_title.setVisible(True)
            self._refresh_student_inline_text_colors()
            
        except Exception as e:
            print(f"Error showing AI Mentor: {e}")
            import traceback
            traceback.print_exc()
            
            # 显示错误信息
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                tr("student.ai_mentor_error_title"),
                tr("student.ai_mentor_error_body")
            )

    def _save_practice_record(self, correct, total):
        """Save a practice record to history file."""
        try:
            from datetime import datetime
            
            history_path = os.path.join("assets", "practice_history.json")
            
            # Load existing data or create new
            if os.path.exists(history_path):
                with open(history_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {"records": []}
            
            # Calculate accuracy percentage
            accuracy = int(correct * 100 / total) if total > 0 else 0
            
            # Create new record
            record = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "accuracy": accuracy,
                "correct": correct,
                "total": total
            }
            
            # Add to records
            data["records"].append(record)
            
            # Save back to file
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"[MainWindow] Saved practice record: {accuracy}% ({correct}/{total})")
            
        except Exception as e:
            print(f"Error saving practice record: {e}")

    def _show_simulation_options(self):
        """Show three training option buttons in simulation page."""
        # Hide all other content containers.
        self._hide_all_content_containers()
        
        # Hide welcome quote and content view
        self.welcome_quote.setVisible(False)
        self.content_view.setVisible(False)
        
        # Show and set title
        self.content_title.setText(tr("student.simulation_training"))
        self.content_title.setVisible(True)
        
        # Create container for the three buttons
        if not hasattr(self, 'simulation_container'):
            self.simulation_container = QFrame()
            self.simulation_container.setStyleSheet("background: transparent;")
            button_layout = QHBoxLayout(self.simulation_container)
            button_layout.setSpacing(12)
            button_layout.setContentsMargins(0, 0, 0, 0)
            
            # Training modules. Catheter removal is one active workflow in the current hardware setup.
            options = [
                (tr("student.comprehensive_training"), "comprehensive"),
                (tr("student.change_dressing_training"), "change_dressing"),
                (tr("student.removal_training"), "remove_needle_simulator"),
                (tr("student.training_records"), "training_records")
            ]
            
            for option_text, option_key in options:
                btn = QPushButton(option_text)
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(77, 163, 255, 0.2);
                        border: 2px solid #4DA3FF;
                        border-radius: 8px;
                        padding: 16px;
                        font-family: 'Segoe Print', 'Segoe UI', Arial;
                        font-size: 16px;
                        font-weight: 600;
                        color: #003366;
                        min-height: 100px;
                    }
                    QPushButton:hover {
                        background: rgba(77, 163, 255, 0.3);
                        border: 2px solid #234f8d;
                    }
                    QPushButton:pressed {
                        background: rgba(77, 163, 255, 0.4);
                    }
                """)
                btn.clicked.connect(lambda _checked=False, key=option_key: self._on_training_button_click(key))
                button_layout.addWidget(btn)
            
            # Add to content area
            content_l = self.content.layout()
            # Insert after title (at position 2 after title, stretch, content_view)
            content_l.insertWidget(2, self.simulation_container)
        
        self.simulation_container.setVisible(True)
        self._refresh_student_inline_text_colors()
    def _hide_all_content_containers(self):
        """隐藏所有内容容器（Settings, Simulation, Practice, E-learning等）"""
        if hasattr(self, 'settings_container'):
            self.settings_container.setVisible(False)
        if hasattr(self, 'simulation_container'):
            self.simulation_container.setVisible(False)
        if hasattr(self, 'student_home_container'):
            self.student_home_container.setVisible(False)
        if hasattr(self, 'topic_container'):
            self.topic_container.setVisible(False)
        if hasattr(self, 'simulator_conn_widget'):
            self.simulator_conn_widget.setVisible(False)
        if hasattr(self, 'training_records_container'):
            self.training_records_container.setVisible(False)
        if hasattr(self, 'ai_mentor_widget') and self.ai_mentor_widget:
            try:
                # hide and clear messages when switching menus
                self.ai_mentor_widget.setVisible(False)
                if hasattr(self.ai_mentor_widget, 'clear_messages'):
                    self.ai_mentor_widget.clear_messages()
            except Exception:
                pass
        # Also hide the generic content view and title so they don't bleed through
        try:
            if hasattr(self, 'content_view') and self.content_view:
                self.content_view.setVisible(False)
        except Exception:
            pass
        try:
            if hasattr(self, 'content_title') and self.content_title:
                self.content_title.setVisible(False)
        except Exception:
            pass
        try:
            if hasattr(self, 'welcome_quote') and self.welcome_quote:
                self.welcome_quote.setVisible(False)
        except Exception:
            pass
    
    def _show_settings(self):
        """Show Settings page with both camera and font configuration"""
        # Hide all other content containers.
        self._hide_all_content_containers()
        
        # Stop any active training.
        self._stop_current_training()
        
        # Clean up the E-learning video player.
        self._cleanup_elearning_video()
        
        # 清理Practice相关容器
        self._cleanup_practice_containers()
        
        # 清除菜单栏选中
        self.menu_list.clearSelection()
        
        # Hide other content
        self.welcome_quote.setVisible(False)
        if hasattr(self, 'simulation_container'):
            self.simulation_container.setVisible(False)
        if hasattr(self, 'simulator_conn_widget'):
            self.simulator_conn_widget.setVisible(False)
        
        # Show title
        self.content_title.setText(tr("common.settings"))
        self.content_title.setVisible(True)
        self.content_view.setVisible(False)
        
        # 创建settings容器（包含摄像头和字体设置）
        if not hasattr(self, 'settings_container'):
            self.settings_container = QFrame()
            self.settings_container.setStyleSheet("background: white; border-radius: 8px;")
            settings_layout = QVBoxLayout(self.settings_container)
            settings_layout.setSpacing(20)
            settings_layout.setContentsMargins(20, 20, 20, 20)
            
            # 创建标签页容器（简单的手动标签页）
            tabs_frame = QFrame()
            tabs_layout = QHBoxLayout(tabs_frame)
            tabs_layout.setContentsMargins(0, 0, 0, 0)
            
            # Camera tab button.
            self.btn_camera_tab = QPushButton(tr("student.camera_settings"))
            self.btn_camera_tab.setMinimumWidth(150)
            self.btn_camera_tab.setMinimumHeight(40)
            self.btn_camera_tab.setStyleSheet("""
                QPushButton {
                    background: #4DA3FF;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover { background: #3a7bc8; }
            """)
            self.btn_camera_tab.clicked.connect(self._show_camera_settings_tab)
            
            # 字体标签按钮
            self.btn_font_tab = QPushButton(tr("student.font_settings"))
            self.btn_font_tab.setMinimumWidth(150)
            self.btn_font_tab.setMinimumHeight(40)
            self.btn_font_tab.setStyleSheet("""
                QPushButton {
                    background: #E0E0E0;
                    color: #333;
                    border: none;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover { background: #D0D0D0; }
            """)
            self.btn_font_tab.clicked.connect(self._show_font_settings_tab)
            
            tabs_layout.addWidget(self.btn_camera_tab)
            tabs_layout.addWidget(self.btn_font_tab)
            tabs_layout.addStretch()
            settings_layout.addWidget(tabs_frame)
            
            # 内容切换区域
            self.settings_content = QFrame()
            self.settings_content.setStyleSheet("background: transparent;")
            self.settings_content_layout = QVBoxLayout(self.settings_content)
            self.settings_content_layout.setContentsMargins(0, 0, 0, 0)
            settings_layout.addWidget(self.settings_content)
            
            content_l = self.content.layout()
            content_l.insertWidget(2, self.settings_container)
        
        self.settings_container.setVisible(True)
        
        # Show camera settings by default.
        self._show_camera_settings_tab()
        self._refresh_student_inline_text_colors()
    
    def _show_camera_settings_tab(self):
        """Show camera settings tab."""
        # 隐藏字体settings widget
        if hasattr(self, 'settings_widget'):
            self.settings_widget.setVisible(False)
        
        # Clear previous content.
        while self.settings_content_layout.count():
            widget = self.settings_content_layout.takeAt(0).widget()
            if widget:
                widget.setParent(None)
        
        # 更新标签按钮样式
        self.btn_camera_tab.setStyleSheet("""
            QPushButton {
                background: #4DA3FF;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background: #3a7bc8; }
        """)
        
        self.btn_font_tab.setStyleSheet("""
            QPushButton {
                background: #E0E0E0;
                color: #333;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background: #D0D0D0; }
        """)
        
        # Create or reuse the camera manager.
        if not hasattr(self, 'camera_manager_widget'):
            self.camera_manager_widget = CameraManager()
        
        self.settings_content_layout.addWidget(self.camera_manager_widget)
        self.camera_manager_widget.setVisible(True)
        self._refresh_student_inline_text_colors()
    
    def _show_font_settings_tab(self):
        """Show font settings tab."""
        # 隐藏摄像头settings widget
        if hasattr(self, 'camera_manager_widget'):
            self.camera_manager_widget.setVisible(False)
        
        # Clear previous content.
        while self.settings_content_layout.count():
            widget = self.settings_content_layout.takeAt(0).widget()
            if widget:
                widget.setParent(None)
        
        # 更新标签按钮样式
        self.btn_camera_tab.setStyleSheet("""
            QPushButton {
                background: #E0E0E0;
                color: #333;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background: #D0D0D0; }
        """)
        
        self.btn_font_tab.setStyleSheet("""
            QPushButton {
                background: #4DA3FF;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background: #3a7bc8; }
        """)
        
        # 创建或获取字体设置widget
        if not hasattr(self, 'settings_widget'):
            self.settings_widget = SettingsWidget()
            self.settings_widget.font_changed.connect(self._apply_font_globally)
        
        self.settings_content_layout.addWidget(self.settings_widget)
        self.settings_widget.setVisible(True)
        self._refresh_student_inline_text_colors()
    
    def _apply_font_globally(self, font_name):
        """Apply selected font to all UI elements"""
        print(f"[Settings] Applying font: {font_name}")
        
        # Save font setting to user_settings.json
        try:
            settings_path = os.path.join(os.path.dirname(__file__), "..", "..", "user_settings.json")
            settings = {}
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    settings = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    settings = {}
            settings["font"] = font_name
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            print(f"[Settings] Saved font to {settings_path}")
        except Exception as e:
            print(f"[Settings] Error saving font: {e}")
        
        # Apply font to main window and all children
        font = QFont(font_name, 11)
        self.setFont(font)
        
        # Apply to specific elements with custom sizes
        self._apply_font_recursive(self, font_name)
        
        print(f"[Settings] Font applied successfully to all UI")
    
    def _apply_font_recursive(self, widget, font_name):
        """Recursively apply font to widget and all children"""
        # Get current font size for this widget
        current_font = widget.font()
        size = current_font.pointSize() if current_font.pointSize() > 0 else 11
        weight = current_font.weight()
        
        # Apply new font with same size and weight
        new_font = QFont(font_name, size)
        new_font.setWeight(weight)
        widget.setFont(new_font)
        
        # Recursively apply to children
        for child in widget.findChildren(QWidget):
            current_font = child.font()
            size = current_font.pointSize() if current_font.pointSize() > 0 else 11
            weight = current_font.weight()
            
            new_font = QFont(font_name, size)
            new_font.setWeight(weight)
            child.setFont(new_font)
    
    def _show_simulator_connection(self):
        """Show Simulator Connection debug page"""
        # Hide all other content containers.
        self._hide_all_content_containers()
        
        # Stop any active training.
        self._stop_current_training()
        
        # Clean up the E-learning video player.
        self._cleanup_elearning_video()
        
        # 清理Practice相关容器
        self._cleanup_practice_containers()
        
        # 清除菜单栏选中
        self.menu_list.clearSelection()
        
        # Hide other content
        self.welcome_quote.setVisible(False)
        
        # Show title
        self.content_title.setText(tr("student.simulator"))
        self.content_title.setVisible(True)
        self.content_view.setVisible(False)
        
        # Create simulator connection widget if not exists
        if not hasattr(self, 'simulator_conn_widget'):
            self.simulator_conn_widget = QFrame()
            self.simulator_conn_widget.setStyleSheet("background: transparent;")
            conn_l = QVBoxLayout(self.simulator_conn_widget)
            conn_l.setSpacing(12)
            conn_l.setContentsMargins(0, 0, 0, 0)
            
            # Hardware connection section
            wifi_frame = QFrame()
            wifi_frame.setStyleSheet("background: transparent;")
            wifi_l = QHBoxLayout(wifi_frame)
            
            wifi_label = QLabel(tr("student.hardware_link"))
            wifi_label.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #003366; font-weight: 700;")
            wifi_l.addWidget(wifi_label)
            
            self.lbl_current_wifi = QLabel(tr("student.hardware_checking"))
            self.lbl_current_wifi.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #234f8d; font-weight: 600;")
            self.lbl_current_wifi.setMinimumWidth(250)
            wifi_l.addWidget(self.lbl_current_wifi)
            
            btn_refresh = QPushButton(tr("common.refresh"))
            btn_refresh.setStyleSheet("""
                QPushButton {
                    background: rgba(77, 163, 255, 0.3);
                    border: 2px solid #4DA3FF;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-family: 'Segoe Print';
                    font-size: 14px;
                    font-weight: 600;
                    color: #003366;
                    min-width: 100px;
                }
                QPushButton:hover { background: rgba(77, 163, 255, 0.4); }
                QPushButton:pressed { background: rgba(77, 163, 255, 0.5); }
            """)
            btn_refresh.clicked.connect(self._refresh_serial_display)
            wifi_l.addWidget(btn_refresh)
            
            # Hardware setup hint
            btn_connect_wifi = QPushButton("WiFi Setup")
            btn_connect_wifi.setStyleSheet("""
                QPushButton {
                    background: rgba(77, 163, 255, 0.3);
                    border: 2px solid #4DA3FF;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-family: 'Segoe Print';
                    font-size: 14px;
                    font-weight: 600;
                    color: #003366;
                    min-width: 140px;
                }
                QPushButton:hover { background: rgba(77, 163, 255, 0.4); }
                QPushButton:pressed { background: rgba(77, 163, 255, 0.5); }
            """)
            btn_connect_wifi.clicked.connect(self._show_wired_hardware_hint)
            wifi_l.addWidget(btn_connect_wifi)
            wifi_l.addStretch()
            conn_l.addWidget(wifi_frame)
            
            # Connection test section
            conn_test_frame = QFrame()
            conn_test_frame.setStyleSheet("background: transparent;")
            conn_test_l = QHBoxLayout(conn_test_frame)
            
            btn_connect = QPushButton("Test Connection")
            btn_connect.setStyleSheet("""
                QPushButton {
                    background: rgba(77, 163, 255, 0.3);
                    border: 2px solid #4DA3FF;
                    border-radius: 6px;
                    padding: 10px 20px;
                    font-family: 'Segoe Print';
                    font-size: 16px;
                    font-weight: 700;
                    color: #003366;
                    min-width: 150px;
                }
                QPushButton:hover { background: rgba(77, 163, 255, 0.4); }
                QPushButton:pressed { background: rgba(77, 163, 255, 0.5); }
            """)
            btn_connect.clicked.connect(self._test_hardware_connection)
            conn_test_l.addWidget(btn_connect)
            conn_test_l.addStretch()
            conn_l.addWidget(conn_test_frame)
            
            # Status display
            self.lbl_connection_status = QLabel("")
            self.lbl_connection_status.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #003366; font-weight: 600;")
            self.lbl_connection_status.setWordWrap(True)
            self.lbl_connection_status.setMinimumHeight(60)
            conn_l.addWidget(self.lbl_connection_status)
            
            conn_l.addStretch()
            
            content_l = self.content.layout()
            content_l.insertWidget(2, self.simulator_conn_widget)
        
        # Refresh hardware link on display
        self._refresh_serial_display()
        self.simulator_conn_widget.setVisible(True)
        self._refresh_student_inline_text_colors()

    def _refresh_serial_display(self):
        """Refresh the hardware transport status shown on the Simulator page."""
        try:
            transport = os.getenv("SURGERYBOX_HARDWARE_TRANSPORT", "serial").strip().lower()
            if transport not in ("serial", "udp"):
                transport = "serial"
            if transport == "udp":
                self.lbl_current_wifi.setText("WiFi UDP: surgeryBox -> 192.168.4.1:4210 (PC 4211)")
                return

            from app.hardware.serial_connector import list_serial_ports
            preferred_port = os.getenv("SURGERYBOX_SERIAL_PORT", "COM4")
            baudrate = os.getenv("SURGERYBOX_SERIAL_BAUDRATE", "115200")
            ports = list_serial_ports()
            if ports:
                available = ", ".join(ports)
                if preferred_port in ports:
                    self.lbl_current_wifi.setText(f"{preferred_port} @ {baudrate} (available)")
                else:
                    self.lbl_current_wifi.setText(f"{preferred_port} @ {baudrate} (available: {available})")
            else:
                self.lbl_current_wifi.setText(f"{preferred_port} @ {baudrate} (no serial ports detected)")
        except Exception as e:
            self.lbl_current_wifi.setText(f"Hardware status error: {str(e)[:60]}")

    def _show_wired_hardware_hint(self):
        """Show hardware setup hints without changing system WiFi."""
        try:
            transport = os.getenv("SURGERYBOX_HARDWARE_TRANSPORT", "serial").strip().lower()
            if transport == "serial":
                port = os.getenv("SURGERYBOX_SERIAL_PORT", "COM4")
                baudrate = os.getenv("SURGERYBOX_SERIAL_BAUDRATE", "115200")
                text = (
                    f"Serial mode: connect mannequin USB serial and camera to this PC. "
                    f"Hardware port is {port} @ {baudrate}. "
                    f"Set SURGERYBOX_HARDWARE_TRANSPORT=udp to use surgeryBox WiFi."
                )
            else:
                text = (
                    "WiFi/UDP mode: connect this PC to the surgeryBox WiFi. "
                    "Password: 12345678. Board: 192.168.4.1:4210. "
                    "The PC listens on UDP 4211 and sends Start/Winding directly to the MCU."
                )
            self.lbl_connection_status.setText(text)
            self.lbl_connection_status.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #003366; font-weight: 600;")
        except Exception:
            pass
    
    def _refresh_wifi_display(self):
        """Refresh WiFi display in background thread"""
        try:
            from app.hardware_connector import WiFiThread
            
            # Prevent multiple concurrent WiFi checks
            if hasattr(self, 'wifi_thread') and self.wifi_thread and self.wifi_thread.isRunning():
                return  # Already checking, ignore new request
            
            # Create and start WiFi thread
            self.wifi_thread = WiFiThread()
            self.wifi_thread.wifi_ready.connect(self._on_wifi_ready)
            self.wifi_thread.finished.connect(lambda: self._cleanup_wifi_thread())
            self.wifi_thread.start()
            
            # Show waiting status
            self.lbl_current_wifi.setText("Checking...")
        except Exception as e:
            self.lbl_current_wifi.setText(f"Error")

    def _connect_mcu_wifi(self):
        """尝试自动连接 MCU WiFi (surgeryBox)"""
        try:
            from app.hardware_connector import HardwareConnector
            success, msg = HardwareConnector.connect_to_mcu_wifi("surgeryBox")
            if success:
                self.lbl_current_wifi.setText(f"{msg}")
            else:
                self.lbl_current_wifi.setText(f"连接失败: {msg}")
        except Exception as e:
            self.lbl_current_wifi.setText(f"错误: {str(e)[:50]}")
    
    def _cleanup_wifi_thread(self):
        """Clean up WiFi thread after it finishes"""
        try:
            if hasattr(self, 'wifi_thread') and self.wifi_thread:
                try:
                    self.wifi_thread.deleteLater()
                except Exception:
                    pass
                self.wifi_thread = None
        except Exception:
            pass
    
    def _on_wifi_ready(self, wifi_name: str):
        """Handle WiFi name ready"""
        try:
            self.lbl_current_wifi.setText(wifi_name)
        except Exception:
            pass
    
    def _cleanup_connection_thread(self):
        """Clean up connection thread after it finishes"""
        try:
            if hasattr(self, 'connection_thread') and self.connection_thread:
                try:
                    self.connection_thread.deleteLater()
                except Exception:
                    pass
                self.connection_thread = None
        except Exception:
            pass
    
    def _test_hardware_connection(self):
        """Test connection to hardware simulator in background thread"""
        try:
            # Prevent multiple concurrent connection tests
            if hasattr(self, 'connection_thread') and self.connection_thread and self.connection_thread.isRunning():
                return  # Already testing, ignore new request
            
            transport = os.getenv("SURGERYBOX_HARDWARE_TRANSPORT", "serial").strip().lower()
            if transport == "serial":
                from app.hardware.serial_connector import SerialConnectionTestThread
                port = os.getenv("SURGERYBOX_SERIAL_PORT", "COM4")
                try:
                    baudrate = int(os.getenv("SURGERYBOX_SERIAL_BAUDRATE", "115200"))
                except ValueError:
                    baudrate = 115200
                self.connection_thread = SerialConnectionTestThread(port, baudrate)
                waiting_text = f"Testing serial connection on {port}..."
            else:
                from app.hardware_connector import ConnectionTestThread
                self.connection_thread = ConnectionTestThread()
                waiting_text = "Testing surgeryBox WiFi board at 192.168.4.1..."
            self.connection_thread.connection_result.connect(self._on_connection_result)
            self.connection_thread.finished.connect(lambda: self._cleanup_connection_thread())
            self.connection_thread.start()
            
            # Show waiting status
            self.lbl_connection_status.setText(waiting_text)
            self.lbl_connection_status.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #003366; font-weight: 600;")
        except Exception as e:
            self.lbl_connection_status.setText("Error")
            self.lbl_connection_status.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #FF0000; font-weight: 700;")
    
    def _on_connection_result(self, success: bool, message: str):
        """Handle connection test result"""
        try:
            if success:
                # Green text for success
                self.lbl_connection_status.setText(f"OK {message}")
                self.lbl_connection_status.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #00AA00; font-weight: 700;")
            else:
                # Red text for failure
                self.lbl_connection_status.setText(f"Error {message}")
                self.lbl_connection_status.setStyleSheet("font-family: 'Segoe Print'; font-size: 16px; color: #FF0000; font-weight: 700;")
        except Exception:
            pass
