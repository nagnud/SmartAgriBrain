from __future__ import annotations

from functools import lru_cache
from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


W, H = 2200, 1240
BG = "#F5F8F7"
INK = "#17363D"
MUTED = "#60757A"
GRID = "#DDE8E5"
TEAL = "#008D79"
CYAN = "#31B7B0"
BLUE = "#397AA7"
CORAL = "#E2684B"
GOLD = "#D5A62E"
WHITE = "#FFFFFF"
PALE_TEAL = "#E4F3EF"
PALE_BLUE = "#E5EFF7"
PALE_CORAL = "#F9EAE5"
PALE_GOLD = "#F7F0D9"


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


def canvas(kicker: str, title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    for x in range(70, W, 80):
        draw.line((x, 0, x, H), fill=GRID, width=1)
    for y in range(70, H, 80):
        draw.line((0, y, W, y), fill=GRID, width=1)
    draw.rectangle((0, 0, W, 190), fill="#F8FBFA")
    draw.rounded_rectangle((92, 38, 410, 82), radius=20, fill=INK)
    draw.text((251, 59), kicker, font=ft(20, True), fill=WHITE, anchor="mm")
    draw.text((92, 104), title, font=ft(48, True), fill=INK, anchor="la")
    draw.text((92, 158), subtitle, font=ft(24), fill=MUTED, anchor="la")
    draw.line((92, 188, W - 92, 188), fill="#B8CFCA", width=2)
    return image, draw


def shadow_box(image: Image.Image, xy, fill=WHITE, outline="#B5CBC6", radius=20, width=2):
    x1, y1, x2, y2 = xy
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((x1 + 8, y1 + 12, x2 + 8, y2 + 12), radius=radius, fill=(20, 54, 61, 28))
    layer = layer.filter(ImageFilter.GaussianBlur(8))
    image.paste(layer, (0, 0), layer)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    return draw


def chip(draw, xy, text: str, fill=PALE_TEAL, color=INK):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=18, fill=fill)
    draw.text(((x1 + x2) / 2, (y1 + y2) / 2), text, font=ft(18, True), fill=color, anchor="mm")


def label(draw, xy, title: str, lines: list[str], accent=TEAL, fill=WHITE, title_size=29, body_size=22):
    shadow_box(draw._image, xy, fill=fill, outline="#AFC5C1")
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle((x1, y1, x1 + 12, y2), radius=6, fill=accent)
    draw.text((x1 + 38, y1 + 34), title, font=ft(title_size, True), fill=INK, anchor="la")
    y = y1 + 87
    for line in lines:
        draw.text((x1 + 38, y), line, font=ft(body_size), fill=MUTED, anchor="la")
        y += body_size + 18


def arrow(draw, points, color=TEAL, width=6, head=18):
    draw.line(points, fill=color, width=width, joint="curve")
    (x1, y1), (x2, y2) = points[-2], points[-1]
    angle = __import__("math").atan2(y2 - y1, x2 - x1)
    left = (x2 - head * cos(angle - pi / 6), y2 - head * sin(angle - pi / 6))
    right = (x2 - head * cos(angle + pi / 6), y2 - head * sin(angle + pi / 6))
    draw.polygon([(x2, y2), left, right], fill=color)


def footer(draw, text: str):
    draw.line((92, 1170, W - 92, 1170), fill="#B8CFCA", width=2)
    draw.text((92, 1200), text, font=ft(20), fill=MUTED, anchor="la")
    draw.text((W - 92, 1200), "SMARTAGRIBRAIN / SYSTEM DESIGN", font=ft(17, True), fill="#84979B", anchor="ra")


def save(image: Image.Image, path: Path):
    image.resize((W, H), Image.Resampling.LANCZOS).save(path, optimize=True)


