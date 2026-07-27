from __future__ import annotations

from functools import lru_cache
from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


W, H = 2200, 1240
INK = "#17383E"
MUTED = "#667C80"
TEAL = "#008E79"
BLUE = "#3278A5"
CORAL = "#E56A4B"
GOLD = "#D8A525"
MINT = "#DDEFEA"
SKY = "#DFEAF3"
PEACH = "#F5E4DE"
CREAM = "#F5EDCF"
WHITE = "#FFFFFF"


@lru_cache(maxsize=None)
def ft(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path(r"C:\Windows\Fonts\msyhbd.ttc") if bold else Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size, index=0)
    return ImageFont.load_default()


def fit_photo(path: Path) -> Image.Image:
    return ImageOps.fit(Image.open(path).convert("RGB"), (W, H), method=Image.Resampling.LANCZOS)


def alpha_panel(image: Image.Image, xy, fill=(255, 255, 255, 220), radius=24):
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(xy, radius=radius, fill=fill)
    image.paste(layer, (0, 0), layer)


def arrow(draw: ImageDraw.ImageDraw, p1, p2, color=TEAL, width=6, head=18):
    draw.line((p1, p2), fill=color, width=width)
    angle = __import__("math").atan2(p2[1] - p1[1], p2[0] - p1[0])
    left = (p2[0] - head * cos(angle - pi / 6), p2[1] - head * sin(angle - pi / 6))
    right = (p2[0] - head * cos(angle + pi / 6), p2[1] - head * sin(angle + pi / 6))
    draw.polygon((p2, left, right), fill=color)


def title(draw, title: str, subtitle: str, dark=False):
    color = WHITE if dark else INK
    muted = "#D7E4E2" if dark else MUTED
    draw.text((90, 70), title, font=ft(48, True), fill=color)
    draw.text((92, 135), subtitle, font=ft(23), fill=muted)


def save(image: Image.Image, path: Path):
    image.save(path, optimize=True)


def architecture(path: Path):
    image = Image.new("RGB", (W, H), "#F7F4EE")
    draw = ImageDraw.Draw(image)
    title(draw, "SmartAgriBrain系统剖面", "从家庭现场到用户交互的五层职责与双向信息流")
    bands = [
        (TEAL, "01  家庭现场", "DHT11 / BH1750 / JW01   ·   补光灯   ·   二维水枪   ·   PC摄像头"),
        (BLUE, "02  边缘终端", "普通ESP32采集执行   ·   ESP32-C5语音显示   ·   端侧失效安全"),
        ("#4D9B8E", "03  消息服务", "EMQX MQTT TLS   ·   FastAPI领域服务   ·   REST / SSE"),
        (CORAL, "04  数据智能", "SQLite   ·   知识库   ·   视觉 / 天气   ·   大模型 / ASR / TTS"),
        (GOLD, "05  用户交互", "Vue Web管理端   ·   C5屏幕与语音   ·   家庭用户"),
    ]
    top = 250
    for index, (color, heading, body) in enumerate(bands):
        y1 = top + index * 165
        y2 = y1 + 120
        wave = [(70, y1), (340, y1 - 14), (650, y1 + 16), (960, y1 - 10), (1280, y1 + 14), (1630, y1 - 12), (2130, y1)]
        lower = [(x, y + 120) for x, y in reversed(wave)]
        draw.polygon(wave + lower, fill=color)
        draw.text((120, y1 + 48), heading, font=ft(27, True), fill=WHITE)
        draw.text((520, y1 + 52), body, font=ft(21), fill=WHITE)
        if index < len(bands) - 1:
            arrow(draw, (2030, y2 + 3), (2030, y2 + 45), "#7D918E", width=4, head=13)
    draw.text((105, 1125), "上行：遥测、状态、能力与知识上下文", font=ft(21, True), fill=TEAL)
    draw.text((2095, 1125), "下行：用户意图、命令、回复与确认", font=ft(21, True), fill=CORAL, anchor="ra")
    save(image, path)


