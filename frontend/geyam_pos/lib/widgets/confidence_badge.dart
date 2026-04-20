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
    final Color bg = needsConfirm ? GeyamTheme.warning : GeyamTheme.success;
    final Color fg = Colors.black87;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(8)),
      child: Text(
        '${(confidence * 100).toStringAsFixed(0)}%${source != null ? " · $source" : ""}',
        style: TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }
}