def architecture(path: Path):
    image, draw = canvas("SYSTEM ARCHITECTURE", "端到端系统架构", "现场感知、云端服务与多终端交互的职责边界")
    x_positions = [95, 515, 935, 1355, 1775]
    titles = ["家庭现场层", "边缘接入层", "消息与服务层", "数据与智能层", "用户交互层"]
    colors = [TEAL, BLUE, TEAL, CORAL, GOLD]
    fills = [PALE_TEAL, PALE_BLUE, PALE_TEAL, PALE_CORAL, PALE_GOLD]
    bodies = [
        ["DHT11 / BH1750 / JW01", "补光灯 / 二维水枪", "PC外接摄像头"],
        ["普通ESP32", "ESP32-C5终端", "本地失效安全"],
        ["EMQX MQTT TLS", "FastAPI领域服务", "REST / SSE"],
        ["SQLite / 知识库", "视觉 / 天气", "大模型 / ASR / TTS"],
        ["Vue Web管理端", "C5屏幕与语音", "家庭用户"],
    ]
    for x, title, color, fill, lines in zip(x_positions, titles, colors, fills, bodies):
        label(draw, (x, 315, x + 330, 655), title, lines, accent=color, fill=fill, title_size=27, body_size=20)
    for index in range(4):
        arrow(draw, [(x_positions[index] + 330, 455), (x_positions[index + 1], 455)], colors[index])
        arrow(draw, [(x_positions[index + 1], 555), (x_positions[index] + 330, 555)], "#5D8793", width=4, head=15)
    chip(draw, (550, 750, 830, 804), "MQTT QoS 1")
    chip(draw, (960, 750, 1240, 804), "统一领域数据", PALE_BLUE)
    chip(draw, (1370, 750, 1650, 804), "REST + SSE", PALE_CORAL)
    shadow_box(image, (235, 880, 1965, 1080), fill=WHITE)
    draw.text((285, 925), "关键约束", font=ft(27, True), fill=INK)
    constraints = [
        ("浏览器不直连Broker", TEAL),
        ("后端是命令唯一发布者", BLUE),
        ("设备ACK确认输出已应用", CORAL),
        ("C5不直接驱动现场GPIO", GOLD),
    ]
    x = 520
    for text, color in constraints:
        draw.ellipse((x - 18, 990 - 18, x + 18, 990 + 18), fill=color)
        draw.text((x + 30, 990), text, font=ft(22, True), fill=INK, anchor="lm")
        x += 390
    footer(draw, "双MCU分工使实时执行、语音显示和云端智能相互解耦。")
    save(image, path)


def message_flow(path: Path):
    image, draw = canvas("DATA & CONTROL FLOW", "遥测与控制双向时序", "message_id用于遥测去重，command_id贯穿命令、回执和页面状态")
    lanes = [(180, "普通ESP32"), (650, "EMQX"), (1120, "FastAPI / SQLite"), (1700, "Web / C5")]
    for x, name in lanes:
        draw.rounded_rectangle((x - 145, 245, x + 145, 315), radius=16, fill=INK)
        draw.text((x, 280), name, font=ft(24, True), fill=WHITE, anchor="mm")
        draw.line((x, 315, x, 1090), fill="#9AB4AF", width=3)
    events = [
        (400, 180, 650, "01  telemetry / 每5秒 / QoS 1", TEAL),
        (505, 650, 1120, "02  校验 · 去重 · 持久化", BLUE),
        (610, 1120, 1700, "03  SSE telemetry / REST state", TEAL),
        (760, 1700, 1120, "04  用户确认后的REST控制", CORAL),
        (865, 1120, 650, "05  command / QoS 1 / retain=false", CORAL),
        (970, 650, 180, "06  精确Topic接收并执行", BLUE),
    ]
    for y, x1, x2, text, color in events:
        arrow(draw, [(x1, y), (x2, y)], color, width=7)
        draw.rounded_rectangle(((x1 + x2) / 2 - 205, y - 42, (x1 + x2) / 2 + 205, y - 5), radius=14, fill=BG)
        draw.text(((x1 + x2) / 2, y - 24), text, font=ft(19, True), fill=INK, anchor="mm")
    draw.arc((310, 995, 1570, 1160), 0, 180, fill=GOLD, width=5)
    draw.text((940, 1085), "07  command_ack沿反向链路返回最终状态", font=ft(21, True), fill=INK, anchor="mm")
    footer(draw, "发布成功不等于硬件成功；Web只有收到匹配ACK后才能显示终态。")
    save(image, path)


