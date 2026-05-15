import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../widgets/app_drawer.dart';
import '../widgets/geyam_leading.dart';
import '../widgets/section_card.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  Map<String, dynamic>? _data;
  String? _error;
  bool _saving = false;

  final _billplzApiKey = TextEditingController();
  final _billplzCollectionId = TextEditingController();
  final _billplzXsign = TextEditingController();
  String _billplzMode = 'sandbox';
  final _receiptFooter = TextEditingController();
  final _shopEmail = TextEditingController();
  final _shopPhone = TextEditingController();
  final _yoloConf = TextEditingController();
  final _yoloMin = TextEditingController();
  final _openaiLimit = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await ApiService.get('/settings');
      if (d is! Map<String, dynamic>) {
        setState(() => _error = 'Unexpected response');
        return;
      }
      setState(() {
        _data = d;
        _error = null;
        _billplzMode = (d['billplz_mode'] ?? 'sandbox').toString();
        _billplzCollectionId.text = (d['billplz_collection_id'] ?? '').toString();
        _receiptFooter.text = (d['receipt_footer'] ?? '').toString();
        _shopEmail.text = (d['shop_contact_email'] ?? '').toString();
        _shopPhone.text = (d['shop_contact_phone'] ?? '').toString();
        _yoloConf.text = (d['yolo_conf_threshold'] ?? '').toString();
        _yoloMin.text = (d['yolo_conf_minimum'] ?? '').toString();
        _openaiLimit.text = (d['openai_daily_limit'] ?? '').toString();
      });
    } catch (e) {
      setState(() => _error = e is ApiException ? e.message : e.toString());
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final body = <String, dynamic>{
      'billplz_mode': _billplzMode,
      'billplz_collection_id': _billplzCollectionId.text.trim(),
      'receipt_footer': _receiptFooter.text,
      'shop_contact_email': _shopEmail.text.trim(),
      'shop_contact_phone': _shopPhone.text.trim(),
    };
    if (_billplzApiKey.text.trim().isNotEmpty) {
      body['billplz_api_key'] = _billplzApiKey.text.trim();
    }
    if (_billplzXsign.text.trim().isNotEmpty) {
      body['billplz_xsign_key'] = _billplzXsign.text.trim();
    }
    final yc = double.tryParse(_yoloConf.text.trim());
    if (yc != null) body['yolo_conf_threshold'] = yc;
    final ym = double.tryParse(_yoloMin.text.trim());
    if (ym != null) body['yolo_conf_minimum'] = ym;
    final ol = int.tryParse(_openaiLimit.text.trim());
    if (ol != null) body['openai_daily_limit'] = ol;

    try {
      await ApiService.patch('/settings', body: body);
      _billplzApiKey.clear();
      _billplzXsign.clear();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Settings saved')),
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: ${e.message}')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _uploadLogo() async {
    final picker = ImagePicker();
    final xf = await picker.pickImage(source: ImageSource.gallery, maxWidth: 2048);
    if (xf == null) return;
    final bytes = await xf.readAsBytes();
    try {
      await ApiService.uploadBytes(
        '/settings/logo',
        bytes: bytes,
        filename: xf.name,
        contentType: 'image/png',
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Logo uploaded')),
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Upload failed: ${e.message}')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        leading: const GeyamLeading(),
        leadingWidth: 96,
        title: const Text('Settings'),
        actions: [
          if (_saving)
            const Padding(
              padding: EdgeInsets.all(16),
              child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
            )
          else
            TextButton(onPressed: _save, child: const Text('Save')),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!, style: const TextStyle(color: Colors.red)))
          : _data == null
              ? const Center(child: CircularProgressIndicator())
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SectionCard(
                        title: 'Billplz (DuitNow QR)',
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(children: [
                              const Text('Mode: '),
                              const SizedBox(width: 8),
                              DropdownButton<String>(
                                value: _billplzMode,
                                items: const [
                                  DropdownMenuItem(value: 'sandbox', child: Text('Sandbox')),
                                  DropdownMenuItem(value: 'production', child: Text('Production')),
                                ],
                                onChanged: (v) => setState(() => _billplzMode = v ?? 'sandbox'),
                              ),
                              const SizedBox(width: 16),
                              if (_data!['billplz_configured'] == true)
                                const Chip(label: Text('Configured'), backgroundColor: Color(0x332ECC71)),
                            ]),
                            const SizedBox(height: 12),
                            _field(_billplzCollectionId, 'Collection ID'),
                            _field(_billplzApiKey, 'API Key (leave blank to keep existing)'),
                            _field(_billplzXsign, 'XSignature Key (leave blank to keep existing)'),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                      SectionCard(
                        title: 'Shop & Receipt',
                        child: Column(
                          children: [
                            Row(children: [
                              Expanded(child: _field(_shopEmail, 'Contact email')),
                              const SizedBox(width: 12),
                              Expanded(child: _field(_shopPhone, 'Contact phone')),
                            ]),
                            _field(_receiptFooter, 'Receipt footer (thank-you line)'),
                            const SizedBox(height: 8),
                            Row(children: [
                              OutlinedButton.icon(
                                onPressed: _uploadLogo,
                                icon: const Icon(Icons.upload),
                                label: const Text('Upload logo'),
                              ),
                              const SizedBox(width: 12),
                              if ((_data!['logo_path'] ?? '').toString().isNotEmpty)
                                Text('Current: ${_data!['logo_path']}',
                                    style: Theme.of(context).textTheme.bodySmall),
                            ]),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                      SectionCard(
                        title: 'Detection thresholds',
                        child: Column(children: [
                          Row(children: [
                            Expanded(child: _field(_yoloConf, 'YOLO confidence threshold (auto-accept)')),
                            const SizedBox(width: 12),
                            Expanded(child: _field(_yoloMin, 'YOLO minimum (below → fallback)')),
                          ]),
                          _field(_openaiLimit, 'OpenAI daily limit (USD cents)'),
                        ]),
                      ),
                      const SizedBox(height: 32),
                    ],
                  ),
                ),
    );
  }

  Widget _field(TextEditingController c, String label) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: TextField(
          controller: c,
          decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
        ),
      );
}
