// Phase 11 — web-only client-side router.
//
// On Flutter web, the landing slot at geyam.com resolves three public routes
// (`/`, `/pricing`, `/signup`) plus the existing POS shell mounted under
// `/app`. On Android/iOS the router is bypassed entirely — the APK boots
// straight into the auth-aware POS picker (LandingScreen → DashboardScreen).
//
// Why GoRouter: deep links to /pricing and /signup must survive a hard refresh
// (Hostinger's SPA fallback rewrites 404 → /index.html), and analytics needs
// distinct URLs per page. Both cheap with GoRouter, ugly without.

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'screens/dashboard_screen.dart';
import 'screens/landing_screen.dart';
import 'screens/login_screen.dart';
import 'screens/pos_screen.dart';
import 'screens/pricing_screen.dart';
import 'screens/tenant_picker_screen.dart';
import 'services/api_service.dart';

GoRouter buildRouter() {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(path: '/', builder: (_, __) => const LandingScreen()),
      GoRoute(path: '/pricing', builder: (_, __) => const PricingScreen()),
      // /signup reuses LoginScreen — it owns the Google OAuth flow and
      // imperatively pushes to SignupScreen (existing) when the backend
      // returns needs_onboarding=true. No duplicate entry-point screen.
      GoRoute(path: '/signup', builder: (_, __) => const LoginScreen()),
      GoRoute(
        path: '/app',
        builder: (_, __) => _appShellForAuth(),
        routes: [
          GoRoute(path: 'pos', builder: (_, __) => const PosScreen()),
          GoRoute(path: 'dashboard', builder: (_, __) => const DashboardScreen()),
          GoRoute(path: 'login', builder: (_, __) => const LoginScreen()),
        ],
      ),
    ],
  );
}

/// Pick the right post-auth screen for /app — mirrors the non-router fallback.
Widget _appShellForAuth() {
  if (ApiService.token == null) return const LoginScreen();
  switch (ApiService.role) {
    case 'cashier':
      return const PosScreen();
    case 'admin':
      return const TenantPickerScreen();
    default:
      return const DashboardScreen();
  }
}

/// True only when the router should be active. Keeps the APK on the
/// imperative-navigation path (Navigator.push everywhere) unchanged.
bool get useWebRouter => kIsWeb;
