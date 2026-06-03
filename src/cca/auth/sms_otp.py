from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone

from cca.store import db


def send_otp(phone: str) -> None:
    code = f"{random.randint(0, 999999):06d}"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    db.save_otp(phone, code, expires_at)
    print(f"[SMS] {phone} 验证码: {code}")  # 开发期可见，上线前删除
    _send_via_tencent(phone, code)


def verify_otp(phone: str, code: str) -> bool:
    return db.check_and_consume_otp(phone, code)


def _send_via_tencent(phone: str, code: str) -> None:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.sms.v20210111 import models, sms_client

    cred = credential.Credential(
        os.environ["TENCENT_SECRET_ID"],
        os.environ["TENCENT_SECRET_KEY"],
    )
    http_profile = HttpProfile()
    http_profile.endpoint = "sms.tencentcloudapi.com"
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    client = sms_client.SmsClient(cred, "ap-guangzhou", client_profile)

    req = models.SendSmsRequest()
    req.SmsSdkAppId = os.environ["SMS_SDK_APP_ID"]
    req.SignName = os.environ["SMS_SIGN_NAME"]
    req.TemplateId = os.environ["SMS_TEMPLATE_ID"]
    req.TemplateParamSet = [code]
    req.PhoneNumberSet = [f"+86{phone}"]
    client.SendSms(req)
