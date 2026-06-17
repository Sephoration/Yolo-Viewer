"""
软件界面_ui部分
保留单独运行能力、以方便测试
定义和布局UI组件
提供用户交互接口
显示数据和状态
触发简单事件（菜单点击、按钮点击）
错误处理应该放在控制器中
不要在UI中添加进度条组件
"""

import sys
import os
from datetime import datetime  # 从datetime模块导入datetime类
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QSlider, QPushButton, QGroupBox,
                               QToolBar, QSizePolicy, QMenu, QScrollArea,
                               QMessageBox, QTextBrowser, QDialog)
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QTimer
from PySide6.QtGui import QAction, QFont, QPainter, QPen


# ============================================================================
# 常量定义类 - 集中管理所有UI相关常量
# ============================================================================
class UIContants:
    # 尺寸常量
    MIN_DISPLAY_WIDTH = 320       # 显示标签最小宽度
    MIN_DISPLAY_HEIGHT = 180      # 显示标签最小高度
    CONTROL_HEIGHT = 40           # 视频控制部件高度
    PLAY_BUTTON_SIZE = 32         # 播放/暂停按钮尺寸
    FILE_LABEL_HEIGHT = 25        # 文件名标签高度
    TIME_LABEL_MIN_WIDTH = 85     # 时间标签最小宽度
    RIGHT_PANEL_MIN_WIDTH = 220   # 右侧面板最小宽度
    BUTTON_MIN_HEIGHT = 35        # 按钮最小高度
    
    # 布局常量
    PADDING_SMALL = 10            # 小间距/内边距
    PADDING_MEDIUM = 12           # 中等间距/内边距
    LAYOUT_SPACING = 10           # 布局间距
    FILE_LABEL_MAX_WIDTH = 300    # 文件名标签最大宽度
    FILE_LABEL_WIDTH_OFFSET = 20  # 文件名标签宽度偏移
    
    # 进度条常量（保留接口，后续可能开发）
    PROGRESS_RANGE = 1000         # 进度条范围
    
    # 字体常量
    TIME_FONT_SIZE = 9            # 时间显示字体大小
    
    # 滑块常量
    SLIDER_LABEL_WIDTH = 60       # 滑块标签宽度
    SLIDER_WIDTH = 80             # 滑块宽度
    SLIDER_VALUE_LABEL_WIDTH = 35 # 滑块值标签宽度
    
    # 窗口常量
    MIN_WINDOW_WIDTH = 1000       # 窗口最小宽度
    MIN_WINDOW_HEIGHT = 650       # 窗口最小高度
    INITIAL_WINDOW_WIDTH = 1140   # 初始窗口宽度
    INITIAL_WINDOW_HEIGHT = 675   # 初始窗口高度
    
    # 位置常量
    FILE_LABEL_X = 10             # 文件名标签X坐标
    FILE_LABEL_Y = 10             # 文件名标签Y坐标