def message_flow(path: Path):
    image = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(image)
    title(draw, "真实遥测与控制时序", "四条泳道展示从采样到ACK的完整闭环；时间由上向下推进")
    lanes = [(170, 455, "普通ESP32", "#E8F2EF"), (560, 845, "EMQX", "#EDF2F6"),
             (950, 1420, "FastAPI / SQLite", "#F9ECE7"), (1530, 2070, "Web / C5", "#F8F0D8")]
    for x1, x2, name, fill in lanes:
        draw.rounded_rectangle((x1, 230, x2, 1120), radius=28, fill=fill)
        draw.text(((x1 + x2) / 2, 285), name, font=ft(26, True), fill=INK, anchor="mm")
        draw.line(((x1 + x2) / 2, 335, (x1 + x2) / 2, 1080), fill="#A8BAB7", width=3)
    centers = [(x1 + x2) / 2 for x1, x2, _, _ in lanes]
    events = [
        (410, 0, 1, "telemetry · 每5秒 · QoS 1", TEAL),
        (520, 1, 2, "校验 / UUID去重 / 持久化", BLUE),
        (630, 2, 3, "SSE实时事件 + REST状态", TEAL),
        (770, 3, 2, "用户确认后的控制请求", CORAL),
        (880, 2, 1, "command · QoS 1 · 不保留", CORAL),
        (990, 1, 0, "设备校验并执行", BLUE),
    ]
    for step, (y, src, dst, text, color) in enumerate(events, 1):
        arrow(draw, (centers[src], y), (centers[dst], y), color, width=7)
        mid = (centers[src] + centers[dst]) / 2
        draw.ellipse((mid - 23, y - 50, mid + 23, y - 4), fill=color)
        draw.text((mid, y - 27), str(step), font=ft(18, True), fill=WHITE, anchor="mm")
        draw.text((mid, y + 24), text, font=ft(19, True), fill=INK, anchor="mm")
    draw.rounded_rectangle((585, 1090, 1510, 1170), radius=30, fill=INK)
    draw.text((1048, 1130), "07  command_ack反向返回：executed / rejected / timeout", font=ft(22, True), fill=WHITE, anchor="mm")
    save(image, path)


def coordinates(path: Path):
    image = Image.new("RGB", (W, H), "#F4F1E8")
    draw = ImageDraw.Draw(image)
    title(draw, "目标位置与双舵机运动学", "左侧为水平方位，右侧为距离到俯仰角的当前线性控制模型")
    draw.line((1100, 220, 1100, 1130), fill="#C8C0B0", width=3)
    draw.text((110, 255), "平面视图 / PAN", font=ft(28, True), fill=INK)
    c = (555, 860)
    r = 410
    draw.arc((c[0] - r, c[1] - r, c[0] + r, c[1] + r), 180, 360, fill="#8CA8A1", width=7)
    draw.line((c[0] - r, c[1], c[0] + r, c[1]), fill="#8CA8A1", width=4)
    for bearing, servo, color in [(-90, 0, BLUE), (-45, 45, TEAL), (0, 90, CORAL), (45, 135, TEAL), (90, 180, BLUE)]:
        angle = pi + (bearing + 90) / 180 * pi
        p = (c[0] + r * cos(angle), c[1] + r * sin(angle))
        draw.line((c, p), fill=color, width=5)
        draw.ellipse((p[0] - 11, p[1] - 11, p[0] + 11, p[1] + 11), fill=color)
        draw.text((p[0], p[1] - 40), f"{bearing}° / {servo}°", font=ft(19, True), fill=INK, anchor="mm")
    draw.ellipse((c[0] - 34, c[1] - 34, c[0] + 34, c[1] + 34), fill=INK)
    draw.text((c[0], 940), "0°正前方 → 水平舵机90°", font=ft(22, True), fill=INK, anchor="mm")
    draw.text((1170, 255), "侧视图 / TILT", font=ft(28, True), fill=INK)
    origin = (1300, 900)
    draw.line((1215, 900, 2070, 900), fill="#8CA8A1", width=5)
    draw.ellipse((origin[0] - 28, origin[1] - 28, origin[0] + 28, origin[1] + 28), fill=INK)
    for distance, angle_deg, endpoint, color in [
        (300, 60, (1450, 410), CORAL), (600, 42, (1640, 520), GOLD),
        (900, 23, (1840, 670), TEAL), (1200, 5, (2050, 805), BLUE)
    ]:
        arrow(draw, origin, endpoint, color, width=6, head=16)
        draw.rounded_rectangle((endpoint[0] - 90, endpoint[1] - 66, endpoint[0] + 90, endpoint[1] - 16), radius=15, fill=color)
        draw.text((endpoint[0], endpoint[1] - 41), f"{distance} mm → {angle_deg}°", font=ft(18, True), fill=WHITE, anchor="mm")
    draw.text((1655, 1015), "5°平射   ·   60°竖直向上   ·   每100 mm约降低6.11°", font=ft(20, True), fill=INK, anchor="mm")
    draw.text((110, 1165), "说明：该图是软件控制映射，不代表实际水流弹道；最终落点需结合喷嘴高度、泵压和结构标定。", font=ft(20), fill=MUTED)
    save(image, path)


