# 检测结果渲染到展示窗口 
# 根据检测框列表，在原始图像上画框与标签
# 分类检测、目标检测、关键点检测



import cv2
import numpy as np
from typing import Dict, Any, List, Tuple, Optional


class BaseDetect:
    """
    通用基础检测渲染器
    
    支持三种渲染模式：
    1. ✅ 目标检测：绘制边界框、类别标签、置信度
    2. ✅ 图像分类：在左上角显示分类结果（简洁列表）
    3. ✅ 关键点检测：绘制边界框、关键点、骨架连接（通用化设计）
    
    关键设计特点：
    1. 不假设任何特定模型（如17个人体关键点）
    2. 根据实际模型信息动态渲染
    3. 配置驱动，可适应不同关键点模型
    4. 所有渲染都在图像边界内
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化通用渲染器
        
        Args:
            config: 渲染配置字典，可选
        """
        # 默认通用配置
        self.config = {
            # 通用字体配置
            'font': cv2.FONT_HERSHEY_SIMPLEX,
            'font_scale': 0.5,
            'font_thickness': 1,
            'text_color': (255, 255, 255),  # 白色文字
            
            # 通用颜色生成配置
            'color_generation': {
                'hue_step': 30,  # 色相步长
                'saturation': 255,
                'value': 255
            },
            
            # 目标检测配置
            'detection': {
                'bbox_thickness': 2,
                'label_background': True,  # 是否显示标签背景
                'default_bbox_color': (200, 100, 0)  # 默认框颜色
            },
            
            # 分类配置
            'classification': {
                'position': (10, 30),           # 左上角起始位置
                'line_spacing': 25,             # 行间距
                'top_result_color': (0, 255, 0), # 绿色（最高置信度）
                'other_result_color': (255, 255, 255), # 白色（其他结果）
                'max_results': 5,               # 最多显示5个结果
                'show_background': False        # 不显示背景框
            },
            
            # 关键点检测配置（手部关键点专有化配置）
            'pose': {
                'bbox_thickness': 2,
                'bbox_color': (0, 255, 255),    # 黄色框（手部）
                'keypoint_radius': 5,
                'skeleton_thickness': 2,
                'skeleton_color': (255, 165, 0), # 橙色骨架（手部）
                'show_keypoint_names': True,    # 显示关键点名称
                'show_skeleton': True,          # 显示骨架连接
                'keypoint_colors': {
                    0: (0, 255, 0),    # MCP_1 - 绿色
                    1: (255, 0, 0),    # MCP_2 - 蓝色
                    2: (0, 0, 255),    # MCP_3 - 红色
                    3: (255, 255, 0)   # MCP_4 - 青色
                },                              # 手部关键点颜色配置
                'keypoint_names': {
                    0: "MCP_1",
                    1: "MCP_2",
                    2: "MCP_3",
                    3: "MCP_4"
                },                              # 手部关键点名称
                'skeleton_connections': [(0, 1), (1, 2), (2, 3)]  # 手部骨架连接
            }
        }
        
        # 更新用户配置（如果有）
        if config:
            self._update_config(config)
        
        # 动态颜色缓存
        self.color_cache = {}
        
        print("✅ 通用基础渲染器初始化完成")
    
    def _update_config(self, config: Dict[str, Any]):
        """递归更新配置"""
        def update_dict(original, new):
            for key, value in new.items():
                if key in original and isinstance(original[key], dict) and isinstance(value, dict):
                    update_dict(original[key], value)
                else:
                    original[key] = value
        
        update_dict(self.config, config)
    
    # ============================================================================
    # 颜色管理方法（通用）
    # ============================================================================
    
    def _generate_color(self, index: int) -> Tuple[int, int, int]:
        """
        根据索引生成颜色（通用方法）
        
        使用HSV颜色空间，确保颜色多样性
        """
        if index in self.color_cache:
            return self.color_cache[index]
        
        hue_step = self.config['color_generation']['hue_step']
        saturation = self.config['color_generation']['saturation']
        value = self.config['color_generation']['value']
        
        # 计算色相（0-179，因为OpenCV的HSV范围是0-179）
        hue = (index * hue_step) % 180
        
        # 转换为BGR
        hsv_color = np.uint8([[[hue, saturation, value]]])
        bgr_color = cv2.cvtColor(hsv_color, cv2.COLOR_HSV2BGR)[0][0]
        
        color = (int(bgr_color[0]), int(bgr_color[1]), int(bgr_color[2]))
        self.color_cache[index] = color
        
        return color
    
    def _get_color_for_class(self, class_name: str, class_id: int = None) -> Tuple[int, int, int]:
        """
        获取类别颜色
        
        优先级：
        1. 配置中指定的颜色
        2. 根据class_id生成的颜色
        3. 默认颜色
        """
        # 首先检查配置中是否有指定颜色
        bbox_colors = self.config['detection'].get('bbox_colors', {})
        if class_name in bbox_colors:
            return bbox_colors[class_name]
        
        # 根据class_id生成颜色
        if class_id is not None:
            return self._generate_color(class_id)
        
        # 默认颜色
        return self.config['detection']['default_bbox_color']
    
    # ============================================================================
    # 主渲染方法 - 统一入口
    # ============================================================================
    
    def render(self, analyzer_result: Dict[str, Any]) -> np.ndarray:
        """
        主渲染方法 - 根据analyzer的输出进行渲染
        
        Args:
            analyzer_result: yolo_analyzer.py的处理结果，包含：
                - success: 处理是否成功
                - raw_image: 原始图像
                - data_type: 数据类型 ('detection', 'classification', 'pose')
                - processed_data: 标准化数据
                - stats: 统计信息
                - model_info: 模型信息（用于动态配置）
                
        Returns:
            np.ndarray: 渲染后的图像
        """
        if not analyzer_result.get('success', False):
            return analyzer_result.get('raw_image', np.zeros((100, 100, 3), dtype=np.uint8))

        raw_image = analyzer_result.get('raw_image')
        data_type = analyzer_result.get('data_type', 'detection')
        processed_data = analyzer_result.get('processed_data', {})
        model_info = analyzer_result.get('model_info', {})

        if raw_image is None:
            return np.zeros((100, 100, 3), dtype=np.uint8)

        image = raw_image.copy()
        self._update_config_from_model(model_info, data_type)

        if data_type == 'detection':
            result = self._render_detection(image, processed_data, model_info)
        elif data_type == 'classification':
            result = self._render_classification(image, processed_data)
        elif data_type == 'pose':
            result = self._render_pose(image, processed_data, model_info)
        else:
            result = image

        if 'stats' in analyzer_result:
            result = self.draw_statistics(result, analyzer_result['stats'])

        return result

    def _update_config_from_model(self, model_info: Dict[str, Any], data_type: str):
        """
        根据模型信息动态更新渲染配置
        
        这是实现通用化的关键：根据实际模型调整渲染方式
        """
        if data_type == 'pose' and 'num_keypoints' in model_info:
            num_keypoints = model_info['num_keypoints']
            
            # 动态生成关键点颜色
            if not self.config['pose']['keypoint_colors']:
                keypoint_colors = {}
                for i in range(num_keypoints):
                    keypoint_colors[i] = self._generate_color(i)
                self.config['pose']['keypoint_colors'] = keypoint_colors
            
            # 如果模型提供了骨架连接，使用模型的
            if 'skeleton' in model_info and model_info['skeleton']:
                self.config['pose']['skeleton_connections'] = model_info['skeleton']
    
    # ============================================================================
    # 目标检测渲染方法
    # ============================================================================
    
    def _render_detection(self, image: np.ndarray, processed_data: Dict[str, Any], 
                         model_info: Dict[str, Any]) -> np.ndarray:
        """
        渲染目标检测结果（通用）
        
        数据结构要求（processed_data['detection']）：
            - boxes: [[x1,y1,x2,y2], ...]  # 边界框坐标
            - labels: ['person', 'car', ...]  # 类别标签
            - confidences: [0.95, 0.87, ...]  # 置信度列表
            - class_ids: [0, 1, ...]  # 类别ID列表
            
        渲染效果：
            1. 绘制边界框
            2. 在框的左上角显示标签和置信度
            3. 确保渲染内容在图像边界内
        """
        # 获取检测数据
        detection_data = processed_data.get('detection', {})
        boxes = detection_data.get('boxes', [])
        labels = detection_data.get('labels', [])
        confidences = detection_data.get('confidences', [])
        class_ids = detection_data.get('class_ids', [])
        
        if not boxes:
            return image
        
        # 获取图像尺寸
        img_height, img_width = image.shape[:2]
        
        # 获取配置
        det_config = self.config['detection']
        bbox_thickness = det_config['bbox_thickness']
        show_bg = det_config['label_background']
        
        # 遍历所有检测结果
        for i, box in enumerate(boxes):
            if len(box) < 4:
                continue
                
            # 提取边界框坐标并确保为整数
            x1, y1, x2, y2 = map(int, box[:4])
            
            # 确保边界框在图像范围内
            x1 = max(0, min(x1, img_width - 1))
            y1 = max(0, min(y1, img_height - 1))
            x2 = max(0, min(x2, img_width - 1))
            y2 = max(0, min(y2, img_height - 1))
            
            # 获取类别信息
            label = labels[i] if i < len(labels) else f"obj_{i}"
            confidence = confidences[i] if i < len(confidences) else 0.0
            class_id = class_ids[i] if i < len(class_ids) else i
            
            # 获取类别颜色
            color = self._get_color_for_class(label, class_id)
            
            # 绘制边界框
            cv2.rectangle(image, (x1, y1), (x2, y2), color, bbox_thickness)
            
            # 构建标签文本
            label_text = f"{label} {confidence:.2f}"
            
            # 计算文本大小
            font = self.config['font']
            font_scale = self.config['font_scale']
            font_thickness = self.config['font_thickness']
            
            (text_width, text_height), baseline = cv2.getTextSize(
                label_text, font, font_scale, font_thickness
            )
            
            if show_bg:
                # 计算文本背景框位置（在边界框左上角）
                text_bg_x1 = x1
                text_bg_y1 = max(0, y1 - text_height - 5)
                text_bg_x2 = x1 + text_width + 5
                text_bg_y2 = y1
                
                # 确保文本背景框在图像范围内
                text_bg_y1 = max(0, text_bg_y1)
                
                # 绘制文本背景
                cv2.rectangle(image, (text_bg_x1, text_bg_y1), 
                             (text_bg_x2, text_bg_y2), color, -1)
                
                # 文本位置
                text_x = x1 + 2
                text_y = y1 - 3 if y1 - 3 > 0 else y1 + text_height
            else:
                # 直接绘制文本，没有背景
                text_x = x1 + 2
                text_y = y1 - 5 if y1 - 5 > 0 else y1 + text_height + 5
            
            # 确保文本位置在图像范围内
            text_y = max(text_height, min(text_y, img_height - 5))
            
            # 绘制文本
            cv2.putText(image, label_text, (text_x, text_y), 
                       font, font_scale, self.config['text_color'], 
                       font_thickness, cv2.LINE_AA)
        
        return image
    
    # ============================================================================
    # 图像分类渲染方法
    # ============================================================================
    
    def _render_classification(self, image: np.ndarray, processed_data: Dict[str, Any]) -> np.ndarray:
        """
        渲染图像分类结果（简洁版）
        
        数据结构要求（processed_data['classification']）：
            - top_predictions: [('cat', 0.95), ('dog', 0.03), ...]  # 前N个预测
            
        渲染效果：
            1. 在图像左上角显示分类结果
            2. 最多显示5个结果，按置信度从高到低排序
            3. 最高置信度的结果用绿色显示，其他用白色
            4. 不添加背景框，简洁显示
            5. 格式："类别: 置信度%"
        """
        # 获取分类数据
        classification_data = processed_data.get('classification', {})
        top_predictions = classification_data.get('top_predictions', [])
        
        if not top_predictions:
            return image
        
        # 获取配置
        cls_config = self.config['classification']
        max_results = cls_config['max_results']
        start_x, start_y = cls_config['position']
        line_spacing = cls_config['line_spacing']
        show_bg = cls_config['show_background']
        
        # 限制显示数量
        display_predictions = top_predictions[:max_results]
        
        # 获取字体配置
        font = self.config['font']
        font_scale = self.config['font_scale']
        font_thickness = self.config['font_thickness']
        
        # 遍历所有要显示的分类结果
        for i, (class_name, confidence) in enumerate(display_predictions):
            # 构建显示文本
            if confidence >= 0.01:  # 大于1%的显示百分比
                text = f"{class_name}: {confidence*100:.1f}%"
            else:  # 小于1%的显示小数
                text = f"{class_name}: {confidence:.3f}"
            
            # 设置颜色：第一个结果用绿色，其他用白色
            if i == 0:
                color = cls_config['top_result_color']
            else:
                color = cls_config['other_result_color']
            
            # 计算当前行位置
            current_y = start_y + i * line_spacing
            
            # 确保位置在图像范围内
            if current_y < 0 or current_y >= image.shape[0]:
                break
            
            if show_bg:
                # 计算文本背景
                (text_width, text_height), baseline = cv2.getTextSize(
                    text, font, font_scale, font_thickness
                )
                
                # 绘制半透明背景
                bg_x1 = start_x - 5
                bg_y1 = current_y - text_height - 5
                bg_x2 = start_x + text_width + 5
                bg_y2 = current_y + 5
                
                if bg_y1 >= 0:
                    overlay = image.copy()
                    cv2.rectangle(overlay, (bg_x1, bg_y1), (bg_x2, bg_y2), 
                                 (0, 0, 0), -1)
                    image = cv2.addWeighted(overlay, 0.5, image, 0.5, 0)
            
            # 直接绘制文本（根据配置决定是否有背景）
            cv2.putText(image, text, (start_x, current_y), 
                       font, font_scale, color, font_thickness, cv2.LINE_AA)
        
        return image
    
    # ============================================================================
    # 关键点检测渲染方法（通用版）
    # ============================================================================
    
    def _render_pose(self, image: np.ndarray, processed_data: Dict[str, Any], 
                    model_info: Dict[str, Any]) -> np.ndarray:
        """
        渲染关键点检测结果（通用）
        
        不假设任何特定关键点模型，根据实际数据动态渲染
        
        数据结构要求（processed_data['pose']）：
            - boxes: [[x1,y1,x2,y2], ...]  # 边界框坐标
            - keypoints: [[[x,y], ...], ...]  # 关键点坐标列表
            - keypoints_conf: [[0.9, 0.8, ...], ...]  # 关键点置信度列表
            - confidences: [0.95, ...]  # 边界框置信度列表
            
        渲染效果：
            1. 绘制边界框（显示类别和置信度）
            2. 绘制关键点（不同关键点不同颜色）
            3. 绘制骨架连接（如果配置中有）
            4. 确保关键点在边界框内（必要时进行限制）
        """
        # 获取关键点数据
        pose_data = processed_data.get('pose', {})
        boxes = pose_data.get('boxes', [])
        keypoints_list = pose_data.get('keypoints', [])
        keypoints_conf_list = pose_data.get('keypoints_conf', [])
        box_confidences = pose_data.get('confidences', [])
        
        if not boxes:
            return image
        
        # 获取图像尺寸
        img_height, img_width = image.shape[:2]
        
        # 获取配置
        pose_config = self.config['pose']
        bbox_color = pose_config['bbox_color']
        bbox_thickness = pose_config['bbox_thickness']
        keypoint_radius = pose_config['keypoint_radius']
        skeleton_thickness = pose_config['skeleton_thickness']
        skeleton_color = pose_config['skeleton_color']
        show_skeleton = pose_config['show_skeleton']
        
        # 获取关键点颜色配置（已根据模型信息动态生成）
        keypoint_colors = pose_config.get('keypoint_colors', {})
        
        # 获取骨架连接配置
        skeleton_connections = pose_config.get('skeleton_connections', [])
        
        # 遍历所有检测对象
        for obj_idx, box in enumerate(boxes):
            if len(box) < 4:
                continue
            
            # 提取边界框坐标
            x1, y1, x2, y2 = map(int, box[:4])
            
            # 确保边界框在图像范围内
            x1 = max(0, min(x1, img_width - 1))
            y1 = max(0, min(y1, img_height - 1))
            x2 = max(0, min(x2, img_width - 1))
            y2 = max(0, min(y2, img_height - 1))
            
            # 获取边界框置信度
            box_confidence = 0.0
            if obj_idx < len(box_confidences):
                box_confidence = box_confidences[obj_idx]
            
            # 绘制边界框
            cv2.rectangle(image, (x1, y1), (x2, y2), bbox_color, bbox_thickness)
            
            # 在边界框上添加标签
            label_text = "Object"
            if 'class_names' in model_info and len(model_info['class_names']) > 0:
                # 如果有类别名称，使用第一个类别（假设关键点检测通常是单类别）
                label_text = model_info['class_names'][0]
            
            # 添加置信度（如果有）
            if box_confidence > 0:
                label_text = f"{label_text} {box_confidence:.2f}"
            
            # 计算文本大小并绘制标签
            self._draw_label_on_box(image, label_text, x1, y1, bbox_color)
            
            # 获取当前对象的关键点
            if obj_idx < len(keypoints_list):
                person_keypoints = keypoints_list[obj_idx]
                person_confidences = []
                if obj_idx < len(keypoints_conf_list):
                    person_confidences = keypoints_conf_list[obj_idx]
                
                # 处理关键点
                valid_keypoints = []
                for kp_idx, kp in enumerate(person_keypoints):
                    if len(kp) >= 2:
                        kp_x, kp_y = float(kp[0]), float(kp[1])
                        
                        # 关键点置信度
                        kp_conf = 1.0
                        if kp_idx < len(person_confidences):
                            kp_conf = float(person_confidences[kp_idx])
                        
                        # 置信度过滤
                        if kp_conf < 0.1:
                            continue
                        
                        # 确保关键点在图像范围内，并尽量在边界框内
                        # 但不硬性限制在框内，保持姿势自然性
                        kp_x = max(0, min(kp_x, img_width - 1))
                        kp_y = max(0, min(kp_y, img_height - 1))
                        
                        # 记录有效关键点
                        valid_keypoints.append({
                            'x': int(kp_x),
                            'y': int(kp_y),
                            'idx': kp_idx,
                            'conf': kp_conf
                        })
                
                # 绘制骨架连接（如果配置中有且需要显示）
                if show_skeleton and skeleton_connections and len(valid_keypoints) > 0:
                    self._draw_skeleton_connections(image, valid_keypoints, 
                                                  skeleton_connections, skeleton_color, 
                                                  skeleton_thickness)
                
                # 绘制关键点
                for kp_info in valid_keypoints:
                    kp_x, kp_y, kp_idx, kp_conf = (kp_info['x'], kp_info['y'], 
                                                  kp_info['idx'], kp_info['conf'])
                    
                    # 获取关键点颜色
                    color = keypoint_colors.get(kp_idx, self._generate_color(kp_idx))
                    
                    # 绘制关键点圆
                    cv2.circle(image, (kp_x, kp_y), keypoint_radius, color, -1)
                    
                    # 显示关键点名称（如果配置了）
                    if pose_config.get('show_keypoint_names', False):
                        keypoint_names = pose_config.get('keypoint_names', {})
                        if kp_idx in keypoint_names:
                            kp_name = keypoint_names[kp_idx]
                            # 绘制关键点名称
                            cv2.putText(image, kp_name, 
                                       (kp_x + 10, kp_y + 10),
                                       self.config['font'], 0.3, color, 1, 
                                       cv2.LINE_AA)
                    
                    # 可选：绘制关键点ID（调试用）
                    # cv2.putText(image, str(kp_idx), (kp_x+5, kp_y+5), 
                    #            self.config['font'], 0.3, color, 1)
        
        return image
    
    # ============================================================================
    # 通用辅助方法
    # ============================================================================
    
    def _draw_label_on_box(self, image: np.ndarray, text: str, x: int, y: int, 
                          color: Tuple[int, int, int]) -> None:
        """
        在边界框上绘制标签（通用方法）
        """
        font = self.config['font']
        font_scale = self.config['font_scale']
        font_thickness = self.config['font_thickness']
        
        (text_width, text_height), baseline = cv2.getTextSize(
            text, font, font_scale, font_thickness
        )
        
        # 计算文本背景框位置
        text_bg_x1 = x
        text_bg_y1 = max(0, y - text_height - 5)
        text_bg_x2 = x + text_width + 5
        text_bg_y2 = y
        
        # 确保文本背景框在图像范围内
        img_height, img_width = image.shape[:2]
        text_bg_y1 = max(0, text_bg_y1)
        text_bg_x2 = min(text_bg_x2, img_width - 1)
        
        # 绘制文本背景
        cv2.rectangle(image, (text_bg_x1, text_bg_y1), 
                     (text_bg_x2, text_bg_y2), color, -1)
        
        # 绘制文本
        text_x = x + 2
        text_y = y - 3 if y - 3 > 0 else y + text_height
        
        cv2.putText(image, text, (text_x, text_y), 
                   font, font_scale, self.config['text_color'], 
                   font_thickness, cv2.LINE_AA)
    
    def _draw_skeleton_connections(self, image: np.ndarray, keypoints: List[Dict], 
                                 connections: List, color: Tuple[int, int, int], 
                                 thickness: int) -> None:
        """
        绘制骨架连接线（通用方法）
        
        Args:
            image: 目标图像
            keypoints: 关键点列表，每个元素是包含'x','y','idx','conf'的字典
            connections: 连接列表，每个元素是(start_idx, end_idx)或[start_idx, end_idx]
            color: 线条颜色
            thickness: 线条粗细
        """
        # 创建索引到关键点的映射
        kp_dict = {kp['idx']: kp for kp in keypoints}
        
        for connection in connections:
            # 解析连接配置
            if isinstance(connection, (list, tuple)) and len(connection) >= 2:
                start_idx, end_idx = connection[0], connection[1]
            elif isinstance(connection, dict):
                start_idx = connection.get('srt_kpt_id', -1)
                end_idx = connection.get('dst_kpt_id', -1)
            else:
                continue
            
            # 获取起始和结束关键点
            start_kp = kp_dict.get(start_idx)
            end_kp = kp_dict.get(end_idx)
            
            # 如果两个关键点都存在且置信度足够，绘制连接线
            if start_kp and end_kp:
                if start_kp['conf'] > 0.1 and end_kp['conf'] > 0.1:
                    cv2.line(image, (start_kp['x'], start_kp['y']), 
                            (end_kp['x'], end_kp['y']), color, thickness)
    
    def draw_statistics(self, image: np.ndarray, stats: Dict[str, Any]) -> np.ndarray:
        """
        在图像上绘制统计信息（可选，右上角）
        
        Args:
            image: 输入图像
            stats: 统计信息字典
            
        Returns:
            np.ndarray: 添加了统计信息的图像
        """
        if not stats:
            return image
        
        # 构建统计文本
        lines = []
        
        # 添加基础统计
        if 'detection_count' in stats:
            lines.append(f"Objects: {stats['detection_count']}")
        
        if 'avg_confidence' in stats and stats['avg_confidence'] > 0:
            lines.append(f"Conf: {stats['avg_confidence']:.2f}")
        
        if 'keypoint_count' in stats:
            lines.append(f"Keypoints: {stats['keypoint_count']}")
        
        if 'inference_time' in stats:
            lines.append(f"Time: {stats['inference_time']:.1f}ms")
        
        # 在图像右上角绘制统计信息
        if lines:
            start_x = image.shape[1] - 150  # 右侧起始位置
            start_y = 30
            line_spacing = 20
            
            font = self.config['font']
            font_scale = 0.4
            font_thickness = 1
            
            for i, line in enumerate(lines):
                y_pos = start_y + i * line_spacing
                if y_pos < image.shape[0]:
                    cv2.putText(image, line, (start_x, y_pos), 
                               font, font_scale, (255, 255, 255), 
                               font_thickness, cv2.LINE_AA)
        
        return image