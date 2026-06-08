// Phase 11 — public /pricing page.
//
// Three columns: Free, Pro (RM 99/mo), Business (RM 299/mo). Mirrors the plan
// quotas enforced by backend services/plan_enforcement.py so the marketing copy
// can't drift from what the backend actually allows. When ENFORCE_QUOTAS limits
// change there, update the rows here in the same commit.

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class PricingScreen extends StatelessWidget {
  const PricingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pricing'),
        actions: [
          TextButton(
            onPressed: () => context.go('/'),
            child: const Text('Back to home'),
          ),
          TextButton(
            onPressed: () => context.go('/signup'),
            child: const Text('Sign up free'),
          ),
          const SizedBox(width: 12),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1100),
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 48),
            child: Column(
              children: [
                Text(
                  'Simple pricing for Malaysian packaged-food shops',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Start free, upgrade when you grow. No setup fees, cancel any time.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: Colors.white70,
                      ),
                ),
                const SizedBox(height: 40),
                LayoutBuilder(builder: (ctx, constraints) {
                  final wide = constraints.maxWidth > 800;
                  final cards = const [
                    _PlanCard(
                      name: 'Free',
                      price: 'RM 0',
                      cadence: 'forever',
                      cta: 'Start free',
                      features: [
                        '1 cashier',
                        '50 menu items',
                        '50 AI vision calls / month',
                        '1 training video / week',
                        'Daily backup',
                        'Email support',
                      ],
                      highlight: false,
                    ),
                    _PlanCard(
                      name: 'Pro',
                      price: 'RM 99',
                      cadence: '/ month',
                      cta: 'Upgrade to Pro',
                      features: [
                        '5 cashiers',
                        '500 menu items',
                        '500 AI vision calls / month',
                        '5 training videos / week',
                        'Forecast + reports export',
                        'Priority email + chat support',
                      ],
                      highlight: true,
                    ),
                    _PlanCard(
                      name: 'Business',
                      price: 'RM 299',
                      cadence: '/ month',
                      cta: 'Upgrade to Business',
                      features: [
                        'Unlimited cashiers',
                        'Unlimited menu items',
                        '5,000 AI vision calls / month',
                        'Unlimited training videos',
                        'Multi-shop dashboard',
                        'Phone support + onboarding call',
                      ],
                      highlight: false,
                    ),
                  ];
                  return wide
                      ? Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: cards
                              .map((c) => Expanded(
                                    child: Padding(
                                      padding: const EdgeInsets.symmetric(horizontal: 12),
                                      child: c,
                                    ),
                                  ))
                              .toList(),
                        )
                      : Column(
                          children: cards
                              .map((c) => Padding(
                                    padding: const EdgeInsets.only(bottom: 16),
                                    child: c,
                                  ))
                              .toList(),
                        );
                }),
                const SizedBox(height: 40),
                const Text(
                  'All prices in MYR. Billing handled by Stripe. '
                  'Past-due accounts are suspended after a 7-day grace period — never silently.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white60),
                ),
                const SizedBox(height: 48),
                const _Footer(),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PlanCard extends StatelessWidget {
  final String name, price, cadence, cta;
  final List<String> features;
  final bool highlight;

  const _PlanCard({
    required this.name,
    required this.price,
    required this.cadence,
    required this.cta,
    required this.features,
    required this.highlight,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      elevation: highlight ? 8 : 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: highlight
            ? BorderSide(color: scheme.primary, width: 2)
            : BorderSide.none,
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (highlight)
              Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: scheme.primary,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Text('MOST POPULAR',
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
              ),
            Text(name, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(price,
                    style: Theme.of(context)
                        .textTheme
                        .headlineLarge
                        ?.copyWith(fontWeight: FontWeight.bold)),
                const SizedBox(width: 4),
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(cadence,
                      style: const TextStyle(color: Colors.white60)),
                ),
              ],
            ),
            const SizedBox(height: 16),
            ...features.map(
              (f) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.check, size: 18, color: scheme.primary),
                    const SizedBox(width: 8),
                    Expanded(child: Text(f)),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => context.go('/signup'),
                child: Text(cta),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Footer extends StatelessWidget {
  const _Footer();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          'Powered by Chenki + Antsilk',
          style: TextStyle(color: Colors.white54, fontSize: 13),
        ),
        const SizedBox(height: 8),
        Text(
          '© ${DateTime.now().year} Geyam — Built in Malaysia',
          style: const TextStyle(color: Colors.white38, fontSize: 12),
        ),
      ],
    );
  }
}
