# -*- coding: utf-8 -*-
"""macOS 身份验证后端。

两道闸的第二道：调 LocalAuthentication 让系统弹 Touch ID / 密码面板。
用 PyObjC 直调，不编译任何东西，也就没有架构和 Gatekeeper 的问题。

为什么不用 `osascript ... with administrator privileges`：
那条路走的是 Authorization Services，认证面板只给密码框，不会弹指纹。
改 /etc/pam.d/sudo 加 pam_tid 对这条路径无效——它不是 sudo。

为什么用 LAPolicyDeviceOwnerAuthentication 而不是 WithBiometrics：
前者在指纹失败/被锁定后自动回落到密码，一个 API 覆盖两种方式；
后者只认生物识别，锁定后还要调用方自己处理回落。
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    method: str          # "biometric" | "password" | "unknown"
    reason: str = ""     # 失败原因码：cancelled / unavailable / timeout / error


def backend_available() -> tuple[bool, str]:
    """检查当前环境能否弹系统认证。不触发 UI。"""
    if sys.platform != "darwin":
        return False, "not macOS"
    try:
        from LocalAuthentication import LAContext, LAPolicyDeviceOwnerAuthentication
    except Exception as e:  # pyobjc 没装
        return False, f"pyobjc unavailable: {e}"
    try:
        ctx = LAContext.new()
        ok, err = ctx.canEvaluatePolicy_error_(LAPolicyDeviceOwnerAuthentication, None)
        if not ok:
            return False, f"policy unavailable: {err}"
        return True, "ok"
    except Exception as e:
        return False, f"probe failed: {e}"


def authenticate(reason: str, timeout: float = 300.0) -> AuthResult:
    """弹出系统认证面板。阻塞直到用户操作、超时或出错。

    任何异常都按失败处理（fail-closed）。调用方拿到 ok=False 必须停止。
    """
    if sys.platform != "darwin":
        return AuthResult(False, "unknown", "unavailable")
    try:
        from LocalAuthentication import LAContext, LAPolicyDeviceOwnerAuthentication
    except Exception:
        return AuthResult(False, "unknown", "unavailable")

    ctx = LAContext.new()
    ok, err = ctx.canEvaluatePolicy_error_(LAPolicyDeviceOwnerAuthentication, None)
    if not ok:
        return AuthResult(False, "unknown", "unavailable")

    done = threading.Event()
    box: dict = {"ok": False, "err": None}

    def reply(success, error):
        box["ok"] = bool(success)
        box["err"] = error
        done.set()

    t0 = time.monotonic()
    try:
        ctx.evaluatePolicy_localizedReason_reply_(
            LAPolicyDeviceOwnerAuthentication, reason, reply)
    except Exception:
        return AuthResult(False, "unknown", "error")

    if not done.wait(timeout):
        # 超时就作废这次上下文，别让面板留着等一个已经放弃的调用。
        try:
            ctx.invalidate()
        except Exception:
            pass
        return AuthResult(False, "unknown", "timeout")

    if box["ok"]:
        # LocalAuthentication 不告诉我们用户按了指纹还是输了密码。
        # 有生物识别硬件时大概率是指纹，但 API 层面无法确认，照实标 unknown。
        return AuthResult(True, "unknown")

    err = box["err"]
    code = getattr(err, "code", None)
    # LAError: -2 userCancel, -3 userFallback, -4 systemCancel, -1 appCancel,
    # -8 biometryLockout, -9 biometryNotEnrolled, -6 biometryNotAvailable
    if code in (-1, -2, -4):
        return AuthResult(False, "unknown", "cancelled")
    if code in (-6, -9):
        return AuthResult(False, "unknown", "unavailable")
    return AuthResult(False, "unknown", "error")
