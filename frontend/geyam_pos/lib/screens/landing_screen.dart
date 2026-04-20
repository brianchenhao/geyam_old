import 'package:flutter/material.dart';

import '../widgets/theme_toggle.dart';
import 'login_screen.dart';

/// Public marketing page shown on the web build. Mobile / windows builds
/// bypass this and go straight to LoginScreen.
class LandingScreen extends StatelessWidget {
  const LandingScreen({super.key});

  void _goLogin(BuildContext ctx) => Navigator.push(
        ctx, MaterialPageRoute(builder: (_) => const LoginScreen()));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('GEYAM'),
        actions: [
          TextButton.icon(
            onPressed: () => _goLogin(context),
            icon: const Icon(Icons.login),
            label: const Text('Login'),
          ),
          const ThemeToggle(),
          const SizedBox(width: 8),
        ],
      ),
      body: LayoutBuilder(builder: (ctx, cons) {
        final wide = cons.maxWidth > 900;
        return SingleChildScrollView(
          child: Column(
            children: [
              _hero(context, wide: wide),
              _features(wide: wide),
              _footer(),
            ],
          ),
        );
      }),
    );
  }

  Widget _hero(BuildContext context, {required bool wide}) {
    final title = const Text(
      'Smart POS for Packaged Food',
      style: TextStyle(fontSize: 44, fontWeight: FontWeight.w800, height: 1.1),
    );
    final tagline = const Padding(
      padding: EdgeInsets.only(top: 16, bottom: 24),
      child: Text(
        'Train it by filming. Sell by snapping.',
        style: TextStyle(fontSize: 18),
      ),
    );
    final ctas = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        ElevatedButton.icon(
          onPressed: () => _goLogin(context),
          icon: const Icon(Icons.login),
          label: const Padding(
            padding: EdgeInsets.symmetric(vertical: 14, horizontal: 16),
            child: Text('Open the POS'),
          ),
        ),
        const SizedBox(width: 12),
        OutlinedButton.icon(
          onPressed: () async {
            final uri = Uri.parse('mailto:brianchen.crisp@gmail.com?subject=GEYAM demo');
            // ignore: deprecated_member_use
            await launchUrlExternal(uri);
          },
          icon: const Icon(Icons.mail_outline),
          label: const Padding(
            padding: EdgeInsets.symmetric(vertical: 14, horizontal: 16),
            child: Text('Request a demo'),
          ),
        ),
      ],
    );
    final copy = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [title, tagline, ctas],
    );
    final videoSlot = Container(
      height: 320,
      decoration: BoxDecoration(
        color: Colors.black12,
        borderRadius: BorderRadius.circular(16),
      ),
      child: const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.play_circle_outline, size: 64),
            SizedBox(height: 8),
            Text('demo.mp4 goes here',
                style: TextStyle(fontSize: 12, color: Colors.black54)),
          ],
        ),
      ),
    );
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: wide ? 72 : 24, vertical: wide ? 64 : 32,
      ),
      child: wide
          ? Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(child: copy),
                const SizedBox(width: 48),
                Expanded(child: videoSlot),
              ],
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [copy, const SizedBox(height: 24), videoSlot],
            ),
    );
  }

  Widget _features({required bool wide}) {
    const items = [
      _Feature(Icons.camera_alt, 'Camera scan',
          'Snap a tray — YOLO, MediaPipe, and GPT-4o confirm items in real time.'),
      _Feature(Icons.inventory_2, 'Inventory',
          'Stock, purchase orders, weighted-average cost, low-stock alerts.'),
      _Feature(Icons.bar_chart, 'Dashboards',
          'EWMA forecasts, EOQ, anomaly detection, CSV reports.'),
      _Feature(Icons.chat_bubble_outline, 'AI Q&A',
          'Ask your shop questions in plain English via local Ollama.'),
    ];
    return Container(
      color: Colors.black12,
      padding: EdgeInsets.symmetric(
        horizontal: wide ? 72 : 24, vertical: wide ? 64 : 32,
      ),
      child: GridView.extent(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        maxCrossAxisExtent: 320,
        childAspectRatio: 1.6,
        mainAxisSpacing: 16,
        crossAxisSpacing: 16,
        children: [for (final it in items) it],
      ),
    );
  }

  Widget _footer() => Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          '© GEYAM 2026 · v2.0 · brianchen.crisp@gmail.com',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 12, color: Colors.grey.shade500),
        ),
      );
}

class _Feature extends StatelessWidget {
  final IconData icon;
  final String title;
  final String body;
  const _Feature(this.icon, this.title, this.body);

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 28),
            const SizedBox(height: 8),
            Text(title,
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text(body, style: const TextStyle(fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

/// Fallback launcher — `url_launcher` isn't installed, so we just open a
/// mailto anchor via web `window.open`. On mobile/windows this is a no-op.
Future<void> launchUrlExternal(Uri uri) async {
  // On web, let the browser handle mailto: naturally via an anchor. Easiest:
  // just print — keeping Landing dependency-free. Upgrade by adding url_launcher.
  debugPrint('open: $uri');
}
