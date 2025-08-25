#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inkguiding (PyQt5) — v3.1

Updates from v3:
- Improved guide click detection with larger hit area
- Visual hover feedback for better targeting
- Easier to click on thin or dashed guides
"""

import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets

import ctypes

# Windows constants
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


GUIDE_HIT_RADIUS = 15  # px - increased for easier interaction
GUIDE_DRAG_RADIUS = 20  # px - larger area for dragging detection

def get_settings_file_path():
    """Get the settings file path in the user's application data directory."""
    # Get the user's application data directory
    if sys.platform == "win32":
        # Windows: Use APPDATA environment variable
        app_data = os.environ.get('APPDATA', os.path.expanduser('~'))
        settings_dir = os.path.join(app_data, 'Inkguiding')
    else:
        # macOS/Linux: Use home directory
        settings_dir = os.path.join(os.path.expanduser('~'), '.inkguiding')
    
    # Create directory if it doesn't exist
    os.makedirs(settings_dir, exist_ok=True)
    
    return os.path.join(settings_dir, 'inkguiding_settings.json')

SETTINGS_FILE = get_settings_file_path()
STYLE_MAP = {
    "Solid": QtCore.Qt.SolidLine,
    "Dashed": QtCore.Qt.DashLine,
    "Dotted": QtCore.Qt.DotLine,
    "Dash-Dot": QtCore.Qt.DashDotLine,
    "Dash-Dot-Dot": QtCore.Qt.DashDotDotLine,
}
STYLE_NAMES = list(STYLE_MAP.keys())

@dataclass
class Guide:
    orientation: str
    pos: int
    color: Tuple[int, int, int, int] = (255, 140, 0, 255)
    thickness: int = 2
    style_name: str = "Solid"

    def to_pen(self) -> QtGui.QPen:
        pen = QtGui.QPen(QtGui.QColor(*self.color))
        pen.setWidth(self.thickness)
        pen.setStyle(STYLE_MAP.get(self.style_name, QtCore.Qt.SolidLine))
        pen.setCosmetic(True)
        return pen