def mqtt_topics(path: Path):
    image = Image.new("RGB", (W, H), "#F7F8F6")
    draw = ImageDraw.Draw(image)
    title(draw, "EMQX五类Topic放射图", "中心为云端Broker；圆周位置表达方向、触发方式和保留策略")
    center = (1100, 620)
    rings = [220, 350]
    for r in rings:
        draw.ellipse((center[0] - r, center[1] - r, center[0] + r, center[1] + r), outline="#CBD8D4", width=3)
    draw.ellipse((885, 405, 1315, 835), fill=INK)
    draw.text(center, "EMQX", font=ft(60, True), fill=WHITE, anchor="mm")
    draw.text((1100, 690), "MQTT 3.1.1 / TLS 8883", font=ft(21), fill="#CEE0DC", anchor="mm")
    topics = [
        ("telemetry", "每5秒 / 不保留", -150, TEAL, "ESP32 → 后端"),
        ("status", "连接 / LWT / 保留", -78, BLUE, "ESP32 → 后端"),
        ("capabilities", "连接或重连 / 保留", -6, GOLD, "ESP32 → 后端"),
        ("command", "按需 / 不保留", 66, CORAL, "后端 → ESP32"),
        ("command_ack", "每条命令终态", 138, TEAL, "ESP32 → 后端"),
    ]
    for index, (name, meta, angle_deg, color, direction) in enumerate(topics, 1):
        angle = angle_deg * pi / 180
        p = (center[0] + 405 * cos(angle), center[1] + 405 * sin(angle))
        q = (center[0] + 235 * cos(angle), center[1] + 235 * sin(angle))
        if name == "command":
            arrow(draw, q, p, color, width=7)
        else:
            arrow(draw, p, q, color, width=7)
        draw.ellipse((p[0] - 135, p[1] - 135, p[0] + 135, p[1] + 135), fill=WHITE, outline=color, width=8)
        draw.text((p[0], p[1] - 48), f"{index:02d}", font=ft(20, True), fill=color, anchor="mm")
        draw.text((p[0], p[1] - 5), name, font=ft(23, True), fill=INK, anchor="mm")
        draw.text((p[0], p[1] + 38), direction, font=ft(17, True), fill=MUTED, anchor="mm")
        draw.text((p[0], p[1] + 70), meta, font=ft(16), fill=MUTED, anchor="mm")
    draw.text((1100, 1165), "全部业务Topic使用QoS 1；只有status和capabilities保留，command永不保留。", font=ft(21, True), fill=INK, anchor="mm")
    save(image, path)


def annotate_gpio(asset_dir: Path, path: Path):
    image = fit_photo(asset_dir / "gpio-realistic-base.png")
    draw = ImageDraw.Draw(image)
    alpha_panel(image, (1120, 45, 2140, 185), fill=(255, 255, 255, 225))
    draw = ImageDraw.Draw(image)
    draw.text((1160, 72), "定制控制PCB与GPIO功能分区", font=ft(36, True), fill=INK)
    draw.text((1162, 130), "依据实际PCB设计适度立体化，接口定义以工程代码和实物复核为准", font=ft(18), fill=MUTED)
    alpha_panel(image, (55, 905, 2145, 1185), fill=(18, 49, 55, 225))
    draw = ImageDraw.Draw(image)
    items = [
        ("GPIO4", "DHT11温湿度", TEAL), ("GPIO14", "补光灯PWM", GOLD),
        ("GPIO26", "水泵PWM", CORAL), ("GPIO27", "水平SG90", BLUE),
        ("GPIO13", "垂直SG90", TEAL), ("I2C / UART", "BH1750 / JW01", BLUE),
    ]
    x = 90
    for pin, name, color in items:
        draw.rounded_rectangle((x, 945, x + 310, 1025), radius=22, fill=color)
        draw.text((x + 155, 985), pin, font=ft(20, True), fill=WHITE, anchor="mm")
        draw.text((x + 155, 1070), name, font=ft(19, True), fill=WHITE, anchor="mm")
        x += 340
    draw.text((90, 1142), "舵机独立稳定5 V供电并与ESP32共地；水泵和补光灯必须经过驱动模块。", font=ft(20, True), fill="#D8E6E3")
    save(image, path)


