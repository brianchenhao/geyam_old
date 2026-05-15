import 'package:flutter/material.dart';

import '../services/api_service.dart';
import 'dashboard_screen.dart';

class SignupScreen extends StatefulWidget {
  final String signupToken;
  final String email;
  const SignupScreen({super.key, required this.signupToken, required this.email});

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final _shopName = TextEditingController();
  final _handle = TextEditingController();
  String? _error;
  bool _busy = false;

  Future<void> _submit() async {
    final name = _shopName.text.trim();
    final handle = _handle.text.trim().toLowerCase();
    if (name.length < 2) { setState(() => _error = 'Shop name too short'); return; }
    if (!RegExp(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$').hasMatch(handle)) {
      setState(() => _error = 'Handle: lowercase letters, digits, hyphen only (2-50 chars)');
      return;
    }
    setState(() { _busy = true; _error = null; });
    try {
      final r = await ApiService.post('/auth/google/signup', body: {
        'signup_token': widget.signupToken,
        'shop_name': name,
        'handle': handle,
      });
      await ApiService.setAuth(
        token: r['access_token'],
        tenantId: r['tenant_id'],
        role: r['role'],
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const DashboardScreen()),
      );
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Create your shop')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Signed in as ${widget.email}', style: const TextStyle(color: Colors.white70)),
                const SizedBox(height: 24),
                TextField(
                  controller: _shopName,
                  decoration: const InputDecoration(
                    labelText: 'Shop name',
                    hintText: "e.g. Brian's Mini Mart",
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _handle,
                  decoration: const InputDecoration(
                    labelText: 'Shop handle (URL-safe)',
                    hintText: 'e.g. brians-mart',
                    helperText: 'Lowercase letters, digits, hyphens. Used in staff logins.',
                  ),
                ),
                const SizedBox(height: 24),
                if (_error != null) Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                ),
                FilledButton(
                  onPressed: _busy ? null : _submit,
                  child: Text(_busy ? 'Creating…' : 'Create shop'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
