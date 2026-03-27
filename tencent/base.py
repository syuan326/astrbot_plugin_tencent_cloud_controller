import json
import time
import hmac
import hashlib
import aiohttp
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple


class tencent_cloud_client:
    """
    腾讯云API客户端基类。改写自官方demo
    """

    service = ""
    host = ""
    version = ""
    _shared_session: Optional[aiohttp.ClientSession] = None

    algorithm = "TC3-HMAC-SHA256"
    content_type = "application/json; charset=utf-8"

    def __init__(
        self,
        timeout: int = 30,
        connector_limit: int = 100,
        connector_limit_per_host: int = 20,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.secret_id: Optional[str] = None
        self.secret_key: Optional[str] = None
        self.token: str = ""

        self._timeout_value = timeout
        self._timeout = aiohttp.ClientTimeout(total=timeout)

        # 如果外部传了session，则不由本类负责关闭
        self._session: Optional[aiohttp.ClientSession] = session
        self._owns_session = session is None

        self._connector_limit = connector_limit
        self._connector_limit_per_host = connector_limit_per_host

    def set_credentials(
        self, secret_id: str, secret_key: str, access_token: str = ""
    ) -> None:
        """注入腾讯云 API 凭证"""
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.token = access_token or ""

    @staticmethod
    def _sign(key: bytes, msg: str) -> bytes:
        """使用 HMAC-SHA256 进行签名"""
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    async def init_session(self) -> aiohttp.ClientSession:
        """
        初始化或复用 aiohttp ClientSession
        """
        if (
            tencent_cloud_client._shared_session is None
            or tencent_cloud_client._shared_session.closed
        ):
            connector = aiohttp.TCPConnector(
                limit=self._connector_limit,
                limit_per_host=self._connector_limit_per_host,
                keepalive_timeout=300,
                force_close=False,
                enable_cleanup_closed=True,
                ttl_dns_cache=300,
            )
            tencent_cloud_client._shared_session = aiohttp.ClientSession(
                timeout=self._timeout,
                connector=connector,
            )
            self._owns_session = True
        return self._shared_session

    async def close(self) -> None:
        """
        主动关闭内部 session
        """
        if (
            self._owns_session
            and self._shared_session
            and not self._shared_session.closed
        ):
            await self._shared_session.close()

    @classmethod
    async def close_session(cls):
        """关闭会话"""
        if cls._shared_session and not cls._shared_session.closed:
            await cls._shared_session.close()
            cls._shared_session = None

    def _build_authorization(
        self,
        action: str,
        payload: str,
        region: str = "",
        timestamp: Optional[int] = None,
    ) -> Tuple[Dict[str, str], bytes]:
        """构造腾讯云API请求的签名和头部"""
        if not self.secret_id or not self.secret_key:
            raise ValueError("请先调用 set_credentials() 注入 secret_id / secret_key")

        if not self.service or not self.host or not self.version:
            raise ValueError("类变量 service / host / version 未设置")

        timestamp = timestamp or int(time.time())
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

        # Canonical Request
        canonical_headers = (
            f"content-type:{self.content_type}\n"
            f"host:{self.host}\n"
            f"x-tc-action:{action.lower()}\n"
        )
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        canonical_request = (
            "POST\n"
            "/\n"
            "\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{hashed_request_payload}"
        )

        # String to Sign
        credential_scope = f"{date}/{self.service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(
            canonical_request.encode("utf-8")
        ).hexdigest()

        string_to_sign = (
            f"{self.algorithm}\n"
            f"{timestamp}\n"
            f"{credential_scope}\n"
            f"{hashed_canonical_request}"
        )

        # Signature
        secret_date = self._sign(("TC3" + self.secret_key).encode("utf-8"), date)
        secret_service = self._sign(secret_date, self.service)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(
            secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Authorization
        authorization = (
            f"{self.algorithm} "
            f"Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        # Headers
        headers = {
            "Authorization": authorization,
            "Content-Type": self.content_type,
            "Host": self.host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": self.version,
        }

        if region:
            headers["X-TC-Region"] = region
        if self.token:
            headers["X-TC-Token"] = self.token

        return headers, payload.encode("utf-8")

    async def request(
        self,
        action: str,
        payload_dict: Optional[Dict[str, Any]] = None,
        region: str = "",
    ) -> Dict[str, Any]:
        """主请求方法，供子类调用"""
        payload_dict = payload_dict or {}
        payload = json.dumps(payload_dict, separators=(",", ":"), ensure_ascii=False)

        headers, body = self._build_authorization(
            action=action,
            payload=payload,
            region=region,
        )

        session = await self.init_session()
        endpoint = f"https://{self.host}"

        try:
            async with session.post(endpoint, headers=headers, data=body) as resp:
                status_code = resp.status
                text = await resp.text()

                # 解析 JSON
                try:
                    full_data = json.loads(text)
                except json.JSONDecodeError:
                    return {
                        "Error": {
                            "Code": "Client.JsonDecodeError",
                            "Message": f"非JSON响应: {text[:100]}",
                        },
                        "RequestId": "N/A",
                    }

                # 直接提取Response节点
                response_data = full_data.get("Response", {})

                # 处理状态码非 200 但没给JSON Error的异常情况
                if status_code != 200 and "Error" not in response_data:
                    response_data["Error"] = {
                        "Code": f"Client.HttpError.{status_code}",
                        "Message": "HTTP请求未被正确处理",
                    }

                return response_data

        except aiohttp.ClientError as e:
            # 捕获断网、DNS失败等错误
            return {
                "Error": {"Code": "Client.NetworkError", "Message": str(e)},
                "RequestId": "N/A",
            }
