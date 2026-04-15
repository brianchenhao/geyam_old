import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'config/theme.dart';
import 'providers/theme_provider.dart';
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
    return MaterialApp(
      title: 'GEYAM POS',
      debugShowCheckedModeBanner: false,
      theme: GeyamTheme.light,
      darkTheme: GeyamTheme.dark,
      themeMode: themeProvider.mode,
      home: const LoginScreen(),
    );
  }
}
