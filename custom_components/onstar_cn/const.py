"""常量定义。"""
DOMAIN = "onstar_cn"

CONF_USERNAME = "username"        # idpUserId (形如 LADPA017243106)
CONF_PERM_TOKEN = "perm_token"    # 长期刷新令牌
CONF_VIN = "vin"

BASE = "https://api.shanghaionstar.com"
CLIENT_INFO = "Mac_OS_wx111113_zh-CN_Mac17,4_jGQrHX0vOjmM3aDe4AvAmw=="
CLIENT_VERSION = "11.1.3"
AES_KEY = b"360fe65ae392fec2"     # key == iv

UPDATE_INTERVAL = 30 * 60         # 秒；车况轮询间隔
TOKEN_MARGIN = 180                # 提前刷新秒数
EVENT_COMMAND = "onstar_cn_command"  # 指令结果事件

CMD_START = "start"
CMD_CANCEL_START = "cancelStart"
CMD_LOCK = "lockDoor"
CMD_UNLOCK = "unlockDoor"
CMD_FLASH = "alert"
CMD_CANCEL_FLASH = "cancelAlert"
CMD_LOCATION = "location"
CMD_DIAGNOSTICS = "diagnostics"
