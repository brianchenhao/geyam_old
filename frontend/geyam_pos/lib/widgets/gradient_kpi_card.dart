import 'package:flutter/material.dart';

import '../config/theme.dart';

/// Gradient KPI card from the design reference — big number + muted label.
class GradientKpiCard extends StatelessWidget {
  final String label;
  final String value;
  final int gradientIndex;
  final VoidCallback? onTap;

  const GradientKpiCard({
    super.key,
    required this.label,
    required this.value,
    this.gradientIndex = 0,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final gradient = GeyamTheme.kpiGradients[gradientIndex % GeyamTheme.kpiGradients.length];
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: gradient,
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: gradient.last.withValues(alpha: 0.3),
                blurRadius: 16,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                label.toUpperCase(),
                style: const TextStyle(
                  color: Color(0xFFFFFFFF),
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                value,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 30,
                  fontWeight: FontWeight.w700,
                  height: 1.0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
