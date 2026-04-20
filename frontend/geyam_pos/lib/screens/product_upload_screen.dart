import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../widgets/theme_toggle.dart';

class ProductUploadScreen extends StatefulWidget {
  const ProductUploadScreen({super.key});

  @override
  State<ProductUploadScreen> createState() => _ProductUploadScreenState();
}

class _ProductUploadScreenState extends State<ProductUploadScreen> {
  final nameCtrl = TextEditingController();
  final priceCtrl = TextEditingController();
  final stockCtrl = TextEditingController(text: '0');
  XFile? video;
  bool busy = false;
  String? message;
  int? lastMenuItemId;

  Future<void> _pickVideo() async {
    final picker = ImagePicker();
    final picked = await picker.pickVideo(source: ImageSource.gallery);
    if (picked != null) setState(() => video = picked);
  }

  Future<void> _createItemThenUpload() async {
    final name = nameCtrl.text.trim();
    final price = double.tryParse(priceCtrl.text);
    final stock = int.tryParse(stockCtrl.text) ?? 0;
    if (name.isEmpty || price == null || price <= 0) {
      setState(() => message = 'Need name and price > 0.');
      return;
    }
    setState(() {
      busy = true;
      message = null;
    });
    try {
      final item = await ApiService.createMenuItem(
        name: name, price: price, stockQty: stock,
      );
      lastMenuItemId = item['id'] as int;
      setState(() => message =
          'Menu item #$lastMenuItemId created. ${video == null ? "Now pick a video and upload." : "Uploading video..."}');
      if (video != null) {
        final job = await ApiService.uploadMenuVideo(lastMenuItemId!, video!);
        setState(() => message =
            'Training job #${job['id']} queued for item #$lastMenuItemId (status: ${job['status']})');
      }
    } catch (e) {
      setState(() => message = 'Error: $e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Add product'),
        actions: const [ThemeToggle()],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: nameCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Product name',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: priceCtrl,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(
                          labelText: 'Price (RM)',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: stockCtrl,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Stock qty',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _pickVideo,
                  icon: const Icon(Icons.video_file),
                  label: Text(video?.name ?? 'Pick training video (≤30s, ≤100MB)'),
                ),
                const SizedBox(height: 20),
                if (message != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(message!),
                  ),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton(
                    onPressed: busy ? null : _createItemThenUpload,
                    child: busy
                        ? const SizedBox(
                            width: 22, height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : Text(video == null ? 'Create item' : 'Create + upload video'),
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Creates a menu_items row first; uploading a video then '
                  'queues a training_job and auto-extracts a middle-frame thumbnail.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 11),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
