import 'package:flutter/material.dart';

/// 知几暗色主题 — 与 React 前端一致的配色
class AppTheme {
  AppTheme._();

  // 主色调
  static const Color background = Color(0xFF0B0C10);
  static const Color panel = Color(0xFF141518);
  static const Color panelHover = Color(0xFF1A1B20);
  static const Color panelActive = Color(0xFF2A2B30);
  static const Color border = Color(0xFF2A2B30);

  // 文字
  static const Color textPrimary = Color(0xFFFFFFFF);
  static const Color textSecondary = Color(0xFF9CA3AF);
  static const Color textMuted = Color(0xFF6B7280);

  // 功能色
  static const Color accent = Color(0xFF7C3AED); // purple-600
  static const Color success = Color(0xFF10B981);
  static const Color warning = Color(0xFFF59E0B);
  static const Color error = Color(0xFFEF4444);
  static const Color info = Color(0xFF3B82F6);

  // 彩色标签
  static const Color blue = Color(0xFF60A5FA);
  static const Color emerald = Color(0xFF34D399);
  static const Color amber = Color(0xFFFBBF24);
  static const Color purple = Color(0xFFA78BFA);
  static const Color cyan = Color(0xFF22D3EE);
  static const Color rose = Color(0xFFFB7185);
  static const Color sky = Color(0xFF38BDF8);
  static const Color orange = Color(0xFFFB923C);
  static const Color teal = Color(0xFF2DD4BF);
  static const Color indigo = Color(0xFF818CF8);

  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: background,
      colorScheme: const ColorScheme.dark(
        surface: panel,
        primary: accent,
        secondary: accent,
        onPrimary: textPrimary,
        onSurface: textPrimary,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: panel,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: textPrimary,
          fontSize: 16,
          fontWeight: FontWeight.w600,
        ),
        iconTheme: IconThemeData(color: textSecondary),
      ),
      cardTheme: CardThemeData(
        color: panel,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: border, width: 0.5),
        ),
      ),
      dividerTheme: const DividerThemeData(
        color: border,
        thickness: 0.5,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF1A1B20),
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: accent),
        ),
        hintStyle: const TextStyle(color: textMuted, fontSize: 14),
      ),
      textTheme: const TextTheme(
        headlineLarge: TextStyle(color: textPrimary, fontSize: 24, fontWeight: FontWeight.bold),
        headlineMedium: TextStyle(color: textPrimary, fontSize: 20, fontWeight: FontWeight.w600),
        titleLarge: TextStyle(color: textPrimary, fontSize: 18, fontWeight: FontWeight.w600),
        titleMedium: TextStyle(color: textPrimary, fontSize: 16, fontWeight: FontWeight.w500),
        bodyLarge: TextStyle(color: textPrimary, fontSize: 15),
        bodyMedium: TextStyle(color: textSecondary, fontSize: 14),
        bodySmall: TextStyle(color: textMuted, fontSize: 12),
      ),
    );
  }
}
