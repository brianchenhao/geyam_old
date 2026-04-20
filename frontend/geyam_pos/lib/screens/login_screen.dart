import 'package:flutter/material.dart';

import '../config/theme.dart';
import '../services/api_service.dart';
import 'dashboard_screen.dart';
import 'pos_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with SingleTickerProviderStateMixin {
  late final TabController _tab = TabController(length: 2, vsync: this);

  final _adminEmail = TextEditingController();
  final _tenantHandle = TextEditingController();
  final _username = TextEditingController();
  final _pin = TextEditingController();

  String? _error;
  bool _busy = false;

  Future<void> _ownerDevLogin() async {
    setState(() { _busy = true; _error = null; });
    try {
      final r = await ApiService.post('/admin/dev-login', body: {'email': _adminEmail.text.trim()});
      ApiService.setAuth(token: r['token'] as String, role: 'admin');
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const DashboardScreen()));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cashierLogin() async {
    setState(() { _busy = true; _error = null; });
    try {
      final r = await ApiService.post('/auth/staff/login', body: {
        'tenant_handle': _tenantHandle.text.trim(),
        'username': _username.text.trim(),
        'pin': _pin.text.trim(),
      });
      ApiService.setAuth(token: r['access_token'], tenantId: r['tenant_id'], role: 'cashier');
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const PosScreen()));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('GEYAM')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TabBar(controller: _tab, tabs: const [Tab(text: 'Owner'), Tab(text: 'Cashier')]),
                const SizedBox(height: 24),
                SizedBox(height: 260, child: TabBarView(controller: _tab, children: [_ownerTab(), _cashierTab()])),
                if (_error != null) Padding(
                  padding: const EdgeInsets.only(top: 16),
                  child: Text(_error!, style: const TextStyle(color: GeyamTheme.error)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _ownerTab() => Column(
    children: [
      const Text('Admin/dev-login path while Google OAuth button is wired. Use your whitelisted admin email.',
          style: TextStyle(fontSize: 12)),
      const SizedBox(height: 16),
      TextField(controller: _adminEmail, decoration: const InputDecoration(labelText: 'Admin email')),
      const SizedBox(height: 16),
      FilledButton(
        onPressed: _busy ? null : _ownerDevLogin,
        child: _busy ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Sign in'),
      ),
    ],
  );

  Widget _cashierTab() => Column(
    children: [
      TextField(controller: _tenantHandle, decoration: const InputDecoration(labelText: 'Shop handle')),
      TextField(controller: _username, decoration: const InputDecoration(labelText: 'Username')),
      TextField(controller: _pin, decoration: const InputDecoration(labelText: 'PIN (6 digits)'),
                obscureText: true, keyboardType: TextInputType.number, maxLength: 6),
      const SizedBox(height: 8),
      FilledButton(onPressed: _busy ? null : _cashierLogin,
                    child: _busy ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Sign in')),
    ],
  );
}
