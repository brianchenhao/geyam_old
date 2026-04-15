import 'package:flutter/material.dart';

class GeyamTheme {
  static const Color navy = Color(0xFF000080);
  static const Color navyDark = Color(0xFF000066);
  static const Color navyCard = Color(0xFF00004D);
  static const Color accent = Color(0xFF1E90FF);
  static const Color primaryDarkText = Color(0xFFF0F0F0);

  static ThemeData light = ThemeData(
    brightness: Brightness.light,
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: navy,
      brightness: Brightness.light,
      primary: navy,
      secondary: accent,
    ),
    scaffoldBackgroundColor: Colors.white,
    appBarTheme: const AppBarTheme(
      backgroundColor: navy,
      foregroundColor: Colors.white,
    ),
    cardTheme: const CardThemeData(color: Color(0xFFF5F5F5)),
  );

  static ThemeData dark = ThemeData(
    brightness: Brightness.dark,
    useMaterial3: true,
    colorScheme: const ColorScheme.dark(
      primary: Color(0xFF4DA6FF),
      secondary: accent,
      surface: navyDark,
      onPrimary: Colors.white,
      onSurface: primaryDarkText,
    ),
    scaffoldBackgroundColor: navy,
    appBarTheme: const AppBarTheme(
      backgroundColor: navyDark,
      foregroundColor: primaryDarkText,
    ),
    cardTheme: const CardThemeData(color: navyCard),
  );
}
