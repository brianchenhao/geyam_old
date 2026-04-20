import 'package:flutter/material.dart';

import '../config/theme.dart';
import 'login_screen.dart';

/// Dark-mode hero landing page (web only). Matches designreference/dark mode.webp.
class LandingScreen extends StatelessWidget {
  const LandingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF050510),
      body: SafeArea(
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
                          onPressed: () {},
                          child: const Text('Learn More  →', style: TextStyle(color: Colors.white)),
                        ),
                        const SizedBox(height: 32),
                        _demoCard(),
                        const SizedBox(height: 32),
                        _featureGrid(),
                        const SizedBox(height: 48),
                        Center(
                          child: Text('© GEYAM 2026 · v2.0',
                            style: TextStyle(color: Colors.white.withValues(alpha: 0.4), fontSize: 12),
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
      ),
    );
  }

  Widget _demoCard() => Container(
    height: 320,
    decoration: BoxDecoration(
      color: const Color(0xFF0B0B1A),
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
    ),
    child: const Center(
      child: Text('demo.mp4 loop', style: TextStyle(color: Color(0xFF666666)))),
  );

  Widget _featureGrid() => Row(
    children: [
      Expanded(child: _featureTile('📷', 'Camera scan', 'YOLO + MediaPipe + OpenAI cascade')),
      const SizedBox(width: 16),
      Expanded(child: _featureTile('📦', 'Inventory', 'POs, suppliers, auto reorder points')),
      const SizedBox(width: 16),
      Expanded(child: _featureTile('📊', 'Dashboards', 'Live KPIs, forecasts, reports')),
      const SizedBox(width: 16),
      Expanded(child: _featureTile('🤖', 'AI Q&A', 'Ask about your shop. Local phi3:mini.')),
    ],
  );

  Widget _featureTile(String emoji, String title, String body) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: const Color(0xFF0B0B1A),
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
  );
}
