import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/download_file.dart';
import '../widgets/app_drawer.dart';
import '../widgets/geyam_leading.dart';
import '../widgets/section_card.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  String _format = 'json';
  Map<String, dynamic>? _preview;
  bool _loading = false;
  String? _error;

  Future<void> _preview1() async {
    setState(() { _loading = true; _error = null; });
    try {
      final r = await ApiService.get('/reports', query: {'format': 'json'});
      setState(() {
        _preview = (r is Map<String, dynamic>) ? r : null;
        _loading = false;
      });
    } catch (e) {
      setState(() { _error = e is ApiException ? e.message : e.toString(); _loading = false; });
    }
  }

  Future<void> _download() async {
    if (_format == 'json') {
      await _preview1();
      return;
    }
    setState(() { _loading = true; _error = null; });
    try {
      final r = await ApiService.getBytes('/reports', query: {'format': _format});
      final mime = r.headers['content-type'] ?? _mimeFor(_format);
      await downloadFile(
        bytes: r.bodyBytes,
        filename: 'geyam_report.$_format',
        mimeType: mime,
      );
      if (mounted) setState(() { _loading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is ApiException ? e.message : e.toString();
        _loading = false;
      });
    }
  }

  String _mimeFor(String fmt) {
    switch (fmt) {
      case 'csv': return 'text/csv';
      case 'xlsx': return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
      case 'pdf': return 'application/pdf';
      default: return 'application/octet-stream';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        leading: const GeyamLeading(),
        leadingWidth: 96,
        title: const Text('Reports'),
        actions: [
          const Text('Format: '),
          DropdownButton<String>(
              value: _format,
              items: const [
                DropdownMenuItem(value: 'json', child: Text('JSON (preview)')),
                DropdownMenuItem(value: 'csv', child: Text('CSV')),
                DropdownMenuItem(value: 'xlsx', child: Text('XLSX')),
                DropdownMenuItem(value: 'pdf', child: Text('PDF')),
              ],
              onChanged: (v) => setState(() => _format = v ?? 'json'),
            ),
            const SizedBox(width: 12),
            FilledButton.icon(onPressed: _download, icon: const Icon(Icons.download), label: const Text('Generate')),
            const SizedBox(width: 12),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!, style: const TextStyle(color: Colors.red)))
              : _preview == null
                  ? const Center(child: Text('Pick a format and click Generate.'))
                  : SingleChildScrollView(
                      padding: const EdgeInsets.all(24),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        SectionCard(title: 'Sales by day', child: _list(_preview!['sales_by_day'])),
                        const SizedBox(height: 16),
                        SectionCard(title: 'Item performance', child: _list(_preview!['item_performance'])),
                        const SizedBox(height: 16),
                        SectionCard(title: 'Staff performance', child: _list(_preview!['staff_performance'])),
                        const SizedBox(height: 16),
                        SectionCard(title: 'Inventory valuation', child: _list(_preview!['inventory_valuation'])),
                      ]),
                    ),
    );
  }

  Widget _list(dynamic data) {
    if (data is! List || data.isEmpty) return const Text('No data');
    final cols = (data.first as Map).keys.toList();
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: [for (final c in cols) DataColumn(label: Text(c))],
        rows: [
          for (final row in data)
            DataRow(cells: [for (final c in cols) DataCell(Text((row as Map)[c]?.toString() ?? ''))])
        ],
      ),
    );
  }
}
