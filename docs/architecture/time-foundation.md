# 时间基础

Time Agent 的数据库时间统一使用 UTC，用户偏好保存明确的 IANA 时区名称。

后端 `common.time` 负责：

- 校验 IANA 时区；
- 将 aware datetime 转换为 UTC；
- 将 UTC 时间转换为用户时区；
- 使用显式注入的当前时间；
- 检测夏令时切换产生的歧义时间和不存在时间。

`UserPreference` 与 Django 用户一对一关联。读取和更新通过 `UserPreferenceService` 完成；API 不直接调用 Serializer 的 `save()`。前端只进行体验层面的基础校验，后端仍是时区和工作时间合法性的最终判断者。

