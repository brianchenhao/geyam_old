import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:provider/provider.dart';

import '../config/theme.dart';
import '../providers/billing_provider.dart';
import '../providers/notification_provider.dart';
import '../services/api_service.dart';
import 'dashboard_screen.dart';
import 'signup_screen.dart';
import 'pos_screen.dart';
import 'tenant_picker_screen.dart';

const _googleClientId =
    '339183567289-5n34ms9cdurfiudsm6h8gvtlommsjhfl.apps.googleusercontent.com';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with SingleTickerProviderStateMixin {
  late final TabController _tab = TabController(length: 2, vsync: this);

  final _tenantHandle = TextEditingController();
  final _username = TextEditingController();
  final _pin = TextEditingController();

  String? _error;
  bool _busy = false;

  late final GoogleSignIn _gsi = GoogleSignIn(
    clientId: _googleClientId,
    scopes: const ['email', 'openid', 'profile'],
  );
  bool _handled = false;

  @override
  void initState() {
    super.initState();
    _gsi.onCurrentUserChanged.listen(_handleGoogleAccount);
  }

  Future<void> _handleGoogleAccount(GoogleSignInAccount? account) async {
    if (!mounted || account == null || _handled) return;
    _handled = true;
    try {
      final auth = await account.authentication;
      final body = <String, dynamic>{};
      if (auth.idToken != null && auth.idToken!.isNotEmpty) {
        body['id_token'] = auth.idToken;
      } else if (auth.accessToken != null && auth.accessToken!.isNotEmpty) {
        body['access_token'] = auth.accessToken;
      } else {
        setState(() { _error = 'Google returned no token'; _busy = false; _handled = false; });
        return;
      }
      final r = await ApiService.post('/auth/google', body: body);
      if (!mounted) return;
      if (r['needs_onboarding'] == true) {
        Navigator.of(context).pushReplacement(MaterialPageRoute(
          builder: (_) => SignupScreen(
            signupToken: r['signup_token'] as String,
            email: r['email'] as String,
          ),
        ));
        return;
      }
      await ApiService.setAuth(
        token: r['access_token'],
        tenantId: r['tenant_id'],
        role: r['role'],
      );
      if (!mounted) return;
      context.read<NotificationProvider>().connect(r['access_token'] as String);
      // ignore: discarded_futures
      context.read<BillingProvider>().refresh();
      final next = r['role'] == 'admin' ? const TenantPickerScreen() : const DashboardScreen();
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => next));
    } on ApiException catch (e) {
      setState(() { _error = e.message; _busy = false; _handled = false; });
    } catch (e) {
      setState(() { _error = 'Sign-in failed: $e'; _busy = false; _handled = false; });
    }
  }

  Future<void> _startGoogleSignIn() async {
    setState(() { _busy = true; _error = null; _handled = false; });
    try {
      await _gsi.signOut();
      await _gsi.signIn();
      // signIn() on web often resolves before account is populated; the real
      // callback is _handleGoogleAccount via onCurrentUserChanged.
    } catch (e) {
      if (mounted) setState(() { _error = 'Google popup failed: $e'; _busy = false; });
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
      await ApiService.setAuth(token: r['access_token'], tenantId: r['tenant_id'], role: 'cashier');
      if (!mounted) return;
      context.read<NotificationProvider>().connect(r['access_token'] as String);
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
      const SizedBox(height: 16),
      Center(
        child: SizedBox(
          height: 48,
          child: OutlinedButton(
            onPressed: _busy ? null : _startGoogleSignIn,
            style: OutlinedButton.styleFrom(
              backgroundColor: Colors.white,
              foregroundColor: const Color(0xFF1F1F1F),
              side: const BorderSide(color: Color(0xFFDADCE0)),
              shape: const StadiumBorder(),
              padding: const EdgeInsets.symmetric(horizontal: 24),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (_busy)
                  const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                else
                  Image.asset('assets/images/google_logo.png', width: 18, height: 18),
                const SizedBox(width: 12),
                const Text(
                  'Sign in with Google',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    letterSpacing: 0.25,
                  ),
                ),
              ],
            ),
          ),
        ),
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
