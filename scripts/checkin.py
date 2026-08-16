#!/usr/bin/env python3
"""
V2Free (Maxo) 每日自动签到脚本
用于 GitHub Actions 云端定时执行，无需开电脑

支持两种认证方式：
  1. 账号密码登录（注意：部分站点会拒绝云端密码登录）
  2. Cookie 直接访问（更稳，推荐）

作者: Tabbit Agent 自动生成/修正
日期: 2026-06-21
"""

import os
import sys
import json
import re
import logging
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    print("正在安装依赖...")
    os.system("pip install requests -q")
    import requests

# ==================== 配置区 ====================

# V2Free 网站地址（可根据实际域名修改）
BASE_URL = os.environ.get("V2FREE_URL", "https://w1.maxo.top")

# 认证方式：password（账号密码）或 cookie（直接用 Cookie）
AUTH_METHOD = os.environ.get("AUTH_METHOD", "cookie").strip().lower()

# 账号密码（从 GitHub Secrets 中读取，不要明文写在这里！）
EMAIL = os.environ.get("V2FREE_EMAIL", "")
PASSWORD = os.environ.get("V2FREE_PASSWORD", "")

EMAIL1 = os.environ.get("V2FREE_EMAIL1", "")
PASSWORD1 = os.environ.get("V2FREE_PASSWORD1", "")

EMAIL2 = os.environ.get("V2FREE_EMAIL2", "")
PASSWORD2 = os.environ.get("V2FREE_PASSWORD2", "")

# Cookie 字符串（从浏览器复制完整 Cookie）
COOKIE = os.environ.get("V2FREE_COOKIE", "")

# 时区设置（用于日志时间显示）
TZ_OFFSET = int(os.environ.get("TZ_OFFSET", "8"))  # 默认东八区

# ==================== 日志配置 ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("v2free-checkin")


# ==================== 辅助函数 ====================

def parse_cookie_string(cookie_str: str) -> dict:
    """把浏览器复制过来的 Cookie 字符串解析为 dict"""
    cookies = {}
    if not cookie_str:
        return cookies
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


# ==================== 核心逻辑 ====================