def watergun(path: Path):
    image, draw = canvas("FAIL-SAFE ACTUATION", "二维水枪安全执行状态机", "目标变化先停泵，舵机稳定后开泵；异常路径统一回到安全关闭")
    steps = [
        ("01", "接收与拼包", "精确Topic / 完整JSON"),
        ("02", "协议校验", "ID / 有效期 / 范围 / 序号"),
        ("03", "GPIO26停泵", "先关闭水路"),
        ("04", "位置映射", "方位→水平 / 距离→俯仰"),
        ("05", "双轴转向", "GPIO27 + GPIO13"),
        ("06", "稳定等待", "非阻塞800 ms"),
        ("07", "建立保护", "定时截止 / 动态3秒"),
        ("08", "开泵并ACK", "返回实际PWM"),
    ]
    left, top = 110, 300
    box_w, box_h, gap = 455, 165, 58
    for i, (num, title, desc) in enumerate(steps):
        row, col = divmod(i, 4)
        if row == 1:
            col = 3 - col
        x = left + col * (box_w + gap)
        y = top + row * 350
        fill = PALE_TEAL if i < 3 else PALE_BLUE if i < 6 else PALE_GOLD
        accent = TEAL if i < 3 else BLUE if i < 6 else GOLD
        shadow_box(image, (x, y, x + box_w, y + box_h), fill=fill)
        draw.rounded_rectangle((x + 22, y + 22, x + 92, y + 72), radius=16, fill=accent)
        draw.text((x + 57, y + 47), num, font=ft(20, True), fill=WHITE, anchor="mm")
        draw.text((x + 115, y + 43), title, font=ft(28, True), fill=INK, anchor="la")
        draw.text((x + 28, y + 115), desc, font=ft(20), fill=MUTED, anchor="la")
        if row == 0 and col < 3:
            arrow(draw, [(x + box_w + 10, y + box_h / 2), (x + box_w + gap - 10, y + box_h / 2)], accent, width=5, head=15)
        elif row == 0:
            arrow(draw, [(x + box_w / 2, y + box_h + 10), (x + box_w / 2, y + 295)], CORAL, width=5, head=15)
        elif col > 0:
            arrow(draw, [(x - 10, y + box_h / 2), (x - gap + 10, y + box_h / 2)], accent, width=5, head=15)
    shadow_box(image, (245, 905, 1955, 1090), fill=PALE_CORAL, outline="#E4B2A5")
    draw.text((295, 950), "FAIL-SAFE", font=ft(22, True), fill=CORAL)
    draw.text((295, 1005), "网络断开  ·  命令过期  ·  动态超时  ·  定时结束  ·  参数非法", font=ft(27, True), fill=INK)
    arrow(draw, [(1750, 1005), (1910, 1005)], CORAL, width=6)
    draw.text((1900, 1045), "GPIO26 = 0", font=ft(22, True), fill=CORAL, anchor="ra")
    footer(draw, "executed ACK表示控制输出已应用，不等于水流、真实角度或命中结果已验证。")
    save(image, path)


def gpio_map(path: Path):
    image, draw = canvas("EDGE HARDWARE", "普通ESP32硬件与GPIO资源", "传感器采集、补光PWM和二维水枪执行的真实接线边界")
    shadow_box(image, (800, 360, 1400, 900), fill="#173A43", outline="#173A43")
    draw.text((1100, 455), "ESP32", font=ft(62, True), fill=WHITE, anchor="mm")
    draw.text((1100, 520), "PlatformIO: esp32dev", font=ft(23), fill="#BFE6DD", anchor="mm")
    chip(draw, (920, 600, 1280, 655), "MQTT device_id", fill="#2A5962", color=WHITE)
    draw.text((1100, 705), "greenhouse_001_s3", font=ft(23, True), fill=WHITE, anchor="mm")
    draw.text((1100, 790), "LEDC CH0 · CH1 · CH2 · CH3", font=ft(22), fill="#BFE6DD", anchor="mm")
    peripherals = [
        ((90, 290, 650, 470), "GPIO4", "DHT11", ["空气温度 temperature_c", "相对湿度 humidity_pct"], TEAL, PALE_TEAL),
        ((90, 530, 650, 710), "I2C 0x23", "BH1750", ["光照 illuminance_lux", "连续高分辨率模式"], BLUE, PALE_BLUE),
        ((90, 770, 650, 950), "UART", "JW01 CO2", ["二氧化碳 co2_ppm", "串口驱动更新"], GOLD, PALE_GOLD),
        ((1550, 260, 2110, 440), "GPIO14", "补光灯", ["1 kHz · 8 bit · CH0", "协议范围 0..90%"], TEAL, PALE_TEAL),
        ((1550, 500, 2110, 680), "GPIO26", "水泵 / 水枪", ["1 kHz · 8 bit · CH1", "协议范围 0..100%"], CORAL, PALE_CORAL),
        ((1550, 740, 2110, 920), "GPIO27 / 13", "双SG90云台", ["50 Hz · 16 bit · CH2/3", "水平0..180° · 俯仰5..60°"], BLUE, PALE_BLUE),
    ]
    for xy, pin, title, lines, accent, fill in peripherals:
        shadow_box(image, xy, fill=fill)
        x1, y1, x2, y2 = xy
        chip(draw, (x1 + 24, y1 + 25, x1 + 175, y1 + 70), pin, fill=accent, color=WHITE)
        draw.text((x1 + 205, y1 + 48), title, font=ft(27, True), fill=INK, anchor="lm")
        draw.text((x1 + 28, y1 + 112), lines[0], font=ft(20), fill=MUTED)
        draw.text((x1 + 28, y1 + 148), lines[1], font=ft(20), fill=MUTED)
        if x1 < 800:
            arrow(draw, [(x2, (y1 + y2) / 2), (800, (y1 + y2) / 2)], accent, width=5, head=15)
        else:
            arrow(draw, [(1400, (y1 + y2) / 2), (x1, (y1 + y2) / 2)], accent, width=5, head=15)
    footer(draw, "舵机使用独立稳定5 V并与ESP32共地；水泵与灯必须经过驱动模块，不能由GPIO直接带载。")
    save(image, path)


