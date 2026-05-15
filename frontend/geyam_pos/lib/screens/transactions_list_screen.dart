import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/app_drawer.dart';
import '../widgets/data_table_soft.dart';
import '../widgets/geyam_leading.dart';
import '../widgets/section_card.dart';
import '../widgets/tabbed_nav.dart';
import 'transaction_detail_screen.dart';

/// Transactions list with status-tab filter and pagination.
class TransactionsListScreen extends StatefulWidget {
  const TransactionsListScreen({super.key});

  @override
  State<TransactionsListScreen> createState() =>
      _TransactionsListScreenState();
}

class _TransactionsListScreenState extends State<TransactionsListScreen> {
  static const _tabs = ['All', 'Pending', 'Paid', 'Voided'];
  static const _statusFor = [null, 'pending', 'paid', 'voided'];

  int _tab = 0;
  int _page = 1;
  static const _pageSize = 25;
  List<dynamic> _rows = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final q = <String, String>{
        'page': '$_page',
        'page_size': '$_pageSize',
      };
      final status = _statusFor[_tab];
      if (status != null) q['status'] = status;
      final r = await ApiService.get('/transactions', query: q);
      setState(() {
        _rows = (r is List) ? r : [];
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e.message : e.toString();
        _loading = false;
      });
    }
  }

  void _open(Map tx) async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => TransactionDetailScreen(txId: tx['id'] as int),
    ));
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        leading: const GeyamLeading(),
        leadingWidth: 96,
        title: const Text('Transactions'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Align(
              alignment: Alignment.centerRight,
              child: TabbedNav(
                tabs: _tabs,
                selectedIndex: _tab,
                onChanged: (i) {
                  setState(() {
                    _tab = i;
                    _page = 1;
                  });
                  _load();
                },
              ),
            ),
            const SizedBox(height: 16),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _error != null
                      ? Center(
                          child: Text(_error!,
                              style: const TextStyle(color: Colors.red)))
                      : SectionCard(
                          fill: true,
                          title: '${_rows.length} row(s) · page $_page',
                          trailing: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              IconButton(
                                icon: const Icon(Icons.chevron_left),
                                onPressed: _page <= 1
                                    ? null
                                    : () {
                                        setState(() => _page--);
                                        _load();
                                      },
                              ),
                              IconButton(
                                icon: const Icon(Icons.chevron_right),
                                onPressed: _rows.length < _pageSize
                                    ? null
                                    : () {
                                        setState(() => _page++);
                                        _load();
                                      },
                              ),
                            ],
                          ),
                          child: _rows.isEmpty
                              ? const Padding(
                                  padding: EdgeInsets.all(24),
                                  child: Center(child: Text('No transactions')),
                                )
                              : DataTableSoft(
                                  columns: const [
                                    'Tx #',
                                    'Status',
                                    'Total',
                                    'Created',
                                    'Items',
                                  ],
                                  highlightColumn: 2,
                                  onRowTap: (i) =>
                                      _open(_rows[i] as Map),
                                  rows: [
                                    for (final tx in _rows)
                                      [
                                        Text(tx['tx_number'] ?? '?'),
                                        _StatusPill(
                                            status: tx['status'] ?? '?'),
                                        Text(
                                            'RM ${(tx['total'] ?? 0).toString()}',
                                            style: const TextStyle(
                                                fontWeight:
                                                    FontWeight.w600)),
                                        Text(_fmtDate(tx['created_at'])),
                                        Text('${(tx['items'] as List?)?.length ?? 0}'),
                                      ],
                                  ],
                                ),
                        ),
            ),
          ],
        ),
      ),
    );
  }
}

String _fmtDate(dynamic iso) {
  if (iso == null) return '';
  final s = iso.toString();
  final dt = DateTime.tryParse(s);
  if (dt == null) return s;
  final d = dt.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${d.year}-${two(d.month)}-${two(d.day)} ${two(d.hour)}:${two(d.minute)}';
}

class _StatusPill extends StatelessWidget {
  final String status;
  const _StatusPill({required this.status});

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      'paid' => const Color(0xFF2ECC71),
      'pending' => const Color(0xFFF1C40F),
      'voided' => const Color(0xFFE74C3C),
      _ => Colors.grey,
    };
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          border: Border.all(color: color.withValues(alpha: 0.4)),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(status,
            style: TextStyle(
                color: color, fontSize: 11, fontWeight: FontWeight.w600)),
      ),
    );
  }
}
