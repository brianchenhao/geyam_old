import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../widgets/confidence_badge.dart';
import '../widgets/notification_bell.dart';
import '../widgets/section_card.dart';

class PosScreen extends StatefulWidget {
  const PosScreen({super.key});

  @override
  State<PosScreen> createState() => _PosScreenState();
}

class _PosScreenState extends State<PosScreen> {
  final _picker = ImagePicker();
  final _searchCtrl = TextEditingController();
  Uint8List? _lastImage;
  List<dynamic> _detected = [];
  List<Map<String, dynamic>> _menu = [];
  String _menuQuery = '';
  bool _menuLoading = false;
  final List<Map<String, dynamic>> _cart = [];
  String? _error;
  bool _busy = false;
  int _wideActive = 0;

  @override
  void initState() {
    super.initState();
    _loadMenu();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadMenu() async {
    setState(() => _menuLoading = true);
    try {
      final r = await ApiService.get('/menu');
      setState(() => _menu = List<Map<String, dynamic>>.from(r as List));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _menuLoading = false);
    }
  }

  Future<void> _snap() async {
    final x = await _picker.pickImage(source: ImageSource.camera, imageQuality: 80);
    if (x == null) return;
    final bytes = await x.readAsBytes();
    setState(() { _lastImage = bytes; _busy = true; _error = null; });
    try {
      final r = await ApiService.uploadBytes(
        '/detect', bytes: bytes, filename: 'snap.jpg', contentType: 'image/jpeg',
      );
      setState(() => _detected = r['items']);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _add(Map<String, dynamic> item) {
    setState(() {
      final existing = _cart.indexWhere((x) => x['menu_item_id'] == item['menu_item_id']);
      if (existing >= 0) {
        _cart[existing]['quantity'] = (_cart[existing]['quantity'] ?? 1) + 1;
      } else {
        _cart.add({
          'menu_item_id': item['menu_item_id'],
          'name': item['name'],
          'price': item['price'],
          'quantity': 1,
          'source': item['source'],
          'confidence': item['confidence'],
        });
      }
    });
  }

  Future<void> _checkout() async {
    if (_cart.isEmpty) return;
    setState(() { _busy = true; _error = null; });
    try {
      final tx = await ApiService.post('/transaction', body: {
        'items': [
          for (final c in _cart)
            {
              'menu_item_id': c['menu_item_id'],
              'quantity': c['quantity'],
              'source': c['source'] ?? 'manual',
              'confidence': c['confidence'],
            }
        ],
      });
      final qr = await ApiService.post('/transaction/${tx['id']}/qr');
      if (!mounted) return;
      setState(() => _cart.clear());
      await _showBillDialog(
        txId: tx['id'] as int,
        txNumber: tx['tx_number'] as String,
        billUrl: qr['bill_url'] as String,
        qrDataUri: qr['bill_qr_png'] as String?,
        amount: qr['amount'] as String?,
      );
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _showBillDialog({
    required int txId,
    required String txNumber,
    required String billUrl,
    String? qrDataUri,
    String? amount,
  }) async {
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => _PaymentDialog(
        txId: txId,
        txNumber: txNumber,
        billUrl: billUrl,
        billQrDataUri: qrDataUri,
        amount: amount,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isNarrow = constraints.maxWidth < 700;
        if (isNarrow) {
          return DefaultTabController(length: 3, child: _buildScaffold(isNarrow: true));
        }
        return _buildScaffold(isNarrow: false);
      },
    );
  }

  Widget _buildScaffold({required bool isNarrow}) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('POS'),
        actions: [
          const NotificationBell(),
          IconButton(icon: const Icon(Icons.logout), onPressed: () async {
            await ApiService.clearAuth();
            if (!context.mounted) return;
            Navigator.of(context).popUntil((r) => r.isFirst);
          }),
        ],
        bottom: isNarrow
            ? TabBar(
                tabs: [
                  const Tab(icon: Icon(Icons.qr_code_scanner), text: 'Scan'),
                  const Tab(icon: Icon(Icons.restaurant_menu), text: 'Menu'),
                  Tab(
                    icon: Badge(
                      isLabelVisible: _cart.isNotEmpty,
                      label: Text('${_cart.fold<int>(0, (a, c) => a + ((c['quantity'] ?? 1) as int))}'),
                      child: const Icon(Icons.shopping_cart_outlined),
                    ),
                    text: 'Cart',
                  ),
                ],
              )
            : null,
      ),
      body: isNarrow ? _narrowBody() : _wideBody(),
      bottomNavigationBar: isNarrow ? _mobileCheckoutBar() : null,
    );
  }

