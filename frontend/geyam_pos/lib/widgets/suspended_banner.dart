import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/billing_provider.dart';
import '../screens/billing_screen.dart';

/// Persistent top banner shown when the tenant's subscription needs attention
/// (past_due or suspended). Tap to jump to /billing. Mutations are still
/// blocked server-side via 423 (suspended) / 402 (over plan limit) regardless
/// of whether this banner is visible.
class SuspendedBanner extends StatelessWidget {
  final Widget child;
  const SuspendedBanner({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final billing = context.watch<BillingProvider>();
    if (!billing.needsAttention) return child;

    final isSuspended = billing.isSuspended;
    final bg = isSuspended ? Colors.red.shade700 : Colors.orange.shade700;
    final msg = isSuspended
        ? 'Service suspended — past-due grace period expired. Update payment to continue.'
        : 'Payment past due. Update your card before the grace period ends.';

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Material(
          color: bg,
          child: InkWell(
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const BillingScreen()),
            ),
            child: SafeArea(
              bottom: false,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                child: Row(
                  children: [
                    Icon(
                      isSuspended ? Icons.lock_outline : Icons.warning_amber_rounded,
                      color: Colors.white,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        msg,
                        style: const TextStyle(
                          color: Colors.white, fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    const Icon(Icons.chevron_right, color: Colors.white),
                  ],
                ),
              ),
            ),
          ),
        ),
        Expanded(child: child),
      ],
    );
  }
}
