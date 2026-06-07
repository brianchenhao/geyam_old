import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../providers/billing_provider.dart';

class BillingScreen extends StatefulWidget {
  const BillingScreen({super.key});

  @override
  State<BillingScreen> createState() => _BillingScreenState();
}

class _BillingScreenState extends State<BillingScreen> {
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<BillingProvider>().refresh();
    });
  }

  Future<void> _withBusy(Future<void> Function() fn) async {
    setState(() => _busy = true);
    try {
      await fn();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Billing error: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openExternal(String url) async {
    final uri = Uri.parse(url);
    if (kIsWeb) {
      // On web, opening in same tab interrupts the SPA — open new tab.
      if (!await launchUrl(uri, webOnlyWindowName: '_blank')) {
        await Clipboard.setData(ClipboardData(text: url));
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Could not open browser; URL copied to clipboard.')),
          );
        }
      }
    } else {
      if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        await Clipboard.setData(ClipboardData(text: url));
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Could not open browser; URL copied to clipboard.')),
          );
        }
      }
    }
  }

  Future<void> _checkout(String plan) async {
    await _withBusy(() async {
      final url = await context.read<BillingProvider>().startCheckout(plan);
      if (url != null) await _openExternal(url);
    });
  }

  Future<void> _portal() async {
    await _withBusy(() async {
      final url = await context.read<BillingProvider>().openPortal();
      if (url != null) await _openExternal(url);
    });
  }

  @override
  Widget build(BuildContext context) {
    final b = context.watch<BillingProvider>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Billing'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: b.loading ? null : () => b.refresh(),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _StatusCard(billing: b),
            const SizedBox(height: 16),
            const Text('Plans', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            _PlanCard(
              name: 'Free', price: 'RM 0', current: b.plan == 'free',
              features: const ['1 cashier', '50 menu items', '100 AI vision calls / month', '1 training video / week'],
              cta: null,
            ),
            _PlanCard(
              name: 'Pro', price: 'RM 99 / mo', current: b.plan == 'pro',
              features: const ['5 cashiers', '500 menu items', '500 AI vision calls / month', '5 training videos / week'],
              cta: b.plan == 'pro' || _busy ? null : () => _checkout('pro'),
              ctaLabel: b.plan == 'free' ? 'Upgrade to Pro' : 'Change to Pro',
            ),
            _PlanCard(
              name: 'Business', price: 'RM 299 / mo', current: b.plan == 'business',
              features: const ['Unlimited cashiers', 'Unlimited menu items', '2000 AI vision calls / month', '20 training videos / week'],
              cta: b.plan == 'business' || _busy ? null : () => _checkout('business'),
              ctaLabel: b.plan == 'free' ? 'Upgrade to Business' : 'Change to Business',
            ),
            const SizedBox(height: 16),
            if (b.hasStripeCustomer)
              FilledButton.tonalIcon(
                icon: const Icon(Icons.credit_card),
                label: const Text('Manage payment / cancel in billing portal'),
                onPressed: _busy ? null : _portal,
              ),
          ],
        ),
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  final BillingProvider billing;
  const _StatusCard({required this.billing});

  @override
  Widget build(BuildContext context) {
    Color colour = Colors.green;
    IconData icon = Icons.check_circle;
    String label = 'Active';
    if (billing.isSuspended) {
      colour = Colors.red; icon = Icons.lock; label = 'Suspended';
    } else if (billing.isPastDue) {
      colour = Colors.orange; icon = Icons.warning; label = 'Past due';
    }
    final renew = billing.currentPeriodEnd;
    return Card(
      child: ListTile(
        leading: Icon(icon, color: colour, size: 32),
        title: Text('Current plan: ${billing.plan.toUpperCase()}',
            style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Status: $label'),
            if (renew != null) Text('Renews / ends: ${renew.toLocal().toString().substring(0, 16)}'),
          ],
        ),
      ),
    );
  }
}

class _PlanCard extends StatelessWidget {
  final String name;
  final String price;
  final bool current;
  final List<String> features;
  final VoidCallback? cta;
  final String? ctaLabel;

  const _PlanCard({
    required this.name,
    required this.price,
    required this.current,
    required this.features,
    this.cta,
    this.ctaLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      shape: RoundedRectangleBorder(
        side: BorderSide(
          color: current ? Theme.of(context).colorScheme.primary : Colors.transparent,
          width: 2,
        ),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                const SizedBox(width: 12),
                if (current)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.primary,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Text('CURRENT', style: TextStyle(color: Colors.white, fontSize: 11)),
                  ),
                const Spacer(),
                Text(price, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
              ],
            ),
            const SizedBox(height: 8),
            ...features.map((f) => Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(children: [const Icon(Icons.check, size: 16), const SizedBox(width: 6), Expanded(child: Text(f))]),
            )),
            if (cta != null && ctaLabel != null) ...[
              const SizedBox(height: 12),
              FilledButton(onPressed: cta, child: Text(ctaLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}
