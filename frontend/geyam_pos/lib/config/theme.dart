import 'package:flutter/material.dart';

/// Stage 2 theme. Design reference: designreference/light mode.png and
/// designreference/dark mode.webp. See docs/PLANstage2.md §Design Reference.
class GeyamTheme {
  static const Color navy = Color(0xFF000080);
  static const Color navyDark = Color(0xFF000066);
  static const Color navyCard = Color(0xFF00004D);
  static const Color accent = Color(0xFF1E90FF);
  static const Color primaryDarkText = Color(0xFFF0F0F0);

  static const Color success = Color(0xFF2ECC71);
  static const Color warning = Color(0xFFF1C40F);
  static const Color error = Color(0xFFE74C3C);
  static const Color info = Color(0xFF3498DB);

  /// Six gradient pairs for KPI cards. Rotate through them for each KPI.
  static const List<List<Color>> kpiGradients = [
    [Color(0xFFEC4899), Color(0xFFDB2777)], // pink
    [Color(0xFF8B5CF6), Color(0xFF6D28D9)], // violet
    [Color(0xFF6366F1), Color(0xFF4338CA)], // indigo
    [Color(0xFF14B8A6), Color(0xFF0F766E)], // teal
    [Color(0xFFF43F5E), Color(0xFFBE123C)], // rose
    [Color(0xFFF59E0B), Color(0xFFB45309)], // amber
  ];

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
      backgroundColor: Colors.white,
      foregroundColor: navy,
      elevation: 0,
    ),
    cardTheme: const CardThemeData(color: Color(0xFFF5F5F5), elevation: 0),
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
      elevation: 0,
    ),
    cardTheme: const CardThemeData(color: navyCard, elevation: 0),
  );
}
