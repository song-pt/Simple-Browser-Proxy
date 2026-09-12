# Browser Data Gateway

## 系统要求

- Ubuntu Server 20.04、22.04 或 24.04（x86_64/arm64）
- Docker Engine 20.10+ 与 Docker Compose v2
- 开放 TCP 6789（或自定义端口）

## 三行部署

```bash
git clone https://github.com/YOUR_NAME/browser-data-gateway.git
cd browser-data-gateway
./deploy/install.sh
```

访问：`http://SERVER_IP:6789/www.example.com`

端口变更：`PORT=8080 ./deploy/install.sh`

## 验证与运维

```bash
python3 -m unittest discover -s tests -v
docker compose ps
docker compose logs -f
docker compose down
```

## 已实现

- GET/POST/PUT/PATCH/DELETE/HEAD 转发
- HTML 常用 URL 属性、`srcset`、meta refresh 及 CSS `url()` 改写
- 每个访问者独立的服务端 CookieJar
- gzip 解压、跳转跟随、请求/响应大小限制、超时和健康检查
- 纯 Python 3.8 标准库，容器以非 root、只读文件系统、无 Linux capabilities 运行

## 技术边界

路径式改写无法普遍复刻原始 Origin。CSP/SRI、Service Worker、WebSocket、OAuth、JS 动态绝对 URL、Canvas/媒体 DRM 和严格跨域逻辑可能需要逐站适配。若要求任意站点最高兼容，应配套浏览器扩展或改用浏览器可配置的 HTTP CONNECT/SOCKS5 代理。
