# ADR 0019：双坐标天气偏好与简报

- 状态：Accepted
- 日期：2026-08-09

## 背景

此前 `weather_location_data` 只有一组 `latitude`/`longitude`。手动选择行政区与点击“使用当前位置”会互相覆盖，导致系统无法同时表达“用户关注的行政区”和“设备实际所在点”，简报也无法解释两类天气差异。

高德天气接口以六位 `adcode` 查询行政区预报，不提供 GPS 点位预报。Open-Meteo 支持直接使用经纬度，因此适合比较行政区代表点与手机 GPS 点位。

## 决策

1. `weather_location` 继续保存可读文字标签；`weather_location_data` 升级为 `schema_version=2` 的结构化 JSON。
2. 行政区、省、市、区、时区、坐标来源 Provider、Provider location ID 和 `adcode` 保存在顶层；坐标分别保存在：
   - `administrative_coordinates`：用户手动选择行政区后解析出的代表性中心坐标；
   - `current_coordinates`：用户明确点击“使用当前位置”后由设备提供的真实 GPS 坐标，可附带定位精度。
3. 两组坐标独立更新。手动改选行政区不得删除已有 GPS；重新定位不得覆盖手动行政区。
4. 对用户保存地点生成简报时，`WeatherDataService` 使用支持点位查询的 Open-Meteo 分别查询两组坐标。高德仍用于逆地理编码、`adcode` 和按行政区查询的兼容路径，但不伪装成 GPS 点位天气。
5. 天气研究结果和来源 ID 带有 `coordinate_role`。简报必须分别标注“手动行政区代表点”和“手机当前位置 GPS”，不得合并、平均或静默省略。
6. 只保存一组坐标时仍可生成天气，但简报标记为部分完成并明确提示缺失的另一组。
7. 数据迁移将旧 `device_geolocation` 坐标归入 `current_coordinates`，其他旧坐标归入 `administrative_coordinates`；无法从历史值可靠推导的另一组坐标不做猜测。

## 结果

用户能在设置页查看两组坐标及 GPS 精度，简报能对比行政区代表点与实际位置天气。GPS 点位会在用户主动授权后发送给 Open-Meteo 进行天气查询；系统不会将其发送给只接受 `adcode` 的高德天气接口。
