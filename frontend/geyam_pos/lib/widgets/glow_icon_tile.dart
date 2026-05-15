import 'package:flutter/material.dart';

import '../config/theme.dart';

/// Glowing violet/teal icon tile from the design reference (dark mode hero
/// sub-cards). A soft gradient square with an icon and a halo behind it.
class GlowIconTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String? subtitle;
  final int gradientIndex;
  final VoidCallback? onTap;
  final double size;

  const GlowIconTile({
    super.key,
    required this.icon,
    required this.label,
    this.subtitle,
    this.gradientIndex = 1,
    this.onTap,
    this.size = 56,
  });

  @override
  Widget build(BuildContext context) {
    final gradient =
        GeyamTheme.kpiGradients[gradientIndex % GeyamTheme.kpiGradients.length];
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final border = isDark
        ? Colors.white.withValues(alpha: 0.12)
        : Colors.black.withValues(alpha: 0.08);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Theme.of(context).cardTheme.color,
            border: Border.all(color: border, width: 1),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            children: [
              Container(
                width: size,
                height: size,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: gradient,
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(14),
                  boxShadow: [
                    BoxShadow(
                      color: gradient.last.withValues(alpha: 0.55),
                      blurRadius: 22,
                      spreadRadius: 1,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: Icon(icon, color: Colors.white, size: size * 0.5),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      label,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (subtitle != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        subtitle!,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Theme.of(context)
                              .colorScheme
                              .onSurface
                              .withValues(alpha: 0.7),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
