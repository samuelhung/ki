import 'package:flutter/material.dart' show Size;

// Web stub for window_manager — no-op on web

class WindowManager {
  static final WindowManager instance = WindowManager._();
  WindowManager._();

  Future<void> ensureInitialized() async {}
  Future<void> setTitle(String title) async {}
  Future<void> setSize(Size size) async {}
  Future<void> setMinimumSize(Size size) async {}
  Future<void> center() async {}
  Future<void> show() async {}
}

final WindowManager windowManager = WindowManager.instance;
