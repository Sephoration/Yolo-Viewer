"""
逻辑控制器
使用Qt信号槽连接播放器、推理器和UI
"""

import os
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, Any, Optional

from PySide6.QtCore import QObject, Signal, Qt, QThread, QTimer, QMutex, QWaitCondition, Slot
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QMessageBox, QFileDialog

from window_ui import YOLOMainWindowUI
from detector_worker import DetectorWorker
from baseDetect import BaseDetect  # 导入BaseDetect渲染器
from yolo_analyzer import UnifiedYOLO
from config import AppConfig


class VideoPlayerThread(QThread):
    """
    简化版视频播放器
    只负责解码和发送帧，移除所有不必要的锁
    """
    
    # 信号定义
    display_frame_ready = Signal(QImage)  # 显示帧 → UI
    raw_frame_ready = Signal(object)      # 原始帧 → 推理器（使用object类型避免numpy导入问题）
    status_updated = Signal(str)          # 状态更新
    playback_finished = Signal()          # 播放完成
    
    def __init__(self):
        super().__init__()
        
        # 播放控制
        self._is_running = False
        self._is_paused = False
        self._stop_requested = False
        
        # 视频/摄像头
        self.cap = None
        self.video_path = None
        self.camera_id = None
        self.play_mode = None  # 'video' or 'camera'
        
        # 视频信息
        self.total_frames = 0
        self.current_frame_num = 0
        self.fps = AppConfig.VIDEO_SETTINGS['min_fps']
        self.duration = 0.0
        
        # 帧缓存
        self.current_frame = None
        
        # 简单的互斥锁（仅用于状态保护）
        self.mutex = QMutex()
        
        # 注意：不在__init__中创建QTimer，在run()中创建
    
    def play_video(self, video_path: str):
        """播放视频文件"""
        self.stop()
        
        self.mutex.lock()
        try:
            self.video_path = video_path
            self.camera_id = None
            self.play_mode = 'video'
            self._is_running = True
            self._is_paused = False
            self._stop_requested = False
            
            if not self.isRunning():
                self.start()
            else:
                # 线程已在运行，开始播放
                self._setup_video()
                
        finally:
            self.mutex.unlock()
    
    def play_camera(self, camera_id: int = 0):
        """播放摄像头"""
        self.stop()
        
        self.mutex.lock()
        try:
            self.video_path = None
            self.camera_id = camera_id
            self.play_mode = 'camera'
            self._is_running = True
            self._is_paused = False
            self._stop_requested = False
            
            if not self.isRunning():
                self.start()
            else:
                # 线程已在运行，开始播放
                self._setup_camera()
                
        finally:
            self.mutex.unlock()
    
    def _setup_video(self):
        """设置视频播放"""
        try:
            import cv2
            
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                self.status_updated.emit(f"无法打开视频文件: {self.video_path}")
                return False
            
            # 获取视频信息
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            if self.fps <= 0:
                self.fps = AppConfig.VIDEO_SETTINGS['min_fps']
            
            self.duration = self.total_frames / self.fps if self.fps > 0 else 0
            
            # 设置定时器间隔
            interval = int(1000 / self.fps) if self.fps > 0 else 33
            if hasattr(self, 'play_timer'):
                self.play_timer.setInterval(max(1, interval))
                
                # 启动定时器
                self.play_timer.start()
            
            self.status_updated.emit(f"开始播放视频: {os.path.basename(self.video_path)}")
            self.status_updated.emit(f"总帧数: {self.total_frames}, FPS: {self.fps:.2f}")
            
            return True
            
        except Exception as e:
            self.status_updated.emit(f"设置视频失败: {str(e)}")
            return False
    
    def _setup_camera(self):
        """设置摄像头"""
        try:
            import cv2
            
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                self.status_updated.emit(f"无法打开摄像头: {self.camera_id}")
                return
            
            # 设置摄像头参数
            width, height = AppConfig.CAMERA_SETTINGS['resolution']
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            
            # 尝试设置FPS
            try:
                self.cap.set(cv2.CAP_PROP_FPS, AppConfig.CAMERA_SETTINGS['target_fps'])
            except:
                pass
            
            self.fps = AppConfig.CAMERA_SETTINGS['target_fps']
            
            # 设置定时器间隔
            interval = int(1000 / self.fps) if self.fps > 0 else 33
            if hasattr(self, 'play_timer'):
                self.play_timer.setInterval(max(1, interval))
                
                # 启动定时器
                self.play_timer.start()
            
            self.status_updated.emit(f"开始摄像头实时显示 ({width}x{height})")
            
        except Exception as e:
            self.status_updated.emit(f"设置摄像头失败: {str(e)}")
    
    def _process_next_frame(self):
        """处理下一帧（定时器触发）"""
        if not self._is_running or self._is_paused or not self.cap:
            return
        
        try:
            import cv2
            import numpy as np
            
            # 读取帧
            ret, frame = self.cap.read()
            
            if not ret or frame is None:
                # 播放结束
                if self.play_mode == 'video':
                    # 视频循环播放
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                    if not ret:
                        self.stop()
                        return
                else:
                    # 摄像头出错
                    self.stop()
                    return
            
            # 更新当前帧号
            if self.play_mode == 'video':
                self.current_frame_num = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            else:
                self.current_frame_num += 1
            
            # 保存当前帧
            self.current_frame = frame.copy() if hasattr(frame, 'copy') else frame
            
            # 发送原始帧给推理器（使用object信号避免numpy依赖问题）
            self.raw_frame_ready.emit(self.current_frame)
            
            # 准备显示帧并发送给UI
            display_qimg = self._frame_to_qimage(self.current_frame)
            self.display_frame_ready.emit(display_qimg)
            
        except Exception as e:
            self.status_updated.emit(f"处理帧失败: {str(e)}")
    
    def _frame_to_qimage(self, frame) -> QImage:
        """将帧转换为QImage"""
        try:
            import cv2
            import numpy as np
            
            if not isinstance(frame, np.ndarray) or frame.size == 0:
                return QImage()
            
            # 确保是3通道BGR图像
            if len(frame.shape) == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            elif frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            elif frame.shape[2] != 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            # 确保内存连续
            if not frame.flags['C_CONTIGUOUS']:
                frame = np.ascontiguousarray(frame)
            
            height, width, channel = frame.shape
            bytes_per_line = 3 * width
            
            return QImage(
                frame.data, width, height, bytes_per_line,
                QImage.Format_BGR888
            ).copy()
            
        except Exception as e:
            print(f"转换帧到QImage失败: {e}")
            return QImage()
    
    def stop(self):
        """停止播放"""
        self.mutex.lock()
        try:
            self._stop_requested = True
            self._is_running = False
            self._is_paused = False
            
            # 停止定时器
            if hasattr(self, 'play_timer') and self.play_timer.isActive():
                self.play_timer.stop()
            
            # 释放资源
            if self.cap:
                try:
                    self.cap.release()
                except:
                    pass
                self.cap = None
            
            # 请求线程退出
            self.quit()
            if self.isRunning():
                self.wait(1000)
            
            self.playback_finished.emit()
            
        finally:
            self.mutex.unlock()
    
    def pause(self):
        """暂停播放"""
        self.mutex.lock()
        try:
            if self._is_running and not self._is_paused:
                self._is_paused = True
                if hasattr(self, 'play_timer') and self.play_timer.isActive():
                    self.play_timer.stop()
        finally:
            self.mutex.unlock()
    
    def resume(self):
        """恢复播放"""
        self.mutex.lock()
        try:
            if self._is_running and self._is_paused:
                self._is_paused = False
                if hasattr(self, 'play_timer') and not self.play_timer.isActive():
                    self.play_timer.start()
        finally:
            self.mutex.unlock()
    
    def seek_frame(self, target_frame: int):
        """跳转到指定帧（仅视频模式）"""
        if not self.cap or self.play_mode != 'video':
            return
        
        try:
            import cv2
            
            # 暂停播放
            was_playing = hasattr(self, 'play_timer') and self.play_timer.isActive()
            if was_playing:
                self.play_timer.stop()
            
            # 跳转
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(target_frame, self.total_frames - 1)))
            
            # 读取一帧
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.current_frame = frame.copy()
                self.current_frame_num = target_frame
                
                # 发送原始帧
                self.raw_frame_ready.emit(self.current_frame)
                
                # 发送显示帧
                display_qimg = self._frame_to_qimage(self.current_frame)
                self.display_frame_ready.emit(display_qimg)
            
            # 恢复播放
            if was_playing and not self._is_paused:
                self.play_timer.start()
                
        except Exception as e:
            self.status_updated.emit(f"跳转失败: {str(e)}")
    
    def get_current_frame(self):
        """获取当前帧"""
        self.mutex.lock()
        try:
            if self.current_frame is not None and hasattr(self.current_frame, 'copy'):
                return self.current_frame.copy()
            return None
        finally:
            self.mutex.unlock()
    
    def run(self):
        """线程主循环"""
        self.status_updated.emit("播放器线程启动")
        
        try:
            # 在run()内部创建QTimer（确保在同一线程）
            self.play_timer = QTimer()
            self.play_timer.timeout.connect(self._process_next_frame)
            
            # 根据播放模式设置
            if self.play_mode == 'video' and self.video_path:
                self._setup_video()
            elif self.play_mode == 'camera' and self.camera_id is not None:
                self._setup_camera()
            else:
                return
            
            # 进入事件循环
            self.exec_()
            
        except Exception as e:
            self.status_updated.emit(f"播放器错误: {str(e)}")
            traceback.print_exc()
        finally:
            # 清理
            if hasattr(self, 'play_timer') and self.play_timer.isActive():
                self.play_timer.stop()
            
            if self.cap:
                try:
                    self.cap.release()
                except:
                    pass
                self.cap = None
            
            self.status_updated.emit("播放器线程结束")