def annotate_watergun(asset_dir: Path, path: Path):
    image = fit_photo(asset_dir / "watergun-realistic-base.png")
    draw = ImageDraw.Draw(image)
    alpha_panel(image, (55, 45, 1010, 175), fill=(255, 255, 255, 225))
    draw = ImageDraw.Draw(image)
    draw.text((90, 72), "二维水枪执行机构", font=ft(40, True), fill=INK)
    draw.text((92, 130), "依据实拍结构美化重构，保留双SG90、金属喷嘴、热熔胶与透明软管", font=ft(18), fill=MUTED)
    callouts = [
        ((895, 155), (390, 260), "金属喷嘴与固定胶", GOLD),
        ((1425, 505), (1760, 350), "垂直轴 / GPIO13", TEAL),
        ((1265, 865), (620, 680), "水平轴 / GPIO27", BLUE),
        ((1980, 515), (1840, 650), "透明输水软管", CORAL),
    ]
    for source, target, text, color in callouts:
        draw.line((source, target), fill=color, width=5)
        draw.ellipse((source[0] - 10, source[1] - 10, source[0] + 10, source[1] + 10), fill=color)
        w = 300
        x1 = target[0] - w / 2
        draw.rounded_rectangle((x1, target[1] - 30, x1 + w, target[1] + 30), radius=18, fill=(255, 255, 255), outline=color, width=4)
        draw.text((target[0], target[1]), text, font=ft(19, True), fill=INK, anchor="mm")
    alpha_panel(image, (135, 1000, 2065, 1180), fill=(20, 49, 55, 225))
    draw = ImageDraw.Draw(image)
    steps = [("1", "停泵"), ("2", "双轴转向"), ("3", "等待800 ms"), ("4", "建立保护后开泵")]
    x = 240
    for index, (num, text) in enumerate(steps):
        color = [CORAL, BLUE, GOLD, TEAL][index]
        draw.ellipse((x, 1040, x + 58, 1098), fill=color)
        draw.text((x + 29, 1069), num, font=ft(20, True), fill=WHITE, anchor="mm")
        draw.text((x + 80, 1069), text, font=ft(21, True), fill=WHITE, anchor="lm")
        if index < 3:
            arrow(draw, (x + 330, 1069), (x + 405, 1069), "#AFC3BF", width=4, head=13)
        x += 455
    draw.text((220, 1145), "网络断开、命令过期、动态超时或定时结束时统一执行 GPIO26 = 0。", font=ft(18), fill="#D6E5E2")
    save(image, path)


def backend_pipeline(path: Path):
    image = Image.new("RGB", (W, H), "#FBFAF6")
    draw = ImageDraw.Draw(image)
    title(draw, "FastAPI数据河流", "不同颜色的数据带汇入领域服务，再分流到存储、实时事件与智能能力")
    sources = [
        (300, "telemetry", TEAL, 360), (470, "status / capabilities", BLUE, 440),
        (640, "command_ack", CORAL, 520), (810, "Web / C5请求", GOLD, 600),
    ]
    for y, text, color, target_y in sources:
        draw.text((90, y), text, font=ft(23, True), fill=INK)
        draw.rounded_rectangle((90, y + 45, 430, y + 75), radius=15, fill=color)
        polygon = [(430, y + 45), (870, target_y - 32), (870, target_y + 32), (430, y + 75)]
        draw.polygon(polygon, fill=color)
    draw.ellipse((760, 350, 1390, 980), fill=INK)
    draw.text((1075, 500), "FastAPI", font=ft(54, True), fill=WHITE, anchor="mm")
    draw.text((1075, 575), "协议校验", font=ft(23), fill="#D2E1DE", anchor="mm")
    draw.text((1075, 625), "站点 / 水枪 / 监控", font=ft(23), fill="#D2E1DE", anchor="mm")
    draw.text((1075, 675), "助手与视觉编排", font=ft(23), fill="#D2E1DE", anchor="mm")
    outputs = [
        (360, "SQLite持久化", "快照 · 历史 · 命令 · ACK", GOLD),
        (560, "SSE实时事件", "telemetry · command_update", TEAL),
        (760, "REST领域接口", "状态 · 控制 · 知识库", BLUE),
        (960, "外部智能服务", "天气 · 视觉 · 大模型", CORAL),
    ]
    for y, heading, body, color in outputs:
        polygon = [(1390, 610 - 35), (1670, y - 38), (1670, y + 38), (1390, 610 + 35)]
        draw.polygon(polygon, fill=color)
        draw.rounded_rectangle((1670, y - 70, 2110, y + 70), radius=26, fill=WHITE, outline=color, width=5)
        draw.text((1710, y - 18), heading, font=ft(23, True), fill=INK)
        draw.text((1710, y + 27), body, font=ft(17), fill=MUTED)
    draw.text((95, 1155), "SQLite保存真实状态；SSE降低延迟；REST负责恢复；外部服务失败不阻断设备接入与安全控制。", font=ft(20, True), fill=INK)
    save(image, path)


