"""二维码生成：把企微活码 URL 转成 PNG base64，给抖音小程序渲染。"""
import base64
import io
import logging

import qrcode
from qrcode.constants import ERROR_CORRECT_M

logger = logging.getLogger("crm.qrcode")


def gen_qrcode_base64(content: str, box_size: int = 12, border: int = 2) -> str:
    """生成内容的二维码 PNG，返回不带前缀的 base64 字符串。

    抖音小程序渲染时拼接 `data:image/png;base64,{result}` 即可直接当图片 src。
    """
    if not content:
        raise ValueError("content 不能为空")

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


if __name__ == "__main__":
    # 本地调试用：直接跑这个文件会生成 test.png
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "https://work.weixin.qq.com/ca/test"
    b64 = gen_qrcode_base64(target)
    logger.info("生成成功，长度=%d", len(b64))
    with open("test.png", "wb") as f:
        f.write(base64.b64decode(b64))
    print("已写入 test.png")