def coordinates(path: Path):
    image, draw = canvas("KINEMATIC MAPPING", "喷水位置与双舵机角度关系", "Web目标使用方位和地面距离；端侧映射后仍受机械与水路标定影响")
    shadow_box(image, (85, 260, 1080, 1100), fill=WHITE)
    shadow_box(image, (1120, 260, 2115, 1100), fill=WHITE)
    draw.text((145, 320), "A  水平方位映射", font=ft(30, True), fill=INK)
    center = (580, 830)
    radius = 390
    draw.arc((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), 180, 360, fill="#9BBDB6", width=5)
    draw.line((center[0] - radius, center[1], center[0] + radius, center[1]), fill="#9BBDB6", width=3)
    for bearing, servo, color in [(-90, 0, BLUE), (-45, 45, TEAL), (0, 90, CORAL), (45, 135, TEAL), (90, 180, BLUE)]:
        angle = pi + (bearing + 90) / 180 * pi
        x = center[0] + radius * cos(angle)
        y = center[1] + radius * sin(angle)
        draw.line((center[0], center[1], x, y), fill=color, width=5)
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=color)
        draw.text((x, y - 34), f"{bearing}° → {servo}°", font=ft(19, True), fill=INK, anchor="mm")
    draw.ellipse((center[0] - 30, center[1] - 30, center[0] + 30, center[1] + 30), fill=INK)
    draw.text((center[0], center[1] + 70), "水枪原点 / 0°正前方", font=ft(21, True), fill=MUTED, anchor="mm")
    draw.text((1180, 320), "B  垂直距离映射", font=ft(30, True), fill=INK)
    base_y = 900
    draw.line((1250, base_y, 2000, base_y), fill="#8EA6A2", width=5)
    draw.ellipse((1300, base_y - 30, 1360, base_y + 30), fill=INK)
    draw.text((1330, base_y + 65), "喷嘴", font=ft(20, True), fill=MUTED, anchor="mm")
    samples = [(300, 60, CORAL), (600, 42, GOLD), (900, 23, TEAL), (1200, 5, BLUE)]
    for idx, (distance, angle_deg, color) in enumerate(samples):
        x2 = 1480 + idx * 165
        y2 = base_y - 460 + idx * 110
        arrow(draw, [(1330, base_y), (x2, y2)], color, width=5, head=14)
        draw.rounded_rectangle((x2 - 90, y2 - 72, x2 + 90, y2 - 20), radius=14, fill=color)
        draw.text((x2, y2 - 46), f"{distance} mm → {angle_deg}°", font=ft(18, True), fill=WHITE, anchor="mm")
    draw.text((1615, 1010), "距离增加100 mm，当前线性模型约降低6.11°", font=ft(21, True), fill=INK, anchor="mm")
    footer(draw, "水平映射保持不变；垂直5°为平射、60°为竖直向上，落点仍需结合水压和安装高度标定。")
    save(image, path)


