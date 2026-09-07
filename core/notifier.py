"""消息推送：当前实现 Server 酱（sct.ftqq.com）"""
import json
import logging
import urllib.parse
import urllib.request
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional


class ServerChanNotifier:
    """Server 酱·Turbo 版：https://sct.ftqq.com/

    免费额度：每日 5 条；超出付费。
    """

    ENDPOINT_TPL = "https://sctapi.ftqq.com/{key}.send"

    def __init__(self, send_key: str, logger: logging.Logger,
                 channel: Optional[str] = None):
        self.send_key = send_key.strip()
        self.logger = logger
        self.channel = channel  # 可指定推送通道，不填默认

    def send(self, title: str, desp: str = "") -> bool:
        if not self.send_key:
            self.logger.debug("Server酱 SendKey 未配置，跳过推送")
            return False
        url = self.ENDPOINT_TPL.format(key=self.send_key)
        payload = {
            "title": title[:60],
            "desp": desp[:32000],
        }
        if self.channel:
            payload["channel"] = self.channel
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", "ignore")
                obj = json.loads(body)
                code = obj.get("code", -1)
                if code == 0:
                    self.logger.info("Server酱 推送成功: %s", title)
                    return True
                self.logger.warning("Server酱 推送失败 code=%s body=%s", code, body[:200])
                return False
        except Exception as e:
            self.logger.warning("Server酱 推送异常: %s", e)
            return False


class WebhookNotifier:
    """通用 JSON Webhook，兼容多数企业微信/自建机器人网关。"""
    def __init__(self, url: str, logger: logging.Logger):
        self.url, self.logger = url.strip(), logger

    def send(self, title: str, desp: str = "") -> bool:
        if not self.url:
            return False
        body = json.dumps({"title": title[:120], "desp": desp[:32000]}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                ok = 200 <= resp.status < 300
                if not ok:
                    self.logger.warning("Webhook 推送失败 HTTP %s", resp.status)
                return ok
        except Exception as e:
            self.logger.warning("Webhook 推送异常: %s", e)
            return False


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, logger: logging.Logger):
        self.bot_token, self.chat_id, self.logger = bot_token.strip(), str(chat_id).strip(), logger

    def send(self, title: str, desp: str = "") -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        body = urllib.parse.urlencode({"chat_id": self.chat_id, "text": f"{title}\n\n{desp}"}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 300
        except Exception as e:
            self.logger.warning("Telegram 推送异常: %s", e)
            return False


class EmailNotifier:
    """SMTP 邮件通知。密码应通过环境变量/GitHub Secret 注入。"""
    def __init__(self, host: str, port: int, user: str, password: str,
                 recipient: str, logger: logging.Logger, use_ssl: bool = True):
        self.host, self.port = host.strip(), int(port)
        self.user, self.password = user.strip(), password
        self.recipient, self.logger = recipient.strip(), logger
        self.use_ssl = use_ssl

    def send(self, title: str, desp: str = "") -> bool:
        if not self.host or not self.user or not self.password or not self.recipient:
            self.logger.debug("SMTP 配置不完整，跳过邮件推送")
            return False
        msg = EmailMessage()
        msg["Subject"] = title[:120]
        msg["From"] = self.user
        msg["To"] = self.recipient
        msg.set_content(desp)
        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.host, self.port, context=ssl.create_default_context(), timeout=15) as server:
                    server.login(self.user, self.password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                    server.starttls(context=ssl.create_default_context())
                    server.login(self.user, self.password)
                    server.send_message(msg)
            self.logger.info("SMTP 邮件推送成功: %s", title)
            return True
        except Exception as e:
            self.logger.warning("SMTP 邮件推送异常: %s", e)
            return False
class MultiNotifier:
    def __init__(self, notifiers, logger: logging.Logger):
        self.notifiers, self.logger = notifiers, logger

    def send(self, title: str, desp: str = "") -> bool:
        results = [n.send(title, desp) for n in self.notifiers]
        return any(results)


def build_notifier(cfg: dict, logger: logging.Logger):
    """根据 notifier 配置块构造推送器；未配置则返回 None"""
    if not cfg:
        return None
    notifiers = []
    sc = (cfg.get("serverchan") or {})
    if sc.get("enabled") and sc.get("send_key"):
        notifiers.append(ServerChanNotifier(
            send_key=sc["send_key"],
            logger=logger,
            channel=sc.get("channel"),
        ))
    wh = (cfg.get("webhook") or {})
    if wh.get("enabled") and wh.get("url"):
        notifiers.append(WebhookNotifier(wh["url"], logger))
    tg = (cfg.get("telegram") or {})
    if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
        notifiers.append(TelegramNotifier(tg["bot_token"], tg["chat_id"], logger))
    em = (cfg.get("email") or {})
    if em.get("enabled") and em.get("host") and em.get("user") and em.get("password") and em.get("to"):
        notifiers.append(EmailNotifier(
            em["host"], em.get("port", 465), em["user"], em["password"],
            em["to"], logger, bool(em.get("ssl", True)),
        ))
    return MultiNotifier(notifiers, logger) if notifiers else None
