// Phase 10 — 4-step onboarding wizard shown after self-serve signup.
//
// step 1: shop info + logo  (placeholder logo upload; settings screen later)
// step 2: first cashier      (collect username + 6-digit PIN)
// step 3: sample items       (3 starter menu items)
// step 4: billing intro      (read-only — explains Free plan, upgrade later)
//
// Each "Continue" press POSTs to /onboarding/step/{n}; the backend is the
// source of truth for current step. On drop-off, /onboarding/status lets the
// app resume at the right page.

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import 'dashboard_screen.dart';

class OnboardingWizardScreen extends StatefulWidget {
  const OnboardingWizardScreen({super.key});

  @override
  State<OnboardingWizardScreen> createState() => _OnboardingWizardScreenState();
}

class _OnboardingWizardScreenState extends State<OnboardingWizardScreen> {
  int _step = 1;
  bool _busy = false;
  String? _error;

  // step 2 inputs
  final _cashierUsername = TextEditingController();
  final _cashierPin = TextEditingController();

  // step 3 inputs (3 sample items)
  final _item1 = TextEditingController(text: 'Iced Coffee');
  final _item1Price = TextEditingController(text: '6.50');
  final _item2 = TextEditingController(text: 'Roti Bun');
  final _item2Price = TextEditingController(text: '2.00');
  final _item3 = TextEditingController(text: 'Mineral Water');
  final _item3Price = TextEditingController(text: '1.50');

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  Future<void> _loadStatus() async {
    try {
      final s = await ApiService.get('/onboarding/status');
      if (!mounted) return;
      final step = (s['step'] as int?) ?? 1;
      setState(() {
        _step = step.clamp(1, 5);
      });
      if (_step >= 5) _exitToDashboard();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    }
  }

  Future<void> _advance({Future<void> Function()? sideEffect}) async {
    setState(() { _busy = true; _error = null; });
    try {
      if (sideEffect != null) await sideEffect();
      final r = await ApiService.post('/onboarding/step/$_step');
      if (!mounted) return;
      final next = (r['step'] as int?) ?? (_step + 1);
      setState(() => _step = next);
      if (_step >= 5) _exitToDashboard();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _exitToDashboard() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const DashboardScreen()),
    );
  }

  Future<void> _createCashier() async {
    final username = _cashierUsername.text.trim();
    final pin = _cashierPin.text.trim();
    if (username.length < 2) throw ApiException(400, 'Cashier name too short');
    if (!RegExp(r'^\d{6}$').hasMatch(pin)) throw ApiException(400, 'PIN must be 6 digits');
    await ApiService.post('/users', body: {
      'username': username, 'pin': pin,
    });
  }

  Future<void> _createSampleItems() async {
    final pairs = [
      (_item1.text.trim(), _item1Price.text.trim()),
      (_item2.text.trim(), _item2Price.text.trim()),
      (_item3.text.trim(), _item3Price.text.trim()),
    ];
    for (final (name, price) in pairs) {
      if (name.isEmpty) continue;
      final p = double.tryParse(price);
      if (p == null || p <= 0) {
        throw ApiException(400, 'Price for "$name" must be a positive number');
      }
      await ApiService.post('/menu', body: {
        'name': name, 'price': p, 'category': 'starter',
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Set up your shop · Step ${_step.clamp(1, 4)} of 4'),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                LinearProgressIndicator(value: (_step - 1) / 4),
                const SizedBox(height: 24),
                _buildStepBody(),
                const SizedBox(height: 24),
                if (_error != null) Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                ),
                _buildPrimaryButton(),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: _busy ? null : _exitToDashboard,
                  child: const Text('Skip for now'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStepBody() {
    switch (_step) {
      case 1:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: const [
            Text('Welcome to Geyam!', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            SizedBox(height: 8),
            Text(
              'Your shop is created. You can polish branding (logo, colour) later '
              'from Settings — for now let\'s get the basics in.',
              style: TextStyle(color: Colors.white70),
            ),
          ],
        );
      case 2:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Add your first cashier',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'Cashiers sign in with the shop handle, their username, and a 6-digit PIN.',
              style: TextStyle(color: Colors.white70),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _cashierUsername,
              decoration: const InputDecoration(labelText: 'Cashier username', hintText: 'e.g. siti'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _cashierPin,
              keyboardType: TextInputType.number,
              maxLength: 6,
              obscureText: true,
              decoration: const InputDecoration(labelText: '6-digit PIN'),
            ),
          ],
        );
      case 3:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Add a few starter items',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'These appear on the POS so you can ring up your first sale today. '
              'You can edit, replace, or bulk-import via CSV from the Menu screen later.',
              style: TextStyle(color: Colors.white70),
            ),
            const SizedBox(height: 16),
            _itemRow(_item1, _item1Price),
            _itemRow(_item2, _item2Price),
            _itemRow(_item3, _item3Price),
          ],
        );
      case 4:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: const [
            Text('Billing — you\'re on Free',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            SizedBox(height: 12),
            Text(
              'The Free plan covers your first cashier, 50 menu items, and 50 AI '
              'vision calls per month. When you\'re ready to grow, upgrade to Pro '
              '(RM 99/mo) or Business (RM 299/mo) from the Billing screen.',
              style: TextStyle(color: Colors.white70),
            ),
            SizedBox(height: 12),
            Text(
              'You can stay on Free for as long as you like. We\'ll never auto-charge.',
              style: TextStyle(color: Colors.white70),
            ),
          ],
        );
      default:
        return const SizedBox.shrink();
    }
  }

  Widget _itemRow(TextEditingController name, TextEditingController price) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Expanded(flex: 3, child: TextField(controller: name, decoration: const InputDecoration(labelText: 'Item name'))),
          const SizedBox(width: 8),
          Expanded(flex: 1, child: TextField(
            controller: price,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Price', prefixText: 'RM '),
          )),
        ],
      ),
    );
  }

  Widget _buildPrimaryButton() {
    String label;
    Future<void> Function()? sideEffect;
    switch (_step) {
      case 1:
        label = 'Continue';
        break;
      case 2:
        label = 'Create cashier';
        sideEffect = _createCashier;
        break;
      case 3:
        label = 'Add items';
        sideEffect = _createSampleItems;
        break;
      case 4:
        label = 'Got it, take me in';
        break;
      default:
        label = 'Continue';
    }
    return FilledButton(
      onPressed: _busy ? null : () => _advance(sideEffect: sideEffect),
      child: Text(_busy ? 'Saving…' : label),
    );
  }

  @override
  void dispose() {
    _cashierUsername.dispose();
    _cashierPin.dispose();
    _item1.dispose(); _item1Price.dispose();
    _item2.dispose(); _item2Price.dispose();
    _item3.dispose(); _item3Price.dispose();
    super.dispose();
  }
}