  Widget _wideBody() => Padding(
    padding: const EdgeInsets.all(16),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(flex: 3, child: _wideScanMenuToggle()),
        const SizedBox(width: 16),
        Expanded(flex: 2, child: _cartPanel(compact: false)),
      ],
    ),
  );

  Widget _wideScanMenuToggle() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SegmentedButton<int>(
          segments: const [
            ButtonSegment(
              value: 0,
              label: Text('Scan'),
              icon: Icon(Icons.qr_code_scanner),
            ),
            ButtonSegment(
              value: 1,
              label: Text('Menu'),
              icon: Icon(Icons.restaurant_menu),
            ),
          ],
          selected: {_wideActive},
          onSelectionChanged: (s) => setState(() => _wideActive = s.first),
        ),
        const SizedBox(height: 16),
        Expanded(
          child: _wideActive == 0
              ? SingleChildScrollView(
                  child: _cameraPanel(cameraHeight: 320, menuHeight: 0),
                )
              : _menuPanel(height: null),
        ),
      ],
    );
  }

  Widget _narrowBody() => TabBarView(
    children: [
      SingleChildScrollView(
        padding: const EdgeInsets.all(12),
        child: _cameraPanel(cameraHeight: 260, menuHeight: 380, scrollable: false),
      ),
      Padding(
        padding: const EdgeInsets.all(12),
        child: _menuPanel(height: null),
      ),
      SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 96),
        child: _cartPanel(compact: true),
      ),
    ],
  );

  Widget _mobileCheckoutBar() {
    final qty = _cart.fold<int>(0, (a, c) => a + ((c['quantity'] ?? 1) as int));
    final total = _cart.fold<double>(
        0, (t, c) => t + ((c['price'] ?? 0).toDouble() * (c['quantity'] ?? 1)));
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
        decoration: BoxDecoration(
          color: Theme.of(context).cardTheme.color,
          border: Border(top: BorderSide(color: Theme.of(context).dividerColor)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('$qty item${qty == 1 ? '' : 's'}',
                      style: const TextStyle(fontSize: 12)),
                  Text('RM ${total.toStringAsFixed(2)}',
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                ],
              ),
            ),
            FilledButton.icon(
              onPressed: (_cart.isEmpty || _busy) ? null : _checkout,
              icon: _busy
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.payment),
              label: const Text('Checkout'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _cameraPanel({required double cameraHeight, required double menuHeight, bool scrollable = true}) => SectionCard(
    title: 'Scan',
    trailing: _busy ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : null,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: cameraHeight,
          child: _lastImage == null
            ? const Center(child: Text('Tap Snap to scan a tray'))
            : Image.memory(_lastImage!, fit: BoxFit.cover),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(onPressed: _snap, icon: const Icon(Icons.camera_alt), label: const Text('Snap')),
        const SizedBox(height: 16),
        if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
        if (_detected.isEmpty && !_busy) const Text('No detections yet'),
        for (final d in _detected) ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(d['name'] ?? d['label'] ?? '?'),
          subtitle: Text('RM ${d['price'] ?? 0}'),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              ConfidenceBadge(
                confidence: (d['confidence'] ?? 0.0).toDouble(),
                needsConfirm: d['needs_confirm'] ?? false,
                source: d['source'],
              ),
              const SizedBox(width: 8),
              IconButton(icon: const Icon(Icons.add), onPressed: () => _add(d as Map<String, dynamic>)),
            ],
          ),
        ),
      ],
    ),
  );

  Widget _menuPanel({required double? height}) {
    final q = _menuQuery.trim().toLowerCase();
    final filtered = q.isEmpty
        ? _menu
        : _menu.where((m) {
            final name = (m['name'] ?? '').toString().toLowerCase();
            final barcode = (m['barcode'] ?? '').toString().toLowerCase();
            final category = (m['category'] ?? '').toString().toLowerCase();
            return name.contains(q) || barcode.contains(q) || category.contains(q);
          }).toList();
    final listView = _menuLoading && _menu.isEmpty
        ? const Center(child: CircularProgressIndicator())
        : filtered.isEmpty
            ? const Center(child: Text('No items'))
            : ListView.builder(
                itemCount: filtered.length,
                itemBuilder: (_, i) {
                  final m = filtered[i];
                  final price = (m['price'] is num)
                      ? (m['price'] as num).toDouble()
                      : double.tryParse('${m['price']}') ?? 0.0;
                  return ListTile(
                    dense: true,
                    title: Text(m['name'] ?? ''),
                    subtitle: Text('RM ${price.toStringAsFixed(2)}'
                        '${m['category'] != null ? ' · ${m['category']}' : ''}'),
                    trailing: IconButton(
                      icon: const Icon(Icons.add),
                      onPressed: () => _add({
                        'menu_item_id': m['id'],
                        'name': m['name'],
                        'price': price,
                        'source': 'manual',
                      }),
                    ),
                    onTap: () => _add({
                      'menu_item_id': m['id'],
                      'name': m['name'],
                      'price': price,
                      'source': 'manual',
                    }),
                  );
                },
              );
    final search = TextField(
      controller: _searchCtrl,
      decoration: InputDecoration(
        hintText: 'Search menu',
        prefixIcon: const Icon(Icons.search),
        suffixIcon: _menuQuery.isEmpty
            ? null
            : IconButton(
                icon: const Icon(Icons.clear),
                onPressed: () {
                  _searchCtrl.clear();
                  setState(() => _menuQuery = '');
                },
              ),
        border: const OutlineInputBorder(),
        isDense: true,
      ),
      onChanged: (v) => setState(() => _menuQuery = v),
    );
    // When height is null we're inside a TabBarView: the tab already has a
    // bounded height, so use Expanded to fill it. Wide layout passes an explicit
    // height so we wrap in SizedBox as before.
    return SectionCard(
      title: 'Menu',
      fill: height == null,
      trailing: IconButton(
        icon: const Icon(Icons.refresh),
        onPressed: _menuLoading ? null : _loadMenu,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          search,
          const SizedBox(height: 8),
          if (height != null)
            SizedBox(height: height, child: listView)
          else
            Expanded(child: listView),
        ],
      ),
    );
  }

  Widget _cartPanel({required bool compact}) {
    final total = _cart.fold<double>(
        0, (t, c) => t + ((c['price'] ?? 0).toDouble() * (c['quantity'] ?? 1)));
    return SectionCard(
      title: 'Cart',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_cart.isEmpty) const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text('Empty'),
          ),
          for (int i = 0; i < _cart.length; i++) Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_cart[i]['name'] ?? '', maxLines: 2, overflow: TextOverflow.ellipsis),
                    Text('RM ${((_cart[i]['price'] ?? 0) as num).toStringAsFixed(2)} each',
                        style: TextStyle(
                          fontSize: 11,
                          color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6),
                        )),
                  ],
                ),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: 'Decrease',
                icon: const Icon(Icons.remove_circle_outline, size: 20),
                onPressed: () => setState(() {
                  final q = (_cart[i]['quantity'] ?? 1) as int;
                  if (q <= 1) {
                    _cart.removeAt(i);
                  } else {
                    _cart[i]['quantity'] = q - 1;
                  }
                }),
              ),
              SizedBox(
                width: 24,
                child: Text('${_cart[i]['quantity']}',
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontWeight: FontWeight.w600)),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: 'Increase',
                icon: const Icon(Icons.add_circle_outline, size: 20),
                onPressed: () => setState(() {
                  _cart[i]['quantity'] = ((_cart[i]['quantity'] ?? 1) as int) + 1;
                }),
              ),
              const SizedBox(width: 4),
              SizedBox(
                width: 72,
                child: Text(
                  'RM ${(((_cart[i]['price'] ?? 0) as num).toDouble() * ((_cart[i]['quantity'] ?? 1) as int)).toStringAsFixed(2)}',
                  textAlign: TextAlign.right,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: 'Remove item',
                icon: Icon(Icons.delete_outline, size: 20,
                    color: Theme.of(context).colorScheme.error),
                onPressed: () => setState(() => _cart.removeAt(i)),
              ),
            ]),
          ),
          const Divider(),
          Row(children: [
            const Text('TOTAL', style: TextStyle(fontWeight: FontWeight.w700)),
            const Spacer(),
            Text('RM ${total.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w700)),
          ]),
          // In compact (mobile) mode the sticky bottom bar owns the Checkout button.
          if (!compact) ...[
            const SizedBox(height: 12),
            FilledButton(onPressed: _cart.isEmpty ? null : _checkout, child: const Text('Checkout')),
          ],
        ],
      ),
    );
  }
}

