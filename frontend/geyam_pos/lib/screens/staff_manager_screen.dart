import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/app_drawer.dart';
import '../widgets/data_table_soft.dart';
import '../widgets/geyam_leading.dart';
import '../widgets/section_card.dart';

class StaffManagerScreen extends StatefulWidget {
  const StaffManagerScreen({super.key});

  @override
  State<StaffManagerScreen> createState() => _StaffManagerScreenState();
}

class _StaffManagerScreenState extends State<StaffManagerScreen> {
  List<dynamic> _rows = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final r = await ApiService.get('/users');
      setState(() { _rows = (r is List) ? r : []; _loading = false; });
    } catch (e) {
      setState(() { _error = e is ApiException ? e.message : e.toString(); _loading = false; });
    }
  }

  Future<void> _create() async {
    final username = TextEditingController();
    final pin = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('New cashier'),
        content: SizedBox(width: 360, child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: username, decoration: const InputDecoration(labelText: 'Username (optional — auto if blank)')),
          TextField(controller: pin, decoration: const InputDecoration(labelText: 'PIN (6 digits)'), obscureText: true, keyboardType: TextInputType.number),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Create')),
        ],
      ),
    );
    if (ok != true) return;
    final body = {
      'username': username.text.trim().isEmpty ? null : username.text.trim(),
      'pin': pin.text.trim(),
    };
    try {
      final r = await ApiService.post('/users', body: body);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Created: username=${r?['username'] ?? '?'}')),
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _resetPin(Map u) async {
    final pin = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Reset PIN · ${u['username']}'),
        content: TextField(controller: pin, decoration: const InputDecoration(labelText: 'New PIN (6 digits)'), obscureText: true),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Reset')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.patch('/users/${u['id']}', body: {'pin': pin.text.trim()});
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _toggleActive(Map u) async {
    try {
      await ApiService.patch('/users/${u['id']}', body: {'is_active': !(u['is_active'] ?? true)});
      await _load();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        leading: const GeyamLeading(),
        leadingWidth: 96,
        title: const Text('Staff'),
        actions: [
          IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh)),
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: FilledButton.icon(onPressed: _create, icon: const Icon(Icons.add), label: const Text('New cashier')),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Text(_error!, style: const TextStyle(color: Colors.red)))
                : SectionCard(
                    fill: true,
                    title: '${_rows.length} cashier(s)',
                    child: _rows.isEmpty
                        ? const Padding(padding: EdgeInsets.all(24), child: Text('No cashiers'))
                        : DataTableSoft(
                            columns: const ['Username', 'Active', 'Actions'],
                            rows: [
                              for (final u in _rows)
                                [
                                  Text(u['username']?.toString() ?? '?'),
                                  Switch(value: u['is_active'] ?? true, onChanged: (_) => _toggleActive(u as Map)),
                                  Row(mainAxisSize: MainAxisSize.min, children: [
                                    TextButton(onPressed: () => _resetPin(u as Map), child: const Text('Reset PIN')),
                                  ]),
                                ]
                            ],
                          ),
                  ),
      ),
    );
  }
}
