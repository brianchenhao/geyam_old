import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../config/theme.dart';
import '../widgets/antsilk_counter.dart';
import '../widgets/sakura_overlay.dart';
import 'info_screen.dart';
import 'login_screen.dart';

/// Dark-mode hero landing page (web only). Matches designreference/dark mode.webp.
class LandingScreen extends StatefulWidget {
  const LandingScreen({super.key});

  @override
  State<LandingScreen> createState() => _LandingScreenState();
}

class _LandingScreenState extends State<LandingScreen> {
  late final VideoPlayerController _controller;

  @override
  void initState() {
    super.initState();
    _controller = VideoPlayerController.asset('assets/videos/demo.mp4')
      ..setLooping(true)
      ..setVolume(0)
      ..initialize().then((_) {
        if (!mounted) return;
        setState(() {});
        _controller.play();
      });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1428),
      body: Stack(children: [const Positioned.fill(child: SakuraOverlay()), SafeArea(
        child: Column(
          children: [
            // Top nav
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              child: Row(
                children: [
                  const Text('GEYAM',
                    style: TextStyle(color: Colors.white, fontSize: 18,
                                      fontWeight: FontWeight.w700, letterSpacing: 2),
                  ),
                  const Spacer(),
                  FilledButton.tonal(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const LoginScreen()),
                    ),
                    child: const Text('Login'),
                  ),
                ],
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 40),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 960),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Features',
                          style: TextStyle(color: GeyamTheme.accent, fontSize: 12,
                                            letterSpacing: 1.5, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 12),
                        const Text(
                          'Smart POS for packaged food.\nTrain it by filming. Sell by snapping.',
                          style: TextStyle(color: Colors.white, fontSize: 42,
                                            fontWeight: FontWeight.w700, height: 1.15),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          'GEYAM gives you clean, real-time insights for your shop — train your own model, take DuitNow QR payments, and email receipts without juggling tools.',
                          style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 14, height: 1.6),
                        ),
                        const SizedBox(height: 24),
                        TextButton(
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(builder: (_) => const InfoScreen()),
                          ),
                          child: const Text('Learn More  →', style: TextStyle(color: Colors.white)),
                        ),
                        const SizedBox(height: 32),
                        _demoCard(),
                        const SizedBox(height: 32),
                        _featureGrid(),
                        const SizedBox(height: 48),
                        const Center(child: AntsilkCounterWidget()),
                        const SizedBox(height: 16),
                        Center(
                          child: Column(
                            children: [
                              Text('Powered by Chenki + Antsilk',
                                style: TextStyle(color: Colors.white.withValues(alpha: 0.5),
                                    fontSize: 13, letterSpacing: 0.5),
                              ),
                              const SizedBox(height: 6),
                              Text('© GEYAM 2026 · v2.0',
                                style: TextStyle(color: Colors.white.withValues(alpha: 0.4), fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      )]),
    );
  }

  Widget _demoCard() => Container(
    height: 320,
    decoration: BoxDecoration(
      color: const Color(0xFF121E3A),
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
    ),
    clipBehavior: Clip.antiAlias,
    child: _controller.value.isInitialized
        ? FittedBox(
            fit: BoxFit.cover,
            child: SizedBox(
              width: _controller.value.size.width,
              height: _controller.value.size.height,
              child: VideoPlayer(_controller),
            ),
          )
        : const Center(child: CircularProgressIndicator()),
  );

  Widget _featureGrid() => LayoutBuilder(builder: (context, constraints) {
    final tiles = [
      (context) => _featureTile(context, '📷', 'Camera scan', 'YOLO + MediaPipe + OpenAI cascade',
        'Point your phone or webcam at a product and GEYAM identifies it instantly. A local YOLOv8 model (trained on your own shop\'s footage) handles the common items. If it\'s unsure, MediaPipe takes a second look. Still unsure? OpenAI vision acts as the final fallback — so even brand-new stock gets recognised on day one.'),
      (context) => _featureTile(context, '📦', 'Inventory', 'Stock + auto reorder points',
        'Track every SKU in real time. Adjust stock with one tap (restock, damage, loss, etc.) and let GEYAM flag items nearing their reorder point before you run out. Stock decrements automatically on every sale.'),
      (context) => _featureTile(context, '📊', 'Dashboards', 'Live KPIs, forecasts, reports',
        'A clean, live view of your shop: today\'s revenue, top sellers, slow movers, and 7/30-day forecasts. Export CSV reports for your accountant with one click.'),
      (context) => _featureTile(context, '🤖', 'AI Q&A', 'Ask about your shop. Local phi3:mini.',
        'Ask plain-English questions like "what sold best last Friday?" or "which item is running low?". Answered locally by phi3:mini — your data never leaves the laptop.'),
    ];
    final columns = constraints.maxWidth < 600 ? 2 : 4;
    const gap = 16.0;
    final tileWidth = (constraints.maxWidth - gap * (columns - 1)) / columns;
    return Wrap(
      spacing: gap,
      runSpacing: gap,
      children: [
        for (final builder in tiles)
          SizedBox(width: tileWidth, child: builder(context)),
      ],
    );
  });

  Widget _featureTile(BuildContext context, String emoji, String title, String body, String details) => Material(
    color: Colors.transparent,
    child: InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () => _showFeatureDetails(context, emoji, title, details),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFF121E3A),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(emoji, style: const TextStyle(fontSize: 28)),
            const SizedBox(height: 12),
            Text(title, style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Text(body, style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 12, height: 1.4)),
          ],
        ),
      ),
    ),
  );

  void _showFeatureDetails(BuildContext context, String emoji, String title, String details) {
    showDialog<void>(
      context: context,
      barrierColor: Colors.black.withValues(alpha: 0.6),
      builder: (ctx) => Dialog(
        backgroundColor: const Color(0xFF121E3A),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: Colors.white.withValues(alpha: 0.08)),
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Padding(
            padding: const EdgeInsets.all(28),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(emoji, style: const TextStyle(fontSize: 32)),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(title,
                        style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w700)),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close, color: Colors.white70),
                      onPressed: () => Navigator.of(ctx).pop(),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Text(details,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 14, height: 1.6)),
                const SizedBox(height: 24),
                Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton.tonal(
                    onPressed: () => Navigator.of(ctx).pop(),
                    child: const Text('Close'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
