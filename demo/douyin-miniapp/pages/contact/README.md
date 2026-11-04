# 抖音小程序骨架 · pages/contact

这个目录是抖音小程序的页面骨架，直接拷进你的小程序项目，改两处就能用：

1. **`index.js` 第 4 行**：把 `CRM_API_BASE` 改成你部署的 CRM 后端地址，例如 `https://crm.yourdomain.com`
2. **`index.js` 第 3 行**：把 `INTERNAL_KEY` 改成你在 `.env` 里设的 `INTERNAL_API_KEY`（开发时 `MOCK_INTERNAL_KEY=true` 可以留空）

## 页面入口

小雪花挂载时，落地页路径填：`pages/contact/index`

如果 CRM 后端已经生成了 lead_token，挂载链接可以带 token 参数：
`pages/contact/index?token=550e8400-e29b-41d4-a716-446655440000`

## 配套后端

CRM 后端需要暴露：`GET /api/contact/qrcode?token=xxx` （代码见 `app/routers/contact.py`）

请求头要带 `X-Internal-Key`，值和后端 `.env` 的 `INTERNAL_API_KEY` 一致。

## 文件清单

- `index.js` — 页面逻辑
- `index.ttml` — 页面模板
- `index.ttss` — 页面样式
- `index.json` — 页面配置
