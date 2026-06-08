import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:provider/provider.dart';

import 'config/theme.dart';
import 'providers/billing_provider.dart';
import 'providers/connectivity_provider.dart';
import 'providers/notification_provider.dart';
import 'providers/theme_provider.dart';
import 'router.dart';
import 'screens/dashboard_screen.dart';
import 'screens/login_screen.dart';
import 'screens/pos_screen.dart';
import 'screens/tenant_picker_screen.dart';
import 'services/api_service.dart';
import 'widgets/suspended_banner.dart';

void main() {
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    debugPrint('GEYAM_FLUTTER_ERROR: ${details.exceptionAsString()}');
    if (details.stack != null) debugPrint('${details.stack}');
  };

  runZonedGuarded<Future<void>>(() async {
    WidgetsFlutterBinding.ensureInitialized();
    // Flutter web defaults to hash-based URLs (/#/pricing). Phase 11's deep
    // links work better with clean paths so SEO crawlers and direct links
    // resolve to /pricing not /#/pricing — and the Hostinger .htaccess SPA
    // fallback handles refresh. No-op on mobile.
    if (kIsWeb) usePathUrlStrategy();
    await ApiService.loadAuth();

    final connectivity = ConnectivityProvider();
    ApiService.isOnline = () => connectivity.isOnline;
    final notifications = NotificationProvider();
    final billing = BillingProvider();
    if (ApiService.token != null) {
      notifications.connect(ApiService.token!);
      // Owner is the only role that can read /subscriptions/me; the provider
      // bails out otherwise. Fire-and-forget — banner just stays hidden until
      // the response lands.
      // ignore: discarded_futures
      billing.refresh();
    }
    runApp(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
          ChangeNotifierProvider<NotificationProvider>.value(value: notifications),
          ChangeNotifierProvider<BillingProvider>.value(value: billing),
        ],
        child: const GeyamApp(),
      ),
    );
  }, (error, stack) {
    debugPrint('GEYAM_ZONED_ERROR: $error');
    debugPrint('$stack');
  });
}

class GeyamApp extends StatefulWidget {
  const GeyamApp({super.key});

  @override
  State<GeyamApp> createState() => _GeyamAppState();
}

class _GeyamAppState extends State<GeyamApp> {
  // Router instance is created once and held — GoRouter rebuilds otherwise
  // discard route history on every theme/auth-state change.
  final _router = kIsWeb ? buildRouter() : null;

  Widget _initialScreen() {
    if (ApiService.token == null) {
      return const LoginScreen();
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

  TransitionBuilder _materialBuilder() => (context, child) {
        if (child == null) return const SizedBox.shrink();
        // Suspended-tenant banner sits above everything so owners see it on
        // every screen until they update payment. Cashiers and admins never
        // trigger it (BillingProvider no-ops on non-owner tokens).
        Widget wrapped = SuspendedBanner(child: child);
        if (kIsWeb) {
          wrapped = ColoredBox(
            color: Theme.of(context).scaffoldBackgroundColor,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1200),
                child: wrapped,
              ),
            ),
          );
        }
        return wrapped;
      };

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    if (_router != null) {
      return MaterialApp.router(
        title: 'GEYAM POS',
        debugShowCheckedModeBanner: false,
        theme: GeyamTheme.light,
        darkTheme: GeyamTheme.dark,
        themeMode: themeProvider.mode,
        routerConfig: _router,
        builder: _materialBuilder(),
      );
    }
    return MaterialApp(
      title: 'GEYAM POS',
      debugShowCheckedModeBanner: false,
      theme: GeyamTheme.light,
      darkTheme: GeyamTheme.dark,
      themeMode: themeProvider.mode,
      home: _initialScreen(),
      builder: _materialBuilder(),
    );
  }
}
