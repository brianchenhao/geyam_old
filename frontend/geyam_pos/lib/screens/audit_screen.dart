import 'package:flutter/material.dart';

import '../services/api_service.dart';

class AuditScreen extends StatefulWidget {
  const AuditScreen({super.key});

  @override
  State<AuditScreen> createState() => _AuditScreenState();
}

class _AuditScreenState extends State<AuditScreen> {
  List<Map<String, dynamic>> rows = [];
  int total = 0;
  int offset = 0;
  final int limit = 50;
  bool loading = true;
  String? err;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      err = null;
    });
    try {
      final r = await ApiService.audit(limit: limit, offset: offset);
      setState(() {
        total = r['total'] as int;
        rows = (r['rows'] as List)
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList();
      });
    } catch (e) {
      setState(() => err = '$e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Audit log'),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Center(child: Text('$total events')),
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : err != null
              ? Center(child: Text(err!))
              : ListView.separated(
                  itemCount: rows.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final r = rows[i];
                    return ListTile(
                      dense: true,
                      title: Text(r['action'] as String),
                      subtitle: Text(
                        '${r['created_at']} · '
                        '${r['entity'] ?? "-"}#${r['entity_id'] ?? "-"} · '
                        'user: ${r['username'] ?? "system"} · '
                        'meta: ${r['meta'] ?? "{}"}',
                      ),
                    );
                  },
                ),
      bottomNavigationBar: BottomAppBar(
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            TextButton(
              onPressed: offset == 0 || loading
                  ? null
                  : () {
                      setState(() => offset = (offset - limit).clamp(0, total));
                      _load();
                    },
              child: const Text('Prev'),
            ),
            Text('showing ${offset + 1}–${offset + rows.length} of $total'),
            TextButton(
              onPressed: offset + limit >= total || loading
                  ? null
                  : () {
                      setState(() => offset += limit);
                      _load();
                    },
              child: const Text('Next'),
            ),
          ],
        ),
      ),
    );
  }
}
