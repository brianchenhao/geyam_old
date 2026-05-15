import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/app_drawer.dart';
import '../widgets/data_table_soft.dart';
import '../widgets/geyam_leading.dart';
import '../widgets/section_card.dart';

class AuditLogScreen extends StatefulWidget {
  const AuditLogScreen({super.key});

  @override
  State<AuditLogScreen> createState() => _AuditLogScreenState();
}

class _AuditLogScreenState extends State<AuditLogScreen> {
  List<dynamic> _rows = [];
  int _page = 1;
  static const _pageSize = 50;
  final _prefix = TextEditingController();
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
      final q = <String, String>{'page': '$_page', 'page_size': '$_pageSize'};
      if (_prefix.text.trim().isNotEmpty) q['action_prefix'] = _prefix.text.trim();
      final r = await ApiService.get('/audit', query: q);
      setState(() { _rows = (r is List) ? r : []; _loading = false; });
    } catch (e) {
      setState(() { _error = e is ApiException ? e.message : e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        leading: const GeyamLeading(),
        leadingWidth: 96,
        title: const Text('Audit log'),
        actions: [IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh))],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Expanded(child: TextField(
              controller: _prefix,
              decoration: const InputDecoration(labelText: 'Action prefix (e.g. tx. or po.)', border: OutlineInputBorder()),
              onSubmitted: (_) { setState(() => _page = 1); _load(); },
            )),
            const SizedBox(width: 12),
            FilledButton(onPressed: () { setState(() => _page = 1); _load(); }, child: const Text('Filter')),
          ]),
          const SizedBox(height: 16),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(child: Text(_error!, style: const TextStyle(color: Colors.red)))
                    : SectionCard(
                        fill: true,
                        title: 'Page $_page · ${_rows.length} row(s)',
                        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                          IconButton(icon: const Icon(Icons.chevron_left), onPressed: _page <= 1 ? null : () { setState(() => _page--); _load(); }),
                          IconButton(icon: const Icon(Icons.chevron_right), onPressed: _rows.length < _pageSize ? null : () { setState(() => _page++); _load(); }),
                        ]),
                        child: _rows.isEmpty
                            ? const Padding(padding: EdgeInsets.all(24), child: Text('No audit entries'))
                            : DataTableSoft(
                                columns: const ['When', 'User', 'Action', 'Entity', 'Meta'],
                                rows: [
                                  for (final r in _rows)
                                    [
                                      Text(r['created_at']?.toString().replaceFirst('T', ' ').split('.').first ?? ''),
                                      Text('${r['user_id'] ?? '—'}'),
                                      Text(r['action']?.toString() ?? ''),
                                      Text('${r['entity'] ?? ''}${r['entity_id'] != null ? " #${r['entity_id']}" : ""}'),
                                      Text((r['meta'] ?? '').toString(), maxLines: 2, overflow: TextOverflow.ellipsis),
                                    ]
                                ],
                              ),
                      ),
          ),
        ]),
      ),
    );
  }
}
