import json
from typing import Any, Optional

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .tencent.dnspod import DNSPodClient



class TencentDNSPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.dnspod_client: Optional[DNSPodClient] = None
        self.domain: Optional[str] = self.config.get("domain", "").strip() or None

    # 初始化DNSPod客户端
    async def _init_dnspod_client(self):
        secret_id = self.config.get("secret_id", "").strip()
        secret_key = self.config.get("secret_key", "").strip()
        domain = self.config.get("domain", "").strip()
        timeout = self.config.get("timeout", 30)

        if not secret_id or not secret_key:
            logger.warn("未配置腾讯云 SecretId 或 SecretKey")
        if not domain:
            logger.warn("未配置管理的域名")
        if not secret_id or not secret_key or not domain:
            self.dnspod_client = None
            self.domain = domain.strip() or None
            return

        self.domain = domain.strip() or None
        if self.dnspod_client is None:
            try:
                self.dnspod_client = DNSPodClient(
                    secret_id=secret_id,
                    secret_key=secret_key,
                    domain=domain,
                    timeout=timeout,
                )
            except Exception as e:
                logger.error(f"初始化 DNSPod 客户端失败: {e}")
                self.dnspod_client = None
            else:
                logger.info("成功初始化 DNSPod 客户端。")

    def _get_config(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    @filter.command("dns_list")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def dns_list(self, event: AstrMessageEvent):
        """获取域名解析记录列表 (仅管理员)"""
        await self._init_dnspod_client()

        if not self.domain:
            yield event.plain_result("错误：请先在插件配置中设置待管理的域名。")
            return
        if not self.dnspod_client:
            yield event.plain_result(
                "错误：DNSPod 客户端未初始化，请检查 SecretId/SecretKey/domain 配置。"
            )
            return

        try:
            # 使用类方法获取原始记录列表
            records, err = await self.dnspod_client._list_records_raw()
            if err:
                yield event.plain_result(f"获取解析记录失败: {err}")
                return

            if not records:
                yield event.plain_result(f"域名 {self.domain} 下暂无解析记录。")
                return

            msg = f"🌐 域名 {self.domain} 解析记录 (前100条):\n"
            msg += "ID | 主机记录 | 类型 | 记录值 | 状态\n"
            msg += "-" * 30 + "\n"
            for r in records:
                msg += f"{r['RecordId']} | {r['Name']} | {r['Type']} | {r['Value']} | {'✅' if r['Status'] == 'ENABLE' else '❌'}\n"

            yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"获取解析列表失败: {e}")
            yield event.plain_result(f"❌ 获取列表失败：{str(e)}")

    @filter.command("dns_add")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def dns_add(
        self, event: AstrMessageEvent, sub_domain: str, record_type: str, value: str
    ):
        """添加新的域名解析记录。参数：子域名 类型 记录值 (仅管理员)"""
        await self._init_dnspod_client()
        record_line = self._get_config("record_line", "默认")
        if not self.domain:
            yield event.plain_result("错误：请先设置待管理的域名。")
            return
        if not self.dnspod_client:
            yield event.plain_result(
                "错误：DNSPod 客户端未初始化，请检查 SecretId/SecretKey/domain 配置。"
            )
            return

        try:
            # 使用类方法添加记录
            res = await self.dnspod_client.add_record(
                sub_domain, record_type.upper(), value, record_line
            )
            yield event.plain_result(f"✅ {res} [线路: {record_line}]")
        except Exception as e:
            logger.error(f"添加解析记录失败: {e}")
            yield event.plain_result(f"❌ 添加记录失败：{str(e)}")

    @filter.command("dns_del")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def dns_del(self, event: AstrMessageEvent, record_id: int):
        """根据记录 ID 删除域名解析记录 (仅管理员)"""
        await self._init_dnspod_client()
        if not self.dnspod_client:
            yield event.plain_result(
                "错误：DNSPod 客户端未初始化，请检查 SecretId/SecretKey/domain 配置。"
            )
            return

        try:
            # 使用类方法删除记录
            res = await self.dnspod_client.delete_record(record_id)
            yield event.plain_result(f"✅ {res}")
        except Exception as e:
            logger.error(f"删除解析记录失败: {e}")
            yield event.plain_result(f"❌ 删除记录失败：{str(e)}")

    # LLM Tool 注册

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.llm_tool(name="get_dns_records")
    async def get_dns_records(self, event: AstrMessageEvent) -> str:
        """向腾讯云获取当前配置域名的 DNS 解析记录列表。注意：此操作仅限管理员触发。"""

        if self._get_config("disable_tool"):
            return "抱歉，该工具已被管理员禁用。"

        await self._init_dnspod_client()
        if not self.domain:
            return "错误：请先在插件配置中设置待管理的域名。"
        if not self.dnspod_client:
            return (
                "错误：DNSPod 客户端未初始化，请检查 SecretId/SecretKey/domain 配置。"
            )

        try:
            records, err = await self.dnspod_client._list_records_raw()
            if err:
                return f"查询失败: {err}"
            return f"查询到 {self.domain} 的记录：{json.dumps(records, ensure_ascii=False)}"
        except Exception as e:
            logger.error(f"LLM查询解析失败: {e}")
            return f"查询失败: {str(e)}"

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.llm_tool(name="add_dns_record")
    async def add_dns_record(
        self, event: AstrMessageEvent, sub_domain: str, record_type: str, value: str
    ) -> str:
        """在腾讯云为当前域名添加一条DNS解析记录。注意：此操作仅限管理员触发。

        Args:
            sub_domain(string): 主机记录，如 'www', '@', 'test'
            record_type(string): 记录类型，可选 A, CNAME, TXT, MX, AAAA 等
            value(string): 记录值，如 IP 地址或域名
        """

        if self._get_config("disable_tool"):
            return "抱歉，该工具已被管理员禁用。"

        await self._init_dnspod_client()
        if not self.domain:
            return "错误：请先在插件配置中设置待管理的域名。"
        if not self.dnspod_client:
            return (
                "错误：DNSPod 客户端未初始化，请检查 SecretId/SecretKey/domain 配置。"
            )

        record_line = self._get_config("record_line", "默认")
        try:
            res = await self.dnspod_client.add_record(
                sub_domain, record_type.upper(), value, record_line
            )
            return str(res)
        except Exception as e:
            logger.error(f"LLM添加解析失败: {e}")
            return f"添加失败: {str(e)}"

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.llm_tool(name="delete_dns_record")
    async def delete_dns_record(self, event: AstrMessageEvent, record_id: int) -> str:
        """在腾讯云根据记录ID删除一条DNS解析记录。注意：此操作仅限管理员触发。如果没有提供record_id，则调用get_dns_records工具获取所有记录。

        Args:
            record_id(number): 要删除的记录 ID
        """

        if self._get_config("disable_tool"):
            return "抱歉，该工具已被管理员禁用。"

        await self._init_dnspod_client()
        if not self.dnspod_client:
            return (
                "错误：DNSPod 客户端未初始化，请检查 SecretId/SecretKey/domain 配置。"
            )

        try:
            res = await self.dnspod_client.delete_record(record_id)
            return str(res)
        except Exception as e:
            logger.error(f"LLM删除解析失败: {e}")
            return f"删除失败: {str(e)}"

    async def terminate(self):
        if DNSPodClient._shared_session and not DNSPodClient._shared_session.closed:
            await DNSPodClient._shared_session.close()
        logger.info("Tencent DNS Plugin 卸载完成。")
