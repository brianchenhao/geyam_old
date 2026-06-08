// Phase 11 — public "X attacks blocked by Antsilk" badge for the landing page.
//
// Reads /antsilk/stats/public on api.geyam.com (unauthed, CORS-allowed).
// Failure is silent: if the API is down or unreachable, the widget renders
// nothing rather than show a broken card to a marketing visitor.

import 'package:flutter/material.dart';

import '../services/api_service.dart';

class AntsilkCounterWidget extends StatefulWidget {
  const AntsilkCounterWidget({super.key});

  @override
  State<AntsilkCounterWidget> createState() => _AntsilkCounterWidgetState();
}

class _AntsilkCounterWidgetState extends State<AntsilkCounterWidget> {
  Future<Map<String, dynamic>?>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>?> _load() async {
    try {
      final r = await ApiService.get('/antsilk/stats/public');
      if (r is Map<String, dynamic>) return r;
      return null;
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>?>(
      future: _future,
      builder: (ctx, snap) {
        if (!snap.hasData || snap.data == null) return const SizedBox.shrink();
        final total = (snap.data!['total_blocked'] as int?) ?? 0;
        if (total <= 0) return const SizedBox.shrink();
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: const Color(0xFF121E3A),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.shield_outlined, size: 18, color: Colors.greenAccent.withValues(alpha: 0.8)),
              const SizedBox(width: 8),
              Text(
                '$total attacks blocked by Antsilk',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 13),
              ),
            ],
          ),
        );
      },
    );
  }
}
