import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/data_table_soft.dart';
import '../widgets/section_card.dart';

/// Transaction drill-down. Shows metadata, line items, and status-conditional
/// actions: void for pending, override-void for paid (owner-only).
class TransactionDetailScreen extends StatefulWidget {
  final int txId;
  const TransactionDetailScreen({super.key, required this.txId});

  @override
  State<TransactionDetailScreen> createState() =>
      _TransactionDetailScreenState();
}

class _TransactionDetailScreenState extends State<TransactionDetailScreen> {
  Map<String, dynamic>? _tx;
  bool _loading = true;
  bool _busy = false;
  String? _error;
  Uint8List? _receiptQrBytes;
  String? _receiptPdfUrl;
  bool _qrLoading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await ApiService.get('/transactions/${widget.txId}');
      if (r is! Map) {
        setState(() { _error = 'Unexpected response'; _loading = false; });
        return;
      }
      setState(() {
        _tx = Map<String, dynamic>.from(r);
        _loading = false;
      });
      if (_tx!['status'] == 'paid') {
        _loadReceiptQr();
      }
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e.message : e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _void() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Void this pending transaction?'),
        content: const Text('Stock is not affected for pending voids.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Void')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() => _busy = true);
    try {
      await ApiService.post('/transaction/${widget.txId}/void');
      await _load();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _overrideVoid() async {
    final reason = await _promptReason();
    if (reason == null || reason.trim().length < 3) return;
    setState(() => _busy = true);
    try {
      await ApiService.post('/transaction/${widget.txId}/override-void',
          body: {'reason': reason.trim()});
      await _load();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadReceiptQr() async {
    setState(() => _qrLoading = true);
    try {
      final r = await ApiService.get('/receipts/${widget.txId}/qr');
      if (r is! Map) return;
      final dataUri = r['qr_png'] as String?;
      Uint8List? bytes;
      if (dataUri != null && dataUri.contains(',')) {
        try {
          bytes = base64Decode(dataUri.split(',').last);
        } catch (_) {
          bytes = null;
        }
      }
      if (!mounted) return;
      setState(() {
        _receiptQrBytes = bytes;
        _receiptPdfUrl = r['pdf_url'] as String?;
      });
    } catch (_) {
      // silent — receipt QR is secondary; don't block the page on failure
    } finally {
      if (mounted) setState(() => _qrLoading = false);
    }
  }

  Future<void> _emailReceipt() async {
    final ctrl = TextEditingController();
    final to = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Email digital receipt'),
        content: TextField(
          controller: ctrl,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(
            hintText: 'customer@example.com (leave blank to use the email saved on this transaction)',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, ctrl.text),
              child: const Text('Send')),
        ],
      ),
    );
    if (to == null) return;
    setState(() => _busy = true);
    try {
      final body = to.trim().isEmpty ? <String, dynamic>{} : {'to': to.trim()};
      final r = await ApiService.post('/receipts/${widget.txId}/email', body: body);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Receipt sent to ${r['to']}')),
      );
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<String?> _promptReason() async {
    final ctrl = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Override-void reason'),
        content: TextField(
          controller: ctrl,
          maxLines: 3,
          decoration: const InputDecoration(
            hintText: 'Why is this paid transaction being voided?',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, ctrl.text),
              child: const Text('Submit')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_tx?['tx_number'] ?? 'Transaction'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null && _tx == null
              ? Center(
                  child: Text(_error!,
                      style: const TextStyle(color: Colors.red)))
              : _body(),
    );
  }

  Widget _body() {
    final tx = _tx!;
    final isOwner = ApiService.role == 'owner';
    final status = tx['status'] as String? ?? '';
    final items = (tx['items'] as List?) ?? [];

    return Padding(
      padding: const EdgeInsets.all(16),
      child: ListView(
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(_error!, style: const TextStyle(color: Colors.red)),
            ),
          SectionCard(
            title: 'Summary',
            trailing: Text('RM ${tx['total']}',
                style: const TextStyle(
                    fontSize: 20, fontWeight: FontWeight.w700)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _kv('Status', status),
                _kv('Payment method', tx['payment_method'] ?? '—'),
                _kv('Payment ref', tx['payment_ref']?.toString() ?? '—'),
                _kv('Staff id', tx['staff_id']?.toString() ?? '—'),
                _kv('Receipt email', tx['receipt_email']?.toString() ?? '—'),
                _kv('Created', tx['created_at']?.toString() ?? '—'),
                _kv('Paid', tx['paid_at']?.toString() ?? '—'),
                _kv('Voided', tx['voided_at']?.toString() ?? '—'),
              ],
            ),
          ),
          const SizedBox(height: 16),
          SectionCard(
            title: 'Line items (${items.length})',
            child: items.isEmpty
                ? const Padding(
                    padding: EdgeInsets.all(12),
                    child: Text('No items'),
                  )
                : DataTableSoft(
                    columns: const ['Item', 'Qty', 'Unit', 'Subtotal', 'Src'],
                    highlightColumn: 3,
                    rows: [
                      for (final li in items)
                        [
                          Text('#${li['menu_item_id']}'),
                          Text('${li['quantity']}'),
                          Text('RM ${li['unit_price']}'),
                          Text(
                              'RM ${(_asDouble(li['unit_price']) * _asDouble(li['quantity'])).toStringAsFixed(2)}',
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600)),
                          Text(li['source']?.toString() ?? '—'),
                        ],
                    ],
                  ),
          ),
          if (status == 'paid') ...[
            const SizedBox(height: 16),
            SectionCard(
              title: 'Digital receipt',
              child: _buildReceiptSection(tx),
            ),
          ],
          const SizedBox(height: 16),
          Row(
            children: [
              if (status == 'pending')
                FilledButton.icon(
                  onPressed: _busy ? null : _void,
                  icon: const Icon(Icons.block),
                  label: const Text('Void'),
                ),
              if (status == 'paid') ...[
                FilledButton.icon(
                  onPressed: _busy ? null : _emailReceipt,
                  icon: const Icon(Icons.email_outlined),
                  label: const Text('Email receipt'),
                ),
              ],
              if (status == 'paid' && isOwner) ...[
                const SizedBox(width: 8),
                FilledButton.tonalIcon(
                  onPressed: _busy ? null : _overrideVoid,
                  icon: const Icon(Icons.undo),
                  label: const Text('Override-void'),
                ),
              ],
              const Spacer(),
              if (_busy)
                const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildReceiptSection(Map<String, dynamic> tx) {
    return Padding(
      padding: const EdgeInsets.all(8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_qrLoading)
            const Padding(
              padding: EdgeInsets.all(24),
              child: SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(strokeWidth: 2)),
            )
          else if (_receiptQrBytes != null)
            Container(
              padding: const EdgeInsets.all(8),
              color: Colors.white,
              child: Image.memory(_receiptQrBytes!,
                  width: 160, height: 160, gaplessPlayback: true),
            )
          else
            const SizedBox(
              width: 160,
              height: 160,
              child: Center(child: Text('QR unavailable')),
            ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Amount transferred',
                    style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context)
                            .colorScheme
                            .onSurface
                            .withValues(alpha: 0.65))),
                const SizedBox(height: 4),
                Text('RM ${tx['total']}',
                    style: const TextStyle(
                        fontSize: 24, fontWeight: FontWeight.w700)),
                const SizedBox(height: 12),
                const Text(
                  'Customer can scan this QR to view the digital receipt PDF, '
                  'or tap "Email receipt" to send a copy.',
                  style: TextStyle(fontSize: 12),
                ),
                if (_receiptPdfUrl != null) ...[
                  const SizedBox(height: 8),
                  SelectableText(_receiptPdfUrl!,
                      style: const TextStyle(
                          fontFamily: 'monospace', fontSize: 11)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  double _asDouble(dynamic v) {
    if (v == null) return 0.0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0.0;
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 140,
              child: Text(k,
                  style: TextStyle(
                      color: Theme.of(context)
                          .colorScheme
                          .onSurface
                          .withValues(alpha: 0.65))),
            ),
            Expanded(child: SelectableText(v)),
          ],
        ),
      );
}
