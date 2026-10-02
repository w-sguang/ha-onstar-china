# 安吉星 (OnStar China) for Home Assistant

把**上汽通用（别克 / 凯迪拉克 / 雪佛兰）** 的车，通过 **安吉星** 接进 Home Assistant：
看车况、锁车解锁、远程启动、寻车鸣笛。

[![hacs-custom](https://img.shields.io/badge/HACS-自定义仓库-41BDF5.svg)](#安装)
[![version](https://img.shields.io/github/manifest-json/v/w-sguang/ha-onstar-china?filename=custom_components%2Fonstar_cn%2Fmanifest.json)](https://github.com/w-sguang/ha-onstar-china/releases)
[![license](https://img.shields.io/github/license/w-sguang/ha-onstar-china)](LICENSE)

> ⚠️ **非官方接口**：逆向自安吉星微信小程序，随时可能失效，且存在账号风控风险。
> 请**低频**使用。**车控指令会真实操作你的车辆**，请自行评估风险。

---

## 能干什么

| 实体 | 类型 | 说明 |
|---|---|---|
| **车门锁** | `lock` | 🔒 上锁 / 🔓 解锁 |
| **远程启动** | `button` | 远程启动发动机 |
| **取消启动** | `button` | 取消远程启动 |
| **闪灯鸣笛** | `button` | 地库寻车 |
| **取消闪灯鸣笛** | `button` | 停止鸣笛闪灯 |
| 剩余续航 | `sensor` | 还能跑多少公里 |
| 油量 (%) / 油量 (L) / 油箱容量 | `sensor` | 油量百分比、剩余升数、油箱容积 |
| 总里程 | `sensor` | 车辆总里程（odometer） |
| 机油寿命 | `sensor` | 机油剩余寿命 % |
| 胎压（左前/右前/左后/右后） | `sensor` | 四轮胎压 (kPa) |
| 上次行程里程 / 上次行程油耗 | `sensor` | 上一段行程数据 |
| 综合油耗 | `sensor` | 全生命周期平均油耗 |
| **胎压告警** | `binary_sensor` | 任一胎压异常时 `on` |
| **最后指令结果** | `sensor` | 上一条远程指令的「成功 / 失败」 |

**特性**

- 🔐 令牌自动刷新，抓一次凭据就能长期使用（**不用**反复登小程序）
- 🧩 完整 UI 配置，支持「重新配置 / 重新认证」，不用改 YAML
- 🔔 指令失败会弹 **HA 通知**（中文说明），并触发 `onstar_cn_command` 事件
- 🚗 车控写操作自动完成**服务密码（PIN）** 校验

> ℹ️ 车况数据来自车辆**上次上报**的快照（不是实时值），每个实体属性里带「数据时间」。

---

## 安装

### 方式一：HACS（推荐）

1. HACS → 集成 → 右上角 **⋮ → 自定义仓库**
2. 填 `https://github.com/w-sguang/ha-onstar-china`，类别选 **Integration**
3. 搜索「**安吉星**」→ 下载
4. **重启 Home Assistant**

> 已提交 HACS 默认商店审核，通过后可直接搜到，无需添加自定义仓库。

### 方式二：手动

把 `custom_components/onstar_cn/` 整个目录复制到 HA 配置目录下的 `custom_components/`
（通常是 `/config/custom_components/`），然后重启 HA。

---

## 配置

**设置 → 设备与服务 → 添加集成 → 搜「安吉星」** → 填 4 项：

| 字段 | 必填 | 说明 |
|---|---|---|
| 用户 ID (idpUserId) | ✅ | 形如 `LADPA017243106` |
| perm_token | ✅ | 256 位长串，来自登录响应 |
| 车架号 VIN | ✅ | 17 位，如 `LSGZR5359PH094753` |
| 服务密码（PIN） | ⭕ 选填 | 车控写操作用；只读车况不需要 |

### 凭据怎么拿？

安吉星的登录**绑死在微信**上（连密码登录都要带微信生成的 code），所以没法在 HA 里直接
用账号密码登录 —— 需要你**从安吉星微信小程序抓一次登录请求**，取出凭据。

👉 **完整图文步骤见 [docs/获取凭据.md](docs/获取凭据.md)**（只需做一次）

### 服务密码（PIN）是什么？

就是你平时在**安吉星 App 里做远程控制时输入的那个密码**（一般 6 位数字）。

安吉星服务端规定：**锁车 / 解锁 / 远程启动 / 鸣笛属于写操作，必须先校验服务密码**，
否则返回 `E7011`。所以：

- **只用车况**（油量、里程、胎压…）→ 这一项**留空**就行
- **要用车控**（锁车 / 启动…）→ 必须填，否则点按钮会提示「未配置服务密码」
- 集成会**自动**做校验并复用会话，你只需要填一次
- 密码只存在**你自己的 HA** 配置里，不会发往任何第三方

---

## 使用示例

### 自动化：到家自动锁车

```yaml
automation:
  - alias: 到家自动锁车
    triggers:
      - trigger: state
        entity_id: person.me
        to: home
    conditions:
      - condition: state
        entity_id: lock.an_ji_xing_094753_che_men_suo
        state: unlocked
    actions:
      - action: lock.lock
        target:
          entity_id: lock.an_ji_xing_094753_che_men_suo
```

### 自动化：胎压异常提醒

```yaml
automation:
  - alias: 胎压异常提醒
    triggers:
      - trigger: state
        entity_id: binary_sensor.an_ji_xing_094753_tai_ya_gao_jing
        to: "on"
    actions:
      - action: notify.mobile_app_你的手机
        data:
          message: "⚠️ 车辆胎压异常，请检查轮胎"
```

### 指令结果通知

每次远程指令（锁车/解锁/启动…）完成后，会触发事件 `onstar_cn_command`：

```yaml
automation:
  - alias: 车控结果通知
    triggers:
      - trigger: event
        event_type: onstar_cn_command
    actions:
      - action: notify.mobile_app_你的手机
        data:
          message: >-
            指令「{{ trigger.event.data.name }}」
            {{ '成功 ✅' if trigger.event.data.success else '失败 ❌ ' + (trigger.event.data.message or '') }}
```

---

## 常见问题

**Q：为什么在 HA 里点锁车会失败 / 提示「未配置服务密码」？**
A：写操作需要服务密码。到 **设置 → 设备与服务 → 安吉星 → 配置** 里填上即可
（只读车况不受影响）。

**Q：为什么不能直接填手机号 + 密码？**
A：安吉星把登录绑在微信上，密码登录接口也强制要带微信 `wx.login` 产生的 code
（服务端拿它换 openid），微信之外拿不到，实测返回 `E3011 Get openid failed`。

**Q：令牌失效了（HA 提示需要重新认证）怎么办？**
A：安吉星是**单点在线**：只要你在**小程序里重新登录**一次，旧 `perm_token` 就作废。
点 **「重新配置」**，把**重新抓到**的 `perm_token` 粘进去即可 —— 不用删集成，
实体和自动化全都保留。

> 💡 想少掉线：抓完凭据后**就别再去小程序里重新登录**了。服务端刷新**不会**轮换
> `perm_token`，只要不重新登录，它就能一直自动续下去。

**Q：锁车状态准吗？**
A：安吉星没有提供「读取当前锁止状态」的接口，所以 `lock` 实体是**假设状态**
（你下发了锁车就显示已锁）。它反映的是**最后一次操作**，不是车辆真实回传值。

**Q：车况数据准吗 / 是实时的吗？**
A：来自安吉星 `lastDiagnostics` 接口，是车辆**上次上报**的快照，可能滞后。
每个实体的属性里有「数据时间」。

**Q：会封号吗？**
A：属于非官方接口，理论上存在风控可能。集成默认 **30 分钟**刷新一次车况，
指令只在你手动触发时下发，属于低频使用。**风险自负。**

---

## 免责声明

本项目为非官方开源项目，与上汽通用 / 安吉星无任何关联。接口通过公开客户端逆向分析得到，
仅供学习与个人自动化使用。使用本集成产生的任何后果（包括但不限于账号风控、车辆异常）
由使用者自行承担。

License: [MIT](LICENSE)