def mqtt_topics(path: Path):
    image, draw = canvas("MQTT CONTRACT", "EMQX五类Topic与触发机制", "只有telemetry固定周期发送；状态、能力、命令与ACK均由事件触发")
    shadow_box(image, (815, 315, 1385, 920), fill="#173A43", outline="#173A43")
    draw.text((1100, 410), "EMQX", font=ft(58, True), fill=WHITE, anchor="mm")
    draw.text((1100, 475), "MQTT 3.1.1 / TLS 8883", font=ft(23), fill="#BFE6DD", anchor="mm")
    draw.text((1100, 580), "smartagribrain/v1", font=ft(26, True), fill=WHITE, anchor="mm")
    draw.text((1100, 630), "/devices/{device_id}", font=ft(22), fill="#BFE6DD", anchor="mm")
    chip(draw, (930, 740, 1270, 800), "QoS 1 · 持久会话", fill="#2A5962", color=WHITE)
    topics = [
        ("telemetry", "ESP32 → 后端", "每5秒", "retain=false", TEAL, 255),
        ("status", "ESP32 / LWT → 后端", "连接、重连、异常断开", "retain=true", BLUE, 430),
        ("capabilities", "ESP32 → 后端", "连接或重连", "retain=true", GOLD, 605),
        ("command", "后端 → ESP32", "用户确认或策略触发", "retain=false", CORAL, 780),
        ("command_ack", "ESP32 → 后端", "每条命令最终结果", "retain=false", TEAL, 955),
    ]
    for index, (name, direction, trigger, retain, color, y) in enumerate(topics, 1):
        left_side = index <= 3
        x1, x2 = (80, 710) if left_side else (1490, 2120)
        shadow_box(image, (x1, y, x2, y + 135), fill=WHITE)
        chip(draw, (x1 + 22, y + 20, x1 + 225, y + 62), f"{index:02d}  {name}", fill=color, color=WHITE)
        draw.text((x1 + 250, y + 42), direction, font=ft(20, True), fill=INK, anchor="lm")
        draw.text((x1 + 28, y + 92), f"触发：{trigger}   ·   {retain}", font=ft(18), fill=MUTED)
        if left_side:
            arrow(draw, [(x2, y + 68), (815, y + 68)], color, width=5, head=14)
        elif name == "command_ack":
            arrow(draw, [(x1, y + 68), (1385, y + 68)], color, width=5, head=14)
        else:
            arrow(draw, [(1385, y + 68), (x1, y + 68)], color, width=5, head=14)
    footer(draw, "Topic确定协议和设备身份，JSON只保留真正变化且执行所需的数据。")
    save(image, path)


def backend_pipeline(path: Path):
    image, draw = canvas("BACKEND DATA PLANE", "FastAPI后端数据处理链路", "MQTT消息进入统一领域服务后，分别形成状态、历史、命令审计和实时事件")
    stages = [
        ("01", "MQTT接入", ["Topic解析", "TLS / QoS 1"], TEAL),
        ("02", "协议校验", ["结构 / 单位", "ID / quality"], BLUE),
        ("03", "领域服务", ["站点聚合", "水枪 / 监控"], TEAL),
        ("04", "SQLite", ["快照 / 历史", "命令 / ACK"], GOLD),
        ("05", "REST + SSE", ["状态读取", "实时事件"], CORAL),
        ("06", "Vue / C5", ["展示 / 确认", "最终状态"], BLUE),
    ]
    x = 80
    for num, title, lines, color in stages:
        shadow_box(image, (x, 355, x + 300, 640), fill=WHITE)
        chip(draw, (x + 25, 382, x + 102, 430), num, fill=color, color=WHITE)
        draw.text((x + 32, 485), title, font=ft(28, True), fill=INK)
        draw.text((x + 32, 545), lines[0], font=ft(20), fill=MUTED)
        draw.text((x + 32, 585), lines[1], font=ft(20), fill=MUTED)
        if x < 1800:
            arrow(draw, [(x + 310, 500), (x + 365, 500)], color, width=5, head=14)
        x += 350
    shadow_box(image, (150, 760, 2050, 1060), fill=WHITE)
    draw.text((205, 815), "SQLite领域数据", font=ft(27, True), fill=INK)
    groups = [
        ("设备事实", "telemetry_records · receipts · presence", TEAL),
        ("站点状态", "site_snapshots · history_samples", BLUE),
        ("控制审计", "device_commands · site_commands", CORAL),
        ("业务知识", "alarms · knowledge · photos · assistant", GOLD),
    ]
    gx = 205
    for title, body, color in groups:
        draw.rounded_rectangle((gx, 875, gx + 420, 1005), radius=18, fill=BG, outline="#C5D6D2", width=2)
        draw.ellipse((gx + 24, 903, gx + 58, 937), fill=color)
        draw.text((gx + 75, 920), title, font=ft(22, True), fill=INK, anchor="lm")
        draw.text((gx + 24, 970), body, font=ft(16), fill=MUTED)
        gx += 455
    footer(draw, "SSE负责降低实时延迟，REST负责断线校准，SQLite负责可恢复的真实状态。")
    save(image, path)


