import 'package:flutter/material.dart';

/// Rounded card with subtle border. Light = #F5F5F5, dark = #00004D.
///
/// Set [fill] to true when the parent provides bounded height and the child
/// must take the remaining space (e.g. a scrollable table inside `Expanded`).
/// Without `fill`, the child renders at its intrinsic height — which overflows
/// a bounded parent once the child's content exceeds the available height.
class SectionCard extends StatelessWidget {
  final String? title;
  final Widget child;
  final Widget? trailing;
  final bool fill;

  const SectionCard({
    super.key,
    this.title,
    required this.child,
    this.trailing,
    this.fill = false,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final border = isDark
        ? Colors.white.withValues(alpha: 0.12)
        : Colors.black.withValues(alpha: 0.08);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        border: Border.all(color: border, width: 1),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: fill ? MainAxisSize.max : MainAxisSize.min,
        children: [
          if (title != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Row(
                children: [
                  Text(title!, style: Theme.of(context).textTheme.titleMedium),
                  const Spacer(),
                  if (trailing != null) trailing!,
                ],
              ),
            ),
          if (fill) Expanded(child: child) else child,
        ],
      ),
    );
  }
}
