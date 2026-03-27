# AstrBot 腾讯云DNS解析控制器

- 自从AstrBot实现Agent电脑能力，LLM操纵服务器的Nginx越发方便，加上在插件市场中不乏开放WebUI的插件，每次开放、修改一个WebUI的端口反代除了需要修改nginx配置，还需要在DNS解析服务商处新建、修改解析记录，非常麻烦
- 使用aiohttp库与腾讯云的HTTP API进行交互的插件，旨在不需要登录腾讯云官网、小程序就能做到操纵腾讯云配置，既然LLM已经可以修改Nginx配置了，不如顺便改一下DNS解析吧

## 插件项目结构

```
astrbot_plugin_tencent_cloud_controller/
├── README.md                 # 本文件
├── main.py                  # 插件主入口
├── metadata.yaml            # 插件元数据
├── _conf_schema.json        # 配置schema定义
├── requirements.txt         # 依赖清单
└── tencent/                # 腾讯云相关模块
    ├── __init__.py
    ├── base.py             # 基础类和方法
    └── dnspod.py           # DNSPod API客户端
```



---

## 安装 & 使用

```bash
git clone https://github.com/syuan326/astrbot_plugin_tencent_cloud_controller.git
```

1. 进入腾讯云用户控制台 ->[用户列表](https://console.cloud.tencent.com/cam/user)
2. 创建或使用一个子用户并赋予[QcloudDNSPodFullAccess](https://console.cloud.tencent.com/cam/policy/detail/78569890&QcloudDNSPodFullAccess&2)策略
   1. 为了安全性
   2. 坚持用主账号的权限也行
3. 新建秘钥并保存
4. 进入AstrBot本插件的插件配置文件中填写
5. 点击保存

---

## 开发

本插件的主逻辑均由腾讯云API基类以及子类实现，理论上可以接入阿里云等的HTTP API
