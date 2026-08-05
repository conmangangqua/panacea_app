// Hub Service Worker — BẢN TỰ HUỶ (Sếp 2026-07-30)
// Chỉ dọn cache và tự gỡ đăng ký. KHÔNG gọi clients.navigate(): nếu việc gỡ chưa
// kịp hoàn tất mà đã điều hướng lại thì tab rơi vào vòng tải lại liên tục và
// trình duyệt không bao giờ hiển thị được trang.
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) await caches.delete(k);
    await self.registration.unregister();
  })());
});
// Không chặn fetch: mọi request đi thẳng ra mạng.
