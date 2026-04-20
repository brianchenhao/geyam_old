import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/theme_toggle.dart';
import 'dashboard_screen.dart';
import 'pos_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  // Stage 2 cashier login: tenant_handle + username + 6-digit PIN.
  final handleCtrl =
      TextEditingController(text: 'brianchenjunhao');
  final usernameCtrl =
      TextEditingController(text: 'staff1.brianchenjunhao');
  final pinCtrl = TextEditingController();
  bool loading = false;
  String? error;

  Future<void> _devOwnerLogin() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      await ApiService.devOwnerLogin(handleCtrl.text.trim());
      if (!mounted) return;
      Navigator.pushReplacement(
        context, MaterialPageRoute(builder: (_) => const DashboardScreen()));
    } catch (e) {
      setState(() => error = 'Owner login failed: $e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _login() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      await ApiService.staffLogin(
        handleCtrl.text.trim(),
        usernameCtrl.text.trim(),
        pinCtrl.text,
      );
      if (!mounted) return;
      final dest = Session.role == 'owner'
          ? const DashboardScreen()
          : const PosScreen();
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => dest),
      );
    } catch (e) {
      setState(() => error = 'Login failed: $e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('GEYAM Login'),
        actions: const [ThemeToggle()],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 380),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: handleCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Shop handle',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: usernameCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Username',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: pinCtrl,
                  obscureText: true,
                  keyboardType: TextInputType.number,
                  maxLength: 6,
                  onSubmitted: (_) => _login(),
                  decoration: const InputDecoration(
                    labelText: '6-digit PIN',
                    border: OutlineInputBorder(),
                  ),
                ),
                if (error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(error!,
                        style: const TextStyle(color: Colors.redAccent)),
                  ),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton(
                    onPressed: loading ? null : _login,
                    child: loading
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Cashier login'),
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  height: 44,
                  child: OutlinedButton.icon(
                    onPressed: loading ? null : _devOwnerLogin,
                    icon: const Icon(Icons.admin_panel_settings),
                    label: const Text('Owner login (dev)'),
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Cashier: staff1.brianchenjunhao / PIN 123456\n'
                  'Owner: uses shop handle only (dev-mode shortcut)',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 11),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