def create_orange_cross_icon(size=64):
    """Create the orange cross icon programmatically."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    
    # Orange color
    orange = QtGui.QColor(255, 140, 0)
    painter.setBrush(orange)
    painter.setPen(QtCore.Qt.NoPen)
    
    # Cross dimensions
    bar_thickness = size // 8
    bar_length = size * 0.75
    center = size // 2
    
    # Horizontal bar
    h_rect = QtCore.QRectF(
        center - bar_length/2, 
        center - bar_thickness/2,
        bar_length,
        bar_thickness
    )
    painter.drawRoundedRect(h_rect, bar_thickness/2, bar_thickness/2)
    
    # Vertical bar
    v_rect = QtCore.QRectF(
        center - bar_thickness/2,
        center - bar_length/2, 
        bar_thickness,
        bar_length
    )
    painter.drawRoundedRect(v_rect, bar_thickness/2, bar_thickness/2)
    
    painter.end()
    return QtGui.QIcon(pix)

class OverlayCanvas(QtWidgets.QWidget):
    guideChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

        self._guides: List[Guide] = []
        self._hover_idx: Optional[int] = None
        self._positioning_idx: Optional[int] = None
        self._interactive = False

    def setInteractive(self, enabled: bool):
        self._interactive = enabled
        # Click-through only if not interactive
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, not enabled)
        if not enabled:
            self._positioning_idx = None
            self._hover_idx = None
            self.update()

    def addGuide(self, guide: Guide):
        self._guides.append(guide)
        self.guideChanged.emit()
        self.update()

    def removeGuideAt(self, index: int):
        if 0 <= index < len(self._guides):
            del self._guides[index]
            
            # Fix indices after removal
            if self._positioning_idx is not None:
                if self._positioning_idx == index:
                    # We're removing the guide we were positioning
                    self._positioning_idx = None
                elif self._positioning_idx > index:
                    # Adjust index since we removed a guide before it
                    self._positioning_idx -= 1
            
            if self._hover_idx is not None:
                if self._hover_idx == index:
                    # We're removing the guide we were hovering
                    self._hover_idx = None
                elif self._hover_idx > index:
                    # Adjust index since we removed a guide before it
                    self._hover_idx -= 1
            
            self.guideChanged.emit()
            self.update()

    def clearGuides(self):
        if self._guides:
            self._guides.clear()
            # Reset all interaction state when clearing guides
            self._positioning_idx = None
            self._hover_idx = None
            self.guideChanged.emit()
            self.update()

    def guides(self) -> List[Guide]:
        return self._guides

    def setGuides(self, guides: List[Guide]):
        self._guides = guides
        self._positioning_idx = None
        self._hover_idx = None
        self.guideChanged.emit()
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QtCore.Qt.transparent)

        # Draw all guides
        for idx, g in enumerate(self._guides):
            painter.setPen(g.to_pen())
            if g.orientation == 'v':
                painter.drawLine(g.pos, 0, g.pos, self.height())
            else:
                painter.drawLine(0, g.pos, self.width(), g.pos)

        # Highlight logic: show highlight if hovering OR positioning
        highlight_idx = None
        if self._interactive:
            if self._positioning_idx is not None:
                # Always highlight the guide we're positioning
                highlight_idx = self._positioning_idx
            elif self._hover_idx is not None:
                # Highlight the guide we're hovering over
                highlight_idx = self._hover_idx

        # Draw highlight
        if (highlight_idx is not None and 
            0 <= highlight_idx < len(self._guides)):
            g = self._guides[highlight_idx]
            
            # Different highlight colors for different states
            if self._positioning_idx == highlight_idx:
                # Bright yellow for positioning mode
                highlight_color = QtGui.QColor(255, 255, 0, 200)
                highlight_width = max(6, g.thickness + 6)  # Increased for better visibility
            else:
                # Softer yellow for hover
                highlight_color = QtGui.QColor(255, 255, 0, 120)
                highlight_width = max(4, g.thickness + 4)  # Increased for better visibility
            
            hl = QtGui.QPen(highlight_color)
            hl.setWidth(highlight_width)
            hl.setStyle(QtCore.Qt.SolidLine)
            hl.setCosmetic(True)
            painter.setPen(hl)
            
            if g.orientation == 'v':
                painter.drawLine(g.pos, 0, g.pos, self.height())
            else:
                painter.drawLine(0, g.pos, self.width(), g.pos)

    def _findGuideAt(self, pos: QtCore.QPoint, use_drag_radius: bool = False) -> Optional[int]:
        """Find a guide at the given position.
        
        Args:
            pos: The position to check
            use_drag_radius: If True, use larger radius for easier dragging
        """
        radius = GUIDE_DRAG_RADIUS if use_drag_radius else GUIDE_HIT_RADIUS
        
        for i, g in enumerate(self._guides):
            if g.orientation == 'v' and abs(pos.x() - g.pos) <= radius:
                return i
            elif g.orientation == 'h' and abs(pos.y() - g.pos) <= radius:
                return i
        return None

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if not self._interactive:
            return
        self._last_mouse_pos = e.pos()
        
        if e.button() == QtCore.Qt.LeftButton:
            # Use larger radius for initial click detection to make dragging easier
            idx = self._findGuideAt(e.pos(), use_drag_radius=True)
            
            if self._positioning_idx is None and idx is not None:
                # Start positioning this guide
                self._positioning_idx = idx
                self._hover_idx = idx  # Keep it highlighted while positioning
            elif self._positioning_idx is not None:
                # Click to finish positioning (validate position)
                self._positioning_idx = None
                self._hover_idx = None  # Clear highlight after validation
            self.update()
            
        elif e.button() == QtCore.Qt.RightButton:
            idx = self._findGuideAt(e.pos(), use_drag_radius=True)
            if idx is not None:
                # If we're positioning this guide, stop positioning first
                if self._positioning_idx == idx:
                    self._positioning_idx = None
                self.removeGuideAt(idx)
                
        elif e.button() == QtCore.Qt.MiddleButton:
            if e.modifiers() & QtCore.Qt.ShiftModifier:
                self.addGuide(Guide('h', e.y()))
            else:
                self.addGuide(Guide('v', e.x()))

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if not self._interactive:
            return
        self._last_mouse_pos = e.pos()
        
        if self._positioning_idx is not None:
            # We're currently positioning a guide
            # Safety check: make sure the positioning index is still valid
            if self._positioning_idx < len(self._guides):
                g = self._guides[self._positioning_idx]
                if g.orientation == 'v':
                    g.pos = int(max(0, min(self.width() - 1, e.x())))
                else:
                    g.pos = int(max(0, min(self.height() - 1, e.y())))
                self.guideChanged.emit()
                self.update()
            else:
                # Invalid index, reset positioning
                self._positioning_idx = None
                self._hover_idx = None
                self.update()
        else:
            # Not positioning, check for hover (use normal radius for hover)
            idx = self._findGuideAt(e.pos(), use_drag_radius=False)
            if idx != self._hover_idx:
                self._hover_idx = idx
                self.update()

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        pass

    def leaveEvent(self, e: QtCore.QEvent):
        """Clear hover highlight when mouse leaves the window."""
        if not self._interactive:
            return
        # Only clear hover if we're not positioning (don't clear during drag)
        if self._positioning_idx is None and self._hover_idx is not None:
            self._hover_idx = None
            self.update()


class ControlPanel(QtWidgets.QWidget):
    addGuideRequested = QtCore.pyqtSignal(Guide)
    clearRequested = QtCore.pyqtSignal()
    styleChangedRequested = QtCore.pyqtSignal(str)
    colorChangedRequested = QtCore.pyqtSignal(QtGui.QColor)
    thicknessChangedRequested = QtCore.pyqtSignal(int)
    closeSettingsRequested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setWindowTitle("Inkguiding Settings")
        self.setFixedWidth(320)

        # Set window icon
        self.setWindowIcon(create_orange_cross_icon(32))

        # Controls
        self.color_btn = QtWidgets.QPushButton("Pick Color")
        self.color_preview = QtWidgets.QLabel()
        self.color_preview.setFixedHeight(18)
        self.color_preview.setFrameShape(QtWidgets.QFrame.Panel)
        self.color_preview.setFrameShadow(QtWidgets.QFrame.Sunken)

        self.thickness_spin = QtWidgets.QSpinBox()
        self.thickness_spin.setRange(1, 20)
        self.thickness_spin.setValue(2)

        self.style_combo = QtWidgets.QComboBox()
        self.style_combo.addItems(STYLE_NAMES)

        self.add_v_btn = QtWidgets.QPushButton("Add Vertical @ Cursor")
        self.add_h_btn = QtWidgets.QPushButton("Add Horizontal @ Cursor")
        self.clear_btn = QtWidgets.QPushButton("Clear All")
        self.btn_close_settings = QtWidgets.QPushButton("Close Settings")

        self.clickthrough_label = QtWidgets.QLabel(
            "Normal mode is click-through. In Settings mode:\n"
            "• Left-click guide to start moving, click again to finish\n" 
            "• Right-click guide to delete\n"
            "• Middle-click to add guide (Shift+Middle = horizontal)"
        )
        self.clickthrough_label.setWordWrap(True)

        # Layout
        form = QtWidgets.QFormLayout()
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(self.color_btn)
        row1.addWidget(self.color_preview)
        form.addRow("Guide Color:", row1)
        form.addRow("Thickness (px):", self.thickness_spin)
        form.addRow("Style:", self.style_combo)
        form.addRow(self.add_v_btn)
        form.addRow(self.add_h_btn)
        form.addRow(self.clear_btn)
        form.addRow(self.btn_close_settings)
        form.addRow(self.clickthrough_label)
        
        self.setLayout(form)

        self._current_color = QtGui.QColor(255, 140, 0)
        self._update_color_preview()

        # Signals
        self.color_btn.clicked.connect(self._choose_color)
        self.thickness_spin.valueChanged.connect(self.thicknessChangedRequested)
        self.style_combo.currentTextChanged.connect(self.styleChangedRequested)
        self.add_v_btn.clicked.connect(lambda: self._emit_add('v'))
        self.add_h_btn.clicked.connect(lambda: self._emit_add('h'))
        self.clear_btn.clicked.connect(self.clearRequested.emit)
        self.btn_close_settings.clicked.connect(self.closeSettingsRequested.emit)

    def _emit_add(self, orientation: str):
        global_pos = QtGui.QCursor.pos()
        screen = QtWidgets.QApplication.primaryScreen()
        geo = screen.geometry()
        if orientation == 'v':
            pos = global_pos.x() - geo.x()
        else:
            pos = global_pos.y() - geo.y()
        g = Guide(
            orientation=orientation,
            pos=max(0, pos),
            color=(self._current_color.red(), self._current_color.green(), self._current_color.blue(), self._current_color.alpha()),
            thickness=self.thickness_spin.value(),
            style_name=self.style_combo.currentText(),
        )
        self.addGuideRequested.emit(g)

    def _choose_color(self):
        col = QtWidgets.QColorDialog.getColor(self._current_color, self, "Pick Guide Color")
        if col.isValid():
            self._current_color = col
            self._update_color_preview()
            self.colorChangedRequested.emit(col)

    def _update_color_preview(self):
        pix = QtGui.QPixmap(60, 18)
        pix.fill(self._current_color)
        self.color_preview.setPixmap(pix)

    def getDefaults(self):
        return {
            "thickness": self.thickness_spin.value(),
            "style": self.style_combo.currentText(),
            "color": [self._current_color.red(), self._current_color.green(), self._current_color.blue(), self._current_color.alpha()],
        }

    def setDefaults(self, d):
        try:
            self.thickness_spin.setValue(int(d.get("thickness", 2)))
            style = d.get("style", "Solid")
            if style in STYLE_NAMES:
                self.style_combo.setCurrentText(style)
            c = d.get("color", [255, 140, 0, 255])
            self._current_color = QtGui.QColor(*c)
            self._update_color_preview()
        except Exception:
            pass

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Inkguiding")
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

        # Set window icon
        self.setWindowIcon(create_orange_cross_icon(32))

        # Size to primary screen
        screen = QtWidgets.QApplication.primaryScreen()
        self.setGeometry(screen.geometry())

        # Central canvas
        self.canvas = OverlayCanvas(self)
        self.setCentralWidget(self.canvas)

        # Control panel
        self.panel = ControlPanel()
        self.panel.move(60, 60)

        # Wire panel to canvas
        self.panel.addGuideRequested.connect(self.canvas.addGuide)
        self.panel.clearRequested.connect(self.canvas.clearGuides)
        self.panel.styleChangedRequested.connect(self._set_default_style)
        self.panel.colorChangedRequested.connect(self._set_default_color)
        self.panel.thicknessChangedRequested.connect(self._set_default_thickness)
        self.panel.closeSettingsRequested.connect(self.toggleSettingsMode)

        # Defaults
        self._default_color = QtGui.QColor(255, 140, 0)
        self._default_thickness = 2
        self._default_style = "Solid"

        # Shortcuts
        QtWidgets.QShortcut(QtGui.QKeySequence("F1"), self, activated=self.toggleSettingsMode)
        QtWidgets.QShortcut(QtGui.QKeySequence("F2"), self, activated=self.toggleGuidesVisibility)
        QtWidgets.QShortcut(QtGui.QKeySequence("Escape"), self, activated=self.quitApp)

        # Tray icon & menu
        self._create_tray()

        # State
        self._settings_mode = False
        self._guides_visible = True
        
        # Obtain native handle for Windows API
        self.hwnd = int(self.winId())
        self._apply_clickthrough()
        
        # Load persisted settings
        self._load_settings()

        # Apply initial mode
        self._apply_modes()

        # Start full screen
        self.showFullScreen()

    def _apply_clickthrough(self):
        """Enable or disable true click-through depending on mode."""
        style = ctypes.windll.user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        if not self._settings_mode:
            # Normal mode: add transparent flag
            ctypes.windll.user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE,
                                                style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        else:
            # Settings mode: remove transparent flag
            ctypes.windll.user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE,
                                                style & ~WS_EX_TRANSPARENT)
            
    def _create_tray(self):
        self.tray = QtWidgets.QSystemTrayIcon(self)
        self.tray.setIcon(create_orange_cross_icon(64))
        self.tray.setToolTip("Inkguiding - Desktop Guide Overlay")

        menu = QtWidgets.QMenu()
        self.act_toggle_settings = menu.addAction("Open Settings")
        self.act_toggle_settings.triggered.connect(self.toggleSettingsMode)
        self.act_toggle_guides = menu.addAction("Hide Guides")
        self.act_toggle_guides.triggered.connect(self.toggleGuidesVisibility)
        menu.addSeparator()
        act_exit = menu.addAction("Exit")
        act_exit.triggered.connect(self.quitApp)
        self.tray.setContextMenu(menu)
        self.tray.show()

        # Left double-click tray to toggle settings
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.DoubleClick:
            self.toggleSettingsMode()

    def _set_default_style(self, name: str):
        self._default_style = name

    def _set_default_color(self, color: QtGui.QColor):
        self._default_color = color

    def _set_default_thickness(self, t: int):
        self._default_thickness = t

    def toggleSettingsMode(self):
        self._settings_mode = not self._settings_mode
        self._apply_modes()
        self._apply_clickthrough()

    def toggleGuidesVisibility(self):
        self._guides_visible = not self._guides_visible
        self._apply_modes()

    def _apply_modes(self):
        # Settings panel
        if self._settings_mode:
            self.panel.show()
            self.panel.raise_()
            self.tray.contextMenu().actions()[0].setText("Close Settings")
        else:
            self.panel.hide()
            self.tray.contextMenu().actions()[0].setText("Open Settings")

        # Canvas interactivity
        self.canvas.setInteractive(self._settings_mode)

        # Guides visibility
        self.setVisible(self._guides_visible)
        self.tray.contextMenu().actions()[1].setText("Show Guides" if not self._guides_visible else "Hide Guides")

    def _load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            print(f"Settings file not found, creating default at: {SETTINGS_FILE}")
            self._write_default_settings()
        try:
            print(f"Loading settings from: {SETTINGS_FILE}")
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error loading settings: {e}")
            data = self._default_settings_dict()

        # load guides
        guides_data = data.get("guides", [])
        guides = []
        for item in guides_data:
            try:
                guides.append(Guide(**item))
            except Exception:
                pass
        self.canvas.setGuides(guides)

        # load UI defaults
        defaults = data.get("settings", {})
        self.panel.setDefaults(defaults)
        # update internal defaults to match panel
        d = self.panel.getDefaults()
        self._default_thickness = int(d["thickness"])
        self._default_style = d["style"]
        c = d["color"]
        self._default_color = QtGui.QColor(*c)

        # other state
        self._guides_visible = bool(data.get("show_guides", True))
        self._settings_mode = False

    def _write_default_settings(self):
        data = self._default_settings_dict()
        try:
            print(f"Writing default settings to: {SETTINGS_FILE}")
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error writing default settings: {e}")

    def _default_settings_dict(self):
        return {
            "guides": [],
            "settings": {
                "thickness": 2,
                "style": "Solid",
                "color": [255, 140, 0, 255],
            },
            "show_guides": True,
        }

    def _save_settings(self):
        data = {
            "guides": [asdict(g) for g in self.canvas.guides()],
            "settings": self.panel.getDefaults(),
            "show_guides": self._guides_visible,
        }
        try:
            print(f"Saving settings to: {SETTINGS_FILE}")
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def quitApp(self):
        self._save_settings()
        QtWidgets.QApplication.quit()

    def closeEvent(self, e: QtGui.QCloseEvent):
        self.quitApp()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Inkguiding")
    app.setOrganizationName("Inkguiding")
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    # Set application icon
    app.setWindowIcon(create_orange_cross_icon(32))

    win = MainWindow()
    if not win._guides_visible:
        win.hide()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
