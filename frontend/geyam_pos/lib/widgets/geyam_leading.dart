import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/theme_provider.dart';

/// Leading cluster: menu (opens drawer) + theme toggle. Use with
/// `leading: const GeyamLeading(), leadingWidth: 96` on every Scaffold AppBar.
class GeyamLeading extends StatelessWidget {
  const GeyamLeading({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = context.watch<ThemeProvider>();
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Builder(
          builder: (ctx) => IconButton(
            icon: const Icon(Icons.menu),
            onPressed: () => Scaffold.of(ctx).openDrawer(),
            tooltip: 'Menu',
          ),
        ),
        IconButton(
          icon: Icon(theme.isDark ? Icons.light_mode : Icons.dark_mode),
          onPressed: theme.toggle,
          tooltip: theme.isDark ? 'Light mode' : 'Dark mode',
        ),
      ],
    );
  }
}
