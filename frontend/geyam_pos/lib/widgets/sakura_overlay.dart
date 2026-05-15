import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

class SakuraOverlay extends StatefulWidget {
  const SakuraOverlay({super.key, this.petalCount = 20});
  final int petalCount;

  @override
  State<SakuraOverlay> createState() => _SakuraOverlayState();
}

class _SakuraOverlayState extends State<SakuraOverlay>
    with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  late final List<_Petal> _petals;
  double _elapsed = 0; // seconds since start, unbounded (no loop seam)

  @override
  void initState() {
    super.initState();
    final rng = Random(7);
    _petals = List.generate(widget.petalCount, (_) => _Petal.random(rng));
    _ticker = createTicker((d) {
      setState(() => _elapsed = d.inMicroseconds / 1e6);
    })..start();
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: IgnorePointer(
        child: CustomPaint(
          painter: _SakuraPainter(_petals, _elapsed),
          size: Size.infinite,
        ),
      ),
    );
  }
}

class _Petal {
  _Petal({
    required this.x,
    required this.phase,
    required this.size,
    required this.fallPeriod,
    required this.swayAmp,
    required this.swayPeriod,
    required this.rotPeriod,
    required this.rotOffset,
  });

  final double x;          // 0..1 horizontal anchor
  final double phase;      // 0..1 initial progress
  final double size;       // px
  final double fallPeriod; // seconds for one top→bottom pass
  final double swayAmp;    // px
  final double swayPeriod; // seconds for one sway cycle
  final double rotPeriod;  // seconds for one full rotation
  final double rotOffset;  // rad

  factory _Petal.random(Random r) => _Petal(
        x: r.nextDouble(),
        phase: r.nextDouble(),
        size: 6 + r.nextDouble() * 7,
        fallPeriod: 14 + r.nextDouble() * 10,
        swayAmp: 15 + r.nextDouble() * 30,
        swayPeriod: 3 + r.nextDouble() * 3,
        rotPeriod: 4 + r.nextDouble() * 5,
        rotOffset: r.nextDouble() * 2 * pi,
      );
}

class _SakuraPainter extends CustomPainter {
  _SakuraPainter(this.petals, this.t);
  final List<_Petal> petals;
  final double t; // seconds, unbounded

  static final _fill = Paint()..color = const Color(0xFFE8A5C0).withOpacity(0.35);

  @override
  void paint(Canvas canvas, Size size) {
    final h = size.height + 40;
    for (final p in petals) {
      final progress = ((t / p.fallPeriod) + p.phase) % 1.0;
      final y = progress * h - 20;
      final sway = sin((t / p.swayPeriod) * 2 * pi + p.rotOffset) * p.swayAmp;
      final x = p.x * size.width + sway;
      final rot = p.rotOffset + (t / p.rotPeriod) * 2 * pi;

      canvas.save();
      canvas.translate(x, y);
      canvas.rotate(rot);
      canvas.drawOval(
        Rect.fromCenter(center: Offset.zero, width: p.size * 0.7, height: p.size),
        _fill,
      );
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(covariant _SakuraPainter old) => old.t != t;
}
