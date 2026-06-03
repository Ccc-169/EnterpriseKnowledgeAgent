"""
alarm_api.py — 安全生产监控平台示例后端
启动：python alarm_api.py
     或 uvicorn alarm_api:app --port 8002 --reload
文档：http://localhost:8002/docs

接口列表：
  GET  /api/alarms/count        报警数量统计
  GET  /api/devices/status      设备状态查询
  POST /api/hazard/report       安全隐患上报
  GET  /api/monitor/realtime    传感器实时监测数据
  GET  /api/workorder/stats     工单统计
"""
import random
from datetime import date, datetime, timedelta
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="安全生产监控平台 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 模拟数据（固定随机种子，结果可复现）─────────────────────
random.seed(42)

_LEVEL_LABEL  = {0: "低级", 1: "中级", 2: "高级"}
_AREAS        = ["A区-生产车间", "B区-仓储中心", "C区-化工车间", "D区-供电机房", "E区-污水处理"]
_DEVICE_TYPES = ["气体检测仪", "烟雾探测器", "温压传感器", "噪音监测仪", "视频监控"]
_DEV_STATUSES = ["online", "warning", "fault", "offline"]
_METRICS_CFG  = {
    "co":          {"unit": "ppm", "normal": (0, 25),   "warn": (25, 50),   "danger": (50, 200)},
    "temperature": {"unit": "℃",  "normal": (18, 35),  "warn": (35, 45),   "danger": (45, 80)},
    "humidity":    {"unit": "%RH", "normal": (40, 70),  "warn": (70, 85),   "danger": (85, 100)},
    "pressure":    {"unit": "kPa", "normal": (96, 106), "warn": (106, 115), "danger": (115, 130)},
    "noise":       {"unit": "dB",  "normal": (40, 80),  "warn": (80, 100),  "danger": (100, 130)},
}
_WO_TYPES     = ["inspection", "maintenance", "repair"]
_WO_STATUSES  = ["pending", "processing", "closed"]
_WO_T_LABEL   = {"inspection": "巡检", "maintenance": "维保", "repair": "维修"}
_WO_S_LABEL   = {"pending": "待处理", "processing": "处理中", "closed": "已关闭"}


def _gen_alarms(n=600):
    base = date(2025, 1, 1)
    return [{"date": base + timedelta(days=random.randint(0, 364)), "level": random.randint(0, 2)}
            for _ in range(n)]


def _gen_devices(n=40):
    devs = []
    for i in range(1, n + 1):
        status = random.choices(_DEV_STATUSES, weights=[0.65, 0.15, 0.1, 0.1])[0]
        devs.append({
            "device_id":      f"DEV-{i:04d}",
            "name":           f"{random.choice(_DEVICE_TYPES)}_{i:03d}",
            "type":           random.choice(_DEVICE_TYPES),
            "area":           random.choice(_AREAS),
            "status":         status,
            "last_heartbeat": (datetime(2025, 6, 1, 8, 0) + timedelta(minutes=random.randint(0, 1440)))
                              .strftime("%Y-%m-%d %H:%M:%S"),
        })
    return devs


def _gen_sensors(devices, n=20):
    sensors = []
    for i, dev in enumerate(devices[:n]):
        metric = random.choice(list(_METRICS_CFG.keys()))
        cfg    = _METRICS_CFG[metric]
        r      = random.random()
        lo, hi = cfg["normal"] if r < 0.75 else (cfg["warn"] if r < 0.92 else cfg["danger"])
        value  = round(random.uniform(lo, hi), 2)
        state  = "normal" if value <= cfg["normal"][1] else ("warning" if value <= cfg["warn"][1] else "danger")
        sensors.append({
            "sensor_id":  f"SEN-{i + 1:04d}",
            "device_id":  dev["device_id"],
            "area":       dev["area"],
            "metric":     metric,
            "value":      value,
            "unit":       cfg["unit"],
            "state":      state,
            "updated_at": (datetime(2025, 6, 1, 14, 0) + timedelta(seconds=random.randint(0, 3600)))
                          .strftime("%Y-%m-%d %H:%M:%S"),
        })
    return sensors


def _gen_workorders(n=300):
    base = date(2025, 1, 1)
    return [{
        "date":          base + timedelta(days=random.randint(0, 364)),
        "type":          random.choice(_WO_TYPES),
        "status":        random.choices(_WO_STATUSES, weights=[0.2, 0.3, 0.5])[0],
        "resolve_hours": random.randint(1, 72) if random.random() > 0.5 else None,
    } for _ in range(n)]


_ALARMS    = _gen_alarms()
_DEVICES   = _gen_devices()
_SENSORS   = _gen_sensors(_DEVICES)
_WORKORDERS = _gen_workorders()


# ── 健康检查 ──────────────────────────────────────────────
@app.get("/", tags=["健康检查"])
def root():
    return {"status": "ok", "service": "安全生产监控平台 API", "port": 8002}


# ── 1. 报警数量统计 ───────────────────────────────────────
@app.get("/api/alarms/count", tags=["报警管理"])
def get_alarm_count(
    start_date: str          = Query(...,    description="开始日期 YYYY-MM-DD"),
    end_date:   str          = Query(...,    description="结束日期 YYYY-MM-DD"),
    level:      Optional[int]= Query(None, ge=0, le=2,
                                     description="报警等级：0=低级 1=中级 2=高级，不传返回全部"),
):
    """查询指定时间段内的报警数量，可按等级筛选。"""
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(400, "日期格式错误，请使用 YYYY-MM-DD")
    if start > end:
        raise HTTPException(400, "start_date 不能晚于 end_date")

    result = [a for a in _ALARMS if start <= a["date"] <= end]
    if level is not None:
        result = [a for a in result if a["level"] == level]

    return {
        "count":      len(result),
        "level":      _LEVEL_LABEL.get(level, "全部"),
        "start_date": start_date,
        "end_date":   end_date,
    }


