// Service Worker for WiFi Notifier (Native Web Push)

self.addEventListener('install', function(event) {
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    event.waitUntil(clients.claim());
});

self.addEventListener('push', function(event) {
    let data = {};
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = { title: 'تنبيه الواي فاي', body: event.data.text() };
        }
    }
    
    const title = data.title || '📶 تنبيه من شبكة الواي فاي';
    const options = {
        body: data.body || '',
        icon: data.icon || '/static/icons/icon.png',
        badge: data.badge || '/static/icons/icon.png',
        vibrate: data.vibrate || [300, 100, 300, 100, 300],
        tag: data.tag || 'wifi-alert',
        renotify: true,
        requireInteraction: data.urgent || false,
        data: {
            url: data.url || '/portal'
        }
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/portal';
    
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if ('focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