/// Payment dialog that shows the Billplz DuitNow QR while pending, polls the
/// transaction every 3s, and swaps to a receipt QR view once the webhook
/// flips status to 'paid'. Customers scan the first QR to pay; cashiers hand
/// them the second QR (or email it) to get the digital receipt PDF.
class _PaymentDialog extends StatefulWidget {
  final int txId;
  final String txNumber;
  final String billUrl;
  final String? billQrDataUri;
  final String? amount;

  const _PaymentDialog({
    required this.txId,
    required this.txNumber,
    required this.billUrl,
    this.billQrDataUri,
    this.amount,
  });

  @override
  State<_PaymentDialog> createState() => _PaymentDialogState();
}

class _PaymentDialogState extends State<_PaymentDialog> {
  Uint8List? _billQrBytes;
  Uint8List? _receiptQrBytes;
  String? _receiptPdfUrl;
  bool _paid = false;
  bool _loadingReceipt = false;
  bool _emailing = false;
  String? _error;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _billQrBytes = _decodeDataUri(widget.billQrDataUri);
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) => _poll());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Uint8List? _decodeDataUri(String? dataUri) {
    if (dataUri == null || !dataUri.contains(',')) return null;
    try {
      return base64Decode(dataUri.split(',').last);
    } catch (_) {
      return null;
    }
  }

  Future<void> _poll() async {
    if (_paid) return;
    try {
      final r = await ApiService.get('/transactions/${widget.txId}');
      if (r is! Map) return;
      final status = (r['status'] ?? '').toString();
      if (status == 'paid') {
        _pollTimer?.cancel();
        if (!mounted) return;
        setState(() {
          _paid = true;
          _loadingReceipt = true;
        });
        await _loadReceiptQr();
      } else if (status == 'voided') {
        _pollTimer?.cancel();
        if (!mounted) return;
        setState(() => _error = 'Transaction was voided before payment.');
      }
    } catch (_) {
      // silent — next tick retries
    }
  }

  Future<void> _loadReceiptQr() async {
    try {
      final r = await ApiService.get('/receipts/${widget.txId}/qr');
      if (r is! Map) return;
      final bytes = _decodeDataUri(r['qr_png'] as String?);
      if (!mounted) return;
      setState(() {
        _receiptQrBytes = bytes;
        _receiptPdfUrl = r['pdf_url'] as String?;
      });
    } catch (_) {
      // leave blank — receipt QR is secondary
    } finally {
      if (mounted) setState(() => _loadingReceipt = false);
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
            hintText: 'customer@example.com',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text), child: const Text('Send')),
        ],
      ),
    );
    if (to == null || to.trim().isEmpty) return;
    setState(() => _emailing = true);
    try {
      final r = await ApiService.post('/receipts/${widget.txId}/email', body: {'to': to.trim()});
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Receipt sent to ${r['to']}')),
      );
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _emailing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final screenW = MediaQuery.of(context).size.width;
    final contentW = screenW < 380 ? screenW - 80 : 320.0;
    final qrSize = contentW < 240 ? contentW - 16 : 240.0;
    return AlertDialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      title: Text(_paid ? 'Paid · ${widget.txNumber}' : 'Pay ${widget.txNumber}'),
      content: SizedBox(
        width: contentW,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            if (widget.amount != null)
              Text('RM ${widget.amount}',
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            if (_paid) ..._paidBody(qrSize) else ..._pendingBody(qrSize),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: const TextStyle(color: Colors.red, fontSize: 12)),
            ],
          ],
        ),
      ),
      actions: _paid
          ? [
              TextButton(
                onPressed: _emailing ? null : _emailReceipt,
                child: _emailing
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Email receipt'),
              ),
              TextButton(onPressed: () => Navigator.pop(context), child: const Text('Done')),
            ]
          : [
              TextButton(
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: widget.billUrl));
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Copied to clipboard')),
                    );
                  }
                },
                child: const Text('Copy URL'),
              ),
              TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
            ],
    );
  }

  List<Widget> _pendingBody(double qrSize) => [
        const Text('Scan with your banking app to pay',
            style: TextStyle(fontSize: 12, color: Colors.grey)),
        const SizedBox(height: 12),
        if (_billQrBytes != null)
          Container(
            padding: const EdgeInsets.all(8),
            color: Colors.white,
            child: Image.memory(_billQrBytes!, width: qrSize, height: qrSize, gaplessPlayback: true),
          )
        else
          SelectableText(widget.billUrl,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
        const SizedBox(height: 12),
        const Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2)),
            SizedBox(width: 8),
            Text('Waiting for payment…', style: TextStyle(fontSize: 11, color: Colors.grey)),
          ],
        ),
      ];

  List<Widget> _paidBody(double qrSize) => [
        const Text('Payment received. Scan to get digital receipt.',
            style: TextStyle(fontSize: 12, color: Colors.grey)),
        const SizedBox(height: 12),
        if (_loadingReceipt)
          SizedBox(
            width: qrSize,
            height: qrSize,
            child: const Center(child: CircularProgressIndicator()),
          )
        else if (_receiptQrBytes != null)
          Container(
            padding: const EdgeInsets.all(8),
            color: Colors.white,
            child: Image.memory(_receiptQrBytes!, width: qrSize, height: qrSize, gaplessPlayback: true),
          )
        else
          SizedBox(
            width: qrSize,
            height: qrSize,
            child: const Center(child: Text('Receipt QR unavailable')),
          ),
        if (_receiptPdfUrl != null) ...[
          const SizedBox(height: 8),
          SelectableText(_receiptPdfUrl!,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 10)),
        ],
      ];
}
