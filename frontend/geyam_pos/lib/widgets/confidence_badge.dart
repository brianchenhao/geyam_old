import 'package:flutter/material.dart';

import '../config/theme.dart';

class ConfidenceBadge extends StatelessWidget {
  final double confidence;
  final bool needsConfirm;
  final String? source;
  const ConfidenceBadge({super.key, required this.confidence,
                          required this.needsConfirm, this.source});

  @override
  Widget build(BuildContext context) {
    final src = (source ?? 'yolo').toLowerCase();
    final pct = confidence > 0 ? ' ${(confidence * 100).round()}%' : '';
    final Color bg;
    final Color fg;
    final Color border;
    final String label;
    if (needsConfirm) {
      bg = GeyamTheme.warning.withValues(alpha: 0.18);
      fg = GeyamTheme.warning;
      border = GeyamTheme.warning;
      label = 'Confirm · $src$pct';
    } else {
      bg = GeyamTheme.success;
      fg = Colors.white;
      border = Colors.transparent;
      label = 'Detected · $src$pct';
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: border, width: needsConfirm ? 1 : 0),
      ),
      child: Text(
        label,
        style: TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }
}