# ── 2. 设备状态查询 ───────────────────────────────────────
@app.get("/api/devices/status", tags=["设备管理"])
def get_device_status(
    area:      Optional[str] = Query(None, description="区域关键字，如 A区"),
    status:    Optional[str] = Query(None, description="状态筛选：online / warning / fault / offline"),
    page:      int           = Query(1,  ge=1,           description="页码，默认 1"),
    page_size: int           = Query(10, ge=1, le=50,    description="每页数量，默认 10"),
):
    """查询设备实时状态列表，支持区域/状态筛选和分页。"""
    if status and status not in _DEV_STATUSES:
        raise HTTPException(400, f"无效状态，可选：{', '.join(_DEV_STATUSES)}")

    result = _DEVICES
    if area:
        result = [d for d in result if area in d["area"]]
    if status:
        result = [d for d in result if d["status"] == status]

    total    = len(result)
    s        = (page - 1) * page_size
    summary  = {st: len([d for d in _DEVICES if d["status"] == st]) for st in _DEV_STATUSES}

    return {
        "total":    total,
        "page":     page,
        "page_size": page_size,
        "data":     result[s: s + page_size],
        "summary":  summary,
    }


# ── 3. 安全隐患上报 ───────────────────────────────────────
class HazardBody(BaseModel):
    location:    str
    description: str
    level:       int           # 0=低级 1=中级 2=高级
    reporter:    str
    area:        Optional[str] = None


@app.post("/api/hazard/report", tags=["安全隐患"], status_code=201)
def report_hazard(body: HazardBody):
    """上报安全隐患，返回工单编号和预计响应时限。"""
    if body.level not in (0, 1, 2):
        raise HTTPException(400, "level 必须为 0/1/2")

    hazard_id   = f"HAZ-{random.randint(10000, 99999)}"
    respond_sla = {2: "2 小时", 1: "8 小时", 0: "24 小时"}[body.level]

    return {
        "hazard_id":  hazard_id,
        "status":     "received",
        "level":      _LEVEL_LABEL[body.level],
        "location":   body.location,
        "reporter":   body.reporter,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message":    f"隐患已受理，工单号 {hazard_id}，将在 {respond_sla} 内响应",
    }


# ── 4. 传感器实时监测数据 ─────────────────────────────────
@app.get("/api/monitor/realtime", tags=["实时监测"])
def get_realtime_monitor(
    area:   Optional[str] = Query(None, description="区域关键字，如 C区"),
    metric: Optional[str] = Query(None,
                                  description="指标类型：co / temperature / humidity / pressure / noise"),
    state:  Optional[str] = Query(None, description="状态筛选：normal / warning / danger"),
):
    """获取传感器实时监测数据，支持区域、指标类型和告警状态筛选。"""
    if metric and metric not in _METRICS_CFG:
        raise HTTPException(400, f"无效指标，可选：{', '.join(_METRICS_CFG)}")
    if state and state not in ("normal", "warning", "danger"):
        raise HTTPException(400, "state 可选：normal / warning / danger")

    result = _SENSORS
    if area:
        result = [s for s in result if area in s["area"]]
    if metric:
        result = [s for s in result if s["metric"] == metric]
    if state:
        result = [s for s in result if s["state"] == state]

    state_summary = {st: len([s for s in _SENSORS if s["state"] == st])
                     for st in ("normal", "warning", "danger")}

    return {
        "count":         len(result),
        "data":          result,
        "state_summary": state_summary,
        "updated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── 5. 工单统计 ───────────────────────────────────────────
@app.get("/api/workorder/stats", tags=["工单管理"])
def get_workorder_stats(
    start_date:   str          = Query(...,  description="开始日期 YYYY-MM-DD"),
    end_date:     str          = Query(...,  description="结束日期 YYYY-MM-DD"),
    workorder_type: Optional[str] = Query(None, alias="type",
                                    description="工单类型：inspection / maintenance / repair"),
):
    """统计指定时间段的工单数量、类型分布及平均处理时长。"""
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(400, "日期格式错误，请使用 YYYY-MM-DD")
    if start > end:
        raise HTTPException(400, "start_date 不能晚于 end_date")
    if workorder_type and workorder_type not in _WO_TYPES:
        raise HTTPException(400, f"无效类型，可选：{', '.join(_WO_TYPES)}")

    result = [w for w in _WORKORDERS if start <= w["date"] <= end]
    if workorder_type:
        result = [w for w in result if w["type"] == workorder_type]

    by_status = {_WO_S_LABEL[s]: len([w for w in result if w["status"] == s]) for s in _WO_STATUSES}
    by_type   = {_WO_T_LABEL[t]: len([w for w in result if w["type"]   == t]) for t in _WO_TYPES}
    closed    = [w for w in result if w["status"] == "closed" and w["resolve_hours"]]
    avg_hours = round(sum(w["resolve_hours"] for w in closed) / len(closed), 1) if closed else None

    return {
        "total":              len(result),
        "start_date":         start_date,
        "end_date":           end_date,
        "by_status":          by_status,
        "by_type":            by_type,
        "avg_resolve_hours":  avg_hours,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
