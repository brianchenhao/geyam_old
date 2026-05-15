import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/section_card.dart';

/// Zero-detection fallback picker. Loads GET /menu, lets the cashier search
/// and tap items to add to the cart. Returns a List<Map> of selections via
/// Navigator.pop — each entry shaped like the detect() items list.
class MenuPickerScreen extends StatefulWidget {
  const MenuPickerScreen({super.key});

  @override
  State<MenuPickerScreen> createState() => _MenuPickerScreenState();
}

class _MenuPickerScreenState extends State<MenuPickerScreen> {
  List<dynamic> _items = [];
  final Map<int, int> _selected = {};
  String _query = '';
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await ApiService.get('/menu');
      setState(() {
        _items = r as List;
        _loading = false;
      });
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  void _bump(Map item, int delta) {
    final id = item['id'] as int;
    final next = (_selected[id] ?? 0) + delta;
    setState(() {
      if (next <= 0) {
        _selected.remove(id);
      } else {
        _selected[id] = next;
      }
    });
  }

  void _done() {
    final result = <Map<String, dynamic>>[];
    for (final entry in _selected.entries) {
      final item = _items.firstWhere((m) => m['id'] == entry.key);
      result.add({
        'menu_item_id': item['id'],
        'name': item['name'],
        'price': item['price'],
        'quantity': entry.value,
        'source': 'manual',
        'confidence': null,
      });
    }
    Navigator.of(context).pop(result);
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _items.where((m) {
      if (_query.isEmpty) return true;
      final name = (m['name'] ?? '').toString().toLowerCase();
      return name.contains(_query.toLowerCase());
    }).toList();

    final totalQty = _selected.values.fold<int>(0, (a, b) => a + b);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Pick items'),
        actions: [
          TextButton(
            onPressed: totalQty == 0 ? null : _done,
            child: Text('Add $totalQty'),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: SectionCard(
          title: 'Menu',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: 'Search menu…',
                  border: OutlineInputBorder(),
                ),
                onChanged: (v) => setState(() => _query = v),
              ),
              const SizedBox(height: 12),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_error != null)
                Text(_error!, style: const TextStyle(color: Colors.red))
              else if (filtered.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(child: Text('No items')),
                )
              else
                SizedBox(
                  height: MediaQuery.of(context).size.height * 0.6,
                  child: ListView.separated(
                    itemCount: filtered.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (_, i) {
                      final m = filtered[i];
                      final qty = _selected[m['id']] ?? 0;
                      final stock = m['stock_qty'] ?? 0;
                      return ListTile(
                        title: Text(m['name'] ?? '?'),
                        subtitle: Text(
                            'RM ${m['price']}  ·  stock $stock'),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              icon: const Icon(Icons.remove_circle_outline),
                              onPressed:
                                  qty == 0 ? null : () => _bump(m, -1),
                            ),
                            SizedBox(
                              width: 24,
                              child: Text('$qty',
                                  textAlign: TextAlign.center),
                            ),
                            IconButton(
                              icon: const Icon(Icons.add_circle_outline),
                              onPressed: () => _bump(m, 1),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
