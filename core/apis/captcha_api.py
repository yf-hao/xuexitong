class CaptchaAPI:
    """验证码与滑块相关能力。"""

    def detect_slider_displacement(self, shade_image_bytes: bytes, cutout_image_bytes: bytes) -> int:
        """
        使用 OpenCV 计算滑块缺口偏移量。
        """
        import cv2
        import numpy as np

        # 将 bytes 转换为 numpy 数组并解码为图像
        shade_np = np.frombuffer(shade_image_bytes, np.uint8)
        cutout_np = np.frombuffer(cutout_image_bytes, np.uint8)

        shade_img = cv2.imdecode(shade_np, cv2.IMREAD_GRAYSCALE)
        cutout_img = cv2.imdecode(cutout_np, cv2.IMREAD_GRAYSCALE)

        print(f"DEBUG: detect_slider_displacement shade_img shape: {shade_img.shape if shade_img is not None else 'None'}")
        print(f"DEBUG: detect_slider_displacement cutout_img shape: {cutout_img.shape if cutout_img is not None else 'None'}")

        if shade_img is None or cutout_img is None:
            print("DEBUG: detect_slider_displacement failed due to None image")
            return 0

        def _get_canny(image):
            image = cv2.GaussianBlur(image, (3, 3), 0)
            return cv2.Canny(image, 50, 150)

        # 边缘检测
        shade_canny = _get_canny(shade_img)
        cutout_canny = _get_canny(cutout_img)

        # 模板匹配
        res = cv2.matchTemplate(shade_canny, cutout_canny, cv2.TM_CCOEFF_NORMED)
        # 获取匹配结果
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        # 对标用户 snippet: top_left = max_loc[0]
        print(f"DEBUG: detect_slider_displacement max_val={max_val}, max_loc={max_loc}")
        return max_loc[0]