# ============================================================================
# 自定义组件：保持16:9比例且左右贴边的显示标签
# 功能：确保图像显示区域始终保持16:9比例，随父容器宽度自适应调整
# ============================================================================
class AspectRatioDisplayLabel(QLabel):
    """保持16:9显示比例的居中图像标签，支持缩放和拖拽平移"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(UIContants.MIN_DISPLAY_WIDTH, UIContants.MIN_DISPLAY_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 原始图像（用于自定义绘制）
        self._original_pixmap = None
        self._placeholder_text = ""

        # 缩放/平移状态
        self._zoom_level = 1.0
        self._min_zoom = 1.0
        self._max_zoom = 10.0
        self._pan_offset = QPoint(0, 0)
        self._is_panning = False
        self._last_mouse_pos = QPoint()
        self._display_rect = QRect()

        # 缩放指示器
        self._show_zoom_indicator = False
        self._zoom_indicator_timer = QTimer()
        self._zoom_indicator_timer.setSingleShot(True)
        self._zoom_indicator_timer.timeout.connect(self._hide_zoom_indicator)

        # 启用鼠标追踪（悬停时改变光标）
        self.setMouseTracking(True)

    def setPixmap(self, pixmap, frame_id=None):
        """设置显示图像（支持缩放/平移）
        Args:
            pixmap: QPixmap对象
            frame_id: 保留参数，不再使用
        """
        if not pixmap.isNull():
            self._original_pixmap = pixmap
            self._placeholder_text = ""
            self.update()
        else:
            super().setPixmap(pixmap)

    # -------- 缩放方法 --------

    def get_zoom_level(self) -> float:
        """获取当前缩放级别"""
        return self._zoom_level

    def reset_zoom(self):
        """重置缩放和平移到初始状态"""
        self._zoom_level = 1.0
        self._pan_offset = QPoint(0, 0)
        self._show_zoom_indicator = True
        self._zoom_indicator_timer.start(1500)
        self.update()

    def fit_to_window(self):
        """缩放到适合窗口（同reset_zoom）"""
        self.reset_zoom()

    def clear_cache(self):
        """兼容接口 - 不再需要"""
        pass

    def clear(self):
        """清空显示"""
        self._original_pixmap = None
        self._placeholder_text = ""
        super().clear()

    # -------- 事件处理 --------

    def resizeEvent(self, event):
        """重写resize事件，保持16:9比例"""
        super().resizeEvent(event)

        parent_widget = self.parent() if self.parent() else None
        if parent_widget:
            rect = parent_widget.contentsRect()
            parent_width = rect.width()
            parent_height = rect.height()

            try:
                ctrl = parent_widget.findChild(QWidget, "VideoControlWidget")
                if ctrl and ctrl.isVisible():
                    ctrl_h = ctrl.sizeHint().height()
                    parent_layout = parent_widget.layout()
                    spacing = parent_layout.spacing() if parent_layout else 0
                    parent_height = max(0, parent_height - (ctrl_h + spacing))
            except Exception:
                pass
        else:
            parent_width = self.width()
            parent_height = self.height()

        ideal_width = parent_width
        ideal_height = int(ideal_width * 9 / 16)

        if ideal_height > parent_height:
            ideal_height = parent_height
            ideal_width = int(ideal_height * 16 / 9)

        self.setFixedSize(ideal_width, ideal_height)

    def paintEvent(self, event):
        """自定义绘制，支持缩放和平移"""
        if self._original_pixmap is None or self._original_pixmap.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 计算基础显示区域（保持宽高比居中）
        label_rect = self.rect()
        pix_size = self._original_pixmap.size()
        scaled_size = pix_size.scaled(label_rect.size(), Qt.KeepAspectRatio)

        base_rect = QRect(
            (label_rect.width() - scaled_size.width()) // 2,
            (label_rect.height() - scaled_size.height()) // 2,
            scaled_size.width(),
            scaled_size.height()
        )

        # 应用缩放（以图像中心为原点）
        center = base_rect.center()
        zoomed_w = max(1, int(base_rect.width() * self._zoom_level))
        zoomed_h = max(1, int(base_rect.height() * self._zoom_level))

        display_rect = QRect(
            center.x() - zoomed_w // 2,
            center.y() - zoomed_h // 2,
            zoomed_w,
            zoomed_h
        )
        display_rect.translate(self._pan_offset)

        # 保存用于鼠标交互
        self._display_rect = QRect(display_rect)

        # 绘制图像
        painter.drawPixmap(display_rect, self._original_pixmap, self._original_pixmap.rect())

        # 绘制缩放指示器
        if self._show_zoom_indicator or self._zoom_level != 1.0:
            self._draw_zoom_indicator(painter)

    def wheelEvent(self, event):
        """鼠标滚轮缩放：以鼠标位置为中心点"""
        if self._original_pixmap is None:
            return

        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        new_zoom = max(self._min_zoom, min(self._zoom_level * factor, self._max_zoom))

        if self._display_rect.width() > 0:
            mouse_pos = event.position().toPoint()
            rel_x = (mouse_pos.x() - self._display_rect.x()) / self._display_rect.width()
            rel_y = (mouse_pos.y() - self._display_rect.y()) / self._display_rect.height()
            rel_x = max(0, min(1, rel_x))
            rel_y = max(0, min(1, rel_y))

            old_w = self._display_rect.width()
            old_h = self._display_rect.height()
            self._zoom_level = new_zoom

            # 占位更新使 _display_rect 重新计算
            self.update()

            # 补偿平移，使鼠标位置对应的图像点不变
            new_w = self._display_rect.width()
            new_h = self._display_rect.height()
            self._pan_offset += QPoint(int((new_w - old_w) * rel_x),
                                       int((new_h - old_h) * rel_y))
        else:
            self._zoom_level = new_zoom

        self._clamp_pan_offset()
        self._show_zoom_indicator = True
        self._zoom_indicator_timer.start(1500)
        self.update_cursor()
        event.accept()

    def mousePressEvent(self, event):
        """鼠标按下：中键或左键（缩放>1时）进入平移模式"""
        if event.button() == Qt.MiddleButton or \
           (event.button() == Qt.LeftButton and self._zoom_level > 1.0 and self._original_pixmap):
            self._is_panning = True
            self._last_mouse_pos = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.LeftButton and self._zoom_level <= 1.0:
            # 未缩放时左键传递给父类（保留原有交互）
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动：平移图像或更新光标"""
        if self._is_panning:
            pos = event.position().toPoint()
            delta = pos - self._last_mouse_pos
            self._pan_offset += delta
            self._last_mouse_pos = pos
            self._clamp_pan_offset()
            self.update()
            event.accept()
        else:
            self.update_cursor()
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放结束平移"""
        if self._is_panning:
            self._is_panning = False
            self.update_cursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击左键重置缩放"""
        if event.button() == Qt.LeftButton:
            self.reset_zoom()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def update_cursor(self):
        """根据状态更新光标样式"""
        if self._is_panning:
            self.setCursor(Qt.ClosedHandCursor)
        elif self._zoom_level > 1.0 and self._original_pixmap:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    # -------- 内部辅助方法 --------

    def _clamp_pan_offset(self):
        """限制平移范围，防止图像完全移出视野"""
        if self._original_pixmap is None:
            return
        label_rect = self.rect()
        overflow_w = max(0, (self._display_rect.width() - label_rect.width()) // 2)
        overflow_h = max(0, (self._display_rect.height() - label_rect.height()) // 2)
        self._pan_offset.setX(max(-overflow_w, min(overflow_w, self._pan_offset.x())))
        self._pan_offset.setY(max(-overflow_h, min(overflow_h, self._pan_offset.y())))

    def _draw_zoom_indicator(self, painter):
        """在左下角绘制缩放百分比"""
        text = f"{self._zoom_level * 100:.0f}%"
        painter.setPen(QPen(Qt.white, 1))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(10, self.height() - 10, text)

    def _hide_zoom_indicator(self):
        """隐藏缩放指示器"""
        self._show_zoom_indicator = False
        if self._original_pixmap is not None:
            self.update()


# ============================================================================
# 左侧展示区域组件
# 功能：负责图像/视频/摄像头内容展示，包含播放控制和文件名显示
# ============================================================================
class LeftDisplayPanel(QWidget):
    """左侧展示面板：4:3容器，文件名直接印在黑边上，16:9区域贴边"""
    
    # 定义信号
    play_pause_clicked = Signal()   # 播放/暂停按钮点击信号
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 480)  # 4:3最小尺寸
        self.current_mode = None  # 模式：'image', 'video', 'camera'
        self.is_playing = False   # 视频播放状态标记
        self._init_ui()           # 初始化UI
        self._setup_style()       # 设置样式
    
    def _init_ui(self):
        """初始化UI组件"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 黑色显示容器
        self.display_container = QWidget()
        self.display_container.setObjectName("DisplayContainer")
        
        # 容器布局 - 使用弹性空间让内容居中
        container_layout = QVBoxLayout(self.display_container)
        container_layout.setContentsMargins(0, 0, 0, 0)  # 移除左右内边距，让16:9区域完全贴边
        container_layout.setSpacing(0)
        
        # 添加上方弹性空间
        container_layout.addStretch(1)
        
        # 16:9显示标签 - 居中显示
        self.display_label = AspectRatioDisplayLabel()
        self.display_label.setObjectName("DisplayLabel")
        container_layout.addWidget(self.display_label, alignment=Qt.AlignCenter)
        
        # 添加下方弹性空间
        container_layout.addStretch(1)
        
        main_layout.addWidget(self.display_container)
        
        # 创建叠加层：文件名标签和视频控制部件
        self._create_overlay_widgets()
        
        # 默认禁用视频控制（图片模式）
        self.set_controls_enabled(False)
    
    def _create_overlay_widgets(self):
        """创建叠加在显示区域上的控件（文件名和视频控制）"""
        # 创建文件名标签（叠加在黑色背景上）
        self.filename_label = QLabel(self.display_container)
        self.filename_label.setObjectName("FilenameLabel")
        self.filename_label.setFixedHeight(UIContants.FILE_LABEL_HEIGHT)
        self.filename_label.hide()  # 默认隐藏
        
        # 创建视频控制部件（叠加层）- 只显示文件名，移除进度条和时间显示
        self.video_control_widget = self._create_video_control_widget()
        self.video_control_widget.setObjectName("VideoControlWidget")
        self.video_control_widget.setParent(self.display_container)
        self.video_control_widget.hide()  # 默认隐藏
        self.video_control_widget.raise_()  # 确保在最上层
    
    def _create_video_control_widget(self):
        """创建视频控制部件（仅文件名）- 叠加层版本"""
        control_widget = QWidget()
        control_widget.setFixedHeight(UIContants.FILE_LABEL_HEIGHT)
        
        # 视频控制布局
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(0)
        
        # 播放状态标签（用于显示播放状态，但隐藏不显示）
        self.status_label = QLabel("")
        self.status_label.setFixedWidth(0)  # 设置为0宽度，隐藏
        self.status_label.hide()
        
        control_layout.addWidget(self.status_label)
        
        return control_widget
    
    def _on_play_pause_clicked(self):
        """播放/暂停按钮点击事件处理"""
        self.is_playing = not self.is_playing  # 切换播放状态
        self._update_play_button_state()       # 更新按钮显示
        self.play_pause_clicked.emit()         # 发射点击信号
    
    def _update_play_button_state(self):
        """更新播放按钮显示状态"""
        # 移除播放按钮相关代码
        pass
    
    def resizeEvent(self, event):
        """重写resize事件，调整叠加控件位置"""
        super().resizeEvent(event)
        
        # 更新文件名标签位置和宽度
        if self.filename_label.isVisible():
            self.filename_label.move(10, 10)  # 左上角偏移10px
            # 最大宽度不超过容器宽度-20，且不超过300px
            self.filename_label.setFixedWidth(min(300, self.display_container.width() - 20))
        
        # 更新视频控制部件位置（左上角，与文件名标签对齐）
        if self.video_control_widget.isVisible():
            self.video_control_widget.move(10, 10)
            self.video_control_widget.setFixedWidth(min(300, self.display_container.width() - 20))
            self.video_control_widget.raise_()  # 确保在最上层
    
    def _setup_style(self):
        """设置样式表"""
        self.setStyleSheet("""
            QWidget {{
                background-color: #f5f5f5;
            }}
            QWidget#DisplayContainer {{
                background-color: #2a2a2a;  /* 黑色显示区域背景 */
            }}
            QLabel#DisplayLabel {{
                background-color: #2a2a2a;
                border: none;
                color: white;
                font-size: 12px;
            }}
            QLabel#FilenameLabel {{
                background-color: transparent;
                color: white;
                padding: 0;
                border: none;
                border-radius: 0;
                font-family: 'Microsoft YaHei';
                font-size: 11px;
                font-weight: bold;
                text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.8);
            }}
            QWidget#VideoControlWidget {{
                background-color: transparent;
                border: none;
            }}
        """.format(
            6,  # 进度条槽高度
            3,  # 进度条槽圆角
            16, # 进度条手柄宽度
            16, # 进度条手柄高度
            8   # 进度条手柄圆角
        ))
    
    # ===== 公共接口方法 =====
    
    def update_info(self, file_name="", mode="image"):
        """更新显示信息（文件名和模式）"""
        self.current_mode = mode
        
        # 更新文件名显示
        if mode == "camera":
            self.filename_label.setText("摄像头")
            self.filename_label.show()
        elif file_name:
            # 过长文件名显示省略号
            text = "..." + file_name[-27:] if len(file_name) > 30 else file_name
            self.filename_label.setText(text)
            self.filename_label.show()
            # 设置文件名标签的位置
            self.filename_label.move(12, 12)
        else:
            self.filename_label.hide()
        
        # 根据模式启用/禁用视频控制
        if mode == "video":
            self.video_control_widget.show()
            self.set_controls_enabled(True)
            self.is_playing = False  # 视频默认不播放，等待点击开始
        else:
            self.video_control_widget.hide()
            self.set_controls_enabled(False)
            self.is_playing = False
        
        # 更新叠加控件位置
        self.resizeEvent(None)
    
    def set_display_image(self, pixmap, frame_id=None):
        """设置显示图像（保持原比例）
        
        Args:
            pixmap: QPixmap对象
            frame_id: 可选的帧ID，用于缓存管理
        """
        if pixmap:
            # 使用带缓存的setPixmap方法
            self.display_label.setPixmap(pixmap, frame_id)
        else:
            self.display_label.clear()
    
    def clear_display(self):
        """清空显示区域"""
        self.display_label.clear()
        self.display_label.setText("等待显示图像...")
        self.filename_label.hide()
        self.video_control_widget.hide()
        self.set_controls_enabled(False)
    
    def set_controls_enabled(self, enabled):
        """启用/禁用视频控制部件
        
        Args:
            enabled: 是否启用控制部件
        """
        # 移除播放按钮相关代码
        pass
    
    def set_play_state(self, is_playing: bool):
        """设置播放状态
        
        Args:
            is_playing: 是否正在播放
        """
        self.is_playing = is_playing
        # 移除播放按钮相关代码


# ============================================================================
# 右侧控制面板组件
# 功能：提供参数设置、模型信息展示、统计信息显示和控制按钮
# ============================================================================
class RightControlPanel(QWidget):
    """右侧控制面板：参数设置和统计信息"""
    
    # 定义信号
    iou_changed = Signal(float)          # IOU阈值改变信号
    confidence_changed = Signal(float)   # 置信度阈值改变信号
    delay_changed = Signal(int)          # 延迟时间改变信号
    line_width_changed = Signal(int)     # 线宽改变信号
    save_screenshot = Signal()           # 保存截图信号
    start_inference = Signal()           # 开始推理信号
    stop_inference = Signal()            # 停止推理信号
    
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(UIContants.RIGHT_PANEL_MIN_WIDTH)
        self._init_ui()    # 初始化UI
        self._setup_style()  # 设置样式
    
    def _init_ui(self):
        """初始化UI组件"""
        # 创建滚动区域（支持垂直滚动）
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        main_scroll.setStyleSheet("QScrollArea { border: none; }")
        
        # 滚动区域内容组件
        content_widget = QWidget()
        self._content_layout = QVBoxLayout(content_widget)
        self._content_layout.setContentsMargins(UIContants.PADDING_SMALL, UIContants.PADDING_SMALL, UIContants.PADDING_SMALL, UIContants.PADDING_SMALL)
        self._content_layout.setSpacing(UIContants.LAYOUT_SPACING)
        
        # 添加各组组件
        self.model_info_group = self._create_model_info_group()
        self._content_layout.addWidget(self.model_info_group)
        
        self.params_group = self._create_params_group()
        self._content_layout.addWidget(self.params_group)
        
        self.stats_group = self._create_stats_group()
        self._content_layout.addWidget(self.stats_group)
        
        self.control_buttons = self._create_control_buttons()
        self._content_layout.addWidget(self.control_buttons)
        
        self.save_button = self._create_save_button()
        self._content_layout.addWidget(self.save_button)
        
        # 添加弹性空间（将内容顶到上方）
        self._content_layout.addStretch(1)
        
        # 设置滚动区域内容
        main_scroll.setWidget(content_widget)
        
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(main_scroll)
    
    def _create_model_info_group(self):
        """创建模型信息显示组"""
        group = QGroupBox("模型信息")
        layout = QVBoxLayout(group)
        
        self.model_name_label = QLabel("模型: 未加载")
        layout.addWidget(self.model_name_label)
        
        self.task_type_label = QLabel("任务: 未知")
        layout.addWidget(self.task_type_label)
        
        self.input_size_label = QLabel("尺寸: 未知")
        layout.addWidget(self.input_size_label)
        
        self.class_count_label = QLabel("类别: 未知")
        layout.addWidget(self.class_count_label)
        
        return group
    
    def _create_params_group(self):
        """创建参数调节组（IOU、置信度、延迟、线宽）"""
        group = QGroupBox("推理参数")
        layout = QVBoxLayout(group)
        layout.setSpacing(5)
        
        # IOU阈值滑块
        iou_container = self._create_slider_widget(
            "IOU阈值:", 0.0, 1.0, 0.45, 100,
            self.iou_changed, lambda v: v / 100
        )
        self.iou_slider = iou_container["slider"]
        self.iou_value_label = iou_container["label"]
        layout.addWidget(iou_container["widget"])
        
        # 置信度阈值滑块
        conf_container = self._create_slider_widget(
            "置信度:", 0.0, 1.0, 0.5, 100,
            self.confidence_changed, lambda v: v / 100
        )
        self.confidence_slider = conf_container["slider"]
        self.confidence_value_label = conf_container["label"]
        layout.addWidget(conf_container["widget"])
        
        # 延迟时间滑块
        delay_container = self._create_slider_widget(
            "延迟(ms):", 0, 100, 10, 1,
            self.delay_changed
        )
        self.delay_slider = delay_container["slider"]
        self.delay_value_label = delay_container["label"]
        layout.addWidget(delay_container["widget"])
        
        # 线宽滑块
        line_width_container = self._create_slider_widget(
            "线宽:", 1, 10, 2, 1,
            self.line_width_changed
        )
        self.line_width_slider = line_width_container["slider"]
        self.line_width_value_label = line_width_container["label"]
        layout.addWidget(line_width_container["widget"])
        
        return group
    
    def _create_slider_widget(self, label_text, min_val, max_val, default_val, 
                             scale_factor=1, signal=None, transform_func=None):
        """
        创建滑块控件组
        参数:
            label_text: 标签文本
            min_val: 最小值
            max_val: 最大值
            default_val: 默认值
            scale_factor: 缩放因子（用于将浮点数转为整数处理）
            signal: 信号对象
            transform_func: 值转换函数
        返回:
            包含widget、slider、label的字典
        """
        widget = QWidget()
        widget.setMinimumHeight(30)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 标签
        label = QLabel(label_text)
        label.setMinimumWidth(UIContants.SLIDER_LABEL_WIDTH)
        label.setMaximumWidth(UIContants.SLIDER_LABEL_WIDTH)
        layout.addWidget(label)
        
        # 滑块
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val * scale_factor, max_val * scale_factor)
        slider.setValue(default_val * scale_factor)
        slider.setMinimumWidth(UIContants.SLIDER_WIDTH)
        
        # 值显示标签
        value_label = QLabel(str(default_val))
        value_label.setMinimumWidth(UIContants.SLIDER_VALUE_LABEL_WIDTH)
        value_label.setMaximumWidth(UIContants.SLIDER_VALUE_LABEL_WIDTH)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        # 连接信号
        if signal and transform_func:
            slider.valueChanged.connect(
                lambda v: self._on_slider_changed(v, value_label, signal, transform_func)
            )
        elif signal:
            slider.valueChanged.connect(
                lambda v: self._on_slider_changed(v, value_label, signal)
            )
        
        layout.addWidget(slider)
        layout.addWidget(value_label)
        
        return {
            "widget": widget,
            "slider": slider,
            "label": value_label
        }
    
    def _on_slider_changed(self, value, value_label, signal, transform_func=None):
        """滑块值改变时的处理函数"""
        # 转换值（如果需要）
        if transform_func:
            display_value = transform_func(value)
            actual_value = display_value
        else:
            display_value = value
            actual_value = value
        
        # 更新显示文本
        if isinstance(display_value, float):
            value_label.setText(f"{display_value:.2f}")
        else:
            value_label.setText(str(display_value))
        
        # 发射信号
        signal.emit(actual_value)
    
    def _create_stats_group(self):
        """创建实时统计组"""
        group = QGroupBox("实时统计")
        layout = QVBoxLayout(group)
        
        self.detection_count_label = QLabel("检测数: 0")
        layout.addWidget(self.detection_count_label)
        
        self.confidence_label = QLabel("置信度: 0.00")
        layout.addWidget(self.confidence_label)
        
        self.inference_time_label = QLabel("推理时间: 0ms")
        layout.addWidget(self.inference_time_label)
        
        self.fps_label = QLabel("FPS: 0.0")
        layout.addWidget(self.fps_label)
        
        return group
    
    def _create_control_buttons(self):
        """创建控制按钮组（开始/停止推理）"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        self.start_button = QPushButton("开始")
        self.start_button.setMinimumHeight(UIContants.BUTTON_MIN_HEIGHT)
        self.start_button.clicked.connect(self.start_inference.emit)
        
        self.stop_button = QPushButton("停止")
        self.stop_button.setMinimumHeight(UIContants.BUTTON_MIN_HEIGHT)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_inference.emit)
        
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        
        return widget
    
    def _create_save_button(self):
        """创建保存截图按钮"""
        button = QPushButton("保存截图")
        button.setMinimumHeight(UIContants.BUTTON_MIN_HEIGHT)
        button.clicked.connect(self.save_screenshot.emit)
        return button
    
    def _setup_style(self):
        """设置样式表"""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: normal;
                border: 1px solid #cccccc;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 10px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #0078d7;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                font-weight: normal;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QLabel {
                color: #333333;
                padding: 2px;
                font-size: 11px;
            }
            QSlider::groove:horizontal {
                height: 5px;
                background: #d0d0d0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0078d7;
                width: 12px;
                height: 12px;
                margin: -3px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #106ebe;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)
    
    # ===== 公共接口方法 =====
    
    def update_model_info(self, model_path="", task_type="", input_size="", class_count=""):
        """更新模型信息显示"""
        if model_path:
            import os
            model_name = os.path.basename(model_path)
            self.model_name_label.setText(f"模型: {model_name}")
        else:
            self.model_name_label.setText("模型: 未加载")
        
        self.task_type_label.setText(f"任务: {task_type}" if task_type else "任务: 未知")
        self.input_size_label.setText(f"尺寸: {input_size}" if input_size else "尺寸: 未知")
        self.class_count_label.setText(f"类别: {class_count}" if class_count else "类别: 未知")
    
    def update_statistics(self, detection_count=0, confidence=0.0, inference_time=0, fps=0.0):
        """更新统计信息显示"""
        self.detection_count_label.setText(f"检测数: {detection_count}")
        self.confidence_label.setText(f"置信度: {confidence:.2f}")
        self.inference_time_label.setText(f"推理时间: {inference_time:.2f}ms")
        self.fps_label.setText(f"FPS: {fps:.1f}")
    
    def get_parameters(self):
        """获取当前参数值"""
        return {
            "iou_threshold": self.iou_slider.value() / 100.0,
            "confidence_threshold": self.confidence_slider.value() / 100.0,
            "delay_ms": self.delay_slider.value(),
            "line_width": self.line_width_slider.value()
        }
    
    def set_parameters(self, iou_threshold=None, confidence_threshold=None, delay_ms=None, line_width=None):
        """设置参数值"""
        if iou_threshold is not None:
            self.iou_slider.setValue(int(iou_threshold * 100))
        if confidence_threshold is not None:
            self.confidence_slider.setValue(int(confidence_threshold * 100))
        if delay_ms is not None:
            self.delay_slider.setValue(delay_ms)
        if line_width is not None:
            self.line_width_slider.setValue(line_width)
    
    def set_control_state(self, is_running):
        """设置控制按钮状态（根据推理是否运行）"""
        self.start_button.setEnabled(not is_running)
        self.stop_button.setEnabled(is_running)


# ============================================================================
# 主窗口UI
# 功能：整合左侧展示区和右侧控制区，提供菜单栏和工具栏
# ============================================================================
class YOLOMainWindowUI(QMainWindow):
    """主窗口UI类 - 简化版，只负责UI展示"""
    
    # 只保留与菜单直接相关的信号
    file_menu_init = Signal()
    file_menu_save_as = Signal()
    file_menu_save = Signal()
    file_menu_exit = Signal()
    model_load = Signal()
    image_open = Signal()
    video_open = Signal()
    camera_open = Signal()
    detect_settings = Signal()  # 新增：检测设置信号
    help_menu_about = Signal()
    help_menu_manual = Signal()
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YOLO多功能检测系统")
        self.setGeometry(100, 100, 1140, 675)  # 初始窗口大小
        
        self._init_ui()        # 初始化主UI
        self._setup_toolbar()  # 设置工具栏
        self._setup_signals()  # 设置信号连接
    
    def _init_ui(self):
        """初始化主UI布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局（水平排列左右面板）
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 左侧展示面板（占4份空间）
        self.left_panel = LeftDisplayPanel()
        main_layout.addWidget(self.left_panel, 4)
        
        # 右侧控制面板（占1份空间）
        self.right_panel = RightControlPanel()
        main_layout.addWidget(self.right_panel, 1)
    
    def _setup_toolbar(self):
        """设置单行工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        
        # 工具栏样式
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #f0f0f0;
                border-bottom: 1px solid #e0e0e0;
                spacing: 2px;
                padding: 1px;
            }
            QToolButton {
                background-color: transparent;
                border: none;
                padding: 4px 12px;
                font-family: 'Microsoft YaHei';
                font-size: 11px;
                color: #333333;
                min-height: 26px;
            }
            QToolButton:hover {
                background-color: #e8e8e8;
            }
            QToolButton:pressed {
                background-color: #d8d8d8;
            }
        """)
        
        self.addToolBar(toolbar)
        
        # 创建工具栏按钮
        self.btn_file = QAction("文件", self)
        self.btn_file.triggered.connect(self._show_file_menu)
        toolbar.addAction(self.btn_file)
        
        self.btn_model = QAction("打开模型", self)
        self.btn_model.triggered.connect(self.model_load.emit)  # 直接触发信号
        toolbar.addAction(self.btn_model)
        
        self.btn_image = QAction("打开图片", self)
        self.btn_image.triggered.connect(self.image_open.emit)  # 直接触发信号
        toolbar.addAction(self.btn_image)
        
        self.btn_video = QAction("打开视频", self)
        self.btn_video.triggered.connect(self.video_open.emit)  # 直接触发信号
        toolbar.addAction(self.btn_video)
        
        self.btn_camera = QAction("打开摄像头", self)
        self.btn_camera.triggered.connect(self.camera_open.emit)  # 直接触发信号
        toolbar.addAction(self.btn_camera)
        
        self.btn_detect_settings = QAction("检测设置", self)
        self.btn_detect_settings.triggered.connect(self.detect_settings.emit)  # 直接触发信号
        toolbar.addAction(self.btn_detect_settings)
        
        self.btn_help = QAction("帮助", self)
        self.btn_help.triggered.connect(self._show_help_menu)
        toolbar.addAction(self.btn_help)
        
        # 添加 spacer 把按钮推到左侧
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
    
    def _setup_signals(self):
        """设置信号连接 - 简化版本，只暴露子组件信号"""
        # 子组件的信号直接暴露给外部
        # 外部控制器可以这样连接：
        # controller.ui.left_panel_play_pause.connect(handler)
        self.left_panel_play_pause = self.left_panel.play_pause_clicked
        self.iou_changed = self.right_panel.iou_changed
        self.confidence_changed = self.right_panel.confidence_changed
        self.delay_changed = self.right_panel.delay_changed
        self.line_width_changed = self.right_panel.line_width_changed
        self.save_screenshot = self.right_panel.save_screenshot
        self.start_inference = self.right_panel.start_inference
        self.stop_inference = self.right_panel.stop_inference
    
    def _show_file_menu(self):
        """显示文件下拉菜单"""
        file_menu = QMenu(self)
        
        # "初始化"菜单项 - 使用UI的确认对话框
        init_action = QAction("初始化", self)
        init_action.triggered.connect(self._on_file_init_clicked)
        file_menu.addAction(init_action)
        
        # "另存为"和"保存"菜单项（暂时保留原有信号）
        file_menu.addAction("另存为", self.file_menu_save_as.emit)
        file_menu.addAction("保存", self.file_menu_save.emit)
        
        file_menu.addSeparator()
        
        # "退出"菜单项 - 使用UI的确认对话框
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self._on_file_exit_clicked)
        file_menu.addAction(exit_action)
        
        # 查找"文件"按钮位置并显示菜单
        for action in self.findChildren(QAction):
            if action.text() == "文件":
                toolbar = self.findChild(QToolBar)
                if toolbar:
                    for act in toolbar.actions():
                        if act.text() == "文件":
                            tool_btn = toolbar.widgetForAction(act)
                            if tool_btn:
                                # 在按钮下方显示菜单
                                pos = tool_btn.mapToGlobal(tool_btn.rect().bottomLeft())
                                file_menu.exec_(pos)
                                return
        
        # fallback: 在窗口左上角显示
        file_menu.exec_(self.mapToGlobal(self.rect().topLeft()))
    
    def _show_help_menu(self):
        """显示帮助菜单"""
        help_menu = QMenu("帮助", self)
        
        # "关于"菜单项 - 直接使用UI方法
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_help_about_clicked)
        help_menu.addAction(about_action)
        
        # "使用说明"菜单项 - 直接使用UI方法
        manual_action = QAction("使用说明", self)
        manual_action.triggered.connect(self._on_help_manual_clicked)
        help_menu.addAction(manual_action)
        
        # 查找"帮助"按钮位置并在按钮下方显示菜单
        toolbar = self.findChild(QToolBar)
        if toolbar:
            for act in toolbar.actions():
                if act.text() == "帮助":
                    tool_btn = toolbar.widgetForAction(act)
                    if tool_btn:
                        # 在按钮下方显示菜单
                        pos = tool_btn.mapToGlobal(tool_btn.rect().bottomLeft())
                        help_menu.exec_(pos)
                        return
        
        # 如果找不到按钮，使用原始的fallback逻辑
        help_menu.exec_(self.mapToGlobal(self.rect().topLeft()))
    
    def _on_file_init_clicked(self):
        """文件菜单中的初始化点击处理"""
        # 显示确认对话框
        if self.show_init_dialog():
            # 发送信号给控制器执行初始化逻辑
            self.file_menu_init.emit()
            # UI自己可以在这里执行一些UI相关的初始化（如果需要）
            # 控制器会处理完成后调用show_init_complete_dialog()
    
    def _on_file_exit_clicked(self):
        """文件菜单中的退出点击处理"""
        # 显示确认对话框
        if self.show_confirm_exit_dialog():
            # 发送信号给控制器执行退出逻辑
            self.file_menu_exit.emit()
    
    def _on_help_about_clicked(self):
        """帮助菜单中的关于点击处理"""
        # 直接显示关于对话框（UI独立功能）
        self.show_about_dialog()
        # 同时发射信号给控制器（可选）
        self.help_menu_about.emit()
    
    def _on_help_manual_clicked(self):
        """帮助菜单中的使用说明点击处理"""
        # 直接显示使用说明对话框（UI独立功能）
        self.show_help_manual_dialog()
        # 同时发射信号给控制器（可选）
        self.help_menu_manual.emit()

    # ===== UI对话框方法（所有弹窗都在UI中处理） =====
    
    def show_init_dialog(self) -> bool:
        """显示初始化确认对话框
        
        Returns:
            bool: 用户是否确认初始化
        """
        result = QMessageBox.question(
            self,
            "确认初始化",
            "是否要初始化所有设置？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return result == QMessageBox.Yes
    
    def show_init_complete_dialog(self):
        """显示初始化完成对话框"""
        QMessageBox.information(
            self,
            "初始化完成",
            "所有设置已重置"
        )
    
    def show_confirm_exit_dialog(self) -> bool:
        """显示退出确认对话框
        
        Returns:
            bool: 用户是否确认退出
        """
        result = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return result == QMessageBox.Yes
    
    def show_about_dialog(self):
        """显示关于对话框
        
        此方法可以独立运行，也可以通过控制器信号触发。
        显示应用程序的基本信息，包括名称、版本、开发者和版权信息。
        """
        QMessageBox.about(
            self,
            "关于 YOLO_Viewer",
            f"""<h3>YOLO_Viewer</h3>
            <p>强大的YOLO目标检测可视化工具</p>
            <p><b>版本:</b> 1.0.0</p>
            <p><b>开发者:</b> YOLO Team</p>
            <p><b>版权所有:</b> © {datetime.now().year}</p>
            <p>支持多种YOLO模型的实时推理和可视化</p>"""
        )
        
    def show_help_manual_dialog(self):
        """显示使用说明对话框
        
        此方法可以独立运行，也可以通过控制器信号触发。
        显示应用程序的使用指南和帮助信息。
        """
        # 创建自定义对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("使用说明")
        dialog.resize(600, 500)
        
        # 创建文本浏览器显示说明内容
        text_browser = QTextBrowser()
        text_browser.setHtml("""
        <h3>YOLO_Viewer 使用指南</h3>
        
        <h4>基本功能</h4>
        <ul>
            <li><b>加载模型:</b> 点击工具栏中的模型图标，选择YOLO模型文件</li>
            <li><b>打开图像:</b> 点击工具栏中的图像图标，选择要分析的图像</li>
            <li><b>打开视频:</b> 点击工具栏中的视频图标，选择要分析的视频</li>
            <li><b>打开摄像头:</b> 点击工具栏中的摄像头图标，启动实时摄像头分析</li>
        </ul>
        
        <h4>推理控制</h4>
        <ul>
            <li><b>开始推理:</b> 加载模型和媒体文件后，点击"开始"按钮</li>
            <li><b>停止推理:</b> 点击"停止"按钮暂停分析</li>
            <li><b>调整参数:</b> 使用右侧面板调整置信度、IOU阈值等参数</li>
        </ul>
        
        <h4>其他功能</h4>
        <ul>
            <li><b>保存截图:</b> 点击工具栏中的保存图标，保存当前显示的图像</li>
            <li><b>检测设置:</b> 点击"检测设置"按钮，调整检测相关参数</li>
        </ul>
        
        <p>如有任何问题或建议，请联系开发者团队。</p>
        """)
        
        # 设置布局
        layout = QVBoxLayout()
        layout.addWidget(text_browser)
        dialog.setLayout(layout)
        
        # 显示对话框
        dialog.exec_()
    
    def show_detect_settings_dialog(self):
        """显示检测设置对话框"""
        # 这里只是一个简单的实现，后续可以根据需要扩展
        QMessageBox.information(
            self,
            "检测设置",
            "检测设置功能正在开发中..."
        )

    # ===== 公共接口方法 =====
    
    def get_left_panel(self) -> LeftDisplayPanel:
        """获取左侧面板实例"""
        return self.left_panel
    
    def get_right_panel(self) -> RightControlPanel:
        """获取右侧面板实例"""
        return self.right_panel
    
    def update_display(self, pixmap):
        """更新显示图像"""
        self.left_panel.set_display_image(pixmap)
    
    def update_time_display(self, current_time, total_time):
        """更新时间显示"""
        # 原方法，现在不需要了
        pass
    
    def set_play_state(self, is_playing):
        """设置播放状态"""
        self.left_panel.set_play_state(is_playing)
    
    def update_info(self, file_name="", mode=""):
        """更新信息显示"""
        self.left_panel.update_info(file_name, mode)
    
    def update_model_info(self, model_path="", task_type="", input_size="", class_count=""):
        """更新模型信息"""
        self.right_panel.update_model_info(model_path, task_type, input_size, class_count)
    
    def update_statistics(self, detection_count=0, confidence=0.0, inference_time=0, fps=0.0):
        """更新统计信息"""
        self.right_panel.update_statistics(detection_count, confidence, inference_time, fps)
    
    def set_control_state(self, is_running):
        """设置控制状态"""
        self.right_panel.set_control_state(is_running)
    
    def clear_display(self):
        """清空显示"""
        self.left_panel.clear_display()
    
    def get_parameters(self):
        """获取当前参数值"""
        return self.right_panel.get_parameters()
    
    def set_parameters(self, iou_threshold=None, confidence_threshold=None, delay_ms=None, line_width=None):
        """设置参数值"""
        self.right_panel.set_parameters(iou_threshold, confidence_threshold, delay_ms, line_width)
    
    def set_controls_enabled(self, enabled):
        """启用/禁用控制面板"""
        self.left_panel.set_controls_enabled(enabled)


# ============================================================================
# 测试使用
# 功能：单独运行时显示UI界面，用于测试布局和交互效果
# ============================================================================
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    
    # 创建应用实例
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 使用Fusion风格，跨平台一致性更好
    
    # 创建并显示主窗口
    window = YOLOMainWindowUI()
    window.setMinimumSize(1000, 650)  # 设置最小窗口大小
    window.show()
    
    # 测试信息输出
    print("=" * 60)
    print("YOLO GUI界面测试")
    print("=" * 60)
    
    left_panel = window.get_left_panel()
    
    # 测试专用: 在单独运行UI时把显示区域变成白底并显示文件名，便于视觉校验
    try:
        # 把显示标签背景设为白色并显示测试文字
        left_panel.display_label.setStyleSheet("background-color: white; color: black;")
        left_panel.display_label.setText("测试显示窗口")

        # 显示测试文件名（作为叠加标签）并使用与容器内边距一致的位置
        left_panel.update_info(file_name="测试文件名.jpg", mode="image")
        if left_panel.filename_label.isVisible():
            left_panel.filename_label.move(12, 12)

        # 确保图片模式下控制栏被禁用
        left_panel.set_controls_enabled(False)
    except Exception:
        pass

    # 启动应用事件循环
    sys.exit(app.exec())