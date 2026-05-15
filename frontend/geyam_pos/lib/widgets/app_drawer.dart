import 'package:flutter/material.dart';

import '../config/theme.dart';
import '../screens/audit_log_screen.dart';
import '../screens/dashboard_screen.dart';
import '../screens/inventory_screen.dart';
import '../screens/login_screen.dart';
import '../screens/menu_manager_screen.dart';
import '../screens/pos_screen.dart';
import '../screens/reports_screen.dart';
import '../screens/settings_screen.dart';
import '../screens/staff_manager_screen.dart';
import '../screens/training_screen.dart';
import '../screens/transactions_list_screen.dart';
import '../services/api_service.dart';

class AppDrawer extends StatelessWidget {
  const AppDrawer({super.key});

  @override
  Widget build(BuildContext context) {
    final isOwner = ApiService.role == 'owner';
    return Drawer(
      child: SafeArea(
        child: ListView(padding: EdgeInsets.zero, children: [
          Container(
            padding: const EdgeInsets.fromLTRB(20, 32, 20, 20),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.08))),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('GEYAM',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 2)),
                const SizedBox(height: 6),
                Text('TENANT · ${ApiService.role?.toUpperCase() ?? ""}',
                    style: TextStyle(
                        color: GeyamTheme.accent,
                        fontSize: 10,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w600)),
                const SizedBox(height: 2),
                Text('#${ApiService.tenantId ?? "?"}',
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 12)),
              ],
            ),
          ),
          _item(context, Icons.point_of_sale, 'POS', const PosScreen()),
          _item(context, Icons.receipt_long, 'Transactions', const TransactionsListScreen()),
          if (isOwner) const Divider(),
          if (isOwner) _item(context, Icons.dashboard, 'Dashboard', const DashboardScreen()),
          if (isOwner) _item(context, Icons.summarize, 'Reports', const ReportsScreen()),
          if (isOwner) _item(context, Icons.inventory_2, 'Inventory', const InventoryScreen()),
          if (isOwner) _item(context, Icons.restaurant_menu, 'Menu', const MenuManagerScreen()),
          if (isOwner) _item(context, Icons.model_training, 'Training', const TrainingScreen()),
          if (isOwner) _item(context, Icons.badge, 'Staff', const StaffManagerScreen()),
          if (isOwner) _item(context, Icons.history, 'Audit log', const AuditLogScreen()),
          if (isOwner) const Divider(),
          if (isOwner) _item(context, Icons.settings, 'Settings', const SettingsScreen()),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.logout),
            title: const Text('Sign out'),
            onTap: () async {
              await ApiService.clearAuth();
              if (!context.mounted) return;
              Navigator.of(context).pushAndRemoveUntil(
                MaterialPageRoute(builder: (_) => const LoginScreen()),
                (_) => false,
              );
            },
          ),
        ]),
      ),
    );
  }

  Widget _item(BuildContext context, IconData icon, String label, Widget screen) {
    return ListTile(
      leading: Icon(icon),
      title: Text(label),
      onTap: () {
        Navigator.pop(context);
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
      },
    );
  }
}
