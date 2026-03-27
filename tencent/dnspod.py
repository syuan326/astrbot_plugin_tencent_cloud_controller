from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


from .base import tencent_cloud_client


class DNSPodClient(tencent_cloud_client):
    """
    DNSPod API 客户端
    """

    service = "dnspod"
    host = "dnspod.tencentcloudapi.com"
    version = "2021-03-23"

    def __init__(self, secret_id: str, secret_key: str, domain: str, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.domain = domain
        self.set_credentials(secret_id=secret_id, secret_key=secret_key)


    @staticmethod
    def _extract_error_message(resp: Dict[str, Any]) -> Optional[str]:
        err = resp.get("Error")
        if not err:
            return None
        if isinstance(err, dict):
            msg = err.get("Message") or err.get("message") or err.get("Code") or str(err)
            return str(msg)
        return str(err)

    @staticmethod
    def _format_record_line(r: Dict[str, Any]) -> str:
        return (
            f"ID:{r.get('RecordId')} | {r.get('Name')} | {r.get('Type')} | "
            f"{r.get('Value')} | {r.get('Status')} | {r.get('RecordLine')}"
        )

    async def _list_records_raw(self) -> Tuple[Optional[list], Optional[str]]:
        resp = await self.request("DescribeRecordList", payload_dict={"Domain": self.domain})
        err_msg = self._extract_error_message(resp)
        if err_msg:
            return None, f"查询失败: {err_msg}"
        records = resp.get("RecordList", []) or []
        return records, None

    async def list_records(self) -> str:
        records, err = await self._list_records_raw()
        if err:
            return err
        records = records or []
        if not records:
            return f"域名 {self.domain} 下暂无解析记录。"

        res_str = f"域名 {self.domain} 解析记录列表：\n"
        for r in records:
            res_str += self._format_record_line(r) + "\n"
        return res_str

    async def get_records_by_subdomain(self, sub_domain: str, record_type: str = "") -> str:
        records, err = await self._list_records_raw()
        if err:
            return err

        sub_domain = (sub_domain or "").strip()
        record_type = (record_type or "").strip().upper()
        if not sub_domain:
            return "请输入子域名（如：test 或 @）。"

        matches = [r for r in (records or []) if str(r.get("Name", "")).strip() == sub_domain]
        if record_type:
            matches = [r for r in matches if str(r.get("Type", "")).strip().upper() == record_type]

        if not matches:
            fqdn = f"{sub_domain}.{self.domain}" if sub_domain != "@" else self.domain
            type_hint = f"（类型: {record_type}）" if record_type else ""
            return f"未找到记录：{fqdn}{type_hint}"

        fqdn = f"{sub_domain}.{self.domain}" if sub_domain != "@" else self.domain
        res = f"{fqdn} 匹配到 {len(matches)} 条记录：\n"
        for r in matches:
            res += self._format_record_line(r) + "\n"
        if len(matches) > 1:
            res += "存在多条匹配记录时，修改/删除建议使用 record_id 精确操作。"
        return res

    async def modify_record_by_subdomain(self, sub_domain: str, record_type: str, value: str) -> str:
        records, err = await self._list_records_raw()
        if err:
            return err

        sub_domain = (sub_domain or "").strip()
        record_type = (record_type or "").strip().upper()
        if not sub_domain or not record_type:
            return "参数不足：需要提供子域名与记录类型。"

        matches = [
            r
            for r in (records or [])
            if str(r.get("Name", "")).strip() == sub_domain
            and str(r.get("Type", "")).strip().upper() == record_type
        ]

        if not matches:
            fqdn = f"{sub_domain}.{self.domain}" if sub_domain != "@" else self.domain
            return f"未找到可修改的记录：{fqdn}（类型: {record_type}）"

        if len(matches) > 1:
            fqdn = f"{sub_domain}.{self.domain}" if sub_domain != "@" else self.domain
            res = f"匹配到多条记录，无法确定要修改哪一条：{fqdn}（类型: {record_type}）\n"
            for r in matches:
                res += self._format_record_line(r) + "\n"
            res += "请改用 /dns_mod <record_id> ... 精确指定。"
            return res

        target = matches[0]
        record_id = int(target.get("RecordId"))
        record_line = str(target.get("RecordLine") or "默认")

        resp = await self.request(
            "ModifyRecord",
            payload_dict={
                "Domain": self.domain,
                "RecordId": record_id,
                "SubDomain": sub_domain,
                "RecordType": record_type,
                "RecordLine": record_line,
                "Value": value,
            },
        )

        err_msg = self._extract_error_message(resp)
        if err_msg:
            return f"修改失败: {err_msg}"

        return f"解析记录已修改：{self._format_record_line({**target, 'Value': value})}"

    async def delete_record_by_subdomain(self, sub_domain: str, record_type: str = "") -> str:
        records, err = await self._list_records_raw()
        if err:
            return err

        sub_domain = (sub_domain or "").strip()
        record_type = (record_type or "").strip().upper()
        if not sub_domain:
            return "请输入子域名（如：test 或 @）。"

        matches = [r for r in (records or []) if str(r.get("Name", "")).strip() == sub_domain]
        if record_type:
            matches = [r for r in matches if str(r.get("Type", "")).strip().upper() == record_type]

        if not matches:
            fqdn = f"{sub_domain}.{self.domain}" if sub_domain != "@" else self.domain
            type_hint = f"（类型: {record_type}）" if record_type else ""
            return f"未找到可删除的记录：{fqdn}{type_hint}"

        if len(matches) > 1:
            fqdn = f"{sub_domain}.{self.domain}" if sub_domain != "@" else self.domain
            res = f"匹配到多条记录，无法确定要删除哪一条：{fqdn}\n"
            for r in matches:
                res += self._format_record_line(r) + "\n"
            res += "请增加 record_type 过滤，或改用 /dns_del <record_id> 精确指定。"
            return res

        record_id = int(matches[0].get("RecordId"))
        return await self.delete_record(record_id)

    async def add_record(self, sub_domain: str, record_type: str, value: str, line: str = "默认") -> str:
        resp = await self.request(
            "CreateRecord",
            payload_dict={
                "Domain": self.domain,
                "SubDomain": sub_domain,
                "RecordType": record_type,
                "RecordLine": line,
                "Value": value,
            },
        )

        err_msg = self._extract_error_message(resp)
        if err_msg:
            return f"添加失败: {err_msg}"

        return f"{sub_domain}.{self.domain}解析记录添加成功！ID: {resp.get('RecordId')}"

    async def modify_record(
        self, record_id: int, sub_domain: str, record_type: str, value: str, line: str = "默认"
    ) -> str:
        resp = await self.request(
            "ModifyRecord",
            payload_dict={
                "Domain": self.domain,
                "RecordId": int(record_id),
                "SubDomain": sub_domain,
                "RecordType": record_type,
                "RecordLine": line,
                "Value": value,
            },
        )

        err_msg = self._extract_error_message(resp)
        if err_msg:
            return f"修改失败: {err_msg}"

        return f"解析记录 {record_id} 修改成功！"

    async def delete_record(self, record_id: int) -> str:
        resp = await self.request(
            "DeleteRecord",
            payload_dict={
                "Domain": self.domain,
                "RecordId": int(record_id),
            },
        )

        err_msg = self._extract_error_message(resp)
        if err_msg:
            return f"删除失败: {err_msg}"

        return f"解析记录 {record_id} 已删除。"
