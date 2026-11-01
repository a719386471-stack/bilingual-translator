# 第三方组件说明

本项目的 MIT 许可只覆盖本项目原创代码和 logo，不重新许可第三方组件或商标。

- Apple 芯片 Mac 安装包包含 Astral `python-build-standalone` 分发的 CPython 3.12.16。上游发布与摘要见 `packaging/runtime.json`。CPython 使用 Python Software Foundation License；运行时还包含依各自许可分发的组件，其许可文件保留在运行时归档中。参见 https://github.com/astral-sh/python-build-standalone 和 https://docs.python.org/3/license.html 。
- 锁定依赖见 `requirements-lock.txt`，离线安装包保留原始 wheel 及其许可元数据，包括 PyJWT（MIT）、cryptography（Apache-2.0 / BSD-3-Clause）、cffi（MIT）、pycparser（BSD-3-Clause）、requests（Apache-2.0）、urllib3（MIT）、certifi（MPL-2.0）、charset-normalizer（MIT）、idna（BSD-3-Clause）、youtube-transcript-api（MIT）、defusedxml（Python Software Foundation License）、typing_extensions（PSF-2.0）。以发布包中相应 wheel 的 LICENSE/METADATA 为准。
- Playwright 仅用于开发测试，按 Apache-2.0 许可，不随运行安装包分发。
- Codex/ChatGPT 官方组件不随本项目分发，由使用者从官方渠道安装、登录；仍受 OpenAI 的服务、订阅及组件条款约束。
- Antigravity ACP 不包含在本项目源码或离线 Python 包中。安装脚本仅从 Google 官方下载固定版本，校验注册表公布的 SHA-256；运行与登录仍受 Google 对该组件、账号及服务的条款约束。参见 https://github.com/agentclientprotocol/registry/tree/main/antigravity-acp 。

产品和服务名称仅用来描述兼容对象，不表示这些公司的授权、赞助或官方背书。