def ai_workflow(path: Path):
    image = Image.new("RGB", (W, H), "#F2F5F1")
    draw = ImageDraw.Draw(image)
    title(draw, "AI证据环与确认门", "事实、知识、推断和物理执行采用不同层级，避免模型直接控制GPIO")
    center = (1030, 700)
    draw.ellipse((530, 200, 1530, 1200), fill="#E1EEE9")
    draw.ellipse((675, 345, 1385, 1055), fill="#DCE8F0")
    nodes = [
        (430, 360, "实时环境", "温湿度 / 光照 / CO2", TEAL),
        (330, 765, "历史趋势", "SQLite时间序列", BLUE),
        (670, 1015, "视觉结果", "摄像头 / 病害图片", CORAL),
        (1330, 1015, "知识与天气", "本地知识库 / 外部来源", GOLD),
        (1630, 680, "云端模型", "回答 / 分析 / 参数补问", BLUE),
        (1440, 300, "语音链路", "ASR / TTS", TEAL),
    ]
    for x, y, heading, body, color in nodes:
        dx = x - center[0]
        dy = y - center[1]
        length = (dx * dx + dy * dy) ** 0.5
        endpoint = (center[0] + dx / length * 225, center[1] + dy / length * 225)
        draw.line(((x, y), endpoint), fill=color, width=4)
        draw.ellipse((x - 115, y - 115, x + 115, y + 115), fill=WHITE, outline=color, width=8)
        draw.text((x, y - 24), heading, font=ft(21, True), fill=INK, anchor="mm")
        draw.text((x, y + 25), body, font=ft(16), fill=MUTED, anchor="mm")
    draw.ellipse((815, 485, 1245, 915), fill=INK)
    draw.text((1030, 645), "Assistant", font=ft(40, True), fill=WHITE, anchor="mm")
    draw.text((1030, 705), "Orchestrator", font=ft(34, True), fill=WHITE, anchor="mm")
    draw.text((1030, 775), "检索 · 工具 · 模型", font=ft(21), fill="#CFE2DE", anchor="mm")
    draw.rounded_rectangle((1620, 850, 2110, 1110), radius=36, fill="#F7E3DC", outline=CORAL, width=5)
    draw.text((1865, 910), "用户确认门", font=ft(30, True), fill=CORAL, anchor="mm")
    draw.text((1865, 975), "知识回答 → 直接返回", font=ft(19), fill=INK, anchor="mm")
    draw.text((1865, 1020), "补光 / 水枪 → 确认后命令", font=ft(19, True), fill=INK, anchor="mm")
    draw.text((1865, 1065), "设备ACK → 最终状态", font=ft(19), fill=MUTED, anchor="mm")
    arrow(draw, (1480, 805), (1670, 890), CORAL, width=7)
    draw.text((95, 1160), "大模型只生成建议或候选动作；后端复核参数，用户确认后才进入MQTT控制链路。", font=ft(20, True), fill=INK)
    save(image, path)


def generate_all(asset_dir: Path) -> dict[str, Path]:
    asset_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "product": asset_dir / "product-realistic.png",
        "modules": asset_dir / "modules-realistic.png",
        "architecture": asset_dir / "architecture-layered.png",
        "message": asset_dir / "message-swimlane.png",
        "coordinates": asset_dir / "coordinate-engineering.png",
        "mqtt": asset_dir / "mqtt-radial.png",
        "gpio": asset_dir / "gpio-annotated-photo.png",
        "watergun": asset_dir / "watergun-annotated-photo.png",
        "backend": asset_dir / "backend-river.png",
        "ai": asset_dir / "ai-evidence-ring.png",
    }
    architecture(outputs["architecture"])
    message_flow(outputs["message"])
    coordinates(outputs["coordinates"])
    mqtt_topics(outputs["mqtt"])
    annotate_gpio(asset_dir, outputs["gpio"])
    annotate_watergun(asset_dir, outputs["watergun"])
    backend_pipeline(outputs["backend"])
    ai_workflow(outputs["ai"])
    return outputs


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".tmp/design-doc-assets-refined")
    result = generate_all(target)
    for key, value in result.items():
        print(f"{key}={value}")
