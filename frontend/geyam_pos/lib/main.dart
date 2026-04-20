import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'config/theme.dart';
import 'providers/theme_provider.dart';
import 'screens/landing_screen.dart';
import 'screens/login_screen.dart';

void main() {
  runApp(
    ChangeNotifierProvider(
      create: (_) => ThemeProvider(),
      child: const GeyamApp(),
    ),
  );
}

class GeyamApp extends StatelessWidget {
  const GeyamApp({super.key});

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    // Plan rule (web-only): landing is the first screen on the web build;
    // mobile/windows builds go straight to Login.
    final home = kIsWeb ? const LandingScreen() : const LoginScreen();
    return MaterialApp(
      title: 'GEYAM',
      debugShowCheckedModeBanner: false,
      theme: GeyamTheme.light,
      darkTheme: GeyamTheme.dark,
      themeMode: themeProvider.mode,
      home: home,
    );
  }
}
