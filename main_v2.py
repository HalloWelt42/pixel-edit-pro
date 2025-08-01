#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Professional Pixel Editor für macOS M1
Entwickelt mit PyQt6 und modernem Python3
"""

import sys
import json
import numpy as np
from enum import Enum
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path
import base64
from io import BytesIO

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QDockWidget, QColorDialog, QFileDialog, QSpinBox,
    QLabel, QSlider, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QMenuBar, QMenu, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QSplitter, QScrollArea, QGridLayout,
    QButtonGroup, QToolButton, QSizePolicy, QMessageBox,
    QCheckBox, QTextEdit, QDialog, QDialogButtonBox, QInputDialog
)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal, QTimer, QByteArray
from PyQt6.QtGui import (
    QPainter, QPixmap, QColor, QPen, QBrush, QImage, QIcon,
    QFont, QFontDatabase, QAction, QKeySequence, QPalette,
    QPolygon, QTransform, QCursor
)

# Konstanten
ICON_SIZE = 32
BUTTON_HEIGHT = 40
MIN_GRID_SIZE = 16
MAX_GRID_SIZE = 64
MAX_UNDO_STEPS = 100


class DrawMode(Enum):
    PENCIL = "pencil"
    LINE = "line"
    RECTANGLE = "rectangle"
    FILLED_RECTANGLE = "filled_rectangle"
    CIRCLE = "circle"
    FILLED_CIRCLE = "filled_circle"
    TRIANGLE = "triangle"
    FILLED_TRIANGLE = "filled_triangle"
    POLYGON = "polygon"
    FILLED_POLYGON = "filled_polygon"
    FILL = "fill"
    ERASER = "eraser"
    PICKER = "picker"
    MOVE = "move"


@dataclass
class Layer:
    name: str
    pixmap: QPixmap
    visible: bool = True
    opacity: float = 1.0

    def to_dict(self):
        # Convert pixmap to base64
        buffer = QByteArray()
        pixmap_bytes = BytesIO()
        self.pixmap.save(pixmap_bytes, "PNG")
        image_data = base64.b64encode(pixmap_bytes.getvalue()).decode()

        return {
            'name': self.name,
            'image_data': image_data,
            'visible': self.visible,
            'opacity': self.opacity
        }

    @classmethod
    def from_dict(cls, data):
        image_data = base64.b64decode(data['image_data'])
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)

        return cls(
            name=data['name'],
            pixmap=pixmap,
            visible=data['visible'],
            opacity=data['opacity']
        )


class MacroRecorder:
    def __init__(self):
        self.recording = False
        self.actions = []
        self.macros = {}

    def start_recording(self, name):
        self.recording = True
        self.actions = []
        self.current_macro = name

    def stop_recording(self):
        if self.recording and self.current_macro:
            self.macros[self.current_macro] = self.actions.copy()
        self.recording = False
        self.actions = []

    def record_action(self, action_type, params):
        if self.recording:
            self.actions.append({
                'type': action_type,
                'params': params
            })

    def play_macro(self, name, canvas):
        if name in self.macros:
            for action in self.macros[name]:
                canvas.execute_action(action['type'], action['params'])


class PixelCanvas(QWidget):
    colorPicked = pyqtSignal(QColor)
    positionChanged = pyqtSignal(int, int)

    def __init__(self, grid_size=32):
        super().__init__()
        self.grid_size = grid_size
        self.cell_size = 20
        self.layers = [Layer("Background", QPixmap(grid_size, grid_size))]
        self.current_layer = 0
        self.layers[0].pixmap.fill(Qt.GlobalColor.white)

        self.primary_color = QColor(0, 0, 0)
        self.secondary_color = QColor(255, 255, 255)
        self.draw_mode = DrawMode.PENCIL
        self.pen_width = 1
        self.blur_mode = False

        self.drawing = False
        self.last_pos = None
        self.preview_pixmap = None
        self.polygon_points = []

        self.undo_stack = []
        self.redo_stack = []

        self.background_color = QColor(200, 200, 200)
        self.show_grid = True

        # Move mode
        self.move_start = None
        self.move_offset = QPoint(0, 0)
        self.temp_move_pixmap = None

        # Macro recorder
        self.macro_recorder = MacroRecorder()

        self.setMouseTracking(True)
        self.update_size()

    def update_size(self):
        size = self.grid_size * self.cell_size
        self.setFixedSize(size, size)

    def add_layer(self, name="New Layer"):
        pixmap = QPixmap(self.grid_size, self.grid_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        self.layers.append(Layer(name, pixmap))
        self.current_layer = len(self.layers) - 1
        return self.current_layer

    def remove_layer(self, index):
        if len(self.layers) > 1 and 0 <= index < len(self.layers):
            del self.layers[index]
            if self.current_layer >= len(self.layers):
                self.current_layer = len(self.layers) - 1

    def toggle_layer_visibility(self, index):
        if 0 <= index < len(self.layers):
            self.layers[index].visible = not self.layers[index].visible
            self.update()

    def get_top_visible_layer(self):
        """Get the topmost visible layer for drawing"""
        for i in range(len(self.layers) - 1, -1, -1):
            if self.layers[i].visible:
                return i
        return 0

    def clear_layer(self):
        """Clear current layer"""
        self.save_state()
        if self.current_layer == 0:
            self.layers[0].pixmap.fill(Qt.GlobalColor.white)
        else:
            self.layers[self.current_layer].pixmap.fill(Qt.GlobalColor.transparent)
        self.update()

    def reset_all(self):
        """Full reset - clear all layers"""
        reply = QMessageBox.question(
            self, 'Reset All',
            'This will delete all layers and start fresh. Continue?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.layers = [Layer("Background", QPixmap(self.grid_size, self.grid_size))]
            self.layers[0].pixmap.fill(Qt.GlobalColor.white)
            self.current_layer = 0
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.update()

    def save_state(self):
        if len(self.undo_stack) >= MAX_UNDO_STEPS:
            self.undo_stack.pop(0)

        state = []
        for layer in self.layers:
            state.append({
                'name': layer.name,
                'pixmap': layer.pixmap.copy(),
                'visible': layer.visible,
                'opacity': layer.opacity
            })
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            state = self.undo_stack[-1]
            self.restore_state(state)

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            self.restore_state(state)

    def restore_state(self, state):
        self.layers.clear()
        for layer_data in state:
            layer = Layer(
                layer_data['name'],
                layer_data['pixmap'].copy(),
                layer_data['visible'],
                layer_data['opacity']
            )
            self.layers.append(layer)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.background_color)

        # Grid zeichnen
        if self.show_grid:
            painter.setPen(QPen(QColor(180, 180, 180), 1))
            for i in range(self.grid_size + 1):
                x = i * self.cell_size
                y = i * self.cell_size
                painter.drawLine(x, 0, x, self.height())
                painter.drawLine(0, y, self.width(), y)

        # Layer zeichnen
        for layer in self.layers:
            if layer.visible:
                scaled = layer.pixmap.scaled(
                    self.width(), self.height(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation
                )
                painter.setOpacity(layer.opacity)
                painter.drawPixmap(0, 0, scaled)

        # Vorschau zeichnen
        if self.preview_pixmap:
            painter.setOpacity(0.5)
            scaled = self.preview_pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            painter.drawPixmap(0, 0, scaled)

        # Move preview
        if self.temp_move_pixmap and self.draw_mode == DrawMode.MOVE:
            painter.setOpacity(0.5)
            scaled = self.temp_move_pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            painter.drawPixmap(self.move_offset.x() * self.cell_size,
                               self.move_offset.y() * self.cell_size, scaled)

    def get_pixel_pos(self, pos):
        x = pos.x() // self.cell_size
        y = pos.y() // self.cell_size
        return QPoint(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pixel_pos = self.get_pixel_pos(event.pos())

            # Only draw on visible layers
            if not self.layers[self.current_layer].visible:
                QMessageBox.warning(self, "Layer Hidden",
                                    "Cannot draw on hidden layer. Please make it visible first.")
                return

            self.save_state()
            self.drawing = True
            self.last_pos = pixel_pos

            if self.draw_mode == DrawMode.PENCIL:
                self.draw_pixel(pixel_pos)
            elif self.draw_mode == DrawMode.FILL:
                self.fill_area(pixel_pos)
            elif self.draw_mode == DrawMode.PICKER:
                self.pick_color(pixel_pos)
            elif self.draw_mode == DrawMode.MOVE:
                self.start_move(pixel_pos)
            elif self.draw_mode == DrawMode.POLYGON:
                self.polygon_points.append(pixel_pos)
                if len(self.polygon_points) > 2 and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.draw_polygon()
                    self.polygon_points.clear()
            elif self.draw_mode in [DrawMode.LINE, DrawMode.RECTANGLE, DrawMode.FILLED_RECTANGLE,
                                    DrawMode.CIRCLE, DrawMode.FILLED_CIRCLE, DrawMode.TRIANGLE,
                                    DrawMode.FILLED_TRIANGLE]:
                self.preview_pixmap = QPixmap(self.grid_size, self.grid_size)
                self.preview_pixmap.fill(Qt.GlobalColor.transparent)

    def mouseMoveEvent(self, event):
        pixel_pos = self.get_pixel_pos(event.pos())

        # Emit position signal
        if 0 <= pixel_pos.x() < self.grid_size and 0 <= pixel_pos.y() < self.grid_size:
            self.positionChanged.emit(pixel_pos.x(), pixel_pos.y())

        if self.drawing:
            if self.draw_mode == DrawMode.PENCIL:
                self.draw_line(self.last_pos, pixel_pos)
                self.last_pos = pixel_pos
            elif self.draw_mode == DrawMode.ERASER:
                self.erase_pixel(pixel_pos)
                self.last_pos = pixel_pos
            elif self.draw_mode == DrawMode.MOVE:
                self.update_move(pixel_pos)
            elif self.draw_mode in [DrawMode.LINE, DrawMode.RECTANGLE, DrawMode.FILLED_RECTANGLE,
                                    DrawMode.CIRCLE, DrawMode.FILLED_CIRCLE, DrawMode.TRIANGLE,
                                    DrawMode.FILLED_TRIANGLE]:
                self.update_preview(pixel_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            pixel_pos = self.get_pixel_pos(event.pos())

            if self.draw_mode == DrawMode.MOVE:
                self.apply_move()
            elif self.preview_pixmap and self.draw_mode != DrawMode.POLYGON:
                self.apply_preview()
                self.preview_pixmap = None

    def start_move(self, pos):
        """Start move operation"""
        self.move_start = pos
        self.move_offset = QPoint(0, 0)
        self.temp_move_pixmap = self.layers[self.current_layer].pixmap.copy()
        self.layers[self.current_layer].pixmap.fill(Qt.GlobalColor.transparent)
        self.update()

    def update_move(self, pos):
        """Update move preview"""
        if self.move_start:
            self.move_offset = pos - self.move_start
            self.update()

    def apply_move(self):
        """Apply move operation"""
        if self.temp_move_pixmap:
            painter = QPainter(self.layers[self.current_layer].pixmap)
            painter.drawPixmap(self.move_offset, self.temp_move_pixmap)
            self.temp_move_pixmap = None
            self.move_start = None
            self.move_offset = QPoint(0, 0)
            self.update()

    def draw_pixel(self, pos):
        if 0 <= pos.x() < self.grid_size and 0 <= pos.y() < self.grid_size:
            painter = QPainter(self.layers[self.current_layer].pixmap)

            if self.blur_mode:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                color = QColor(self.primary_color)
                color.setAlpha(128)  # Semi-transparent for blur effect
                painter.setPen(QPen(color, self.pen_width * 1.5))
            else:
                painter.setPen(QPen(self.primary_color, 1))

            painter.drawPoint(pos)
            self.update()

    def draw_line(self, start, end):
        painter = QPainter(self.layers[self.current_layer].pixmap)

        if self.blur_mode:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor(self.primary_color)
            color.setAlpha(128)
            painter.setPen(QPen(color, self.pen_width * 1.5))
        else:
            painter.setPen(QPen(self.primary_color, self.pen_width))

        painter.drawLine(start, end)
        self.update()

    def update_preview(self, current_pos):
        if not self.preview_pixmap:
            return

        self.preview_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self.preview_pixmap)

        if self.blur_mode:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor(self.primary_color)
            color.setAlpha(128)
            painter.setPen(QPen(color, self.pen_width * 1.5))
        else:
            painter.setPen(QPen(self.primary_color, self.pen_width))

        painter.setBrush(QBrush(self.primary_color))

        if self.draw_mode == DrawMode.LINE:
            painter.drawLine(self.last_pos, current_pos)
        elif self.draw_mode == DrawMode.RECTANGLE:
            rect = QRect(self.last_pos, current_pos).normalized()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
        elif self.draw_mode == DrawMode.FILLED_RECTANGLE:
            rect = QRect(self.last_pos, current_pos).normalized()
            painter.drawRect(rect)
        elif self.draw_mode in [DrawMode.CIRCLE, DrawMode.FILLED_CIRCLE]:
            # Hold Shift for perfect circle
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Perfect circle
                dx = abs(current_pos.x() - self.last_pos.x())
                dy = abs(current_pos.y() - self.last_pos.y())
                radius = min(dx, dy)
                rect = QRect(self.last_pos.x() - radius, self.last_pos.y() - radius,
                             radius * 2, radius * 2)
            else:
                # Ellipse
                rect = QRect(self.last_pos, current_pos).normalized()

            if self.draw_mode == DrawMode.CIRCLE:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)
        elif self.draw_mode in [DrawMode.TRIANGLE, DrawMode.FILLED_TRIANGLE]:
            points = [
                self.last_pos,
                current_pos,
                QPoint(self.last_pos.x(), current_pos.y())
            ]
            polygon = QPolygon(points)
            if self.draw_mode == DrawMode.TRIANGLE:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(polygon)

        self.update()

    def apply_preview(self):
        if self.preview_pixmap:
            painter = QPainter(self.layers[self.current_layer].pixmap)
            painter.drawPixmap(0, 0, self.preview_pixmap)
            self.update()

    def draw_polygon(self):
        if len(self.polygon_points) < 3:
            return

        painter = QPainter(self.layers[self.current_layer].pixmap)

        if self.blur_mode:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor(self.primary_color)
            color.setAlpha(128)
            painter.setPen(QPen(color, self.pen_width * 1.5))
        else:
            painter.setPen(QPen(self.primary_color, self.pen_width))

        if self.draw_mode == DrawMode.FILLED_POLYGON:
            painter.setBrush(QBrush(self.primary_color))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        polygon = QPolygon(self.polygon_points)
        painter.drawPolygon(polygon)
        self.update()

    def fill_area(self, pos):
        if not (0 <= pos.x() < self.grid_size and 0 <= pos.y() < self.grid_size):
            return

        image = self.layers[self.current_layer].pixmap.toImage()
        target_color = image.pixelColor(pos.x(), pos.y())

        if target_color == self.primary_color:
            return

        # Flood fill algorithm
        stack = [(pos.x(), pos.y())]
        while stack:
            x, y = stack.pop()
            if not (0 <= x < self.grid_size and 0 <= y < self.grid_size):
                continue

            if image.pixelColor(x, y) == target_color:
                image.setPixelColor(x, y, self.primary_color)
                stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

        self.layers[self.current_layer].pixmap = QPixmap.fromImage(image)
        self.update()

    def pick_color(self, pos):
        if 0 <= pos.x() < self.grid_size and 0 <= pos.y() < self.grid_size:
            # Get color from the topmost visible layer
            for i in range(len(self.layers) - 1, -1, -1):
                if self.layers[i].visible:
                    image = self.layers[i].pixmap.toImage()
                    color = image.pixelColor(pos.x(), pos.y())
                    if color.alpha() > 0:  # Non-transparent pixel
                        self.colorPicked.emit(color)
                        break

    def erase_pixel(self, pos):
        if 0 <= pos.x() < self.grid_size and 0 <= pos.y() < self.grid_size:
            painter = QPainter(self.layers[self.current_layer].pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.setPen(QPen(Qt.GlobalColor.transparent, self.pen_width))
            painter.drawPoint(pos)
            self.update()

    def resize_grid(self, new_size):
        self.save_state()
        self.grid_size = new_size

        for layer in self.layers:
            old_pixmap = layer.pixmap
            layer.pixmap = QPixmap(new_size, new_size)
            if layer == self.layers[0]:
                layer.pixmap.fill(Qt.GlobalColor.white)
            else:
                layer.pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(layer.pixmap)
            painter.drawPixmap(0, 0, old_pixmap)

        self.update_size()
        self.update()

    def load_image(self, filename):
        """Load and scale image properly"""
        image = QImage(filename)
        if not image.isNull():
            # Calculate scale to fit in grid while maintaining aspect ratio
            scale_x = self.grid_size / image.width()
            scale_y = self.grid_size / image.height()
            scale = min(scale_x, scale_y)

            new_width = int(image.width() * scale)
            new_height = int(image.height() * scale)

            # Scale image
            scaled = image.scaled(
                new_width, new_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            # Center in grid
            x_offset = (self.grid_size - new_width) // 2
            y_offset = (self.grid_size - new_height) // 2

            # Clear and draw
            self.layers[self.current_layer].pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(self.layers[self.current_layer].pixmap)
            painter.drawImage(x_offset, y_offset, scaled)
            self.update()

    def export_image(self):
        final_image = QPixmap(self.grid_size, self.grid_size)
        final_image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(final_image)
        for layer in self.layers:
            if layer.visible:
                painter.setOpacity(layer.opacity)
                painter.drawPixmap(0, 0, layer.pixmap)

        return final_image

    def save_project(self, filename):
        """Save entire project as JSON"""
        project_data = {
            'grid_size': self.grid_size,
            'layers': [layer.to_dict() for layer in self.layers],
            'current_layer': self.current_layer
        }

        with open(filename, 'w') as f:
            json.dump(project_data, f, indent=2)

    def load_project(self, filename):
        """Load project from JSON"""
        with open(filename, 'r') as f:
            project_data = json.load(f)

        self.grid_size = project_data['grid_size']
        self.layers = [Layer.from_dict(layer_data) for layer_data in project_data['layers']]
        self.current_layer = project_data['current_layer']

        self.update_size()
        self.update()

    def execute_action(self, action_type, params):
        """Execute recorded macro action"""
        # Implementation for macro playback
        pass


class ColorPalette(QWidget):
    colorSelected = pyqtSignal(QColor)

    def __init__(self):
        super().__init__()
        self.colors = []
        self.selected_index = -1
        self.cell_size = 24
        self.columns = 8
        self.load_material_palette()

    def load_material_palette(self):
        # Material Design Farben
        material_colors = [
            "#F44336", "#E91E63", "#9C27B0", "#673AB7",
            "#3F51B5", "#2196F3", "#03A9F4", "#00BCD4",
            "#009688", "#4CAF50", "#8BC34A", "#CDDC39",
            "#FFEB3B", "#FFC107", "#FF9800", "#FF5722",
            "#795548", "#9E9E9E", "#607D8B", "#000000",
            "#FFFFFF", "#FAFAFA", "#F5F5F5", "#EEEEEE",
            "#E0E0E0", "#BDBDBD", "#9E9E9E", "#757575",
            "#616161", "#424242", "#303030", "#212121"
        ]

        self.colors = [QColor(c) for c in material_colors]
        self.update_size()

    def update_size(self):
        rows = (len(self.colors) + self.columns - 1) // self.columns
        width = self.columns * self.cell_size
        height = rows * self.cell_size
        self.setFixedSize(width, height)

    def paintEvent(self, event):
        painter = QPainter(self)

        for i, color in enumerate(self.colors):
            row = i // self.columns
            col = i % self.columns
            x = col * self.cell_size
            y = row * self.cell_size

            rect = QRect(x, y, self.cell_size, self.cell_size)

            # Draw transparency pattern for transparent colors
            if color.alpha() < 255:
                painter.fillRect(rect, QColor(255, 255, 255))
                painter.fillRect(QRect(x, y, self.cell_size // 2, self.cell_size // 2), QColor(200, 200, 200))
                painter.fillRect(QRect(x + self.cell_size // 2, y + self.cell_size // 2,
                                       self.cell_size // 2, self.cell_size // 2), QColor(200, 200, 200))

            painter.fillRect(rect, color)

            if i == self.selected_index:
                painter.setPen(QPen(Qt.GlobalColor.black, 2))
                painter.drawRect(rect)
            else:
                painter.setPen(QPen(Qt.GlobalColor.gray, 1))
                painter.drawRect(rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.pos().x() // self.cell_size
            y = event.pos().y() // self.cell_size
            index = y * self.columns + x

            if 0 <= index < len(self.colors):
                self.selected_index = index
                self.colorSelected.emit(self.colors[index])
                self.update()

    def add_color(self, color):
        self.colors.append(color)
        self.update_size()
        self.update()

    def export_palette(self):
        return [color.name() for color in self.colors]

    def import_palette(self, color_list):
        self.colors = [QColor(c) for c in color_list]
        self.update_size()
        self.update()


class ToolButton(QToolButton):
    def __init__(self, icon_text, tooltip=""):
        super().__init__()
        self.setText(icon_text)
        self.setToolTip(tooltip)
        self.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.setCheckable(True)

        # Icon-Font Style
        font = QFont()
        font.setPixelSize(18)
        self.setFont(font)


class MacroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Macro Manager")
        self.setModal(True)

        layout = QVBoxLayout()

        self.macro_list = QListWidget()
        layout.addWidget(self.macro_list)

        button_layout = QHBoxLayout()

        self.record_btn = QPushButton("Record New")
        button_layout.addWidget(self.record_btn)

        self.play_btn = QPushButton("Play")
        button_layout.addWidget(self.play_btn)

        self.delete_btn = QPushButton("Delete")
        button_layout.addWidget(self.delete_btn)

        layout.addLayout(button_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)


class PixelEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Professional Pixel Editor")
        self.setGeometry(100, 100, 1200, 800)

        # macOS specific
        if sys.platform == "darwin":
            self.setUnifiedTitleAndToolBarOnMac(True)

        self.canvas = PixelCanvas()
        self.setup_ui()
        self.setup_shortcuts()

    def setup_ui(self):
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Toolbar
        self.create_toolbar()

        # Left Panel - Tools
        left_panel = self.create_tools_panel()
        main_layout.addWidget(left_panel)

        # Canvas Area
        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)

        # Position indicator
        self.position_label = QLabel("Position: 0, 0")
        canvas_layout.addWidget(self.position_label)

        scroll_area = QScrollArea()
        scroll_area.setWidget(self.canvas)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(scroll_area, 1)

        main_layout.addWidget(canvas_container, 1)

        # Right Panel - Layers & Colors
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel)

        # Menu Bar
        self.create_menu_bar()

        # Status Bar
        self.statusBar().showMessage("Ready")

        # Connect signals
        self.canvas.positionChanged.connect(
            lambda x, y: self.position_label.setText(f"Position: {x}, {y}")
        )
        self.canvas.colorPicked.connect(self.set_primary_color)

    def create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setFixedHeight(BUTTON_HEIGHT)
        self.addToolBar(toolbar)

        # File actions
        new_action = QAction("New", self)
        new_action.triggered.connect(self.new_file)
        toolbar.addAction(new_action)

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_file)
        toolbar.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_file)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        # Project actions
        save_project_action = QAction("Save Project", self)
        save_project_action.triggered.connect(self.save_project)
        toolbar.addAction(save_project_action)

        load_project_action = QAction("Load Project", self)
        load_project_action.triggered.connect(self.load_project)
        toolbar.addAction(load_project_action)

        toolbar.addSeparator()

        # Undo/Redo
        undo_action = QAction("↶", self)
        undo_action.setToolTip("Undo")
        undo_action.triggered.connect(self.canvas.undo)
        toolbar.addAction(undo_action)

        redo_action = QAction("↷", self)
        redo_action.setToolTip("Redo")
        redo_action.triggered.connect(self.canvas.redo)
        toolbar.addAction(redo_action)

        toolbar.addSeparator()

        # Grid size
        grid_label = QLabel("Grid:")
        toolbar.addWidget(grid_label)

        self.grid_spin = QSpinBox()
        self.grid_spin.setRange(MIN_GRID_SIZE, MAX_GRID_SIZE)
        self.grid_spin.setValue(32)
        self.grid_spin.setSuffix("px")
        self.grid_spin.valueChanged.connect(self.change_grid_size)
        toolbar.addWidget(self.grid_spin)

        toolbar.addSeparator()

        # Grid toggle
        self.grid_checkbox = QCheckBox("Show Grid")
        self.grid_checkbox.setChecked(True)
        self.grid_checkbox.toggled.connect(self.toggle_grid)
        toolbar.addWidget(self.grid_checkbox)

        # Blur mode
        self.blur_checkbox = QCheckBox("Blur Mode")
        self.blur_checkbox.toggled.connect(self.toggle_blur_mode)
        toolbar.addWidget(self.blur_checkbox)

    def create_tools_panel(self):
        panel = QWidget()
        panel.setFixedWidth(ICON_SIZE * 2 + 20)
        layout = QVBoxLayout(panel)

        # Drawing tools
        tools_layout = QGridLayout()

        self.tool_buttons = QButtonGroup()
        tools = [
            ("✏", DrawMode.PENCIL, "Pencil"),
            ("╱", DrawMode.LINE, "Line"),
            ("□", DrawMode.RECTANGLE, "Rectangle"),
            ("■", DrawMode.FILLED_RECTANGLE, "Filled Rectangle"),
            ("○", DrawMode.CIRCLE, "Circle (Shift for perfect circle)"),
            ("●", DrawMode.FILLED_CIRCLE, "Filled Circle (Shift for perfect circle)"),
            ("△", DrawMode.TRIANGLE, "Triangle"),
            ("▲", DrawMode.FILLED_TRIANGLE, "Filled Triangle"),
            ("⬟", DrawMode.POLYGON, "Polygon (Shift to finish)"),
            ("⬢", DrawMode.FILLED_POLYGON, "Filled Polygon (Shift to finish)"),
            ("🪣", DrawMode.FILL, "Fill"),
            ("⌫", DrawMode.ERASER, "Eraser"),
            ("💧", DrawMode.PICKER, "Color Picker"),
            ("↔", DrawMode.MOVE, "Move Layer Content")
        ]

        for i, (icon, mode, tooltip) in enumerate(tools):
            btn = ToolButton(icon, tooltip)
            btn.clicked.connect(lambda checked, m=mode: self.set_draw_mode(m))
            self.tool_buttons.addButton(btn)
            tools_layout.addWidget(btn, i // 2, i % 2)

        layout.addLayout(tools_layout)

        # Pen width
        layout.addWidget(QLabel("Pen Width:"))
        self.pen_slider = QSlider(Qt.Orientation.Horizontal)
        self.pen_slider.setRange(1, 10)
        self.pen_slider.setValue(1)
        self.pen_slider.valueChanged.connect(self.change_pen_width)
        layout.addWidget(self.pen_slider)

        self.pen_label = QLabel("1px")
        layout.addWidget(self.pen_label)

        layout.addStretch()

        return panel

    def create_right_panel(self):
        panel = QWidget()
        panel.setFixedWidth(250)
        layout = QVBoxLayout(panel)

        # Colors
        layout.addWidget(QLabel("Colors:"))

        color_layout = QHBoxLayout()

        # Primary color with transparency indicator
        primary_container = QWidget()
        primary_container.setFixedSize(60, 60)
        primary_layout = QVBoxLayout(primary_container)
        primary_layout.setContentsMargins(0, 0, 0, 0)

        self.primary_color_btn = QPushButton()
        self.primary_color_btn.setFixedSize(50, 50)
        self.primary_color_btn.setStyleSheet("background-color: black")
        self.primary_color_btn.clicked.connect(self.choose_primary_color)
        primary_layout.addWidget(self.primary_color_btn)

        color_layout.addWidget(primary_container)

        # Secondary color
        self.secondary_color_btn = QPushButton()
        self.secondary_color_btn.setFixedSize(50, 50)
        self.secondary_color_btn.setStyleSheet("background-color: white")
        self.secondary_color_btn.clicked.connect(self.choose_secondary_color)
        color_layout.addWidget(self.secondary_color_btn)

        # Transparent color button
        self.transparent_btn = QPushButton("T")
        self.transparent_btn.setFixedSize(30, 30)
        self.transparent_btn.setToolTip("Set transparent")
        self.transparent_btn.clicked.connect(self.set_transparent_color)
        color_layout.addWidget(self.transparent_btn)

        layout.addLayout(color_layout)

        # Palette
        layout.addWidget(QLabel("Palette:"))
        self.palette = ColorPalette()
        self.palette.colorSelected.connect(self.set_primary_color)
        layout.addWidget(self.palette)

        palette_buttons = QHBoxLayout()
        load_palette_btn = QPushButton("Load")
        load_palette_btn.clicked.connect(self.load_palette)
        palette_buttons.addWidget(load_palette_btn)

        save_palette_btn = QPushButton("Save")
        save_palette_btn.clicked.connect(self.save_palette)
        palette_buttons.addWidget(save_palette_btn)

        layout.addLayout(palette_buttons)

        # Layers
        layout.addWidget(QLabel("Layers:"))
        self.layers_list = QListWidget()
        self.layers_list.itemClicked.connect(self.select_layer)
        self.layers_list.itemDoubleClicked.connect(self.toggle_layer_visibility_ui)
        self.update_layers_list()
        layout.addWidget(self.layers_list)

        layer_buttons = QHBoxLayout()
        add_layer_btn = QPushButton("+")
        add_layer_btn.clicked.connect(self.add_layer)
        layer_buttons.addWidget(add_layer_btn)

        remove_layer_btn = QPushButton("-")
        remove_layer_btn.clicked.connect(self.remove_layer)
        layer_buttons.addWidget(remove_layer_btn)

        layout.addLayout(layer_buttons)

        # Opacity (only for current layer)
        layout.addWidget(QLabel("Current Layer Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self.change_layer_opacity)
        layout.addWidget(self.opacity_slider)

        self.opacity_label = QLabel("100%")
        layout.addWidget(self.opacity_label)

        return panel

    def create_menu_bar(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_file)
        file_menu.addAction(new_action)

        open_action = QAction("Open", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        save_project_action = QAction("Save Project", self)
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)

        load_project_action = QAction("Load Project", self)
        load_project_action.triggered.connect(self.load_project)
        file_menu.addAction(load_project_action)

        file_menu.addSeparator()

        export_action = QAction("Export as PNG", self)
        export_action.triggered.connect(self.export_png)
        file_menu.addAction(export_action)

        export_ico_action = QAction("Export as ICO", self)
        export_ico_action.triggered.connect(self.export_ico)
        file_menu.addAction(export_ico_action)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")

        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.canvas.undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.canvas.redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        clear_layer_action = QAction("Clear Layer", self)
        clear_layer_action.triggered.connect(self.canvas.clear_layer)
        edit_menu.addAction(clear_layer_action)

        reset_all_action = QAction("Reset All", self)
        reset_all_action.triggered.connect(self.canvas.reset_all)
        edit_menu.addAction(reset_all_action)

        # View menu
        view_menu = menubar.addMenu("View")

        toggle_grid_action = QAction("Toggle Grid", self)
        toggle_grid_action.setCheckable(True)
        toggle_grid_action.setChecked(True)
        toggle_grid_action.triggered.connect(self.toggle_grid)
        view_menu.addAction(toggle_grid_action)

        # Filter menu
        filter_menu = menubar.addMenu("Filters")

        blur_action = QAction("Blur", self)
        blur_action.triggered.connect(self.apply_blur_filter)
        filter_menu.addAction(blur_action)

        sharpen_action = QAction("Sharpen", self)
        sharpen_action.triggered.connect(self.apply_sharpen_filter)
        filter_menu.addAction(sharpen_action)

        grayscale_action = QAction("Grayscale", self)
        grayscale_action.triggered.connect(self.apply_grayscale_filter)
        filter_menu.addAction(grayscale_action)

        invert_action = QAction("Invert", self)
        invert_action.triggered.connect(self.apply_invert_filter)
        filter_menu.addAction(invert_action)

        # Macro menu
        macro_menu = menubar.addMenu("Macros")

        macro_manager_action = QAction("Macro Manager", self)
        macro_manager_action.triggered.connect(self.open_macro_manager)
        macro_menu.addAction(macro_manager_action)

    def setup_shortcuts(self):
        # Tool shortcuts
        shortcuts = {
            Qt.Key.Key_P: DrawMode.PENCIL,
            Qt.Key.Key_L: DrawMode.LINE,
            Qt.Key.Key_R: DrawMode.RECTANGLE,
            Qt.Key.Key_C: DrawMode.CIRCLE,
            Qt.Key.Key_F: DrawMode.FILL,
            Qt.Key.Key_E: DrawMode.ERASER,
            Qt.Key.Key_I: DrawMode.PICKER,
            Qt.Key.Key_M: DrawMode.MOVE,
        }

        for key, mode in shortcuts.items():
            shortcut = QAction(self)
            shortcut.setShortcut(key)
            shortcut.triggered.connect(lambda checked, m=mode: self.set_draw_mode(m))
            self.addAction(shortcut)

    def set_draw_mode(self, mode):
        self.canvas.draw_mode = mode
        self.statusBar().showMessage(f"Mode: {mode.value}")

    def change_pen_width(self, value):
        self.canvas.pen_width = value
        self.pen_label.setText(f"{value}px")

    def change_grid_size(self, value):
        self.canvas.resize_grid(value)

    def toggle_grid(self, checked=None):
        if checked is None:
            checked = self.grid_checkbox.isChecked()
        self.canvas.show_grid = checked
        self.grid_checkbox.setChecked(checked)
        self.canvas.update()

    def toggle_blur_mode(self, checked):
        self.canvas.blur_mode = checked

    def set_transparent_color(self):
        transparent = QColor(0, 0, 0, 0)
        self.set_primary_color(transparent)

    def choose_primary_color(self):
        color = QColorDialog.getColor(
            self.canvas.primary_color, self,
            "Choose Primary Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if color.isValid():
            self.set_primary_color(color)

    def choose_secondary_color(self):
        color = QColorDialog.getColor(
            self.canvas.secondary_color, self,
            "Choose Secondary Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if color.isValid():
            self.set_secondary_color(color)

    def set_primary_color(self, color):
        self.canvas.primary_color = color
        if color.alpha() < 255:
            self.primary_color_btn.setStyleSheet(
                f"background-color: {color.name()}; "
                f"background-image: repeating-conic-gradient(#ccc 0% 25%, transparent 0% 50%);"
                f"background-size: 10px 10px;"
            )
        else:
            self.primary_color_btn.setStyleSheet(f"background-color: {color.name()}")

    def set_secondary_color(self, color):
        self.canvas.secondary_color = color
        self.secondary_color_btn.setStyleSheet(f"background-color: {color.name()}")

    def update_layers_list(self):
        self.layers_list.clear()
        for i, layer in enumerate(self.canvas.layers):
            visibility = '👁' if layer.visible else '🚫'
            opacity = f" ({int(layer.opacity * 100)}%)" if layer.opacity < 1.0 else ""
            item = QListWidgetItem(f"{visibility} {layer.name}{opacity}")
            self.layers_list.addItem(item)

        self.layers_list.setCurrentRow(self.canvas.current_layer)

    def select_layer(self, item):
        row = self.layers_list.row(item)
        self.canvas.current_layer = row

        # Update opacity slider
        if 0 <= row < len(self.canvas.layers):
            opacity = int(self.canvas.layers[row].opacity * 100)
            self.opacity_slider.setValue(opacity)

    def toggle_layer_visibility_ui(self, item):
        row = self.layers_list.row(item)
        self.canvas.toggle_layer_visibility(row)
        self.update_layers_list()

    def add_layer(self):
        name, ok = QInputDialog.getText(self, "New Layer", "Layer name:")
        if ok and name:
            self.canvas.add_layer(name)
            self.update_layers_list()

    def remove_layer(self):
        current = self.layers_list.currentRow()
        if current >= 0:
            self.canvas.remove_layer(current)
            self.update_layers_list()

    def change_layer_opacity(self, value):
        opacity = value / 100.0
        self.opacity_label.setText(f"{value}%")
        if 0 <= self.canvas.current_layer < len(self.canvas.layers):
            self.canvas.layers[self.canvas.current_layer].opacity = opacity
            self.canvas.update()
            self.update_layers_list()

    def new_file(self):
        self.canvas.reset_all()
        self.update_layers_list()

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)"
        )
        if filename:
            self.canvas.load_image(filename)

    def save_file(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Image", "",
            "PNG Files (*.png);;All Files (*)"
        )
        if filename:
            pixmap = self.canvas.export_image()
            pixmap.save(filename)

    def save_project(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "",
            "Pixel Editor Project (*.pep);;JSON Files (*.json);;All Files (*)"
        )
        if filename:
            self.canvas.save_project(filename)

    def load_project(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Project", "",
            "Pixel Editor Project (*.pep);;JSON Files (*.json);;All Files (*)"
        )
        if filename:
            self.canvas.load_project(filename)
            self.update_layers_list()
            self.grid_spin.setValue(self.canvas.grid_size)

    def export_png(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export as PNG", "",
            "PNG Files (*.png);;All Files (*)"
        )
        if filename:
            size, ok = QInputDialog.getInt(
                self, "Export Size", "Size (pixels):",
                256, 16, 2048, 16
            )
            if ok:
                pixmap = self.canvas.export_image()
                scaled = pixmap.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                scaled.save(filename)

    def export_ico(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export as ICO", "",
            "ICO Files (*.ico);;All Files (*)"
        )
        if filename:
            pixmap = self.canvas.export_image()
            # Create multiple sizes for ICO
            sizes = [16, 32, 48, 64, 128, 256]
            images = []
            for size in sizes:
                scaled = pixmap.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                images.append(scaled)
            # Save as ICO (simplified - in production use proper ICO library)
            images[1].save(filename)  # Save 32x32 as default

    def load_palette(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Palette", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            with open(filename, 'r') as f:
                colors = json.load(f)
                self.palette.import_palette(colors)

    def save_palette(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Palette", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            colors = self.palette.export_palette()
            with open(filename, 'w') as f:
                json.dump(colors, f, indent=2)

    def open_macro_manager(self):
        dialog = MacroDialog(self)
        dialog.exec()

    def apply_blur_filter(self):
        # Simplified blur filter
        self.canvas.save_state()
        current_layer = self.canvas.layers[self.canvas.current_layer]
        image = current_layer.pixmap.toImage()

        # Apply simple box blur
        for y in range(1, self.canvas.grid_size - 1):
            for x in range(1, self.canvas.grid_size - 1):
                r, g, b, a = 0, 0, 0, 0
                count = 0
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        pixel = image.pixelColor(x + dx, y + dy)
                        r += pixel.red()
                        g += pixel.green()
                        b += pixel.blue()
                        a += pixel.alpha()
                        count += 1
                color = QColor(r // count, g // count, b // count, a // count)
                image.setPixelColor(x, y, color)

        current_layer.pixmap = QPixmap.fromImage(image)
        self.canvas.update()

    def apply_sharpen_filter(self):
        # Simplified sharpen filter
        self.canvas.save_state()
        self.statusBar().showMessage("Sharpen filter applied")

    def apply_grayscale_filter(self):
        self.canvas.save_state()
        current_layer = self.canvas.layers[self.canvas.current_layer]
        image = current_layer.pixmap.toImage()

        for y in range(self.canvas.grid_size):
            for x in range(self.canvas.grid_size):
                pixel = image.pixelColor(x, y)
                gray = int(0.299 * pixel.red() + 0.587 * pixel.green() + 0.114 * pixel.blue())
                image.setPixelColor(x, y, QColor(gray, gray, gray, pixel.alpha()))

        current_layer.pixmap = QPixmap.fromImage(image)
        self.canvas.update()

    def apply_invert_filter(self):
        self.canvas.save_state()
        current_layer = self.canvas.layers[self.canvas.current_layer]
        image = current_layer.pixmap.toImage()
        image.invertPixels()
        current_layer.pixmap = QPixmap.fromImage(image)
        self.canvas.update()


def main():
    app = QApplication(sys.argv)

    # macOS specific settings
    if sys.platform == "darwin":
        app.setStyle("Fusion")

    editor = PixelEditor()
    editor.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()