class YOLOMainController(QObject):
    """重构后的主逻辑控制器"""
    
    def __init__(self, ui_window: YOLOMainWindowUI):
        super().__init__()
        self.ui = ui_window
        
        # 核心组件
        self.video_player = VideoPlayerThread()  # 简化版播放器
        self.detector_worker = DetectorWorker()  # 独立推理器
        self.yolo_processor = None               # YOLO推理引擎
        
        # 状态变量
        self.model_loaded = False
        self.model_path = None
        self.model_mode = None
        
        # 处理状态
        self.is_processing = False      # 是否正在YOLO处理
        self.is_playing = False         # 是否正在播放
        self.current_file = None
        self.current_mode = None        # 'image', 'video', 'camera'
        
        # 参数
        self.default_params = {
            'iou_threshold': AppConfig.YOLO_SETTINGS['default_iou'],
            'confidence_threshold': AppConfig.YOLO_SETTINGS['default_confidence'],
            'delay_ms': 10,
            'line_width': AppConfig.YOLO_SETTINGS['default_line_width']
        }
        
        # 获取UI组件引用
        self.left_panel = self.ui.get_left_panel()
        self.right_panel = self.ui.get_right_panel()
        
        # 初始化
        self._init_ui_state()
        self._setup_connections()
        
        print("YOLO逻辑控制器初始化完成")
    
    def _init_ui_state(self):
        """初始化UI状态"""
        self.right_panel.set_parameters(**self.default_params)
        self.left_panel.clear_display()
        self.right_panel.update_model_info()
        self.right_panel.set_control_state(False)
    
    def _setup_connections(self):
        """设置所有信号连接"""
        
        # ===== 视频播放器信号连接 =====
        self.video_player.display_frame_ready.connect(self._on_display_frame_ready)
        self.video_player.raw_frame_ready.connect(self.detector_worker.on_frame_received)
        self.video_player.status_updated.connect(self._on_status_updated)
        self.video_player.playback_finished.connect(self._on_playback_finished)
        
        # ===== 推理工作器信号连接 =====
        self.detector_worker.frame_processed.connect(self._on_frame_processed)
        self.detector_worker.detection_stats.connect(self._on_detection_stats)
        self.detector_worker.status_updated.connect(self._on_status_updated)
        self.detector_worker.error_occurred.connect(self._on_detector_error)
        self.detector_worker.processing_complete.connect(self._on_processing_complete)
        
        # ===== UI信号连接 =====
        # 文件菜单
        self.ui.file_menu_init.connect(self._on_file_init)
        self.ui.file_menu_exit.connect(self._on_file_exit)
        
        # 帮助菜单
        self.ui.help_menu_about.connect(self._on_help_about)
        self.ui.help_menu_manual.connect(self._on_help_manual)
        
        # 主要功能
        self.ui.model_load.connect(self.handle_load_model)
        self.ui.image_open.connect(self.handle_open_image)
        self.ui.video_open.connect(self.handle_open_video)
        self.ui.camera_open.connect(self.handle_open_camera)
        self.ui.detect_settings.connect(self.handle_detect_settings)
        
        # 控制按钮
        self.right_panel.start_inference.connect(self.handle_start_inference)
        self.right_panel.stop_inference.connect(self.handle_stop_inference)
        self.right_panel.save_screenshot.connect(self.handle_save_screenshot)
        
        # 播放控制
        self.left_panel.play_pause_clicked.connect(self.handle_play_pause)
        
        # 参数变化
        self.right_panel.iou_changed.connect(self.handle_iou_change)
        self.right_panel.confidence_changed.connect(self.handle_confidence_change)
        self.right_panel.delay_changed.connect(self.handle_delay_change)
        self.right_panel.line_width_changed.connect(self.handle_line_width_change)
    
    # ============================================================================
    # 信号处理方法
    # ============================================================================
    
    @Slot(QImage)
    def _on_display_frame_ready(self, q_image: QImage):
        """显示帧就绪（来自播放器）"""
        try:
            if not self.is_processing:
                pixmap = QPixmap.fromImage(q_image)
                self.left_panel.set_display_image(pixmap)
        except Exception as e:
            print(f"显示原始帧失败: {e}")
    
    @Slot(QImage)
    def _on_frame_processed(self, q_image: QImage):
        """处理后的帧就绪（来自推理器）"""
        try:
            pixmap = QPixmap.fromImage(q_image)
            self.left_panel.set_display_image(pixmap)
        except Exception as e:
            print(f"显示处理帧失败: {e}")
    
    @Slot(dict)
    def _on_detection_stats(self, stats: dict):
        """检测统计信息"""
        try:
            self.right_panel.update_statistics(
                detection_count=stats.get('detection_count', 0),
                confidence=stats.get('avg_confidence', 0.0),
                inference_time=stats.get('inference_time', 0),
                fps=stats.get('fps', 0.0)
            )
        except Exception as e:
            print(f"更新统计信息失败: {e}")
    
    @Slot(str)
    def _on_status_updated(self, status: str):
        """状态更新"""
        print(f"状态: {status}")
    
    @Slot(str)
    def _on_detector_error(self, error_msg: str):
        """推理器错误"""
        print(f"推理器错误: {error_msg}")
    
    @Slot()
    def _on_processing_complete(self):
        """处理完成"""
        self.is_processing = False
        self.right_panel.set_control_state(False)
        print("推理处理完成")
    
    @Slot()
    def _on_playback_finished(self):
        """播放完成"""
        self.is_playing = False
        self.left_panel.set_play_state(False)
        print("播放完成")
    
    @Slot()
    def handle_play_pause(self):
        """播放/暂停"""
        try:
            if self.current_mode in ['video', 'camera']:
                if self.video_player._is_paused:
                    self.video_player.resume()
                    self.left_panel.set_play_state(True)
                else:
                    self.video_player.pause()
                    self.left_panel.set_play_state(False)
        except Exception as e:
            print(f"播放/暂停失败: {e}")
    
    # ============================================================================
    # 文件处理方法
    # ============================================================================
    
    def handle_load_model(self):
        """加载模型"""
        try:
            model_filter = AppConfig.FILE_SETTINGS['file_filters']['model']
            model_path, _ = QFileDialog.getOpenFileName(
                self.ui, "选择YOLO模型文件", "", model_filter
            )
            
            if model_path:
                self.model_path = None
                self.model_mode = None
                self.yolo_processor = None
                self.model_loaded = False
                
                print(f"开始分析模型: {model_path}")
                
                try:
                    from yolo_analyzer import UnifiedYOLO
                    model_info = UnifiedYOLO.analyze_model_info(model_path)
                    
                    if model_info:
                        model_name = os.path.basename(model_path)
                        task_type = model_info.get('task_type', 'detection')
                        input_size = model_info.get('input_size', '640x640')
                        class_count = model_info.get('class_count', '未知')
                        
                        task_display_map = AppConfig.TASK_CONFIG['task_display_map']
                        display_name = task_display_map.get(task_type, task_type)
                        self.model_mode = task_type
                        
                        self.right_panel.update_model_info(
                            model_path=model_path,
                            task_type=display_name,
                            input_size=input_size,
                            class_count=class_count
                        )
                        
                        self.model_path = model_path
                        
                        QMessageBox.information(
                            self.ui, "模型分析成功",
                            f"✅ 已自动识别模型类型\n\n"
                            f"📦 模型: {model_name}\n"
                            f"🎯 任务类型: {display_name}\n"
                            f"📏 输入尺寸: {input_size}\n"
                            f"🔢 类别数量: {class_count}\n\n"
                            f"模型将在点击'开始'时正式加载。"
                        )
                        
                    else:
                        raise Exception("无法识别模型类型")
                    
                except Exception as e:
                    print(f"模型分析失败: {e}")
                    self._show_model_type_dialog(model_path)
                    
        except Exception as e:
            self._show_error("选择模型失败", str(e))
    
    def handle_open_image(self):
        """打开图片"""
        try:
            self._stop_all()
            
            image_filter = AppConfig.FILE_SETTINGS['file_filters']['image']
            image_path, _ = QFileDialog.getOpenFileName(
                self.ui, "选择图片文件", "", image_filter
            )
            
            if image_path:
                self.current_file = image_path
                self.current_mode = 'image'
                
                self.left_panel.update_info(os.path.basename(image_path), 'image')
                
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    self.left_panel.set_display_image(pixmap)
                    print(f"已加载图片: {os.path.basename(image_path)}")
                else:
                    QMessageBox.warning(self.ui, "警告", "无法加载图片文件")
                
        except Exception as e:
            self._show_error("打开图片失败", str(e))
    
    def handle_open_video(self):
        """打开视频"""
        try:
            self._stop_all()
            
            video_filter = AppConfig.FILE_SETTINGS['file_filters']['video']
            video_path, _ = QFileDialog.getOpenFileName(
                self.ui, "选择视频文件", "", video_filter
            )
            
            if video_path:
                self.current_file = video_path
                self.current_mode = 'video'
                self.is_playing = True
                
                self.left_panel.update_info(os.path.basename(video_path), 'video')
                self.video_player.play_video(video_path)
                self.left_panel.set_play_state(True)
                
                print(f"开始播放视频: {os.path.basename(video_path)}")
                
        except Exception as e:
            self._show_error("打开视频失败", str(e))
    
    def handle_open_camera(self):
        """打开摄像头"""
        try:
            self._stop_all()
            
            camera_id = AppConfig.CAMERA_SETTINGS['default_camera_id']
            
            self.current_file = f"摄像头 {camera_id}"
            self.current_mode = 'camera'
            self.is_playing = True
            
            self.left_panel.update_info(f"摄像头 {camera_id}", 'camera')
            self.video_player.play_camera(camera_id)
            self.left_panel.set_play_state(True)
            
            print(f"开始摄像头实时显示")
                
        except Exception as e:
            self._show_error("打开摄像头失败", str(e))
    
    # ============================================================================
    # 推理控制方法
    # ============================================================================
    
    def handle_start_inference(self):
        """开始推理"""
        try:
            # 检查必要条件
            if not self.current_file:
                QMessageBox.warning(self.ui, "警告", "请先选择媒体文件！")
                return
            
            if not self.model_path or not self.model_mode:
                QMessageBox.warning(self.ui, "警告", "请先选择模型！")
                return
            
            # 加载模型
            if not self._load_yolo_processor():
                return
            
            # 设置推理器参数
            params = self.right_panel.get_parameters()
            delay_ms = params.get('delay_ms', 10)
            
            # 根据延迟计算处理间隔（延迟越大，处理间隔越大）
            process_interval = max(1, delay_ms // 10)
            self.detector_worker.set_process_interval(process_interval)
            
            # 设置YOLO处理器到推理器
            self.detector_worker.set_yolo_processor(self.yolo_processor)
            
            # 开始推理
            success = self.detector_worker.start_processing()
            if success:
                self.is_processing = True
                self.right_panel.set_control_state(True)
                print(f"开始{self.current_mode}处理，处理间隔: 每{process_interval}帧处理一次")
            else:
                QMessageBox.warning(self.ui, "警告", "无法启动推理处理")
                
        except Exception as e:
            self._show_error("开始处理失败", str(e))
    
    def handle_stop_inference(self):
        """停止推理"""
        self.detector_worker.stop_processing()
        self.is_processing = False
        self.right_panel.set_control_state(False)
        print("推理处理已停止")
    
    def _load_yolo_processor(self) -> bool:
        """加载YOLO处理器"""
        try:
            if not self.model_path or not self.model_mode:
                QMessageBox.warning(self.ui, "警告", "请先选择模型！")
                return False
            
            if self.yolo_processor is not None:
                print("YOLO处理器已加载，跳过重复加载")
                return True
            
            # 获取参数
            params = self.right_panel.get_parameters()
            
            print(f"正在加载YOLO模型: {os.path.basename(self.model_path)}")
            
            # 创建YOLO处理器
            self.yolo_processor = UnifiedYOLO(
                model_path=self.model_path,
                mode=self.model_mode,
                conf_threshold=params['confidence_threshold'],
                iou_threshold=params['iou_threshold']
            )
            
            self.model_loaded = True
            
            # 获取模型信息
            model_info = self.yolo_processor.get_model_info()
            
            # 更新UI
            task_display_map = AppConfig.TASK_CONFIG['task_display_map']
            display_name = task_display_map.get(self.model_mode, self.model_mode)
            input_size_str = f"{model_info.get('input_size', 640)}"
            class_count = model_info.get('class_count', model_info.get('num_classes', '未知'))
            
            self.right_panel.update_model_info(
                model_path=self.model_path,
                task_type=display_name,
                input_size=input_size_str,
                class_count=str(class_count)
            )
            
            print(f"✅ YOLO处理器加载成功")
            return True
                
        except Exception as e:
            self._show_error("加载YOLO处理器失败", str(e))
            return False
    
    # ============================================================================
    # 其他方法
    # ============================================================================
    
    def _stop_all(self):
        """停止所有处理"""
        self.detector_worker.stop_processing()
        self.video_player.stop()
        self.is_processing = False
        self.is_playing = False
        self.right_panel.set_control_state(False)
    
    def _format_time(self, seconds):
        """格式化时间"""
        try:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes:02d}:{secs:02d}"
        except:
            return "--:--"
    
    def _show_error(self, title: str, message: str):
        """显示错误"""
        QMessageBox.critical(
            self.ui, title,
            f"{message}\n\n详细信息请查看控制台输出。"
        )
        print(f"错误 [{title}]: {message}")
        traceback.print_exc()
    
    # 参数更新方法
    def handle_iou_change(self, value):
        """处理IOU阈值变化"""
        self.default_params['iou_threshold'] = value
        if self.yolo_processor:
            self.yolo_processor.update_params(iou_threshold=value)
            self.detector_worker.update_parameters(iou_threshold=value)
    
    def handle_confidence_change(self, value):
        """处理置信度阈值变化"""
        self.default_params['confidence_threshold'] = value
        if self.yolo_processor:
            success = self.yolo_processor.update_params(conf_threshold=value)
            self.detector_worker.update_parameters(confidence_threshold=value)
            
            if success:
                print(f"置信度阈值已更新: {value}")
            else:
                print(f"错误 [更新置信度阈值失败]: 无效的阈值: {value}")
    
    def handle_delay_change(self, value):
        """处理延迟变化"""
        self.default_params['delay_ms'] = value
    
    def handle_line_width_change(self, value):
        """处理线宽变化"""
        self.default_params['line_width'] = value
        if self.yolo_processor:
            self.yolo_processor.update_params(line_width=value)
            self.detector_worker.update_parameters(line_width=value)
    
    def handle_save_screenshot(self):
        """保存截图"""
        try:
            pixmap = self.left_panel.display_label.pixmap()
            if pixmap and not pixmap.isNull():
                # 使用配置文件中的文件过滤器
                file_filter = AppConfig.FILE_SETTINGS['file_filters']['screenshot']
                
                if self.current_file:
                    base_name = os.path.splitext(os.path.basename(self.current_file))[0]
                else:
                    base_name = "screenshot"
                
                default_name = f"{base_name}.png"
                
                save_path, _ = QFileDialog.getSaveFileName(
                    self.ui, "保存截图",
                    default_name,
                    file_filter
                )
                
                if save_path:
                    if not save_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                        save_path += '.png'
                    
                    success = pixmap.save(save_path)
                    if success:
                        QMessageBox.information(self.ui, "保存成功", f"截图已保存到:\n{save_path}")
                        print(f"截图保存到: {save_path}")
                    else:
                        QMessageBox.warning(self.ui, "保存失败", "无法保存截图")
            else:
                QMessageBox.warning(self.ui, "警告", "没有可保存的图像")
                
        except Exception as e:
            self._show_error("保存截图失败", str(e))
    
    def handle_detect_settings(self):
        """检测设置"""
        # 由UI直接处理对话框显示，这里只做业务逻辑处理
        print("检测设置菜单被点击")
    

    
    # ============================================================================
    # 文件菜单处理方法（从UI接收信号）
    # ============================================================================
    
    def _on_file_init(self):
        """初始化 - 由UI调用，执行实际初始化逻辑"""
        # 执行实际初始化逻辑
        self._stop_all()
        self._init_ui_state()
        
        # 通知UI显示完成对话框（通过UI的方法）
        self.ui.show_init_complete_dialog()
        print("系统已初始化")
    
    def _on_file_exit(self):
        """退出 - 由UI调用，执行退出逻辑"""
        # 执行退出前的清理工作
        self._stop_all()
        # 关闭窗口（UI方法）
        self.ui.close()
        print("程序退出")
    
    # ============================================================================
    # 帮助菜单处理方法（从UI接收信号）
    # ============================================================================
    
    def _on_help_about(self):
        """关于 - 由UI调用，执行额外逻辑"""
        # UI已经显示了对话框，这里可以执行额外的逻辑（如记录日志）
        print("用户查看了关于信息")
    
    def _on_help_manual(self):
        """使用说明 - 由UI调用，执行额外逻辑"""
        # UI已经显示了对话框，这里可以执行额外的逻辑（如记录日志）
        print("用户查看了使用说明")