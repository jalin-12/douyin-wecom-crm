// pages/contact/index.js
const CRM_API_BASE = 'https://crm.yourdomain.com';  // TODO: 改成你的 CRM 后端域名
const INTERNAL_KEY = '';  // TODO: 填 .env 里的 INTERNAL_API_KEY，开发时 MOCK_INTERNAL_KEY=true 可留空

Page({
  data: {
    salesName: '',
    qrcodeBase64: '',
    link: '',
    leadId: 0,
    leadToken: '',
    loading: true,
    error: '',
  },

  async onLoad(query) {
    const token = query.token || '';
    const mobile = query.mobile || '';

    // 如果 URL 没带 token/mobile，可以引导用户手动输入（demo 里暂时跳过）
    if (!token && !mobile) {
      this.setData({ loading: false, error: '缺少线索 token 或手机号参数' });
      return;
    }

    this.setData({ loading: true });

    try {
      const res = await new Promise((resolve, reject) => {
        tt.request({
          url: `${CRM_API_BASE}/api/contact/qrcode`,
          data: { token, mobile },
          header: { 'X-Internal-Key': INTERNAL_KEY },
          success: resolve,
          fail: reject,
        });
      });

      if (res.statusCode === 200 && res.data.ok) {
        this.setData({
          salesName: res.data.sales_name,
          qrcodeBase64: res.data.qrcode_base64,
          link: res.data.link,
          leadId: res.data.lead_id,
          leadToken: res.data.lead_token,
          loading: false,
        });
      } else {
        this.setData({
          loading: false,
          error: res.data.detail || `请求失败（${res.statusCode}）`,
        });
      }
    } catch (err) {
      this.setData({ loading: false, error: '网络错误：' + err.message });
    }
  },

  async onCopiedLink() {
    try {
      await new Promise((resolve, reject) => {
        tt.setClipboardData({ data: this.data.link, success: resolve, fail: reject });
      });
      tt.showToast({ title: '活码链接已复制', icon: 'none' });
    } catch {
      tt.showToast({ title: '复制失败', icon: 'none' });
    }
  },

  onAddedWechat() {
    tt.showToast({ title: '感谢联系，顾问会尽快通过', icon: 'none' });
  },
});