def ai_workflow(path: Path):
    image, draw = canvas("KNOWLEDGE-AUGMENTED AI", "知识库、视觉与大模型协同", "传感器事实、外部知识和模型推断分层进入回答；高风险动作必须经过确认门")
    sources = [
        ("实时环境", "温湿度 / 光照 / CO2", TEAL),
        ("历史趋势", "SQLite时间序列", BLUE),
        ("视觉结果", "摄像头 / 病害图片", CORAL),
        ("知识与天气", "本地知识库 / 外部来源", GOLD),
    ]
    y = 295
    for title, body, color in sources:
        shadow_box(image, (80, y, 560, y + 145), fill=WHITE)
        draw.ellipse((110, y + 46, 158, y + 94), fill=color)
        draw.text((185, y + 52), title, font=ft(24, True), fill=INK)
        draw.text((185, y + 95), body, font=ft(18), fill=MUTED)
        arrow(draw, [(560, y + 72), (760, 610)], color, width=4, head=13)
        y += 190
    shadow_box(image, (760, 390, 1270, 850), fill=PALE_TEAL)
    draw.text((1015, 475), "Assistant Orchestrator", font=ft(30, True), fill=INK, anchor="mm")
    draw.text((1015, 535), "上下文标准化", font=ft(22), fill=MUTED, anchor="mm")
    draw.text((1015, 585), "知识检索与来源选择", font=ft(22), fill=MUTED, anchor="mm")
    draw.text((1015, 635), "模型调用与工具编排", font=ft(22), fill=MUTED, anchor="mm")
    draw.text((1015, 685), "候选动作结构化", font=ft(22), fill=MUTED, anchor="mm")
    chip(draw, (865, 745, 1165, 800), "证据 · 风险 · 动作", fill=TEAL, color=WHITE)
    arrow(draw, [(1270, 520), (1480, 520)], BLUE, width=6)
    shadow_box(image, (1480, 330, 2100, 620), fill=PALE_BLUE)
    draw.text((1790, 405), "云端模型与语音", font=ft(28, True), fill=INK, anchor="mm")
    draw.text((1790, 468), "DeepSeek · ASR · TTS", font=ft(23), fill=MUTED, anchor="mm")
    draw.text((1790, 535), "回答 / 分析 / 参数补问", font=ft(22), fill=MUTED, anchor="mm")
    arrow(draw, [(1790, 620), (1790, 760)], CORAL, width=6)
    shadow_box(image, (1480, 760, 2100, 1045), fill=PALE_CORAL, outline="#E4B2A5")
    draw.text((1790, 830), "用户确认门", font=ft(30, True), fill=CORAL, anchor="mm")
    draw.text((1790, 895), "知识回答 → 直接返回", font=ft(21), fill=INK, anchor="mm")
    draw.text((1790, 945), "补光 / 水枪 → 确认后生成命令", font=ft(21, True), fill=INK, anchor="mm")
    draw.text((1790, 995), "设备ACK → 最终执行状态", font=ft(21), fill=MUTED, anchor="mm")
    footer(draw, "大模型不直接写GPIO；建议、确认、执行和回执形成可审计闭环。")
    save(image, path)


def generate_all(asset_dir: Path) -> dict[str, Path]:
    asset_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "architecture": asset_dir / "architecture-premium.png",
        "message": asset_dir / "message-flow-premium.png",
        "watergun": asset_dir / "watergun-state-premium.png",
        "gpio": asset_dir / "gpio-map-premium.png",
        "coordinates": asset_dir / "coordinate-map-premium.png",
        "mqtt": asset_dir / "mqtt-topics-premium.png",
        "backend": asset_dir / "backend-pipeline-premium.png",
        "ai": asset_dir / "ai-workflow-premium.png",
    }
    architecture(outputs["architecture"])
    message_flow(outputs["message"])
    watergun(outputs["watergun"])
    gpio_map(outputs["gpio"])
    coordinates(outputs["coordinates"])
    mqtt_topics(outputs["mqtt"])
    backend_pipeline(outputs["backend"])
    ai_workflow(outputs["ai"])
    return outputs


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".tmp/design-doc-assets-premium")
    result = generate_all(target)
    for key, value in result.items():
        print(f"{key}={value}")