class V2FreeCheckin:
    """V2Free 自动签到客户端"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def _get(self, path: str, **kwargs) -> requests.Response:
        """发送 GET 请求"""
        return self.session.get(f"{self.base_url}{path}", timeout=30, **kwargs)

    def _post(self, path: str, **kwargs) -> requests.Response:
        """发送 POST 请求"""
        return self.session.post(f"{self.base_url}{path}", timeout=30, **kwargs)

    def login_by_password(self, email: str, password: str) -> bool:
        """使用账号密码登录 V2Free"""
        log.info(f"🔐 正在使用账号密码登录: {email}")

        try:
            # 先访问登录页面获取 CSRF Token 或初始 Cookie
            resp = self._get("/auth/login")

            # 尝试查找 CSRF token（部分面板需要）
            csrf_token = ""
            match = re.search(r'name=["\']csrf["\']\s+content=["\']([^"\']+)', resp.text)
            if match:
                csrf_token = match.group(1)
                log.info("找到 CSRF Token")

            # 发送登录请求
            login_data = {"email": email, "passwd": password}
            if csrf_token:
                login_data["csrf_token"] = csrf_token

            resp = self._post("/auth/login", data=login_data)

            if resp.status_code in (200, 302, 301):
                # 检查是否登录成功（跳转到用户中心或返回成功 JSON）
                final_url = resp.url
                try:
                    result = resp.json()
                except Exception:
                    result = None

                if "/user" in final_url or (result and (result.get("ret") == 1 or result.get("success"))) or "用户中心" in resp.text or email in resp.text:
                    log.info("✅ 账号密码登录成功！")
                    return True

                # 可能被拒绝（云端登录被拦截）
                log.error(f"❌ 登录失败，站点返回: HTTP {resp.status_code}")
                # 输出简短提示，勿打印敏感信息
                if resp.status_code in (401, 403):
                    log.error("❌ 认证被拒绝（401/403），目标站点可能不允许云端密码登录或需要额外验证")
                else:
                    log.debug("登录响应片段:")
                    log.debug(resp.text[:400])
                return False
            else:
                log.error(f"❌ 登录请求失败，HTTP {resp.status_code}")
                return False

        except requests.RequestException as e:
            log.error(f"❌ 登录网络错误: {e}")
            return False

    def set_cookie(self, cookie_str: str) -> bool:
        """设置 Cookie 认证"""
        if not cookie_str:
            log.error("❌ Cookie 为空")
            return False

        log.info("🍪 正在设置 Cookie 认证...（不会在日志中打印完整 Cookie）")

        cookies = parse_cookie_string(cookie_str)
        if not cookies:
            log.error("❌ 解析到的 Cookie 为空，请确认粘贴的是浏览器中的完整 Cookie 字符串")
            return False

        # 使用 requests 的 cookiejar 更新
        try:
            # 不要把 Cookie 值打印到日志；只打印 key 列表
            log.info(f"   Cookie keys: {', '.join(list(cookies.keys())[:10])}")
            self.session.cookies.update(cookies)
            log.info("✅ Cookie 已设置（通过 keys 验证）")
            return True
        except Exception as e:
            log.error(f"❌ 设置 Cookie 失败: {e}")
            return False

    def verify_login(self) -> bool:
        """验证当前登录状态是否有效"""
        log.info("🔍 正在验证登录状态...")

        try:
            resp = self._get("/user")

            if resp.status_code == 200:
                # 检查是否包含用户中心特征
                if any(keyword in resp.text for keyword in ["用户中心", "剩余流量", "上次签到", "account_box"]):
                    log.info("✅ 登录状态有效")

                    # 提取账号信息（谨慎打印）
                    email_match = re.search(r'[\w.-]+@[\w.-]+\.\w+', resp.text)
                    if email_match:
                        log.info(f"   当前账号: {email_match.group()}")

                    # 提取流量信息
                    traffic_match = re.search(r'剩余流量[^\d]*(\d+\.?\d*\s*[KMGT]?B)', resp.text)
                    if traffic_match:
                        log.info(f"   剩余流量: {traffic_match.group(1)}")

                    return True

                elif "/auth/login" in resp.url or "login" in resp.text.lower():
                    log.warning("⚠️ 未登录或会话已过期，请检查 Cookie 或密码")
                    return False
                else:
                    log.warning("⚠️ 无法确定登录状态（响应页面没有明显登录标识）")
                    log.debug(resp.text[:400])
                    return False
            else:
                log.warning(f"⚠️ 验证请求失败 HTTP {resp.status_code}")
                if resp.status_code in (401, 403):
                    log.warning("⚠️ 目标站点可能拒绝云端认证请求（401/403）。考虑使用自托管 runner 或 Cookie 登录）")
                return False

        except requests.RequestException as e:
            log.error(f"❌ 验证网络错误: {e}")
            return False

    def do_checkin(self) -> dict:
        """执行签到操作"""
        log.info("📋 正在执行签到...")
        result = {
            "success": False,
            "message": "",
            "traffic_info": "",
            "checkin_time": datetime.now(timezone(timedelta(hours=TZ_OFFSET))).strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 尝试多种签到路径
        checkin_paths = [
            ("/user/checkin", "POST"),     # ss-panel 标准
            ("/user/checkin", "GET"),      # GET 方式
            ("/user/signin", "POST"),      # 备选路径
            ("/checkin", "POST"),          # 根路径
        ]

        for path, method in checkin_paths:
            log.info(f"   尝试: {method} {path}")

            try:
                if method == "POST":
                    resp = self._post(path)
                else:
                    resp = self._get(path)

                # 处理响应
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        msg = data.get("msg", "")
                        ret = data.get("ret", -1)

                        if ret == 1 or "成功" in msg or "already" in msg.lower() or "已签" in msg:
                            result["success"] = True
                            result["message"] = msg or ("签到成功！" if ret == 1 else "已签到")
                            log.info(f"   ✅ {result['message']}")

                            # 提取流量信息
                            if "traffic" in str(data).lower():
                                result["traffic_info"] = json.dumps(data, ensure_ascii=False, indent=2)

                            return result
                        else:
                            result["message"] = msg or f"签到返回: (ret={ret})"
                            log.info(f"   ⚠️ {result['message']}")
                            continue

                    except (json.JSONDecodeError, ValueError):
                        # 非 JSON 响应，尝试文本解析
                        text = resp.text
                        if "已签到" in text or "already" in text.lower() or "checked" in text.lower():
                            result["success"] = True
                            result["message"] = "已签到"
                            log.info(f"   ✅ 已签到（从响应确认）")
                            return result
                        elif "签到" in text:
                            result["success"] = True
                            result["message"] = "已签到 ✅"
                            log.info(f"   ✅ 已签到（从文本确认）")
                            return result
                        else:
                            log.debug(f"   响应非预期格式...")
                            continue

                elif resp.status_code in (301, 302):
                    # 重定向可能表示需要登录
                    log.warning(f"   ⚠️ 收到重定向 (HTTP {resp.status_code})，可能需要先登录")

                else:
                    log.debug(f"   HTTP {resp.status_code}")

            except requests.RequestException as e:
                log.error(f"   ❌ 网络错误: {e}")
                continue

        # 最终通过用户页面确认签到状态
        log.info("📋 通过用户中心确认签到结果...")
        try:
            verify_resp = self._get("/user")
            if verify_resp.status_code == 200:
                if "已签到" in verify_resp.text:
                    result["success"] = True
                    result["message"] = "已签到（从用户中心确认）"
                    log.info(f"✅ {result['message']}")

                    time_match = re.search(r'上次签到[^\d]*(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2})', verify_resp.text)
                    if time_match:
                        result["checkin_time"] = time_match.group(1)

                    traffic_match = re.search(r'剩余流量[^\d]*(\d+\.?\d*\s*[KMGT]?B)', verify_resp.text)
                    if traffic_match:
                        result["traffic_info"] = f"剩余流量: {traffic_match.group(1)}"

                    used_match = re.search(r'(?:已用|used)[^\d]*(\d+\.?\d*)\s*(?:[KMGT]?B)?', verify_resp.text)
                    if used_match:
                        if result["traffic_info"]:
                            result["traffic_info"] += f"，今日已用: {used_match.group(1)}"
                        else:
                            result["traffic_info"] = f"今日已用: {used_match.group(1)}"

                    return result
        except requests.RequestException as e:
            log.error(f"❌ 验证网络错误: {e}")

        result["message"] = result["message"] or "签到未完成，请检查日志"
        log.error(f"❌ {result['message']}")
        return result


def main(youremail, yourpassword):
    """主函数"""
    print("=" * 50)
    print("  V2Free (Maxo) 每日自动签到")
    print(f"  执行时间: {datetime.now(timezone(timedelta(hours=TZ_OFFSET))).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    client = V2FreeCheckin(BASE_URL)

    # ===== 步骤 1：认证 =====
    authenticated = False

    # 如果在 GitHub Actions 环境并且选择 password，提醒可能被拒绝
    if os.environ.get("GITHUB_ACTIONS", "false").lower() == "true" and AUTH_METHOD == "password":
        log.warning("⚠️ 当前运行在 GitHub Actions，目标站点可能拒绝云端密码登录，建议使用 Cookie 或自托管 runner")

    if AUTH_METHOD == "cookie":
        if COOKIE:
            authenticated = client.set_cookie(COOKIE)
        else:
            log.error("❌ Cookie 为空！请检查 Secrets 中 V2FREE_COOKIE 的配置")
    elif AUTH_METHOD == "password":
        if youremail and yourpassword:
            authenticated = client.login_by_password(youremail, yourpassword)
        else:
            log.error("❌ 邮箱或密码为空！请检查 Secrets 中 V2FREE_EMAIL 和 V2FREE_PASSWORD 的配置")
    else:
        log.error(f"❌ 不支持的认证方式: {AUTH_METHOD}（应为 'password' 或 'cookie'）")

    if not authenticated:
        log.error("\n❌ 认证失败，无法继续签到！")
        print("\n## ❌ 签到失败")
        print("**原因**: 认证失败")
        print("- 请检查 `AUTH_METHOD` 配置（`password` 或 `cookie`）")
        print("- 请在仓库 Settings → Secrets 中配置正确的凭据")
        sys.exit(1)

    # ===== 步骤 2：验证登录 =====
    if not client.verify_login():
        log.error("\n❌ 登录状态无效！")
        print("\n## ❌ 签到失败")
        print("**原因**: 登录状态无效或已过期")
        print("- 如果使用 Cookie，请更新为新的 Cookie")
        print("- 如果使用密码，请检查账号密码是否正确")
        sys.exit(1)

    # ===== 步骤 3：执行签到 =====
    result = client.do_checkin()

    # ===== 输出结果 =====
    print("\n" + "=" * 50)
    if result["success"]:
        print("## ✅ 签到完成")
    else:
        print("## ❌ 签到失败")

    print(f"**状态**: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"**消息**: {result['message']}")
    print(f"**时间**: {result['checkin_time']}")
    if result["traffic_info"]:
        print(f"**流量**: {result['traffic_info']}")
    print(f"**网站**: {BASE_URL}")
    print("=" * 50)

    # 退出码
    # sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    print("--- account 1 ---")
    main(EMAIL, PASSWORD)
    print("--- account 2 ---")
    main(EMAIL1, PASSWORD1)
    print("--- account 3 ---")
    main(EMAIL2, PASSWORD2)
    sys.exit(0)
