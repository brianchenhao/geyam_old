import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/connectivity_provider.dart';
import '../providers/notification_provider.dart';

class NotificationBell extends StatelessWidget {
  const NotificationBell({super.key});

  @override
  Widget build(BuildContext context) {
    final notif = context.watch<NotificationProvider>();
    final offline = context.watch<ConnectivityProvider>().isOffline;
    final count = notif.items.length;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (offline)
          const Padding(
            padding: EdgeInsets.only(right: 4),
            child: Tooltip(
              message: 'Offline — mutations disabled',
              child: Icon(Icons.cloud_off, color: Colors.orange, size: 20),
            ),
          ),
        PopupMenuButton<int>(
          tooltip: 'Notifications',
          icon: Stack(
            clipBehavior: Clip.none,
            children: [
              const Icon(Icons.notifications_outlined),
              if (count > 0)
                Positioned(
                  right: -2, top: -2,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                    decoration: const BoxDecoration(
                      color: Colors.red, shape: BoxShape.rectangle,
                      borderRadius: BorderRadius.all(Radius.circular(8)),
                    ),
                    constraints: const BoxConstraints(minWidth: 14),
                    child: Text(
                      count > 9 ? '9+' : '$count',
                      style: const TextStyle(color: Colors.white, fontSize: 10),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
            ],
          ),
          onSelected: (_) {},
          itemBuilder: (context) {
            if (notif.items.isEmpty) {
              return [
                const PopupMenuItem(enabled: false, child: Text('No notifications')),
              ];
            }
            return [
              ...notif.items.take(10).map((n) => PopupMenuItem(
                enabled: false,
                child: SizedBox(
                  width: 280,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(n.type, style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 12)),
                      const SizedBox(height: 2),
                      Text(n.message, style: const TextStyle(fontSize: 13)),
                      Text(
                        '${n.at.hour.toString().padLeft(2, '0')}:${n.at.minute.toString().padLeft(2, '0')}',
                        style: const TextStyle(fontSize: 11, color: Colors.grey),
                      ),
                    ],
                  ),
                ),
              )),
              const PopupMenuDivider(),
              PopupMenuItem(
                onTap: () => context.read<NotificationProvider>().clear(),
                child: const Text('Clear all'),
              ),
            ];
          },
        ),
      ],
    );
  }
}
