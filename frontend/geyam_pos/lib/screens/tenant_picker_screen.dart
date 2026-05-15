import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/section_card.dart';
import 'dashboard_screen.dart';

/// Shown right after admin dev-login. Lists every tenant; picking one calls
/// /admin/tenants/{id}/impersonate → owner JWT → Dashboard.
class TenantPickerScreen extends StatefulWidget {
  const TenantPickerScreen({super.key});

  @override
  State<TenantPickerScreen> createState() => _TenantPickerScreenState();
}

class _TenantPickerScreenState extends State<TenantPickerScreen> {
  List<dynamic>? _tenants;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await ApiService.get('/admin/tenants');
      setState(() => _tenants = r as List<dynamic>);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    }
  }

  Future<void> _pick(int id) async {
    try {
      final r = await ApiService.post('/admin/tenants/$id/impersonate');
      await ApiService.setAuth(
        token: r['access_token'], tenantId: r['tenant_id'], role: 'owner',
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const DashboardScreen()),
      );
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Pick a tenant')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: _error != null
              ? Text(_error!, style: const TextStyle(color: Colors.red))
              : _tenants == null
                ? const CircularProgressIndicator()
                : SectionCard(
                    title: 'As admin, impersonate which tenant?',
                    child: Column(
                      children: [
                        for (final t in _tenants!)
                          ListTile(
                            title: Text(t['name']),
                            subtitle: Text('${t['handle']} · ${t['owner_email']}'),
                            trailing: FilledButton(
                              onPressed: () => _pick(t['id']),
                              child: const Text('Open'),
                            ),
                          ),
                        if (_tenants!.isEmpty)
                          const Padding(
                            padding: EdgeInsets.all(24),
                            child: Text('No tenants yet. Run scripts/create_tenant.py first.'),
                          ),
                      ],
                    ),
                  ),
          ),
        ),
      ),
    );
  }
}
