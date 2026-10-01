"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import windfarm as router_windfarm
from app.routers import turbine as router_turbine
from app.routers import blade as router_blade
from app.routers import gearbox as router_gearbox
from app.routers import generator as router_generator
from app.routers import pitch as router_pitch
from app.routers import yaw as router_yaw
from app.routers import metmast as router_metmast
from app.routers import collector as router_collector
from app.routers import substation as router_substation
from app.routers import forecast as router_forecast
from app.routers import vibration as router_vibration
from app.routers import defect as router_defect
from app.routers import maintjob as router_maintjob
from app.routers import spare as router_spare
from app.routers import patrol as router_patrol
from app.routers import accept as router_accept
from app.routers import settle as router_settle
from app.routers import seawindow as router_seawindow

ROUTERS = [router_windfarm, router_turbine, router_blade, router_gearbox, router_generator, router_pitch, router_yaw, router_metmast, router_collector, router_substation, router_forecast, router_vibration, router_defect, router_maintjob, router_spare, router_patrol, router_accept, router_settle, router_seawindow]
