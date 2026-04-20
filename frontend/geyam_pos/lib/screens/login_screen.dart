import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../config/theme.dart';
import '../services/api_service.dart';
import 'dashboard_screen.dart';
import 'pos_screen.dart';
import 'tenant_picker_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with SingleTickerProviderStateMixin {
  late final TabController _tab = TabController(length: 2, vsync: this);

  final _adminEmail = TextEditingController();
  final _googleToken = TextEditingController();
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
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const TenantPickerScreen()));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _ownerGoogleLogin() async {
    final tok = _googleToken.text.trim();
    if (tok.isEmpty) { setState(() => _error = 'Paste your Google id_token first'); return; }
    setState(() { _busy = true; _error = null; });
    try {
      final r = await ApiService.post('/auth/google', body: {'id_token': tok});
      ApiService.setAuth(
        token: r['access_token'],
        tenantId: r['tenant_id'],
        role: r['role'],
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const DashboardScreen()));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pasteFromClipboard() async {
    final d = await Clipboard.getData('text/plain');
    if (d?.text != null) {
      setState(() => _googleToken.text = d!.text!);
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
          constraints: const BoxConstraints(maxWidth: 480),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TabBar(controller: _tab, tabs: const [Tab(text: 'Owner'), Tab(text: 'Cashier')]),
                const SizedBox(height: 16),
                SizedBox(height: 480, child: TabBarView(controller: _tab, children: [_ownerTab(), _cashierTab()])),
                if (_error != null) Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(_error!, style: const TextStyle(color: GeyamTheme.error)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _ownerTab() => ListView(
    shrinkWrap: true,
    children: [
      const SizedBox(height: 8),
      const Text('Option A — Real Google OAuth',
                  style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 4),
      const Text('1. Open hostinger/google-test.html in a browser, sign in with Google, copy the id_token.\n2. Paste it here and tap Sign in.',
                  style: TextStyle(fontSize: 12)),
      const SizedBox(height: 8),
      TextField(
        controller: _googleToken,
        decoration: const InputDecoration(
          labelText: 'Google id_token (eyJ…)',
          isDense: true,
        ),
        maxLines: 3,
      ),
      Row(
        children: [
          TextButton.icon(onPressed: _pasteFromClipboard,
                            icon: const Icon(Icons.paste, size: 16), label: const Text('Paste')),
          const Spacer(),
          FilledButton(
            onPressed: _busy ? null : _ownerGoogleLogin,
            child: _busy ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Sign in with Google'),
          ),
        ],
      ),
      const Divider(height: 32),
      const Text('Option B — Admin dev-login (whitelisted email)',
                  style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      TextField(controller: _adminEmail, decoration: const InputDecoration(labelText: 'Admin email', isDense: true)),
      const SizedBox(height: 12),
      FilledButton.tonal(
        onPressed: _busy ? null : _ownerDevLogin,
        child: _busy ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Admin sign in'),
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
