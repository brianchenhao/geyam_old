import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'config/theme.dart';
import 'providers/connectivity_provider.dart';
import 'providers/notification_provider.dart';
import 'providers/theme_provider.dart';
import 'screens/dashboard_screen.dart';
import 'screens/landing_screen.dart';
import 'screens/login_screen.dart';
import 'screens/pos_screen.dart';
import 'screens/tenant_picker_screen.dart';
import 'services/api_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await ApiService.loadAuth();

  final connectivity = ConnectivityProvider();
  ApiService.isOnline = () => connectivity.isOnline;
  final notifications = NotificationProvider();
  if (ApiService.token != null) {
    notifications.connect(ApiService.token!);
  }
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => ThemeProvider()),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
        ChangeNotifierProvider<NotificationProvider>.value(value: notifications),
      ],
      child: const GeyamApp(),
    ),
  );
}

class GeyamApp extends StatelessWidget {
  const GeyamApp({super.key});

  Widget _initialScreen() {
    if (ApiService.token == null) {
      return kIsWeb ? const LandingScreen() : const LoginScreen();
    }
    switch (ApiService.role) {
      case 'cashier':
        return const PosScreen();
      case 'admin':
        return const TenantPickerScreen();
      default:
        return const DashboardScreen();
    }
  }

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    return MaterialApp(
      title: 'GEYAM POS',
      debugShowCheckedModeBanner: false,
      theme: GeyamTheme.light,
      darkTheme: GeyamTheme.dark,
      themeMode: themeProvider.mode,
      home: _initialScreen(),
      builder: (context, child) {
        if (!kIsWeb || child == null) return child ?? const SizedBox.shrink();
        return ColoredBox(
          color: Theme.of(context).scaffoldBackgroundColor,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1200),
              child: child,
            ),
          ),
        );
      },
    );
  }
}
