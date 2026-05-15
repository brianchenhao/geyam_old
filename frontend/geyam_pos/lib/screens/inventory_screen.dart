import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/app_drawer.dart';
import '../widgets/data_table_soft.dart';
import '../widgets/geyam_leading.dart';
import '../widgets/section_card.dart';
import '../widgets/tabbed_nav.dart';

class InventoryScreen extends StatefulWidget {
  const InventoryScreen({super.key});

  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> {
  static const _tabs = ['All', 'Low stock'];
  int _tab = 0;
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
      final path = _tab == 1 ? '/inventory/low-stock' : '/inventory';
      final r = await ApiService.get(path);
      setState(() { _rows = (r is List) ? r : []; _loading = false; });
    } catch (e) {
      setState(() { _error = e is ApiException ? e.message : e.toString(); _loading = false; });
    }
  }

  Future<void> _adjust(Map item) async {
    final delta = TextEditingController();
    final note = TextEditingController();
    String reason = 'adjust_miscount';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setS) {
        return AlertDialog(
          title: Text('Adjust · ${item['name']}'),
          content: SizedBox(
            width: 380,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text('Current stock: ${item['stock_qty']}'),
              TextField(
                controller: delta,
                decoration: const InputDecoration(labelText: 'Delta (e.g. -3 or +5)'),
                keyboardType: const TextInputType.numberWithOptions(signed: true),
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                value: reason,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Reason'),
                items: const [
                  DropdownMenuItem(value: 'adjust_restock', child: Text('Restock')),
                  DropdownMenuItem(value: 'adjust_damage', child: Text('Damage')),
                  DropdownMenuItem(value: 'adjust_loss', child: Text('Loss')),
                  DropdownMenuItem(value: 'adjust_theft', child: Text('Theft')),
                  DropdownMenuItem(value: 'adjust_miscount', child: Text('Miscount')),
                  DropdownMenuItem(value: 'adjust_expired', child: Text('Expired')),
                  DropdownMenuItem(value: 'adjust_other', child: Text('Other')),
                ],
                onChanged: (v) => setS(() => reason = v ?? reason),
              ),
              TextField(controller: note, decoration: const InputDecoration(labelText: 'Note (optional)')),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Apply')),
          ],
        );
      }),
    );
    if (ok != true) return;
    final d = int.tryParse(delta.text.trim());
    if (d == null || d == 0) return;
    try {
      await ApiService.post('/inventory/adjust', body: {
        'menu_item_id': item['id'],
        'delta': d,
        'reason': reason,
        'note': note.text.trim(),
      });
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
        title: const Text('Inventory'),
        actions: [IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh))],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Align(
            alignment: Alignment.centerRight,
            child: TabbedNav(tabs: _tabs, selectedIndex: _tab, onChanged: (i) { setState(() => _tab = i); _load(); }),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(child: Text(_error!, style: const TextStyle(color: Colors.red)))
                    : SectionCard(
                        fill: true,
                        title: '${_rows.length} item(s)',
                        child: _rows.isEmpty
                            ? const Padding(padding: EdgeInsets.all(24), child: Text('Nothing here'))
                            : DataTableSoft(
                                columns: const ['Name', 'Stock', 'Reorder', 'Avg cost', 'Status', 'Adjust'],
                                highlightColumn: 1,
                                rows: [
                                  for (final r in _rows)
                                    [
                                      Text(r['name']?.toString() ?? '?'),
                                      Text('${r['stock_qty']}'),
                                      Text('${r['reorder_point']}'),
                                      Text('RM ${r['avg_cost'] ?? '0'}'),
                                      Text(r['low_stock'] == true ? 'LOW' : 'ok',
                                          style: TextStyle(
                                              color: r['low_stock'] == true ? Colors.orange : null,
                                              fontWeight: FontWeight.w600)),
                                      IconButton(icon: const Icon(Icons.tune, size: 18), onPressed: () => _adjust(r as Map)),
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
