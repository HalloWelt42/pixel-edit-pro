#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Professional Pixel Editor für macOS M1
Entwickelt mit PyQt6 und modernem Python3
"""

import sys
import json
import numpy as np
import math
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
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal, QTimer, QByteArray, QBuffer, QIODevice
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
SETTINGS_FILE = "pixel_editor_settings.json"


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
    selected: bool = False  # For merge selection

    def to_dict(self):
        # Convert pixmap to base64
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.pixmap.save(buffer, "PNG")
        image_data = base64.b64encode(buffer.data()).decode()
        buffer.close()

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
        self.virtual_size = grid_size * 3  # Virtual canvas size for move operations

        # Initialize undo/redo stacks BEFORE creating layers
        self.undo_stack = []
        self.redo_stack = []

        # Initialize layers with virtual size
        self.layers = []
        self.add_initial_layer()
        self.current_layer = 0

        self.primary_color = QColor(0, 0, 0)
        self.secondary_color = QColor(255, 255, 255)
        self.draw_mode = DrawMode.PENCIL
        self.pen_width = 1
        self.blur_mode = False

        self.drawing = False
        self.last_pos = None
        self.preview_pixmap = None
        self.polygon_points = []

        self.background_color = QColor(200, 200, 200)
        self.show_grid = True

        # Move mode
        self.move_start = None
        self.move_offset = QPoint(0, 0)
        self.temp_move_pixmap = None

        # Rotation preview
        self.rotation_preview_angle = 0
        self.rotation_preview_active = False

        # Macro recorder
        self.macro_recorder = MacroRecorder()

        self.setMouseTracking(True)
        self.update_size()

    def add_initial_layer(self):
        """Add initial layer with virtual canvas"""
        pixmap = QPixmap(self.virtual_size, self.virtual_size)
        pixmap.fill(Qt.GlobalColor.transparent)

        # Fill center area with white (visible grid area)
        painter = QPainter(pixmap)
        offset = self.grid_size
        painter.fillRect(offset, offset, self.grid_size, self.grid_size, Qt.GlobalColor.white)
        painter.end()

        self.layers = [Layer("Background", pixmap)]

        # Initialize undo stack with initial state
        self.save_state()

    def get_virtual_offset(self):
        """Get offset for virtual canvas"""
        return self.grid_size  # Center the visible area

    def update_size(self):
        size = self.grid_size * self.cell_size
        self.setFixedSize(size, size)

    def add_layer(self, name="New Layer"):
        pixmap = QPixmap(self.virtual_size, self.virtual_size)
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
        offset = self.get_virtual_offset()

        if self.current_layer == 0:
            # For background, refill the center area with white
            self.layers[0].pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(self.layers[0].pixmap)
            painter.fillRect(offset, offset, self.grid_size, self.grid_size, Qt.GlobalColor.white)
            painter.end()
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
            self.layers.clear()
            self.add_initial_layer()
            self.current_layer = 0
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.update()

    def save_state(self):
        # Don't save if no changes have been made
        if len(self.undo_stack) > 0:
            last_state = self.undo_stack[-1]
            current_matches = True
            if len(last_state) == len(self.layers):
                for i, layer in enumerate(self.layers):
                    if (layer.name != last_state[i]['name'] or
                            layer.visible != last_state[i]['visible'] or
                            layer.opacity != last_state[i]['opacity'] or
                            layer.pixmap.toImage() != last_state[i]['pixmap'].toImage()):
                        current_matches = False
                        break
            else:
                current_matches = False

            if current_matches:
                return  # No changes, don't save

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
        if len(self.undo_stack) > 1:  # Keep at least one state
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

        offset = self.get_virtual_offset()

        # Draw layers (only visible area) - but hide current layer if rotating
        for i, layer in enumerate(self.layers):
            if layer.visible:
                # Skip current layer if we're showing rotation preview
                if i == self.current_layer and self.rotation_preview_active and self.rotation_preview_angle != 0:
                    continue

                # Extract visible area from virtual canvas
                visible_area = layer.pixmap.copy(offset, offset, self.grid_size, self.grid_size)
                scaled = visible_area.scaled(
                    self.width(), self.height(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation
                )
                painter.setOpacity(layer.opacity)
                painter.drawPixmap(0, 0, scaled)

        # Draw rotation preview
        if self.rotation_preview_active and self.rotation_preview_angle != 0:
            painter.setOpacity(self.layers[self.current_layer].opacity * 0.8)  # Slightly transparent

            # Get current layer content
            current_layer = self.layers[self.current_layer]
            visible_area = current_layer.pixmap.copy(offset, offset, self.grid_size, self.grid_size)

            # Apply rotation
            transform = QTransform()
            transform.translate(visible_area.width() / 2, visible_area.height() / 2)
            transform.rotate(self.rotation_preview_angle)
            transform.translate(-visible_area.width() / 2, -visible_area.height() / 2)

            rotated = visible_area.transformed(transform, Qt.TransformationMode.SmoothTransformation)

            # Scale and center the rotated preview
            scaled_rotated = rotated.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )

            x = (self.width() - scaled_rotated.width()) // 2
            y = (self.height() - scaled_rotated.height()) // 2
            painter.drawPixmap(x, y, scaled_rotated)

            painter.setOpacity(1.0)

        # Draw preview
        if self.preview_pixmap:
            painter.setOpacity(0.5)
            visible_preview = self.preview_pixmap.copy(offset, offset, self.grid_size, self.grid_size)
            scaled = visible_preview.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            painter.drawPixmap(0, 0, scaled)

        # Move preview
        if self.temp_move_pixmap and self.draw_mode == DrawMode.MOVE:
            painter.setOpacity(0.5)
            move_x = self.move_offset.x() * self.cell_size
            move_y = self.move_offset.y() * self.cell_size

            # Extract visible area with offset
            visible_move = self.temp_move_pixmap.copy(
                offset - self.move_offset.x(),
                offset - self.move_offset.y(),
                self.grid_size, self.grid_size
            )
            scaled = visible_move.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            painter.drawPixmap(0, 0, scaled)

        # Draw grid on top of everything
        if self.show_grid:
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(180, 180, 180), 1))
            for i in range(self.grid_size + 1):
                x = i * self.cell_size
                y = i * self.cell_size
                painter.drawLine(x, 0, x, self.height())
                painter.drawLine(0, y, self.width(), y)

    def get_pixel_pos(self, pos):
        x = pos.x() // self.cell_size
        y = pos.y() // self.cell_size
        return QPoint(x, y)

    def get_virtual_pos(self, pixel_pos):
        """Convert pixel position to virtual canvas position"""
        offset = self.get_virtual_offset()
        return QPoint(pixel_pos.x() + offset, pixel_pos.y() + offset)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pixel_pos = self.get_pixel_pos(event.pos())

            # Only draw on visible layers
            if not self.layers[self.current_layer].visible:
                QMessageBox.warning(self, "Layer Hidden",
                                    "Cannot draw on hidden layer. Please make it visible first.")
                return

            # Save state BEFORE any drawing operation
            if self.draw_mode != DrawMode.PICKER:  # Don't save state for color picking
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
                self.polygon_points.append(self.get_virtual_pos(pixel_pos))
                if len(self.polygon_points) > 2 and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.draw_polygon()
                    self.polygon_points.clear()
            elif self.draw_mode in [DrawMode.LINE, DrawMode.RECTANGLE, DrawMode.FILLED_RECTANGLE,
                                    DrawMode.CIRCLE, DrawMode.FILLED_CIRCLE, DrawMode.TRIANGLE,
                                    DrawMode.FILLED_TRIANGLE]:
                self.preview_pixmap = QPixmap(self.virtual_size, self.virtual_size)
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
        # Don't clear the layer, just prepare for move

    def update_move(self, pos):
        """Update move preview"""
        if self.move_start:
            # Limit movement to grid size
            dx = pos.x() - self.move_start.x()
            dy = pos.y() - self.move_start.y()
            dx = max(-self.grid_size, min(self.grid_size, dx))
            dy = max(-self.grid_size, min(self.grid_size, dy))
            self.move_offset = QPoint(dx, dy)
            self.update()

    def apply_move(self):
        """Apply move operation"""
        if self.temp_move_pixmap:
            # Clear current layer and redraw at new position
            self.layers[self.current_layer].pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(self.layers[self.current_layer].pixmap)
            painter.drawPixmap(self.move_offset, self.temp_move_pixmap)
            painter.end()

            self.temp_move_pixmap = None
            self.move_start = None
            self.move_offset = QPoint(0, 0)
            self.update()

    def draw_pixel(self, pos):
        virtual_pos = self.get_virtual_pos(pos)

        painter = QPainter(self.layers[self.current_layer].pixmap)

        if self.blur_mode:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor(self.primary_color)
            color.setAlpha(128)  # Semi-transparent for blur effect
            painter.setPen(QPen(color, self.pen_width * 1.5))
        else:
            painter.setPen(QPen(self.primary_color, 1))

        painter.drawPoint(virtual_pos)
        painter.end()
        self.update()

    def draw_line(self, start, end):
        virtual_start = self.get_virtual_pos(start)
        virtual_end = self.get_virtual_pos(end)

        painter = QPainter(self.layers[self.current_layer].pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # Pixel-perfect

        if self.blur_mode:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor(self.primary_color)
            color.setAlpha(128)
            painter.setPen(QPen(color, self.pen_width * 1.5))
        else:
            painter.setPen(QPen(self.primary_color, self.pen_width))

        # Use Bresenham's line algorithm for pixel-perfect lines
        if self.pen_width == 1 and not self.blur_mode:
            self.draw_bresenham_line(painter, virtual_start, virtual_end)
        else:
            painter.drawLine(virtual_start, virtual_end)

        painter.end()
        self.update()

    def draw_bresenham_line(self, painter, start, end):
        """Bresenham's line algorithm for pixel-perfect lines"""
        x0, y0 = start.x(), start.y()
        x1, y1 = end.x(), end.y()

        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        while True:
            painter.drawPoint(x0, y0)

            if x0 == x1 and y0 == y1:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def update_preview(self, current_pos):
        if not self.preview_pixmap:
            return

        self.preview_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self.preview_pixmap)

        virtual_last = self.get_virtual_pos(self.last_pos)
        virtual_current = self.get_virtual_pos(current_pos)

        if self.blur_mode:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor(self.primary_color)
            color.setAlpha(128)
            painter.setPen(QPen(color, self.pen_width * 1.5))
        else:
            painter.setPen(QPen(self.primary_color, self.pen_width))

        painter.setBrush(QBrush(self.primary_color))

        if self.draw_mode == DrawMode.LINE:
            painter.drawLine(virtual_last, virtual_current)
        elif self.draw_mode == DrawMode.RECTANGLE:
            rect = QRect(virtual_last, virtual_current).normalized()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if self.pen_width == 1 and not self.blur_mode:
                # Pixel-perfect rectangle
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.drawRect(rect)
        elif self.draw_mode == DrawMode.FILLED_RECTANGLE:
            rect = QRect(virtual_last, virtual_current).normalized()
            painter.fillRect(rect, self.primary_color)
        elif self.draw_mode in [DrawMode.CIRCLE, DrawMode.FILLED_CIRCLE]:
            # Hold Shift for perfect circle
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Perfect circle
                dx = abs(virtual_current.x() - virtual_last.x())
                dy = abs(virtual_current.y() - virtual_last.y())
                radius = min(dx, dy)
                rect = QRect(virtual_last.x() - radius, virtual_last.y() - radius,
                             radius * 2, radius * 2)
            else:
                # Ellipse
                rect = QRect(virtual_last, virtual_current).normalized()

            if self.draw_mode == DrawMode.CIRCLE:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if self.pen_width == 1 and not self.blur_mode:
                    # Better circle algorithm for pixel art
                    self.draw_pixel_perfect_ellipse(painter, rect)
                else:
                    painter.drawEllipse(rect)
            else:
                # Filled ellipse/circle
                painter.setBrush(QBrush(self.primary_color))
                painter.drawEllipse(rect)
        elif self.draw_mode in [DrawMode.TRIANGLE, DrawMode.FILLED_TRIANGLE]:
            # Better triangle with options
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Equilateral triangle
                center_x = (virtual_last.x() + virtual_current.x()) // 2
                width = abs(virtual_current.x() - virtual_last.x())
                height = int(width * 0.866)  # sqrt(3)/2

                points = [
                    QPoint(center_x, virtual_last.y()),
                    QPoint(virtual_last.x(), virtual_last.y() + height),
                    QPoint(virtual_current.x(), virtual_last.y() + height)
                ]
            else:
                # Right triangle
                points = [
                    virtual_last,
                    virtual_current,
                    QPoint(virtual_last.x(), virtual_current.y())
                ]
            polygon = QPolygon(points)
            if self.draw_mode == DrawMode.TRIANGLE:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(polygon)

        painter.end()
        self.update()

    def apply_preview(self):
        if self.preview_pixmap:
            painter = QPainter(self.layers[self.current_layer].pixmap)
            painter.drawPixmap(0, 0, self.preview_pixmap)
            painter.end()
            self.update()

    def draw_pixel_perfect_ellipse(self, painter, rect):
        """Draw pixel-perfect ellipse using midpoint algorithm"""
        cx = rect.center().x()
        cy = rect.center().y()
        rx = rect.width() // 2
        ry = rect.height() // 2

        # Midpoint ellipse algorithm
        x = 0
        y = ry
        rx2 = rx * rx
        ry2 = ry * ry
        tworx2 = 2 * rx2
        twory2 = 2 * ry2
        p = 0
        px = 0
        py = tworx2 * y

        # Plot initial points
        self.plot_ellipse_points(painter, cx, cy, x, y)

        # Region 1
        p = round(ry2 - (rx2 * ry) + (0.25 * rx2))
        while px < py:
            x += 1
            px += twory2
            if p < 0:
                p += ry2 + px
            else:
                y -= 1
                py -= tworx2
                p += ry2 + px - py
            self.plot_ellipse_points(painter, cx, cy, x, y)

        # Region 2
        p = round(ry2 * (x + 0.5) * (x + 0.5) + rx2 * (y - 1) * (y - 1) - rx2 * ry2)
        while y > 0:
            y -= 1
            py -= tworx2
            if p > 0:
                p += rx2 - py
            else:
                x += 1
                px += twory2
                p += rx2 - py + px
            self.plot_ellipse_points(painter, cx, cy, x, y)

    def plot_ellipse_points(self, painter, cx, cy, x, y):
        """Plot symmetrical points for ellipse"""
        painter.drawPoint(cx + x, cy + y)
        painter.drawPoint(cx - x, cy + y)
        painter.drawPoint(cx + x, cy - y)
        painter.drawPoint(cx - x, cy - y)

    def draw_polygon(self):
        if len(self.polygon_points) < 3:
            return

        painter = QPainter(self.layers[self.current_layer].pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # Pixel-perfect

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

        # Option for regular polygons with Alt key
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier and len(self.polygon_points) >= 3:
            # Convert to regular polygon
            center = polygon.boundingRect().center()
            radius = int(((self.polygon_points[0].x() - center.x()) ** 2 +
                          (self.polygon_points[0].y() - center.y()) ** 2) ** 0.5)
            sides = len(self.polygon_points)

            regular_points = []
            for i in range(sides):
                angle = 2 * math.pi * i / sides - math.pi / 2
                x = int(center.x() + radius * math.cos(angle))
                y = int(center.y() + radius * math.sin(angle))
                regular_points.append(QPoint(x, y))
            polygon = QPolygon(regular_points)

        painter.drawPolygon(polygon)
        painter.end()
        self.update()

    def fill_area(self, pos):
        virtual_pos = self.get_virtual_pos(pos)

        image = self.layers[self.current_layer].pixmap.toImage()
        target_color = image.pixelColor(virtual_pos.x(), virtual_pos.y())

        if target_color == self.primary_color:
            return

        # Flood fill algorithm
        stack = [(virtual_pos.x(), virtual_pos.y())]
        while stack:
            x, y = stack.pop()
            if not (0 <= x < self.virtual_size and 0 <= y < self.virtual_size):
                continue

            if image.pixelColor(x, y) == target_color:
                image.setPixelColor(x, y, self.primary_color)
                stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

        self.layers[self.current_layer].pixmap = QPixmap.fromImage(image)
        self.update()

    def pick_color(self, pos):
        virtual_pos = self.get_virtual_pos(pos)

        # Get color from the topmost visible layer
        for i in range(len(self.layers) - 1, -1, -1):
            if self.layers[i].visible:
                image = self.layers[i].pixmap.toImage()
                color = image.pixelColor(virtual_pos.x(), virtual_pos.y())
                if color.alpha() > 0:  # Non-transparent pixel
                    self.colorPicked.emit(color)
                    break

    def erase_pixel(self, pos):
        virtual_pos = self.get_virtual_pos(pos)

        painter = QPainter(self.layers[self.current_layer].pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.setPen(QPen(Qt.GlobalColor.transparent, self.pen_width))
        painter.drawPoint(virtual_pos)
        painter.end()
        self.update()

    def resize_grid(self, new_size):
        self.save_state()
        old_size = self.grid_size
        self.grid_size = new_size
        self.virtual_size = new_size * 3

        old_offset = old_size
        new_offset = self.get_virtual_offset()

        for layer in self.layers:
            # Extract visible content from old virtual canvas
            visible_content = layer.pixmap.copy(old_offset, old_offset, old_size, old_size)

            # Create new virtual canvas
            new_pixmap = QPixmap(self.virtual_size, self.virtual_size)
            new_pixmap.fill(Qt.GlobalColor.transparent)

            # Paint old content centered in new canvas
            painter = QPainter(new_pixmap)

            # Calculate position to maintain content
            content_x = new_offset + (new_size - old_size) // 2
            content_y = new_offset + (new_size - old_size) // 2

            if layer == self.layers[0]:
                # Background layer - fill center with white first
                painter.fillRect(new_offset, new_offset, new_size, new_size, Qt.GlobalColor.white)

            # Draw old content
            painter.drawPixmap(content_x, content_y, visible_content)
            painter.end()

            layer.pixmap = new_pixmap

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
            offset = self.get_virtual_offset()
            x_offset = offset + (self.grid_size - new_width) // 2
            y_offset = offset + (self.grid_size - new_height) // 2

            # Clear and draw
            self.layers[self.current_layer].pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(self.layers[self.current_layer].pixmap)
            painter.drawImage(x_offset, y_offset, scaled)
            painter.end()
            self.update()

    def export_image(self):
        """Export only the visible area"""
        offset = self.get_virtual_offset()
        final_image = QPixmap(self.grid_size, self.grid_size)
        final_image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(final_image)
        for layer in self.layers:
            if layer.visible:
                painter.setOpacity(layer.opacity)
                # Extract only visible area
                visible_area = layer.pixmap.copy(offset, offset, self.grid_size, self.grid_size)
                painter.drawPixmap(0, 0, visible_area)
        painter.end()

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
        self.virtual_size = self.grid_size * 3
        self.layers = [Layer.from_dict(layer_data) for layer_data in project_data['layers']]
        self.current_layer = project_data['current_layer']

        self.update_size()
        self.update()

    def rotate_layer(self, angle):
        """Rotate current layer by angle"""
        # Don't save state if this is just a preview
        if not hasattr(self, 'rotation_preview_active') or not self.rotation_preview_active:
            self.save_state()

        current_layer = self.layers[self.current_layer]
        offset = self.get_virtual_offset()

        # Extract visible area
        visible_area = current_layer.pixmap.copy(offset, offset, self.grid_size, self.grid_size)

        # Create transform
        transform = QTransform()
        transform.translate(visible_area.width() / 2, visible_area.height() / 2)
        transform.rotate(angle)
        transform.translate(-visible_area.width() / 2, -visible_area.height() / 2)

        # Rotate the visible area
        rotated = visible_area.transformed(transform, Qt.TransformationMode.SmoothTransformation)

        # Clear the visible area in the layer
        painter = QPainter(current_layer.pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(offset, offset, self.grid_size, self.grid_size, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Calculate new position to center the rotated image
        new_x = offset + (self.grid_size - rotated.width()) // 2
        new_y = offset + (self.grid_size - rotated.height()) // 2
        painter.drawPixmap(new_x, new_y, rotated)
        painter.end()

        self.update()

    def flip_layer(self, horizontal):
        """Flip current layer horizontally or vertically"""
        self.save_state()

        current_layer = self.layers[self.current_layer]
        offset = self.get_virtual_offset()

        # Extract visible area
        visible_area = current_layer.pixmap.copy(offset, offset, self.grid_size, self.grid_size)

        # Create transform
        transform = QTransform()
        if horizontal:
            transform.scale(-1, 1)
            transform.translate(-visible_area.width(), 0)
        else:
            transform.scale(1, -1)
            transform.translate(0, -visible_area.height())

        # Flip the visible area
        flipped = visible_area.transformed(transform, Qt.TransformationMode.FastTransformation)

        # Clear and redraw
        painter = QPainter(current_layer.pixmap)
        painter.fillRect(offset, offset, self.grid_size, self.grid_size, Qt.GlobalColor.transparent)
        painter.drawPixmap(offset, offset, flipped)
        painter.end()

        self.update()

    def merge_selected_layers(self):
        """Merge all selected layers into one"""
        selected_indices = [i for i, layer in enumerate(self.layers) if layer.selected]

        if len(selected_indices) < 2:
            QMessageBox.warning(self, "Merge Layers",
                                "Please select at least 2 layers to merge (Ctrl+Click to select)")
            return

        self.save_state()

        # Create new merged pixmap
        merged_pixmap = QPixmap(self.virtual_size, self.virtual_size)
        merged_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(merged_pixmap)

        # Draw selected layers from bottom to top
        for idx in selected_indices:
            if self.layers[idx].visible:
                painter.setOpacity(self.layers[idx].opacity)
                painter.drawPixmap(0, 0, self.layers[idx].pixmap)

        painter.end()

        # Create new layer with merged content
        base_names = [self.layers[i].name for i in selected_indices]
        merged_name = f"Merged ({', '.join(base_names[:3])}{'...' if len(base_names) > 3 else ''})"

        # Remove selected layers (from top to bottom to maintain indices)
        for idx in reversed(selected_indices):
            del self.layers[idx]

        # Add merged layer
        new_layer = Layer(merged_name, merged_pixmap)
        self.layers.insert(min(selected_indices), new_layer)

        # Update current layer
        self.current_layer = min(selected_indices)

        # Clear selections
        for layer in self.layers:
            layer.selected = False

        self.update()


class ColorPalette(QWidget):
    colorSelected = pyqtSignal(QColor)

    def __init__(self):
        super().__init__()
        self.material_colors = []
        self.user_colors = []
        self.selected_index = -1
        self.selected_is_user = False
        self.cell_size = 24
        self.columns = 10  # Increased from 8 to 10
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

        self.material_colors = [QColor(c) for c in material_colors]

        # Initialize user colors with transparent
        self.user_colors = [QColor(0, 0, 0, 0) for _ in range(20)]  # 20 user color slots

        self.update_size()

    def update_size(self):
        material_rows = (len(self.material_colors) + self.columns - 1) // self.columns
        user_rows = (len(self.user_colors) + self.columns - 1) // self.columns
        total_rows = material_rows + user_rows + 1  # +1 for separator

        width = self.columns * self.cell_size
        height = total_rows * self.cell_size + 10  # +10 for separator space
        self.setFixedSize(width, height)

    def paintEvent(self, event):
        painter = QPainter(self)

        # Draw material colors
        for i, color in enumerate(self.material_colors):
            row = i // self.columns
            col = i % self.columns
            x = col * self.cell_size
            y = row * self.cell_size

            self.draw_color_cell(painter, x, y, color, i == self.selected_index and not self.selected_is_user)

        # Draw separator
        separator_y = ((len(self.material_colors) + self.columns - 1) // self.columns) * self.cell_size + 5
        painter.setPen(QPen(QColor(180, 180, 180), 2))
        painter.drawLine(0, separator_y, self.width(), separator_y)

        # Draw user colors
        user_start_y = separator_y + 10
        for i, color in enumerate(self.user_colors):
            row = i // self.columns
            col = i % self.columns
            x = col * self.cell_size
            y = user_start_y + row * self.cell_size

            # Mark this as user color area for draw_color_cell
            self.selected_is_user = True
            self.draw_color_cell(painter, x, y, color, i == self.selected_index and self.selected_is_user)

    def draw_color_cell(self, painter, x, y, color, selected):
        rect = QRect(x, y, self.cell_size, self.cell_size)

        # Draw transparency pattern for transparent/empty colors
        if color.alpha() < 255:
            painter.fillRect(rect, QColor(255, 255, 255))
            painter.fillRect(QRect(x, y, self.cell_size // 2, self.cell_size // 2), QColor(200, 200, 200))
            painter.fillRect(QRect(x + self.cell_size // 2, y + self.cell_size // 2,
                                   self.cell_size // 2, self.cell_size // 2), QColor(200, 200, 200))

        painter.fillRect(rect, color)

        # Draw "+" for empty user slots
        if color.alpha() == 0 and hasattr(self, 'selected_is_user'):
            painter.setPen(QPen(QColor(150, 150, 150), 2))
            center_x = x + self.cell_size // 2
            center_y = y + self.cell_size // 2
            size = self.cell_size // 3
            painter.drawLine(center_x - size, center_y, center_x + size, center_y)
            painter.drawLine(center_x, center_y - size, center_x, center_y + size)

        if selected:
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
            painter.drawRect(rect)
        else:
            painter.setPen(QPen(Qt.GlobalColor.gray, 1))
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        x = event.pos().x() // self.cell_size
        y = event.pos().y() // self.cell_size

        # Check if in material colors
        material_rows = (len(self.material_colors) + self.columns - 1) // self.columns
        if y < material_rows:
            index = y * self.columns + x
            if 0 <= index < len(self.material_colors):
                self.selected_index = index
                self.selected_is_user = False
                self.colorSelected.emit(self.material_colors[index])
                self.update()
        else:
            # Check if in user colors
            separator_rows = material_rows * self.cell_size + 10
            user_y = (event.pos().y() - separator_rows) // self.cell_size
            if user_y >= 0:
                index = user_y * self.columns + x
                if 0 <= index < len(self.user_colors):
                    self.selected_index = index
                    self.selected_is_user = True

                    if event.button() == Qt.MouseButton.RightButton:
                        # Right-click to set new color
                        color = QColorDialog.getColor(
                            self.user_colors[index], self,
                            "Choose Color",
                            QColorDialog.ColorDialogOption.ShowAlphaChannel
                        )
                        if color.isValid():
                            self.user_colors[index] = color
                            self.colorSelected.emit(color)
                    elif event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                        # Ctrl+Click to set new color (alternative)
                        color = QColorDialog.getColor(
                            self.user_colors[index], self,
                            "Choose Color",
                            QColorDialog.ColorDialogOption.ShowAlphaChannel
                        )
                        if color.isValid():
                            self.user_colors[index] = color
                            self.colorSelected.emit(color)
                    else:
                        # Normal click to select color
                        if self.user_colors[index].alpha() > 0:  # Only select if not empty
                            self.colorSelected.emit(self.user_colors[index])
                    self.update()

    def add_color(self, color):
        # Add to first empty user slot
        for i, c in enumerate(self.user_colors):
            if c.alpha() == 0:
                self.user_colors[i] = color
                self.update()
                break

    def export_palette(self):
        return {
            'material': [c.name() for c in self.material_colors],
            'user': [c.name() for c in self.user_colors]
        }

    def import_palette(self, palette_data):
        if isinstance(palette_data, dict):
            if 'material' in palette_data:
                self.material_colors = [QColor(c) for c in palette_data['material']]
            if 'user' in palette_data:
                self.user_colors = [QColor(c) for c in palette_data['user']]
        else:
            # Legacy format
            self.material_colors = [QColor(c) for c in palette_data]
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
        self.resize(400, 300)

        layout = QVBoxLayout()

        # Instructions
        instructions = QTextEdit()
        instructions.setReadOnly(True)
        instructions.setMaximumHeight(100)
        instructions.setPlainText(
            "Macro Manager Instructions:\n"
            "1. Click 'Record New' to start recording actions\n"
            "2. Perform drawing actions in the editor\n"
            "3. Click 'Stop Recording' to save the macro\n"
            "4. Select a macro and click 'Play' to repeat actions\n"
            "5. Use 'Delete' to remove selected macro"
        )
        layout.addWidget(instructions)

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
        self.load_settings()

    def setup_ui(self):
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Toolbar
        self.create_toolbar()
        self.create_transform_toolbar()

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

    def create_transform_toolbar(self):
        """Create transformation toolbar"""
        transform_toolbar = QToolBar("Transform")
        transform_toolbar.setMovable(False)
        transform_toolbar.setFixedHeight(BUTTON_HEIGHT)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, transform_toolbar)

        # Rotation slider
        transform_toolbar.addWidget(QLabel("Rotation:"))

        self.rotation_slider = QSlider(Qt.Orientation.Horizontal)
        self.rotation_slider.setRange(0, 360)
        self.rotation_slider.setValue(0)
        self.rotation_slider.setFixedWidth(200)
        self.rotation_slider.setTickInterval(45)
        self.rotation_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.rotation_slider.sliderPressed.connect(lambda: setattr(self.canvas, 'rotation_preview_active', True))
        self.rotation_slider.valueChanged.connect(self.preview_rotation)
        self.rotation_slider.sliderReleased.connect(self.apply_rotation)
        transform_toolbar.addWidget(self.rotation_slider)

        self.rotation_label = QLabel("0°")
        self.rotation_label.setFixedWidth(40)
        transform_toolbar.addWidget(self.rotation_label)

        transform_toolbar.addSeparator()

        # Quick rotation buttons
        rot_90_btn = QPushButton("↻ 90°")
        rot_90_btn.clicked.connect(lambda: self.quick_rotate(90))
        transform_toolbar.addWidget(rot_90_btn)

        rot_neg90_btn = QPushButton("↺ 90°")
        rot_neg90_btn.clicked.connect(lambda: self.quick_rotate(-90))
        transform_toolbar.addWidget(rot_neg90_btn)

        rot_180_btn = QPushButton("↕ 180°")
        rot_180_btn.clicked.connect(lambda: self.quick_rotate(180))
        transform_toolbar.addWidget(rot_180_btn)

        transform_toolbar.addSeparator()

        # Flip buttons
        flip_h_btn = QPushButton("↔ Flip H")
        flip_h_btn.clicked.connect(lambda: self.canvas.flip_layer(True))
        transform_toolbar.addWidget(flip_h_btn)

        flip_v_btn = QPushButton("↕ Flip V")
        flip_v_btn.clicked.connect(lambda: self.canvas.flip_layer(False))
        transform_toolbar.addWidget(flip_v_btn)

        transform_toolbar.addSeparator()

        # Reset button
        reset_transform_btn = QPushButton("Reset")
        reset_transform_btn.setToolTip("Reset rotation preview without applying")
        reset_transform_btn.clicked.connect(self.reset_rotation)
        transform_toolbar.addWidget(reset_transform_btn)

        # Store reference
        self.transform_toolbar = transform_toolbar

        # Initialize rotation preview
        self.rotation_preview_angle = 0

    def create_tools_panel(self):
        panel = QWidget()
        panel.setFixedWidth(ICON_SIZE * 2 + 20)
        layout = QVBoxLayout(panel)

        # Drawing tools
        tools_layout = QGridLayout()

        self.tool_buttons = QButtonGroup()
        tools = [
            ("✏", DrawMode.PENCIL, "Pencil (P)"),
            ("╱", DrawMode.LINE, "Line (L)"),
            ("□", DrawMode.RECTANGLE, "Rectangle (R)"),
            ("■", DrawMode.FILLED_RECTANGLE, "Filled Rectangle"),
            ("○", DrawMode.CIRCLE, "Circle/Ellipse (C)\nShift: Perfect circle"),
            ("●", DrawMode.FILLED_CIRCLE, "Filled Circle/Ellipse\nShift: Perfect circle"),
            ("△", DrawMode.TRIANGLE, "Triangle\nShift: Equilateral"),
            ("▲", DrawMode.FILLED_TRIANGLE, "Filled Triangle\nShift: Equilateral"),
            ("⬟", DrawMode.POLYGON, "Polygon\nShift: Finish\nAlt: Regular polygon"),
            ("⬢", DrawMode.FILLED_POLYGON, "Filled Polygon\nShift: Finish\nAlt: Regular"),
            ("🪣", DrawMode.FILL, "Fill (F)"),
            ("⌫", DrawMode.ERASER, "Eraser (E)"),
            ("💧", DrawMode.PICKER, "Color Picker (I)"),
            ("↔", DrawMode.MOVE, "Move Layer Content (M)")
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
        self.primary_color_btn.setStyleSheet("background-color: black; border: 2px solid #888888;")
        self.primary_color_btn.clicked.connect(self.choose_primary_color)
        primary_layout.addWidget(self.primary_color_btn)

        # Alpha value label
        self.alpha_label = QLabel("100%")
        self.alpha_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alpha_label.setStyleSheet("font-size: 9px; color: gray;")
        primary_layout.addWidget(self.alpha_label)

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
        self.transparent_btn.setToolTip("Transparenz setzen\nSetzt die Primärfarbe auf vollständig transparent")
        self.transparent_btn.clicked.connect(self.set_transparent_color)
        color_layout.addWidget(self.transparent_btn)

        layout.addLayout(color_layout)

        # Palette
        layout.addWidget(QLabel("Palette:"))
        palette_info = QLabel("(Right-click or Ctrl+Click on user colors to edit)")
        palette_info.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(palette_info)
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
        layout.addWidget(QLabel("Layers (Double-click: visibility, Ctrl+Click: select):"))
        self.layers_list = QListWidget()
        self.layers_list.itemClicked.connect(self.select_layer)
        self.layers_list.itemDoubleClicked.connect(self.toggle_layer_visibility_ui)
        self.update_layers_list()
        layout.addWidget(self.layers_list)

        layer_buttons = QHBoxLayout()
        add_layer_btn = QPushButton("+")
        add_layer_btn.setToolTip("Neue Ebene hinzufügen")
        add_layer_btn.clicked.connect(self.add_layer)
        layer_buttons.addWidget(add_layer_btn)

        remove_layer_btn = QPushButton("-")
        remove_layer_btn.setToolTip("Ebene entfernen")
        remove_layer_btn.clicked.connect(self.remove_layer)
        layer_buttons.addWidget(remove_layer_btn)

        merge_btn = QPushButton("⬇")
        merge_btn.setToolTip("Ausgewählte Ebenen zusammenführen")
        merge_btn.clicked.connect(self.merge_layers)
        layer_buttons.addWidget(merge_btn)

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

        # Transform submenu
        transform_menu = edit_menu.addMenu("Transform")

        rotate_90_action = QAction("Rotate 90° CW", self)
        rotate_90_action.setShortcut("Ctrl+R")
        rotate_90_action.triggered.connect(lambda: self.canvas.rotate_layer(90))
        transform_menu.addAction(rotate_90_action)

        rotate_neg90_action = QAction("Rotate 90° CCW", self)
        rotate_neg90_action.setShortcut("Ctrl+Shift+R")
        rotate_neg90_action.triggered.connect(lambda: self.canvas.rotate_layer(-90))
        transform_menu.addAction(rotate_neg90_action)

        rotate_180_action = QAction("Rotate 180°", self)
        rotate_180_action.triggered.connect(lambda: self.canvas.rotate_layer(180))
        transform_menu.addAction(rotate_180_action)

        transform_menu.addSeparator()

        flip_h_action = QAction("Flip Horizontal", self)
        flip_h_action.setShortcut("Ctrl+H")
        flip_h_action.triggered.connect(lambda: self.canvas.flip_layer(True))
        transform_menu.addAction(flip_h_action)

        flip_v_action = QAction("Flip Vertical", self)
        flip_v_action.setShortcut("Ctrl+Shift+H")
        flip_v_action.triggered.connect(lambda: self.canvas.flip_layer(False))
        transform_menu.addAction(flip_v_action)

        edit_menu.addSeparator()

        clear_layer_action = QAction("Clear Layer", self)
        clear_layer_action.triggered.connect(self.canvas.clear_layer)
        edit_menu.addAction(clear_layer_action)

        merge_layers_action = QAction("Merge Selected Layers", self)
        merge_layers_action.setShortcut("Ctrl+E")
        merge_layers_action.triggered.connect(self.merge_layers)
        edit_menu.addAction(merge_layers_action)

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
        # Rotate shortcuts
        rotate_cw = QAction(self)
        rotate_cw.setShortcut("Ctrl+R")
        rotate_cw.triggered.connect(lambda: self.canvas.rotate_layer(90))
        self.addAction(rotate_cw)

        rotate_ccw = QAction(self)
        rotate_ccw.setShortcut("Ctrl+Shift+R")
        rotate_ccw.triggered.connect(lambda: self.canvas.rotate_layer(-90))
        self.addAction(rotate_ccw)

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

    def merge_layers(self):
        """Merge selected layers"""
        self.canvas.merge_selected_layers()
        self.update_layers_list()

    def set_primary_color(self, color):
        self.canvas.primary_color = color

        # Update alpha label
        alpha_percent = int((color.alpha() / 255) * 100)
        self.alpha_label.setText(f"{alpha_percent}%")

        # Update button style to show transparency better
        if color.alpha() < 255:
            # Show with checkerboard pattern background
            self.primary_color_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-image: 
                        repeating-conic-gradient(#CCCCCC 0% 25%, #FFFFFF 0% 50%);
                    background-size: 10px 10px;
                    background-position: 0 0;
                    border: 2px solid #888888;
                }}
                """
            )
            # Apply color overlay
            pixmap = QPixmap(48, 48)
            pixmap.fill(color)
            icon = QIcon(pixmap)
            self.primary_color_btn.setIcon(icon)
            self.primary_color_btn.setIconSize(QSize(48, 48))

            # Update status bar
            self.statusBar().showMessage(f"Drawing with transparency (Alpha: {alpha_percent}%)")
        else:
            self.primary_color_btn.setIcon(QIcon())  # Remove icon
            self.primary_color_btn.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()}); "
                f"border: 2px solid #888888;"
            )
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage("Ready")

    def set_secondary_color(self, color):
        self.canvas.secondary_color = color
        self.secondary_color_btn.setStyleSheet(
            f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})")

    def update_layers_list(self):
        self.layers_list.clear()
        for i, layer in enumerate(self.canvas.layers):
            visibility = '👁' if layer.visible else '🚫'
            selection = '☑' if layer.selected else '☐'
            opacity = f" ({int(layer.opacity * 100)}%)" if layer.opacity < 1.0 else ""
            item = QListWidgetItem(f"{selection} {visibility} {layer.name}{opacity}")
            self.layers_list.addItem(item)

        self.layers_list.setCurrentRow(self.canvas.current_layer)

    def select_layer(self, item):
        row = self.layers_list.row(item)

        # Check if Ctrl/Cmd is pressed for multi-selection
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
            # Toggle selection
            self.canvas.layers[row].selected = not self.canvas.layers[row].selected
            self.update_layers_list()
        else:
            # Normal selection - clear others
            for layer in self.canvas.layers:
                layer.selected = False
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
            # Check if user wants to include transparency
            msg = QMessageBox()
            msg.setWindowTitle("Export Options")
            msg.setText("Export with transparency?")
            msg.setInformativeText("Choose 'Yes' to preserve transparency or 'No' for white background")
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            msg.setDefaultButton(QMessageBox.StandardButton.Yes)

            result = msg.exec()

            if result == QMessageBox.StandardButton.Cancel:
                return

            size, ok = QInputDialog.getInt(
                self, "Export Size", "Size (pixels):",
                256, 16, 2048, 16
            )
            if ok:
                pixmap = self.canvas.export_image()

                # If no transparency wanted, composite on white background
                if result == QMessageBox.StandardButton.No:
                    white_bg = QPixmap(pixmap.size())
                    white_bg.fill(Qt.GlobalColor.white)
                    painter = QPainter(white_bg)
                    painter.drawPixmap(0, 0, pixmap)
                    painter.end()
                    pixmap = white_bg

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
        offset = self.canvas.get_virtual_offset()

        # Extract visible area
        visible_area = current_layer.pixmap.copy(offset, offset, self.canvas.grid_size, self.canvas.grid_size)
        image = visible_area.toImage()

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

        # Put back into virtual canvas
        painter = QPainter(current_layer.pixmap)
        painter.drawImage(offset, offset, image)
        painter.end()
        self.canvas.update()

    def apply_sharpen_filter(self):
        # Simplified sharpen filter
        self.canvas.save_state()
        self.statusBar().showMessage("Sharpen filter applied")

    def apply_grayscale_filter(self):
        self.canvas.save_state()
        current_layer = self.canvas.layers[self.canvas.current_layer]
        offset = self.canvas.get_virtual_offset()

        # Extract visible area
        visible_area = current_layer.pixmap.copy(offset, offset, self.canvas.grid_size, self.canvas.grid_size)
        image = visible_area.toImage()

        for y in range(self.canvas.grid_size):
            for x in range(self.canvas.grid_size):
                pixel = image.pixelColor(x, y)
                gray = int(0.299 * pixel.red() + 0.587 * pixel.green() + 0.114 * pixel.blue())
                image.setPixelColor(x, y, QColor(gray, gray, gray, pixel.alpha()))

        # Put back into virtual canvas
        painter = QPainter(current_layer.pixmap)
        painter.drawImage(offset, offset, image)
        painter.end()
        self.canvas.update()

    def apply_invert_filter(self):
        self.canvas.save_state()
        current_layer = self.canvas.layers[self.canvas.current_layer]
        offset = self.canvas.get_virtual_offset()

        # Extract visible area
        visible_area = current_layer.pixmap.copy(offset, offset, self.canvas.grid_size, self.canvas.grid_size)
        image = visible_area.toImage()
        image.invertPixels()

        # Put back into virtual canvas
        painter = QPainter(current_layer.pixmap)
        painter.drawImage(offset, offset, image)
        painter.end()
        self.canvas.update()

    def save_settings(self):
        """Save app settings"""
        settings = {
            'grid_size': self.canvas.grid_size,
            'show_grid': self.canvas.show_grid,
            'blur_mode': self.canvas.blur_mode,
            'pen_width': self.canvas.pen_width,
            'primary_color': self.canvas.primary_color.name(),
            'secondary_color': self.canvas.secondary_color.name(),
            'palette': self.palette.export_palette(),
            'window_geometry': {
                'x': self.x(),
                'y': self.y(),
                'width': self.width(),
                'height': self.height()
            }
        }

        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
        except:
            pass  # Fail silently

    def load_settings(self):
        """Load app settings"""
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)

            # Apply settings
            if 'grid_size' in settings:
                self.canvas.grid_size = settings['grid_size']
                self.canvas.virtual_size = settings['grid_size'] * 3
                self.canvas.update_size()
                self.grid_spin.setValue(settings['grid_size'])

            if 'show_grid' in settings:
                self.canvas.show_grid = settings['show_grid']
                self.grid_checkbox.setChecked(settings['show_grid'])

            if 'blur_mode' in settings:
                self.canvas.blur_mode = settings['blur_mode']
                self.blur_checkbox.setChecked(settings['blur_mode'])

            if 'pen_width' in settings:
                self.canvas.pen_width = settings['pen_width']
                self.pen_slider.setValue(settings['pen_width'])

            if 'primary_color' in settings:
                self.set_primary_color(QColor(settings['primary_color']))

            if 'secondary_color' in settings:
                self.set_secondary_color(QColor(settings['secondary_color']))

            if 'palette' in settings:
                self.palette.import_palette(settings['palette'])

            if 'window_geometry' in settings:
                geo = settings['window_geometry']
                self.setGeometry(geo['x'], geo['y'], geo['width'], geo['height'])

        except:
            pass  # Use defaults if no settings file

    def preview_rotation(self, angle):
        """Preview rotation in real-time"""
        # Store the angle for preview
        self.rotation_preview_angle = angle
        self.canvas.rotation_preview_angle = angle
        self.canvas.rotation_preview_active = True

        # Snap to 45° increments if Shift is pressed
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            angle = round(angle / 45) * 45
            self.rotation_slider.setValue(angle)
            self.canvas.rotation_preview_angle = angle

        self.rotation_label.setText(f"{angle}°")

        # Update preview immediately
        self.canvas.update()

    def update_rotation_preview(self):
        """Update the rotation preview"""
        self.canvas.update()

    def apply_rotation(self):
        """Apply the rotation when slider is released"""
        angle = self.rotation_slider.value()

        # Snap to 45° increments if Shift is pressed
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            angle = round(angle / 45) * 45

        if angle != 0:
            self.canvas.rotate_layer(angle)

        # Reset slider and preview
        self.rotation_slider.setValue(0)
        self.rotation_label.setText("0°")
        self.canvas.rotation_preview_angle = 0
        self.canvas.rotation_preview_active = False
        self.canvas.update()

    def quick_rotate(self, angle):
        """Quick rotation buttons"""
        self.canvas.rotate_layer(angle)
        self.rotation_slider.setValue(0)
        self.canvas.rotation_preview_angle = 0
        self.canvas.rotation_preview_active = False

    def reset_rotation(self):
        """Reset rotation slider and cancel preview"""
        self.rotation_slider.setValue(0)
        self.rotation_label.setText("0°")
        self.canvas.rotation_preview_angle = 0
        self.canvas.rotation_preview_active = False
        self.canvas.update()
        self.statusBar().showMessage("Rotation preview reset")

    def closeEvent(self, event):
        """Save settings on close"""
        self.save_settings()
        event.accept()


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