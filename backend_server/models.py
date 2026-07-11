from sqlalchemy import Column, Integer, Float, String
from database import Base


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    timestamp = Column(Integer)

    # 传感器核心数据
    temperature = Column(Float)
    humidity = Column(Float)
    pressure = Column(Float)
    gas_resistance = Column(Float)

    # 设备状态数据
    wifi_status = Column(String)
    mqtt_status = Column(String)
    fan_status = Column(Integer)