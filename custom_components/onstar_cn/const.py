"""常量定义。"""
DOMAIN = "onstar_cn"

CONF_USERNAME = "username"        # idpUserId (形如 LADPA017243106)
CONF_PERM_TOKEN = "perm_token"    # 长期刷新令牌
CONF_VIN = "vin"
CONF_PIN = "pin"                  # 服务密码：锁车/解锁/远程启动等写操作需要

BASE = "https://api.shanghaionstar.com"
CLIENT_INFO = "Mac_OS_wx111113_zh-CN_Mac17,4_jGQrHX0vOjmM3aDe4AvAmw=="
CLIENT_VERSION = "11.1.3"
AES_KEY = b"360fe65ae392fec2"     # key == iv

UPDATE_INTERVAL = 30 * 60         # 秒；车况轮询间隔
TOKEN_MARGIN = 180                # 提前刷新秒数
PIN_TTL = 300                     # 秒；服务密码校验会话缓存时间
EVENT_COMMAND = "onstar_cn_command"  # 指令结果事件

CMD_START = "start"
CMD_CANCEL_START = "cancelStart"
CMD_LOCK = "lockDoor"
CMD_UNLOCK = "unlockDoor"
CMD_FLASH = "alert"
CMD_CANCEL_FLASH = "cancelAlert"
CMD_LOCATION = "location"
CMD_DIAGNOSTICS = "diagnostics"

# 需要先校验服务密码的写指令（只读不受影响）
CMDS_NEED_PIN = {
    CMD_LOCK, CMD_UNLOCK, CMD_START, CMD_CANCEL_START, CMD_FLASH, CMD_CANCEL_FLASH,
}
