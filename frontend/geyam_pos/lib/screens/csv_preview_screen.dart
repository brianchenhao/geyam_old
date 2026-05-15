import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/data_table_soft.dart';
import '../widgets/section_card.dart';

class CsvPreviewScreen extends StatefulWidget {
  final Uint8List bytes;
  final String filename;

  const CsvPreviewScreen({super.key, required this.bytes, required this.filename});

  @override
  State<CsvPreviewScreen> createState() => _CsvPreviewScreenState();
}

class _CsvPreviewScreenState extends State<CsvPreviewScreen> {
  List<String> _headers = [];
  List<List<String>> _rows = [];
  bool _importing = false;

  @override
  void initState() {
    super.initState();
    _parse();
  }

  void _parse() {
    final text = utf8.decode(widget.bytes, allowMalformed: true);
    final lines = const LineSplitter().convert(text).where((l) => l.trim().isNotEmpty).toList();
    if (lines.isEmpty) return;
    _headers = _splitCsv(lines.first);
    _rows = lines.skip(1).take(50).map(_splitCsv).toList();
    setState(() {});
  }

  List<String> _splitCsv(String line) {
    final out = <String>[];
    var cur = StringBuffer();
    var inQ = false;
    for (var i = 0; i < line.length; i++) {
      final c = line[i];
      if (c == '"') { inQ = !inQ; continue; }
      if (c == ',' && !inQ) { out.add(cur.toString()); cur = StringBuffer(); continue; }
      cur.write(c);
    }
    out.add(cur.toString());
    return out;
  }

  Future<void> _import() async {
    setState(() => _importing = true);
    try {
      final result = await ApiService.uploadBytes(
        '/menu/bulk',
        bytes: widget.bytes,
        filename: widget.filename,
        contentType: 'text/csv',
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Imported: ${result ?? "ok"}')),
      );
      Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _importing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('CSV Preview · ${widget.filename}'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: FilledButton(
              onPressed: _importing ? null : _import,
              child: _importing ? const Text('Importing…') : const Text('Confirm import'),
            ),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: SectionCard(
          fill: true,
          title: '${_rows.length} row(s) · showing first 50',
          child: _headers.isEmpty
              ? const Text('Empty CSV')
              : DataTableSoft(
                  columns: _headers,
                  rows: [
                    for (final r in _rows)
                      [for (var i = 0; i < _headers.length; i++) Text(i < r.length ? r[i] : '')]
                  ],
                ),
        ),
      ),
    );
  }
}
